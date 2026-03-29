import secrets
import time
from typing import Callable, Optional, Type

from models.contracts import LiveProviderRecord
from services.route_enforcer import build_execution_trace


def _is_reply_invocation_only(user_text: str, persona: str) -> bool:
    cleaned = " ".join((user_text or "").split()).strip().lower()
    if not cleaned:
        return False
    if persona == "enterprise":
        variants = {"enterprise", "enterprise?"}
    else:
        variants = {"jarvis", "jarvis?"}
    return cleaned in variants


def _build_direct_live_answer(
    bridge: "TelegramBridge",
    route_decision: "RouteDecision",
    user_text: str,
) -> tuple[str, tuple[LiveProviderRecord, ...]]:
    if route_decision.route_kind == "live_weather":
        location_query = bridge.detect_weather_location(user_text)
        if not location_query:
            return "", ()
        return bridge.live_gateway.fetch_weather_answer(location_query)
    if route_decision.route_kind == "live_fx":
        currency_pair = bridge.detect_currency_pair(user_text)
        if not currency_pair:
            return "", ()
        return bridge.live_gateway.fetch_exchange_rate_answer(currency_pair[0], currency_pair[1])
    if route_decision.route_kind == "live_crypto":
        crypto_asset = bridge.detect_crypto_asset(user_text)
        if not crypto_asset:
            return "", ()
        return bridge.live_gateway.fetch_crypto_price_answer(crypto_asset)
    if route_decision.route_kind == "live_stocks":
        stock_symbol = bridge.detect_stock_symbol(user_text)
        if not stock_symbol:
            return "", ()
        return bridge.live_gateway.fetch_stock_price_answer(stock_symbol)
    if route_decision.route_kind == "live_news":
        news_query = bridge.detect_news_query(user_text)
        if not news_query:
            return "", ()
        return bridge.live_gateway.fetch_news_answer(news_query, limit=3)
    if route_decision.route_kind == "live_current_fact":
        fact_query = bridge.detect_current_fact_query(user_text)
        if not fact_query:
            return "", ()
        return bridge.live_gateway.fetch_current_fact_answer(fact_query, limit=3)
    return "", ()


