from typing import Any, Callable, Optional

from models.contracts import MemoryContextItem
from services.context_bundle_utils import collect_memory_context_items, render_memory_trace


def build_text_context_bundle(
    *,
    context_bundle_factory: Callable[..., Any],
    state: Any,
    chat_id: int,
    user_text: str,
    route_decision: Any,
    user_id: Optional[int],
    message: Optional[dict],
    reply_context: str,
    active_group_followup: bool,
    detect_local_chat_query_func: Callable[[str], bool],
    should_include_database_context_func: Callable[[str], bool],
    is_owner_private_chat_func: Callable[[Optional[int], int], bool],
    build_current_discussion_context_func: Callable[..., str],
    build_route_summary_text_func: Callable[[Any], str],
    build_guardrail_note_func: Callable[[Any], str],
    should_include_entity_context_func: Callable[..., bool],
) -> Any:
    reply_to = ((message or {}).get("reply_to_message") or {}).get("from") or {}
    include_local_context = detect_local_chat_query_func(user_text)
    include_database_context = should_include_database_context_func(user_text)
    include_entity_context = should_include_entity_context_func(
        persona=route_decision.persona,
        use_workspace=route_decision.use_workspace,
        query_text=user_text,
        is_owner_chat=is_owner_private_chat_func(user_id, chat_id),
        detect_local_chat_query_func=detect_local_chat_query_func,
    )
    discussion_context = build_current_discussion_context_func(
        chat_id,
        message=message,
        user_id=user_id,
        active_group_followup=active_group_followup,
    )
    route_summary = build_route_summary_text_func(route_decision)
    guardrail_note = build_guardrail_note_func(route_decision)
    history_window = int(getattr(state, "history_limit", 0) or 0)
    history_rows = list(state.get_history(chat_id))
    continuity_note = ""
    if history_window > 0 and len(history_rows) >= history_window:
        continuity_note = (
            f"История диалога урезана до последних {history_window} сообщений. "
            "Для continuity опирайся на summary_memory/chat_memory и не утверждай, что помнишь более ранние детали дословно."
        )
        route_summary = f"{route_summary}\n{continuity_note}".strip() if route_summary else continuity_note
    event_context = state.get_event_context(chat_id, user_text) if include_local_context else ""
    database_context = state.get_database_context(chat_id, user_text) if include_database_context else ""
    world_state_text = state.get_world_state_context(limit=8) if include_entity_context else ""
    get_task_context_func = getattr(state, "get_task_context", None)
    task_context_text = (
        get_task_context_func(chat_id, limit=4)
        if (include_entity_context or route_decision.use_workspace) and callable(get_task_context_func)
        else ""
    )
    user_memory_text = state.get_user_memory_context(chat_id, user_id=user_id, reply_to_user_id=reply_to.get("id"))
    relation_memory_text = state.get_relation_memory_context(chat_id, user_id=user_id, reply_to_user_id=reply_to.get("id"), query=user_text)
    chat_memory_text = state.get_chat_memory_context(chat_id, query=user_text)
    summary_memory_text = state.get_summary_memory_context(chat_id, limit=3)
    request_kind = str(getattr(route_decision, "request_kind", "") or "")

    if request_kind == "runtime":
        chat_memory_text = ""
        summary_memory_text = ""
        user_memory_text = ""
        relation_memory_text = ""
    elif request_kind == "live":
        database_context = ""
        event_context = ""
        chat_memory_text = ""
        summary_memory_text = ""
    elif request_kind == "project" and not include_local_context:
        user_memory_text = ""
        relation_memory_text = ""
        summary_memory_text = ""

    memory_items = collect_memory_context_items(
        (
            MemoryContextItem("database_context", database_context, priority=1),
            MemoryContextItem("reply_context", reply_context, priority=2),
            MemoryContextItem("chat_events", event_context, priority=3),
            MemoryContextItem("task_context", task_context_text, priority=4),
            MemoryContextItem("world_state", world_state_text, priority=5),
            MemoryContextItem("user_memory", user_memory_text, priority=6),
            MemoryContextItem("relation_memory", relation_memory_text, priority=7),
            MemoryContextItem("chat_memory", chat_memory_text, priority=8),
            MemoryContextItem("summary_memory", summary_memory_text, priority=9),
        ),
        max_items=6,
    )

    return context_bundle_factory(
        summary_text=state.get_summary(chat_id),
        facts_text=state.render_facts(chat_id, query=user_text, limit=8),
        event_context=event_context,
        database_context=database_context,
        reply_context=reply_context,
        discussion_context=discussion_context,
        self_model_text=state.get_self_model_context(route_decision.persona) if include_entity_context else "",
        autobiographical_text=state.get_autobiographical_context(chat_id, query=user_text, limit=4) if include_entity_context else "",
        skill_memory_text=state.get_skill_memory_context(user_text, route_kind=route_decision.route_kind, limit=3) if include_entity_context else "",
        world_state_text=world_state_text,
        drive_state_text=state.get_drive_context() if include_entity_context else "",
        user_memory_text=user_memory_text,
        relation_memory_text=relation_memory_text,
        chat_memory_text=chat_memory_text,
        summary_memory_text=summary_memory_text,
        task_context_text=task_context_text,
        memory_trace_text=render_memory_trace(memory_items),
        web_context="",
        route_summary=route_summary,
        guardrail_note=guardrail_note,
    )


