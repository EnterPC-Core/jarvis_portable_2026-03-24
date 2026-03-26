from typing import Callable, List, Optional, Sequence, Tuple

from services.route_contracts import AttachmentBundle, ContextBundle, LiveProviderRecord, RouteDecision, SelfCheckReport


def derive_tools_used(route_decision: RouteDecision) -> Tuple[str, ...]:
    tools: List[str] = []
    if route_decision.use_workspace:
        tools.append("workspace_exec")
    if route_decision.request_kind == "runtime":
        tools.append("direct_runtime_probe")
    if route_decision.use_live:
        tools.append("live_provider")
    if route_decision.use_web:
        tools.append("web_search_context")
    if route_decision.use_database:
        tools.append("sqlite_memory")
    if route_decision.use_events:
        tools.append("chat_events")
    if route_decision.use_reply:
        tools.append("reply_context")
    return tuple(dict.fromkeys(tools))


def derive_memory_used(context_bundle: Optional[ContextBundle], route_decision: RouteDecision) -> Tuple[str, ...]:
    if context_bundle is None:
        return tuple(
            source
            for source in ("database_context", "reply_context")
            if getattr(route_decision, "use_database" if source == "database_context" else "use_reply", False)
        )
    layers: List[str] = []
    if context_bundle.user_memory_text:
        layers.append("user_memory")
    if context_bundle.relation_memory_text:
        layers.append("relation_memory")
    if context_bundle.chat_memory_text:
        layers.append("chat_memory")
    if context_bundle.summary_memory_text:
        layers.append("summary_memory")
    if context_bundle.reply_context:
        layers.append("reply_context")
    if context_bundle.event_context:
        layers.append("chat_events")
    if context_bundle.database_context:
        layers.append("database_context")
    if context_bundle.world_state_text:
        layers.append("world_state")
    if len(layers) > 4:
        layers = layers[:4]
    return tuple(layers)


def derive_response_mode(outcome: str) -> str:
    normalized = (outcome or "").strip().lower()
    if normalized == "ok":
        return "verified"
    if normalized == "uncertain":
        return "inferred"
    return "insufficient"


def derive_confidence(report: SelfCheckReport, route_decision: RouteDecision) -> float:
    if report.outcome == "ok":
        base = 0.88 if route_decision.use_live or route_decision.use_workspace else 0.76
    elif report.outcome == "uncertain":
        base = 0.52
    else:
        base = 0.18
    penalty = min(0.35, 0.08 * len(report.uncertain_points))
    return max(0.0, min(1.0, base - penalty))


def derive_freshness(route_decision: RouteDecision) -> str:
    if route_decision.request_kind in {"runtime", "live"}:
        return "live"
    if route_decision.request_kind in {"chat_local_context", "project", "owner_admin"}:
        return "session-local"
    return "not-applicable"


def enrich_self_check_report(
    report: SelfCheckReport,
    *,
    route_decision: RouteDecision,
    context_bundle: Optional[ContextBundle] = None,
    notes: str = "",
) -> SelfCheckReport:
    sources = [route_decision.source_label] if route_decision.source_label else []
    sources.extend(report.observed_basis)
    return SelfCheckReport(
        outcome=report.outcome,
        answer=report.answer,
        flags=report.flags,
        observed_basis=report.observed_basis,
        uncertain_points=report.uncertain_points,
        mode=derive_response_mode(report.outcome),
        route=route_decision.route_kind,
        sources=tuple(dict.fromkeys(source for source in sources if source)),
        tools_used=derive_tools_used(route_decision),
        memory_used=derive_memory_used(context_bundle, route_decision),
        confidence=derive_confidence(report, route_decision),
        freshness=derive_freshness(route_decision),
        notes=notes or route_decision.answer_contract,
    )


def build_persisted_self_check_report(
    report: SelfCheckReport,
    *,
    route_decision: RouteDecision,
    live_records: Sequence[LiveProviderRecord] = (),
) -> SelfCheckReport:
    enriched_sources = list(report.sources)
    live_status_notes: List[str] = []
    live_freshness = report.freshness
    for record in live_records:
        enriched_sources.append(record.provider)
        live_status_notes.append(f"{record.provider}:{record.status}:{record.freshness}")
    if route_decision.use_live:
        fresh_markers = [record.freshness for record in live_records if record.freshness]
        if fresh_markers:
            live_freshness = ", ".join(dict.fromkeys(fresh_markers))
    return SelfCheckReport(
        outcome=report.outcome,
        answer=report.answer,
        flags=report.flags,
        observed_basis=report.observed_basis,
        uncertain_points=report.uncertain_points,
        mode=report.mode,
        route=report.route,
        sources=tuple(dict.fromkeys(source for source in enriched_sources if source)),
        tools_used=report.tools_used,
        memory_used=report.memory_used,
        confidence=report.confidence,
        freshness=live_freshness,
        notes="; ".join(part for part in (report.notes, ", ".join(live_status_notes)) if part),
    )


def build_attachment_bundle(
    *,
    attachment_type: str,
    extracted_text: str = "",
    structured_features: str = "",
    source_message_link: str = "",
    relevance_score: float = 0.0,
    used_in_response: bool = False,
    normalize_whitespace_func: Callable[[str], str],
    truncate_text_func: Callable[[str, int], str],
) -> AttachmentBundle:
    return AttachmentBundle(
        attachment_type=attachment_type,
        extracted_text=truncate_text_func(normalize_whitespace_func(extracted_text), 3500),
        structured_features=truncate_text_func(normalize_whitespace_func(structured_features), 1200),
        source_message_link=truncate_text_func(source_message_link, 160),
        relevance_score=max(0.0, min(1.0, float(relevance_score))),
        used_in_response=used_in_response,
    )
