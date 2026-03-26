from datetime import datetime
from typing import Callable, Dict, Optional

from services.failure_detectors import detect_failure_signals, render_failure_signals
from services.repair_playbooks import render_playbook_summary, select_playbooks_for_signals
from utils.ops_utils import inspect_runtime_log, read_recent_log_highlights
from utils.report_utils import render_bridge_runtime_watch, render_resource_summary, render_route_diagnostics_rows
from utils.text_utils import normalize_whitespace, truncate_text


class OwnerCommandService:
    def __init__(
        self,
        *,
        owner_user_id: int,
        is_owner_private_chat_func: Callable[[Optional[int], int], bool],
        memory_user_usage_text: str,
        reflections_usage_text: str,
        chat_digest_usage_text: str,
    ) -> None:
        self.owner_user_id = owner_user_id
        self.is_owner_private_chat_func = is_owner_private_chat_func
        self.memory_user_usage_text = memory_user_usage_text
        self.reflections_usage_text = reflections_usage_text
        self.chat_digest_usage_text = chat_digest_usage_text

    def handle_memory_chat_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], query: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        bridge.safe_send_text(chat_id, bridge.state.get_chat_memory_context(chat_id, query=query or "") or "Chat memory пока пуста.")
        return True

    def handle_memory_user_command(
        self,
        bridge: "TelegramBridge",
        chat_id: int,
        user_id: Optional[int],
        raw_target: str,
        message: Optional[dict],
    ) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        target_user_id: Optional[int] = None
        cleaned = (raw_target or "").strip()
        reply_to = (message or {}).get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        if cleaned:
            if cleaned.startswith("@"):
                resolved_id, _label = bridge.state.resolve_chat_user(chat_id, cleaned)
                target_user_id = resolved_id
            else:
                try:
                    target_user_id = int(cleaned)
                except ValueError:
                    resolved_id, _label = bridge.state.resolve_chat_user(chat_id, cleaned)
                    target_user_id = resolved_id
        elif reply_to and not reply_from.get("is_bot"):
            target_user_id = reply_from.get("id")
        else:
            bridge.safe_send_text(chat_id, self.memory_user_usage_text)
            return True
        if target_user_id is None:
            bridge.safe_send_text(chat_id, "Не удалось определить участника в памяти текущего чата.")
            return True
        context = bridge.state.get_user_memory_context(chat_id, user_id=target_user_id)
        if not context:
            bridge.safe_send_text(chat_id, "User memory по этому участнику пока пуста.")
            return True
        bridge.safe_send_text(chat_id, context)
        return True

    def handle_memory_summary_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        context = bridge.state.get_summary_memory_context(chat_id, limit=6)
        bridge.safe_send_text(chat_id, context or "Summary memory пока пуста.")
        return True

    def handle_self_state_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        bridge.safe_send_text(chat_id, bridge.state.get_self_model_context("enterprise"))
        return True

    def handle_world_state_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        payload = bridge.refresh_world_state_registry("manual_world_state", chat_id=chat_id)
        bridge.state.record_autobiographical_event(
            category="owner",
            event_type="world_state_check",
            chat_id=chat_id,
            user_id=user_id,
            route_kind="owner_command",
            title="owner requested world state",
            details=f"world_state keys={sorted(payload.keys())}",
            status="ok",
            importance=40,
            open_state="closed",
            tags="owner,world-state",
            observed_payload=payload,
        )
        bridge.safe_send_text(chat_id, bridge.state.get_world_state_context(limit=12) or "World state пока пуст.")
        return True

    def handle_drives_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        scores = bridge.recompute_drive_scores()
        bridge.state.record_autobiographical_event(
            category="owner",
            event_type="drive_check",
            chat_id=chat_id,
            user_id=user_id,
            route_kind="owner_command",
            title="owner requested drive pressures",
            details=", ".join(f"{key}={value:.1f}" for key, value in sorted(scores.items())),
            status="ok",
            importance=40,
            open_state="closed",
            tags="owner,drives",
        )
        bridge.safe_send_text(chat_id, bridge.state.get_drive_context() or "Drive pressures пока не рассчитаны.")
        return True

    def handle_autobio_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], query: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        context = bridge.state.get_autobiographical_context(chat_id, query=query or "", limit=8)
        bridge.safe_send_text(chat_id, context or "Autobiographical memory пока пуста.")
        return True

    def handle_skills_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], query: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        context = bridge.state.get_skill_memory_context(query or "owner operations", route_kind="", limit=6)
        bridge.safe_send_text(chat_id, context or "Skill memory пока пуста.")
        return True

    def handle_reflections_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if user_id != self.owner_user_id:
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу.")
            return True
        limit = 6
        cleaned = (payload or "").strip()
        if cleaned:
            try:
                limit = max(1, min(20, int(cleaned)))
            except ValueError:
                bridge.safe_send_text(chat_id, self.reflections_usage_text)
                return True
        context = bridge.state.get_reflection_context(limit=limit)
        bridge.safe_send_text(chat_id, context or "Reflections пока пусты.")
        return True

    def handle_chat_digest_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], payload: str) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        cleaned = (payload or "").strip()
        if not cleaned:
            bridge.safe_send_text(chat_id, self.chat_digest_usage_text)
            return True
        parts = cleaned.split(maxsplit=1)
        try:
            target_chat_id = int(parts[0])
        except ValueError:
            bridge.safe_send_text(chat_id, self.chat_digest_usage_text)
            return True
        day = parts[1].strip() if len(parts) > 1 else ""
        bridge.safe_send_text(chat_id, self.render_chat_digest_text(bridge, target_chat_id, day))
        return True

    def render_chat_digest_text(self, bridge: "TelegramBridge", target_chat_id: int, day: str) -> str:
        target_day, rows = bridge.state.get_daily_summary_context(target_chat_id, day)
        if not rows:
            return f"За {target_day} событий не найдено."
        user_rows = [row for row in rows if row[5] == "user"]
        assistant_rows = [row for row in rows if row[5] == "assistant"]
        type_counts: Dict[str, int] = {}
        user_counts: Dict[str, int] = {}
        highlights: list[str] = []
        for created_at, user_id, username, first_name, last_name, role, message_type, content in rows:
            type_counts[message_type] = type_counts.get(message_type, 0) + 1
            if role == "user":
                actor = bridge.build_actor_name(user_id, username or "", first_name or "", last_name or "", role)
                user_counts[actor] = user_counts.get(actor, 0) + 1
                if len(highlights) < 6 and message_type in {"text", "caption", "edited_text", "photo", "voice", "document"}:
                    stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                    highlights.append(f"[{stamp}] {actor}: {truncate_text(content, 120)}")
        top_users = sorted(user_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        top_types = sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
        lines = [
            f"Digest за {target_day}",
            f"Чат: {target_chat_id}",
            f"Всего событий: {len(rows)}",
            f"Сообщений пользователей: {len(user_rows)}",
            f"Ответов/сервисных действий бота: {len(assistant_rows)}",
        ]
        if top_users:
            lines.append("")
            lines.append("Топ активности:")
            lines.extend(f"- {name}: {count}" for name, count in top_users)
        if top_types:
            lines.append("")
            lines.append("Типы событий:")
            lines.extend(f"- {name}: {count}" for name, count in top_types)
        if highlights:
            lines.append("")
            lines.append("Ключевые куски дня:")
            lines.extend(f"- {item}" for item in highlights)
        return "\n".join(lines)

    def handle_owner_report_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        payload = bridge.refresh_world_state_registry("owner_report", chat_id=chat_id)
        scores = bridge.recompute_drive_scores(payload)
        bridge.state.record_autobiographical_event(
            category="owner",
            event_type="owner_report",
            chat_id=chat_id,
            user_id=user_id,
            route_kind="owner_command",
            title="owner requested operational report",
            details=f"errors={payload.get('recent_errors_count', 0)}; git_dirty={payload.get('git_dirty_count', 0)}; runtime_risk={scores.get('runtime_risk_pressure', 0):.1f}",
            status="ok",
            importance=55,
            open_state="closed",
            tags="owner,report,runtime",
            observed_payload=payload,
        )
        bridge.safe_send_text(chat_id, self.render_owner_report_text(bridge, chat_id))
        return True

    def handle_repair_status_command(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int]) -> bool:
        if not self.is_owner_private_chat_func(user_id, chat_id):
            bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
            return True
        runtime_snapshot = inspect_runtime_log(bridge.log_path)
        recent_errors = read_recent_log_highlights(bridge.log_path, normalize_whitespace, truncate_text, limit=10)
        recent_routes = bridge.state.get_recent_request_diagnostics(limit=8)
        signals = detect_failure_signals(
            runtime_snapshot=runtime_snapshot,
            recent_errors=recent_errors,
            recent_routes=recent_routes,
            heartbeat_timeout_seconds=bridge.config.heartbeat_timeout_seconds,
        )
        playbooks = select_playbooks_for_signals(signals)
        if signals:
            for signal in signals:
                bridge.state.record_repair_journal(
                    signal_code=signal.signal_code,
                    playbook_id=signal.suggested_playbook,
                    status="detected",
                    summary=signal.summary,
                    evidence=signal.evidence,
                    verification_result="signal_detected_only",
                    notes="repair not executed automatically",
                )
        lines = [
            render_failure_signals(signals),
            "",
            render_playbook_summary(playbooks),
        ]
        recent_journal = bridge.state.get_recent_repair_journal(limit=6)
        if recent_journal:
            lines.extend(["", "Repair journal"])
            for row in recent_journal:
                stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
                lines.append(
                    f"- [{stamp}] signal={row['signal_code'] or '-'} playbook={row['playbook_id'] or '-'} status={row['status'] or '-'}"
                )
                if row["summary"]:
                    lines.append(f"  {truncate_text(row['summary'], 200)}")
        bridge.safe_send_text(chat_id, "\n".join(lines))
        return True

    def render_owner_report_text(self, bridge: "TelegramBridge", chat_id: int) -> str:
        status_snapshot = bridge.state.get_status_snapshot(chat_id)
        last_backup_raw = bridge.state.get_meta("last_backup_ts", "0")
        try:
            last_backup_value = float(last_backup_raw or "0")
        except ValueError:
            last_backup_value = 0.0
        backup_text = datetime.utcfromtimestamp(last_backup_value).strftime("%Y-%m-%d %H:%M:%S UTC") if last_backup_value > 0 else "ещё не было"
        runtime_snapshot = inspect_runtime_log(bridge.log_path)
        recent_errors = read_recent_log_highlights(bridge.log_path, normalize_whitespace, truncate_text, limit=8)
        recent_routes = bridge.state.get_recent_request_diagnostics(limit=5)
        failure_signals = detect_failure_signals(
            runtime_snapshot=runtime_snapshot,
            recent_errors=recent_errors,
            recent_routes=recent_routes,
            heartbeat_timeout_seconds=bridge.config.heartbeat_timeout_seconds,
        )
        repair_playbooks = select_playbooks_for_signals(failure_signals)
        repair_journal = bridge.state.get_recent_repair_journal(limit=4)
        lines = [
            "OWNER REPORT",
            f"Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"Режим чата: {bridge.state.get_mode(chat_id)}",
            f"События в этом чате: {status_snapshot['events_count']}",
            f"Факты в этом чате: {status_snapshot['facts_count']}",
            f"История в этом чате: {status_snapshot['history_count']}",
            f"User memory profiles в этом чате: {status_snapshot['user_memory_profiles']}",
            f"Relation memory в этом чате: {status_snapshot['relation_memory_rows']}",
            f"Summary snapshots в этом чате: {status_snapshot['summary_snapshots']}",
            f"Autobiographical events: {status_snapshot['autobiographical_rows']}",
            f"Reflections: {status_snapshot['reflections_rows']}",
            f"World-state rows: {status_snapshot['world_state_rows']}",
            f"Всего событий в БД: {status_snapshot['total_events']}",
            f"Route decisions в БД: {status_snapshot['total_route_decisions']}",
            f"Upgrade активен: {'да' if bridge.state.global_upgrade_active else 'нет'}",
            f"Heartbeat: {bridge.config.heartbeat_path}",
            f"Heartbeat timeout: {bridge.config.heartbeat_timeout_seconds}s",
            f"Последний backup: {backup_text}",
            "",
            "Ресурсы:",
            render_resource_summary(),
            "",
            render_bridge_runtime_watch(),
        ]
        world_state_context = bridge.state.get_world_state_context(limit=6)
        drive_context = bridge.state.get_drive_context()
        if world_state_context:
            lines.extend(["", world_state_context])
        if drive_context:
            lines.extend(["", drive_context])
        if recent_routes:
            lines.extend(["", "Последние route decisions:", render_route_diagnostics_rows(recent_routes)])
        lines.extend(["", render_failure_signals(failure_signals), "", render_playbook_summary(repair_playbooks)])
        if repair_journal:
            lines.append("")
            lines.append("Последние repair journal entries:")
            for row in repair_journal:
                stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
                lines.append(
                    f"- [{stamp}] signal={row['signal_code'] or '-'} playbook={row['playbook_id'] or '-'} status={row['status'] or '-'}"
                )
        if recent_errors:
            lines.extend(["", "Недавние ошибки/сбои:", *[f"- {item}" for item in recent_errors]])
        else:
            lines.extend(["", "Недавние ошибки/сбои:", "- Явных ошибок в хвосте лога не найдено."])
        if int(runtime_snapshot.get("warning_count", 0)):
            lines.extend(["", "Недавние recoverable warnings:", *[f"- {item}" for item in runtime_snapshot.get("recent_warning_lines", [])[-5:]]])
        return "\n".join(lines)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
