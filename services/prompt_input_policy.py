from __future__ import annotations

from models.contracts import ContextBundle, RouteDecision


def select_prompt_inputs(route_decision: RouteDecision, context_bundle: ContextBundle) -> dict[str, str]:
    include_identity_memory = (
        bool(getattr(route_decision, "use_workspace", False))
        or str(getattr(route_decision, "request_kind", "") or "") in {"project", "owner_admin", "runtime"}
        or str(getattr(route_decision, "persona", "") or "") == "enterprise"
    )
    return {
        "summary_text": getattr(context_bundle, "summary_text", ""),
        "facts_text": getattr(context_bundle, "facts_text", ""),
        "event_context": getattr(context_bundle, "event_context", ""),
        "database_context": getattr(context_bundle, "database_context", ""),
        "reply_context": getattr(context_bundle, "reply_context", ""),
        "discussion_context": getattr(context_bundle, "discussion_context", ""),
        "web_context": getattr(context_bundle, "web_context", "") if bool(getattr(route_decision, "use_web", False)) else "",
        "route_summary": getattr(context_bundle, "route_summary", ""),
        "guardrail_note": getattr(context_bundle, "guardrail_note", ""),
        "self_model_text": getattr(context_bundle, "self_model_text", "") if include_identity_memory else "",
        "autobiographical_text": getattr(context_bundle, "autobiographical_text", "") if include_identity_memory else "",
        "skill_memory_text": getattr(context_bundle, "skill_memory_text", "") if include_identity_memory else "",
        "world_state_text": getattr(context_bundle, "world_state_text", "") if include_identity_memory else "",
        "drive_state_text": getattr(context_bundle, "drive_state_text", "") if include_identity_memory else "",
        "user_memory_text": getattr(context_bundle, "user_memory_text", ""),
        "relation_memory_text": getattr(context_bundle, "relation_memory_text", ""),
        "chat_memory_text": getattr(context_bundle, "chat_memory_text", ""),
        "summary_memory_text": getattr(context_bundle, "summary_memory_text", ""),
        "task_context_text": getattr(context_bundle, "task_context_text", ""),
        "memory_trace_text": getattr(context_bundle, "memory_trace_text", ""),
    }