def build_attachment_context_bundle(
    *,
    context_bundle_factory: Callable[..., Any],
    state: Any,
    chat_id: int,
    prompt_text: str,
    persona: str,
    message: Optional[dict],
    reply_context: str,
    build_current_discussion_context_func: Callable[..., str],
    build_route_summary_text_func: Callable[[str], str],
    build_guardrail_note_func: Callable[[str], str],
    should_include_event_context_func: Callable[[str], bool],
    should_include_database_context_func: Callable[[str], bool],
) -> Any:
    from_user = (message or {}).get("from") or {}
    reply_to_user = (((message or {}).get("reply_to_message") or {}).get("from") or {})
    include_entity_context = bool(prompt_text)
    discussion_context = build_current_discussion_context_func(
        chat_id,
        message=message,
        user_id=from_user.get("id"),
        active_group_followup=False,
    )
    route_summary = build_route_summary_text_func(persona)
    guardrail_note = build_guardrail_note_func(persona)
    event_context = state.get_event_context(chat_id, prompt_text) if should_include_event_context_func(prompt_text) else ""
    database_context = state.get_database_context(chat_id, prompt_text) if should_include_database_context_func(prompt_text) else ""
    world_state_text = state.get_world_state_context(limit=8) if include_entity_context else ""
    get_task_context_func = getattr(state, "get_task_context", None)
    task_context_text = get_task_context_func(chat_id, limit=4) if include_entity_context and callable(get_task_context_func) else ""
    user_memory_text = state.get_user_memory_context(chat_id, user_id=from_user.get("id"), reply_to_user_id=reply_to_user.get("id"))
    relation_memory_text = state.get_relation_memory_context(chat_id, user_id=from_user.get("id"), reply_to_user_id=reply_to_user.get("id"), query=prompt_text)
    chat_memory_text = state.get_chat_memory_context(chat_id, query=prompt_text)
    summary_memory_text = state.get_summary_memory_context(chat_id, limit=3)
    memory_items = collect_memory_context_items(
        (
            MemoryContextItem("database_context", database_context, priority=1),
            MemoryContextItem("reply_context", reply_context, priority=2),
            MemoryContextItem("chat_events", event_context, priority=3),
            MemoryContextItem("task_context", task_context_text, priority=4),
            MemoryContextItem("world_state", world_state_text, priority=5),
            MemoryContextItem("user_memory", user_memory_text, priority=6),
            MemoryContextItem("relation_memory", relation_memory_text, priority=7),
            MemoryContextItem("chat_memory", chat_memory_text, priority=8),
            MemoryContextItem("summary_memory", summary_memory_text, priority=9),
        ),
        max_items=6,
    )
    return context_bundle_factory(
        summary_text=state.get_summary(chat_id),
        facts_text=state.render_facts(chat_id, query=prompt_text, limit=10),
        event_context=event_context,
        database_context=database_context,
        reply_context=reply_context,
        discussion_context=discussion_context,
        route_summary=route_summary,
        guardrail_note=guardrail_note,
        self_model_text=state.get_self_model_context(persona) if include_entity_context else "",
        autobiographical_text=state.get_autobiographical_context(chat_id, query=prompt_text, limit=4) if include_entity_context else "",
        skill_memory_text=state.get_skill_memory_context(prompt_text, route_kind="codex_chat", limit=3) if include_entity_context else "",
        world_state_text=world_state_text,
        drive_state_text=state.get_drive_context() if include_entity_context else "",
        user_memory_text=user_memory_text,
        relation_memory_text=relation_memory_text,
        chat_memory_text=chat_memory_text,
        summary_memory_text=summary_memory_text,
        task_context_text=task_context_text,
        memory_trace_text=render_memory_trace(memory_items),
    )
