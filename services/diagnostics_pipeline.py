from typing import Callable, List, Optional, Sequence, Tuple

from services.route_contracts import AttachmentBundle, ContextBundle, ExecutionTrace, LiveProviderRecord, RouteDecision, SelfCheckReport
from services.context_bundle_utils import collect_memory_context_items
from models.contracts import MemoryContextItem
from services.route_enforcer import enforce_route_contract


def derive_tools_used(route_decision: RouteDecision, execution_trace: Optional[ExecutionTrace] = None) -> Tuple[str, ...]:
    if execution_trace is not None and execution_trace.tools_succeeded:
        return execution_trace.tools_succeeded
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


def derive_memory_used(
    context_bundle: Optional[ContextBundle],
    route_decision: RouteDecision,
    execution_trace: Optional[ExecutionTrace] = None,
) -> Tuple[str, ...]:
    if execution_trace is not None and execution_trace.memory_layers_read:
        return execution_trace.memory_layers_read
    if context_bundle is None:
        return tuple(
            source
            for source in ("database_context", "reply_context")
            if getattr(route_decision, "use_database" if source == "database_context" else "use_reply", False)
        )
    collected = collect_memory_context_items(
        (
            MemoryContextItem("database_context", context_bundle.database_context, priority=1),
            MemoryContextItem("reply_context", context_bundle.reply_context, priority=2),
            MemoryContextItem("chat_events", context_bundle.event_context, priority=3),
            MemoryContextItem("task_context", context_bundle.task_context_text, priority=4),
            MemoryContextItem("world_state", context_bundle.world_state_text, priority=5),
            MemoryContextItem("user_memory", context_bundle.user_memory_text, priority=6),
            MemoryContextItem("relation_memory", context_bundle.relation_memory_text, priority=7),
            MemoryContextItem("chat_memory", context_bundle.chat_memory_text, priority=8),
            MemoryContextItem("summary_memory", context_bundle.summary_memory_text, priority=9),
        ),
        max_items=4,
    )
    return tuple(item.layer for item in collected)


def derive_response_mode(outcome: str, route_decision: RouteDecision, execution_trace: Optional[ExecutionTrace] = None) -> str:
    enforced_mode, _violations = enforce_route_contract(route_decision, execution_trace)
    if enforced_mode == "insufficient":
        return "insufficient"
    if enforced_mode == "verified" and (outcome or "").strip().lower() == "ok":
        return "verified"
    normalized = (outcome or "").strip().lower()
    if normalized == "ok" and route_decision.request_kind != "chat":
        return "inferred"
    if normalized == "ok":
        return "verified"
    if normalized == "uncertain":
        return "inferred"
    return "insufficient"


def derive_confidence(
    report: SelfCheckReport,
    route_decision: RouteDecision,
    response_mode: str,
    execution_trace: Optional[ExecutionTrace] = None,
) -> float:
    if response_mode == "verified":
        base = 0.9 if route_decision.use_live or route_decision.use_workspace else 0.82
    elif response_mode == "inferred":
        base = 0.52
    else:
        base = 0.18
    if execution_trace is not None and execution_trace.contract_violations:
        base = min(base, 0.24)
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
    execution_trace: Optional[ExecutionTrace] = None,
    notes: str = "",
) -> SelfCheckReport:
    sources = [route_decision.source_label] if route_decision.source_label else []
    sources.extend(report.observed_basis)
    if execution_trace is not None:
        sources.extend(execution_trace.source_records)
    response_mode, enforcement_notes = enforce_route_contract(route_decision, execution_trace)
    normalized_outcome = (report.outcome or "").strip().lower()
    if response_mode == "verified" and normalized_outcome != "ok":
        response_mode = derive_response_mode(report.outcome, route_decision, execution_trace)
    elif response_mode not in {"verified", "inferred", "insufficient"}:
        response_mode = derive_response_mode(report.outcome, route_decision, execution_trace)
    evidence_notes = []
    if execution_trace is not None:
        if execution_trace.tools_attempted:
            evidence_notes.append(f"attempted={', '.join(execution_trace.tools_attempted)}")
        if execution_trace.contract_violations:
            evidence_notes.append(f"violations={', '.join(execution_trace.contract_violations)}")
    if enforcement_notes:
        evidence_notes.append(f"enforcement={', '.join(enforcement_notes)}")
    return SelfCheckReport(
        outcome=report.outcome,
        answer=report.answer,
        flags=report.flags,
        observed_basis=report.observed_basis,
        uncertain_points=report.uncertain_points,
        mode=response_mode,
        route=route_decision.route_kind,
        sources=tuple(dict.fromkeys(source for source in sources if source)),
        tools_used=derive_tools_used(route_decision, execution_trace),
        memory_used=derive_memory_used(context_bundle, route_decision, execution_trace),
        confidence=derive_confidence(report, route_decision, response_mode, execution_trace),
        freshness=derive_freshness(route_decision),
        notes="; ".join(part for part in (notes or route_decision.answer_contract, "; ".join(evidence_notes)) if part),
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