def ask_codex(
    bridge: "TelegramBridge",
    *,
    chat_id: int,
    user_text: str,
    user_id: Optional[int] = None,
    chat_type: str = "private",
    assistant_persona: str = "",
    message: Optional[dict] = None,
    spontaneous_group_reply: bool = False,
    suppress_status_messages: bool = False,
    build_meta_identity_answer_func: Callable[..., str],
    build_owner_contact_reply_func: Callable[..., str],
    analyze_request_route_func: Callable[..., "RouteDecision"],
    enrich_self_check_report_func: Callable[..., "SelfCheckReport"],
    apply_self_check_contract_func: Callable[..., "SelfCheckReport"],
    render_enterprise_runtime_report_func: Callable[[], str],
    build_context_budget_status_func: Callable[..., str],
    build_progress_target_label_func: Callable[[Optional[dict], Optional[int]], str],
    detect_local_chat_query_func: Callable[[str], bool],
    is_explicit_runtime_probe_request_func: Callable[[str], bool],
    is_explicit_runtime_restart_request_func: Callable[[str], bool],
    postprocess_answer_func: Callable[..., str],
    owner_user_id: int,
    owner_agent_running_text: str,
    jarvis_agent_running_text: str,
    default_enterprise_workspace_timeout: int,
    heartbeat_guard_cls: Type["HeartbeatGuard"],
    progress_status_guard_cls: Type["ProgressStatusGuard"],
) -> str:
    started_at = time.perf_counter()
    request_trace_id = f"req-{int(time.time() * 1000)}-{secrets.token_hex(4)}"
    has_explicit_reply_target = bool(((message or {}).get("reply_to_message") or {}))
    if has_explicit_reply_target and _is_reply_invocation_only(user_text, assistant_persona or "jarvis"):
        user_text = "Ответь на сообщение, на которое я ответил."
    reply_context = bridge.build_reply_context(chat_id, message)
    active_subject_context = bridge.build_active_subject_context(chat_id, user_id, user_text, message)
    if active_subject_context:
        reply_context = f"{reply_context}\n\n{active_subject_context}" if reply_context else active_subject_context
    effective_persona = assistant_persona or "jarvis"
    meta_identity_answer = build_meta_identity_answer_func(user_text, persona=effective_persona)
    if meta_identity_answer and effective_persona != "enterprise" and not has_explicit_reply_target:
        return postprocess_answer_func(meta_identity_answer, latency_ms=max(1, int((time.perf_counter() - started_at) * 1000)))
    if user_id == owner_user_id and not reply_context and not has_explicit_reply_target:
        owner_contact_reply = build_owner_contact_reply_func(user_text, persona=effective_persona)
        if owner_contact_reply and effective_persona == "enterprise":
            owner_contact_reply = ""
        if owner_contact_reply:
            return postprocess_answer_func(owner_contact_reply, latency_ms=max(1, int((time.perf_counter() - started_at) * 1000)))
    initial_route_decision = analyze_request_route_func(
        user_text,
        assistant_persona=assistant_persona,
        chat_type=chat_type,
        user_id=user_id,
        reply_context=reply_context,
    )
    operational_state = bridge.refresh_world_state_registry("ask_codex", chat_id=chat_id)
    drive_scores = bridge.recompute_drive_scores(operational_state)
    route_decision = bridge.apply_persistent_pressures_to_route(initial_route_decision, user_text)
    current_goals = (
        "сохранить continuity и честность; "
        f"закрыть текущий запрос через {route_decision.route_kind}; "
        f"снизить uncertainty={drive_scores.get('uncertainty_pressure', 0):.0f} и runtime-risk={drive_scores.get('runtime_risk_pressure', 0):.0f}"
    )
    active_constraints = (
        f"route={route_decision.route_kind}; guardrails={', '.join(route_decision.guardrails)}; "
        f"safe_chat_only={'yes' if bridge.config.safe_chat_only else 'no'}"
    )
    bridge.state.update_self_model_state(
        active_mode=bridge.state.get_mode(chat_id),
        current_goals=current_goals,
        active_constraints=active_constraints,
        last_route_kind=route_decision.route_kind,
    )
    early_status_message_id: Optional[int] = None
    allow_status_message = (not suppress_status_messages) and (
        chat_type not in {"group", "supergroup"}
        or (chat_type in {"group", "supergroup"} and user_id == owner_user_id and assistant_persona == "enterprise")
    )
    initial_status = owner_agent_running_text if route_decision.persona == "enterprise" else jarvis_agent_running_text
    progress_target_label = build_progress_target_label_func(message, user_id)
    bridge.log(
        "ask_codex route "
        f"chat={chat_id} user={user_id} route={route_decision.route_kind} "
        f"persona={route_decision.persona} intent={route_decision.intent} "
        f"use_live={route_decision.use_live} use_web={route_decision.use_web} "
        f"use_events={route_decision.use_events} use_db={route_decision.use_database} "
        f"use_reply={route_decision.use_reply} query_len={len(user_text or '')}"
    )
    if allow_status_message and spontaneous_group_reply:
        early_status_message_id = bridge.send_status_message(chat_id, initial_status)
    elif allow_status_message and user_id == owner_user_id:
        early_status_message_id = bridge.send_status_message(chat_id, initial_status)
    if detect_local_chat_query_func(user_text) and drive_scores.get("stale_memory_pressure", 0.0) >= 35.0:
        bridge.state.refresh_relation_memory(chat_id)

    lowered_user_text = bridge.normalize_whitespace(user_text).lower()

    if route_decision.use_live and not route_decision.use_workspace:
        direct_answer, live_records = _build_direct_live_answer(bridge, route_decision, user_text)
        if direct_answer:
            direct_execution_trace = build_execution_trace(
                route_decision,
                raw_answer=direct_answer,
                live_records=live_records,
                permission_checked=(user_id == owner_user_id),
            )
            report = enrich_self_check_report_func(
                apply_self_check_contract_func(
                    direct_answer,
                    route_decision,
                    execution_trace=direct_execution_trace,
                ),
                route_decision=route_decision,
                execution_trace=direct_execution_trace,
                notes="direct live route without secondary LLM synthesis",
            )
            bridge.state.update_self_model_state(last_outcome=report.outcome)
            bridge.run_post_task_reflection(
                chat_id=chat_id,
                user_id=user_id,
                route_decision=route_decision,
                user_text=user_text,
                report=report,
                source="direct_live_route",
            )
            bridge.record_route_diagnostic(
                chat_id=chat_id,
                user_id=user_id,
                route_decision=route_decision,
                report=report,
                started_at=started_at,
                query_text=user_text,
                request_trace_id=request_trace_id,
                task_id=bridge.state.find_latest_task_id_by_request_trace(request_trace_id),
                execution_trace=direct_execution_trace,
                live_records=live_records,
            )
            return postprocess_answer_func(
                report.answer,
                latency_ms=max(1, int((time.perf_counter() - started_at) * 1000)),
            )

    context_progress_style = "enterprise" if route_decision.persona == "enterprise" else "jarvis"
    with heartbeat_guard_cls(bridge), progress_status_guard_cls(
        bridge,
        chat_id=chat_id,
        status_message_id=early_status_message_id,
        initial_status=initial_status,
        progress_style=context_progress_style,
    ):
        preparation = bridge.text_route_service.prepare(
            bridge,
            chat_id=chat_id,
            user_text=user_text,
            route_decision=route_decision,
            user_id=user_id,
            message=message,
            reply_context=reply_context,
            spontaneous_group_reply=spontaneous_group_reply,
            initial_status_message_id=early_status_message_id,
            chat_type=chat_type,
        )
    context_bundle = preparation.context_bundle
    prompt = preparation.prompt
    replace_status_with_answer = preparation.replace_status_with_answer
    delivery_chat_id = bridge.resolve_enterprise_delivery_chat_id(chat_id, chat_type, route_decision.persona)
    effective_initial_status = initial_status
    if chat_type == "private" and route_decision.persona == "enterprise":
        effective_initial_status = (
            f"{initial_status}\n\n"
            f"{build_context_budget_status_func(prompt_len=preparation.prompt_len, history_items=preparation.history_items, history_limit=bridge.config.history_limit, soft_limit=bridge.config.bridge_context_soft_limit)}"
        )

    if route_decision.use_workspace:
        workspace_timeout_seconds = (
            bridge.config.enterprise_task_timeout
            if bridge.config.enterprise_task_timeout is not None
            else default_enterprise_workspace_timeout
        )
        raw_answer = bridge.run_codex_with_progress(
            chat_id,
            prompt,
            initial_status=effective_initial_status,
            sandbox_mode="danger-full-access",
            approval_policy="never",
            json_output=True,
            timeout_seconds=workspace_timeout_seconds,
            progress_style="enterprise",
            replace_status_with_answer=replace_status_with_answer,
            status_message_id=early_status_message_id,
            show_status_message=allow_status_message,
            target_label=progress_target_label,
            delivery_chat_id=delivery_chat_id,
            request_trace_id=request_trace_id,
            task_kind="enterprise_route",
            route_kind=route_decision.route_kind,
            persona=route_decision.persona,
            request_kind=route_decision.request_kind,
            user_id=user_id,
            message_id=int((message or {}).get("message_id") or 0) or None,
            summary=user_text,
        )
    else:
        bridge.log(
            "ask_codex model_start "
            f"chat={chat_id} route={route_decision.route_kind} timeout={preparation.route_timeout_seconds}"
        )
        raw_answer = bridge.run_codex_with_progress(
            chat_id,
            prompt,
            initial_status=effective_initial_status,
            progress_style=preparation.progress_style,
            replace_status_with_answer=replace_status_with_answer,
            status_message_id=early_status_message_id,
            show_status_message=allow_status_message,
            timeout_seconds=preparation.route_timeout_seconds,
            target_label=progress_target_label,
            delivery_chat_id=delivery_chat_id,
            request_trace_id=request_trace_id,
            task_kind="codex_route",
            route_kind=route_decision.route_kind,
            persona=route_decision.persona,
            request_kind=route_decision.request_kind,
            user_id=user_id,
            message_id=int((message or {}).get("message_id") or 0) or None,
            summary=user_text,
        )
        bridge.log(
            "ask_codex model_end "
            f"chat={chat_id} route={route_decision.route_kind} answer_len={len(raw_answer or '')}"
        )

    live_records = bridge.live_gateway.consume_records()
    execution_trace = build_execution_trace(
        route_decision,
        context_bundle=context_bundle,
        raw_answer=raw_answer,
        live_records=live_records,
        permission_checked=(user_id == owner_user_id),
    )
    report = enrich_self_check_report_func(
        apply_self_check_contract_func(
            raw_answer,
            route_decision,
            execution_trace=execution_trace,
        ),
        route_decision=route_decision,
        context_bundle=context_bundle,
        execution_trace=execution_trace,
    )
    bridge.state.update_self_model_state(last_outcome=report.outcome)
    bridge.run_post_task_reflection(
        chat_id=chat_id,
        user_id=user_id,
        route_decision=route_decision,
        user_text=user_text,
        report=report,
        source="enterprise_route",
    )
    bridge.record_route_diagnostic(
        chat_id=chat_id,
        user_id=user_id,
        route_decision=route_decision,
        report=report,
        started_at=started_at,
        query_text=user_text,
        request_trace_id=request_trace_id,
        task_id=bridge.state.find_latest_task_id_by_request_trace(request_trace_id),
        execution_trace=execution_trace,
        live_records=live_records,
    )
    if meta_identity_answer and effective_persona == "enterprise":
        return postprocess_answer_func(
            meta_identity_answer,
            latency_ms=max(1, int((time.perf_counter() - started_at) * 1000)),
        )
    if effective_persona == "enterprise":
        return raw_answer
    return report.answer


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.contracts import RouteDecision, SelfCheckReport
    from tg_codex_bridge import HeartbeatGuard, ProgressStatusGuard, TelegramBridge
