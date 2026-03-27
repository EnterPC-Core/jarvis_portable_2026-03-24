from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from models.contracts import ContextBundle, RouteDecision


@dataclass(frozen=True)
class TextRoutePreparation:
    context_bundle: ContextBundle
    prompt: str
    progress_style: str
    route_timeout_seconds: int
    replace_status_with_answer: bool
    prompt_len: int
    history_items: int


@dataclass(frozen=True)
class TextRouteServiceDeps:
    build_prompt_func: Callable[..., str]
    log_func: Callable[[str], None]
    default_chat_route_timeout: int


class TextRouteService:
    """Builds context, prompt and runtime config for the main text route."""

    def __init__(self, deps: TextRouteServiceDeps) -> None:
        self.deps = deps

    def prepare(
        self,
        bridge: "TelegramBridge",
        *,
        chat_id: int,
        user_text: str,
        route_decision: RouteDecision,
        user_id: Optional[int],
        message: Optional[dict],
        reply_context: str,
        spontaneous_group_reply: bool,
        initial_status_message_id: Optional[int],
        chat_type: str,
    ) -> TextRoutePreparation:
        progress_style = "enterprise" if route_decision.persona == "enterprise" else "jarvis"
        context_bundle = bridge.build_text_context_bundle(
            chat_id=chat_id,
            user_text=user_text,
            route_decision=route_decision,
            user_id=user_id,
            message=message,
            reply_context=reply_context,
            active_group_followup=spontaneous_group_reply or bridge.is_group_followup_message(
                chat_id,
                message or {},
                (message or {}).get("text") or user_text,
            ),
        )
        self.deps.log_func(
            "ask_codex context "
            f"chat={chat_id} route={route_decision.route_kind} "
            f"reply={len(context_bundle.reply_context)} web={len(context_bundle.web_context)} "
            f"user_mem={len(context_bundle.user_memory_text)} rel_mem={len(context_bundle.relation_memory_text)} "
            f"chat_mem={len(context_bundle.chat_memory_text)} summary_mem={len(context_bundle.summary_memory_text)}"
        )
        prompt = self.deps.build_prompt_func(
            mode=route_decision.persona,
            history=list(bridge.state.get_history(chat_id)),
            user_text=user_text,
            summary_text=context_bundle.summary_text,
            facts_text=context_bundle.facts_text,
            event_context=context_bundle.event_context,
            database_context=context_bundle.database_context,
            reply_context=context_bundle.reply_context,
            discussion_context=context_bundle.discussion_context,
            web_context=context_bundle.web_context,
            route_summary=context_bundle.route_summary,
            guardrail_note=context_bundle.guardrail_note,
            self_model_text=context_bundle.self_model_text,
            autobiographical_text=context_bundle.autobiographical_text,
            skill_memory_text=context_bundle.skill_memory_text,
            world_state_text=context_bundle.world_state_text,
            drive_state_text=context_bundle.drive_state_text,
            user_memory_text=context_bundle.user_memory_text,
            relation_memory_text=context_bundle.relation_memory_text,
            chat_memory_text=context_bundle.chat_memory_text,
            summary_memory_text=context_bundle.summary_memory_text,
        )
        history_items = list(bridge.state.get_history(chat_id))
        self.deps.log_func(
            "ask_codex prompt "
            f"chat={chat_id} route={route_decision.route_kind} prompt_len={len(prompt)} "
            f"history_items={len(history_items)}"
        )
        route_timeout_seconds = min(bridge.config.codex_timeout, self.deps.default_chat_route_timeout)
        if len(prompt) >= 14000:
            route_timeout_seconds = min(route_timeout_seconds, 60)
        return TextRoutePreparation(
            context_bundle=context_bundle,
            prompt=prompt,
            progress_style=progress_style,
            route_timeout_seconds=route_timeout_seconds,
            replace_status_with_answer=(
                initial_status_message_id is not None
                and (
                    chat_type in {"group", "supergroup"}
                    or (chat_type == "private" and route_decision.persona == "enterprise")
                )
            ),
            prompt_len=len(prompt),
            history_items=len(history_items),
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
