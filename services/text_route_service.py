from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Optional

from models.contracts import ContextBundle, RouteDecision
from services.external_research_service import build_external_research_context
from services.prompt_input_policy import select_prompt_inputs


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
        progress_style = "enterprise" if getattr(route_decision, "persona", "") == "enterprise" else "jarvis"
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
        if getattr(route_decision, "use_web", False) and not context_bundle.web_context:
            web_context = build_external_research_context(
                query=user_text,
                route_decision=route_decision,
                live_gateway=bridge.live_gateway,
                request_text_with_retry_func=bridge.request_text_with_retry,
                normalize_whitespace_func=bridge.normalize_whitespace,
                truncate_text_func=bridge.truncate_text,
                detect_news_query_func=bridge.detect_news_query,
                detect_current_fact_query_func=bridge.detect_current_fact_query,
                detect_weather_location_func=bridge.detect_weather_location,
                detect_currency_pair_func=bridge.detect_currency_pair,
                detect_crypto_asset_func=bridge.detect_crypto_asset,
                detect_stock_symbol_func=bridge.detect_stock_symbol,
            )
            if web_context:
                context_bundle = replace(context_bundle, web_context=web_context)
        self.deps.log_func(
            "ask_codex context "
            f"chat={chat_id} route={route_decision.route_kind} "
            f"reply={len(context_bundle.reply_context)} web={len(context_bundle.web_context)} "
            f"user_mem={len(context_bundle.user_memory_text)} rel_mem={len(context_bundle.relation_memory_text)} "
            f"chat_mem={len(context_bundle.chat_memory_text)} summary_mem={len(context_bundle.summary_memory_text)}"
        )
        history_items = list(bridge.state.get_history(chat_id))
        prompt_history = history_items
        if getattr(route_decision, "persona", "") == "enterprise":
            prompt_history = []
            prompt = user_text.strip()
            prompt_len = len(prompt)
            self.deps.log_func(
                "ask_codex prompt "
                f"chat={chat_id} route={route_decision.route_kind} prompt_len={prompt_len} "
                f"history_items=0 raw_enterprise=yes"
            )
            route_timeout_seconds = min(bridge.config.codex_timeout, self.deps.default_chat_route_timeout)
            return TextRoutePreparation(
                context_bundle=context_bundle,
                prompt=prompt,
                progress_style=progress_style,
                route_timeout_seconds=route_timeout_seconds,
                replace_status_with_answer=False,
                prompt_len=prompt_len,
                history_items=0,
            )
        prompt_inputs = select_prompt_inputs(route_decision, context_bundle)
        if (
            (getattr(route_decision, "use_web", False) or getattr(route_decision, "use_live", False))
            and str(getattr(route_decision, "request_kind", "") or "") not in {"chat_local_context", "runtime"}
            and len(prompt_history) > 12
        ):
            prompt_history = prompt_history[-12:]
        prompt = self.deps.build_prompt_func(
            mode=route_decision.persona,
            history=prompt_history,
            user_text=user_text,
            **prompt_inputs,
        )
        self.deps.log_func(
            "ask_codex prompt "
            f"chat={chat_id} route={route_decision.route_kind} prompt_len={len(prompt)} "
            f"history_items={len(prompt_history)}"
        )
        route_timeout_seconds = min(bridge.config.codex_timeout, self.deps.default_chat_route_timeout)
        if getattr(route_decision, "use_web", False) or getattr(route_decision, "use_live", False):
            route_timeout_seconds = min(bridge.config.codex_timeout, max(self.deps.default_chat_route_timeout, 120))
        elif len(prompt) >= 14000:
            route_timeout_seconds = min(route_timeout_seconds, 60)
        return TextRoutePreparation(
            context_bundle=context_bundle,
            prompt=prompt,
            progress_style=progress_style,
            route_timeout_seconds=route_timeout_seconds,
            replace_status_with_answer=(
                getattr(route_decision, "persona", "") != "enterprise"
                and
                initial_status_message_id is not None
                and chat_type in {"group", "supergroup"}
            ),
            prompt_len=len(prompt),
            history_items=len(prompt_history),
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
