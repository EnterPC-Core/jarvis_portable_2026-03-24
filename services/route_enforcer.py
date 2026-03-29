from __future__ import annotations

from typing import Optional, Sequence

from models.contracts import ContextBundle, ExecutionTrace, LiveProviderRecord, RouteDecision


def _nonempty_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _derive_memory_layers(context_bundle: Optional[ContextBundle]) -> tuple[str, ...]:
    if context_bundle is None:
        return ()
    mappings = (
        ("database_context", context_bundle.database_context),
        ("reply_context", context_bundle.reply_context),
        ("chat_events", context_bundle.event_context),
        ("discussion_context", context_bundle.discussion_context),
        ("task_context", context_bundle.task_context_text),
        ("world_state", context_bundle.world_state_text),
        ("self_model", context_bundle.self_model_text),
        ("autobiographical", context_bundle.autobiographical_text),
        ("skill_memory", context_bundle.skill_memory_text),
        ("drive_state", context_bundle.drive_state_text),
        ("user_memory", context_bundle.user_memory_text),
        ("relation_memory", context_bundle.relation_memory_text),
        ("chat_memory", context_bundle.chat_memory_text),
        ("summary_memory", context_bundle.summary_memory_text),
        ("web_context", context_bundle.web_context),
    )
    return _nonempty_unique(layer for layer, text in mappings if (text or "").strip())


def build_execution_trace(
    route_decision: RouteDecision,
    *,
    context_bundle: Optional[ContextBundle] = None,
    raw_answer: str = "",
    live_records: Sequence[LiveProviderRecord] = (),
    permission_checked: bool = False,
    direct_tools: Sequence[str] = (),
) -> ExecutionTrace:
    tools_attempted = list(route_decision.required_tools)
    tools_succeeded = list(direct_tools)
    source_kinds = []
    source_records = []
    memory_layers_read = _derive_memory_layers(context_bundle)
    if route_decision.use_workspace:
        tools_attempted.append("workspace_route")
        source_kinds.extend(("workspace", "project_files"))
        if (raw_answer or "").strip():
            tools_succeeded.append("workspace_route")
    if route_decision.request_kind == "runtime":
        tools_attempted.append("direct_runtime_probe")
        source_kinds.extend(("runtime_probe", "logs"))
    if route_decision.request_kind == "owner_admin":
        tools_attempted.append("owner_permission_check")
        source_kinds.append("owner_commands")
        if permission_checked:
            tools_succeeded.append("owner_permission_check")
    if route_decision.use_live:
        tools_attempted.append("live_route")
        source_kinds.append("live_provider")
        if live_records:
            tools_succeeded.append("live_route")
    if route_decision.use_web:
        tools_attempted.append("web_search_context")
        source_kinds.append("generic_web_search")
        if context_bundle is not None and (context_bundle.web_context or "").strip():
            tools_succeeded.append("web_search_context")
    if route_decision.request_kind == "chat_local_context":
        tools_attempted.append("local_chat_context")
        source_kinds.extend(("chat_events", "reply_context", "chat_memory", "summary_memory", "user_memory", "relation_memory"))
        if any(layer in memory_layers_read for layer in ("reply_context", "chat_events", "user_memory", "relation_memory", "chat_memory", "summary_memory")):
            tools_succeeded.append("local_chat_context")
    if route_decision.use_database:
        source_kinds.append("database_context")
    if route_decision.use_events:
        source_kinds.append("chat_events")
    if route_decision.use_reply:
        source_kinds.append("reply_context")
    source_records.extend(record.provider for record in live_records if record.provider)
    missing_required = [tool for tool in route_decision.required_tools if tool not in tools_succeeded]
    violations = [f"missing-required-tool:{tool}" for tool in missing_required]
    if route_decision.use_live and not live_records:
        violations.append("missing-live-evidence")
    if route_decision.use_web and context_bundle is not None and not (context_bundle.web_context or "").strip():
        violations.append("missing-web-context")
    forbidden_hits = [source for source in route_decision.forbidden_sources if source in source_kinds]
    violations.extend(f"forbidden-source:{source}" for source in forbidden_hits)
    return ExecutionTrace(
        tools_attempted=_nonempty_unique(tools_attempted),
        tools_succeeded=_nonempty_unique(tools_succeeded),
        memory_layers_read=memory_layers_read,
        source_kinds=_nonempty_unique(source_kinds),
        source_records=_nonempty_unique(source_records),
        contract_satisfied=not violations,
        contract_violations=tuple(violations),
    )


def enforce_route_contract(route_decision: RouteDecision, execution_trace: Optional[ExecutionTrace]) -> tuple[str, tuple[str, ...]]:
    if execution_trace is None:
        if route_decision.request_kind == "chat":
            return "inferred", ("missing-execution-trace",)
        if route_decision.required_tools or route_decision.use_live or route_decision.use_web or route_decision.use_workspace:
            return "insufficient", ("missing-execution-trace",)
        return "inferred", ("missing-execution-trace",)
    if execution_trace.contract_violations:
        return "insufficient", execution_trace.contract_violations
    if route_decision.route_kind == "live_current_fact":
        return "inferred", ("current-fact-snippets-not-direct-proof",)
    if route_decision.request_kind == "chat":
        return "inferred", ()
    if execution_trace.tools_succeeded:
        return "verified", ()
    return "inferred", ()
