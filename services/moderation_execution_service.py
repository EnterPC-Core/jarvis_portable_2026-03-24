from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from requests.exceptions import RequestException

from moderation.moderation_models import ModerationContext
from services.auto_moderation import AutoModerationDecision


@dataclass(frozen=True)
class ModerationExecutionServiceDeps:
    owner_user_id: int
    normalize_whitespace_func: Callable[[str], str]
    format_duration_seconds_func: Callable[[int], str]
    build_actor_name_func: Callable[[Optional[int], str, str, str, str], str]
    log_func: Callable[[str], None]


class ModerationExecutionService:
    """Compatibility execution layer for auto-moderation actions."""

    def __init__(self, deps: ModerationExecutionServiceDeps) -> None:
        self.deps = deps

    def maybe_apply_auto_moderation(
        self,
        bridge: "TelegramBridge",
        *,
        chat_id: int,
        user_id: Optional[int],
        message: dict,
        chat_type: str,
    ) -> bool:
        if chat_type not in {"group", "supergroup"}:
            return False
        if user_id is None or user_id == self.deps.owner_user_id:
            return False
        from_user = (message.get("from") or {})
        if from_user.get("is_bot"):
            return False
        if not bridge.can_moderate_target(chat_id, int(user_id)):
            return False
        raw_text = (message.get("text") or "").strip()
        if not raw_text:
            return False
        recent_rows = bridge.state.get_recent_user_rows(chat_id, int(user_id), limit=6)
        recent_texts = [self.deps.normalize_whitespace_func(row[6] or "").lower() for row in recent_rows]
        outcome = bridge.moderation_orchestrator.detect_auto_moderation(
            context=ModerationContext(
                chat_id=chat_id,
                user_id=int(user_id),
                chat_type=chat_type,
                chat_title=((message.get("chat") or {}).get("title") or ""),
                message_id=message.get("message_id"),
                text=raw_text,
                recent_texts=tuple(recent_texts),
            ),
            message=message,
            bot_username=bridge.bot_username,
            trigger_name=bridge.config.trigger_name,
        )
        decision = bridge.moderation_orchestrator.legacy_auto_decision(outcome)
        if decision is None:
            return False
        self.apply_auto_moderation_decision(
            bridge,
            chat_id=chat_id,
            target_user_id=int(user_id),
            message=message,
            decision=decision,
        )
        return True

    def apply_auto_moderation_decision(
        self,
        bridge: "TelegramBridge",
        *,
        chat_id: int,
        target_user_id: int,
        message: dict,
        decision: AutoModerationDecision,
    ) -> None:
        from_user = message.get("from") or {}
        username = from_user.get("username") or ""
        first_name = from_user.get("first_name") or ""
        last_name = from_user.get("last_name") or ""
        target_label = self.deps.build_actor_name_func(target_user_id, username, first_name, last_name, "user")
        message_id = message.get("message_id")
        audit_reason = decision.reason
        now_ts = int(time.time())
        until_ts: Optional[int] = None
        action_name = decision.action

        if decision.delete_message and message_id:
            try:
                bridge.delete_message(chat_id, int(message_id))
            except RequestException as error:
                self.deps.log_func(f"auto moderation delete failed chat={chat_id} message_id={message_id}: {error}")

        if decision.add_warning:
            _warn_limit, _warn_mode, warn_expire_seconds = bridge.state.get_warn_settings(chat_id)
            warning_expires_at = now_ts + warn_expire_seconds if warn_expire_seconds > 0 else None
            bridge.state.add_warning(chat_id, target_user_id, audit_reason, self.deps.owner_user_id, expires_at=warning_expires_at)
            bridge.legacy.sync_moderation_event(
                chat_id=chat_id,
                user_id=target_user_id,
                action="auto_warn",
                reason=audit_reason,
                created_by_user_id=self.deps.owner_user_id,
                expires_at=warning_expires_at,
                source_ref=f"auto_moderation:{decision.code}",
            )
            bridge.state.record_event(chat_id, target_user_id, "assistant", "auto_warn", f"[auto_warn {target_user_id}: {audit_reason}]")
            if decision.action == "warn":
                action = bridge.moderation_orchestrator.detect_auto_moderation(
                    context=ModerationContext(chat_id=chat_id, user_id=target_user_id, chat_type="group", text=(message.get("text") or "").strip()),
                    message=message,
                    bot_username=bridge.bot_username,
                    trigger_name=bridge.config.trigger_name,
                ).decision
                if action is not None:
                    bridge.safe_send_text(
                        chat_id,
                        bridge.moderation_orchestrator.text_policy.format_public_notice(target_label, action.action),
                )
                bridge.notify_owner(
                    bridge.render_auto_moderation_owner_report(
                        chat_id=chat_id,
                        message=message,
                        target_user_id=target_user_id,
                        target_label=target_label,
                        decision=decision,
                        applied_action="warn",
                    )
                )
                return

        if decision.action == "deescalate":
            cooldown_key = f"soft_moderation_notice:{chat_id}:{decision.code}"
            try:
                last_notice_ts = int(str(bridge.state.get_meta(cooldown_key, "0") or "0").strip() or "0")
            except ValueError:
                last_notice_ts = 0
            if now_ts - last_notice_ts < 120:
                return
            bridge.state.set_meta(cooldown_key, str(now_ts))
            bridge.safe_send_text(chat_id, f"JARVIS: {decision.public_reason}")
            bridge.state.record_event(
                chat_id,
                target_user_id,
                "assistant",
                "auto_deescalate",
                f"[auto_deescalate {target_user_id}: {decision.reason}]",
            )
            return

        try:
            if decision.action == "mute":
                until_ts = now_ts + decision.mute_seconds if decision.mute_seconds > 0 else None
                bridge.restrict_chat_member(chat_id, target_user_id, False, until_ts=until_ts)
                if until_ts is not None:
                    bridge.state.add_moderation_action(chat_id, target_user_id, "mute", audit_reason, self.deps.owner_user_id, expires_at=until_ts)
                    action_name = "tmute"
                action = bridge.moderation_orchestrator.detect_auto_moderation(
                    context=ModerationContext(chat_id=chat_id, user_id=target_user_id, chat_type="group", text=(message.get("text") or "").strip()),
                    message=message,
                    bot_username=bridge.bot_username,
                    trigger_name=bridge.config.trigger_name,
                ).decision
                if action is not None:
                    bridge.safe_send_text(
                        chat_id,
                        bridge.moderation_orchestrator.text_policy.format_public_notice(target_label, action.action),
                    )
                else:
                    bridge.safe_send_text(
                        chat_id,
                        f"JARVIS: {target_label} получил мут за нарушение правил: {decision.public_reason}."
                        + (
                            f" Срок: {self.deps.format_duration_seconds_func(decision.mute_seconds)}."
                            if decision.mute_seconds > 0
                            else ""
                        ),
                    )
            else:
                return
        except RequestException as error:
            self.deps.log_func(
                f"auto moderation action failed chat={chat_id} target={target_user_id} action={decision.action}: {error}"
            )
            return

        bridge.legacy.sync_moderation_event(
            chat_id=chat_id,
            user_id=target_user_id,
            action=action_name,
            reason=audit_reason,
            created_by_user_id=self.deps.owner_user_id,
            expires_at=until_ts,
            source_ref=f"auto_moderation:{decision.code}",
        )
        bridge.state.record_event(chat_id, target_user_id, "assistant", f"auto_{action_name}", f"[auto_{action_name} {target_user_id}: {audit_reason}]")
        bridge.notify_owner(
            bridge.render_auto_moderation_owner_report(
                chat_id=chat_id,
                message=message,
                target_user_id=target_user_id,
                target_label=target_label,
                decision=decision,
                applied_action=decision.action,
            )
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
