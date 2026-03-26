from typing import Any, Callable, Optional


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
    build_external_research_context_func: Callable[[str], str],
    build_route_summary_text_func: Callable[[Any], str],
    build_guardrail_note_func: Callable[[Any], str],
    should_include_entity_context_func: Callable[..., bool],
) -> Any:
    web_context = build_external_research_context_func(user_text) if route_decision.use_web else ""
    event_context = state.get_event_context(chat_id, user_text, limit=40 if detect_local_chat_query_func(user_text) else 24) if route_decision.use_events else ""
    database_context = state.get_database_context(chat_id, user_text) if route_decision.use_database else ""
    reply_to = ((message or {}).get("reply_to_message") or {}).get("from") or {}
    include_entity_context = should_include_entity_context_func(
        persona=route_decision.persona,
        use_workspace=route_decision.use_workspace,
        query_text=user_text,
        is_owner_chat=is_owner_private_chat_func(user_id, chat_id),
        detect_local_chat_query_func=detect_local_chat_query_func,
    )
    return context_bundle_factory(
        summary_text=state.get_summary(chat_id),
        facts_text=state.render_facts(chat_id, query=user_text, limit=10),
        event_context=event_context,
        database_context=database_context,
        reply_context=reply_context,
        discussion_context=build_current_discussion_context_func(
            chat_id,
            message=message,
            user_id=user_id,
            active_group_followup=active_group_followup,
        ),
        self_model_text=state.get_self_model_context(route_decision.persona) if include_entity_context else "",
        autobiographical_text=state.get_autobiographical_context(chat_id, query=user_text, limit=4) if include_entity_context else "",
        skill_memory_text=state.get_skill_memory_context(user_text, route_kind=route_decision.route_kind, limit=3) if include_entity_context else "",
        world_state_text=state.get_world_state_context(limit=8) if include_entity_context else "",
        drive_state_text=state.get_drive_context() if include_entity_context else "",
        user_memory_text=state.get_user_memory_context(chat_id, user_id=user_id, reply_to_user_id=reply_to.get("id")),
        relation_memory_text=state.get_relation_memory_context(chat_id, user_id=user_id, reply_to_user_id=reply_to.get("id"), query=user_text),
        chat_memory_text=state.get_chat_memory_context(chat_id, query=user_text),
        summary_memory_text=state.get_summary_memory_context(chat_id, limit=3),
        web_context=web_context,
        route_summary=build_route_summary_text_func(route_decision),
        guardrail_note=build_guardrail_note_func(route_decision),
    )


def build_attachment_context_bundle(
    *,
    context_bundle_factory: Callable[..., Any],
    state: Any,
    chat_id: int,
    prompt_text: str,
    message: Optional[dict],
    reply_context: str,
    should_include_event_context_func: Callable[[str], bool],
    should_include_database_context_func: Callable[[str], bool],
) -> Any:
    from_user = (message or {}).get("from") or {}
    reply_to_user = (((message or {}).get("reply_to_message") or {}).get("from") or {})
    include_entity_context = bool(prompt_text)
    return context_bundle_factory(
        summary_text=state.get_summary(chat_id),
        facts_text=state.render_facts(chat_id, query=prompt_text, limit=10),
        event_context=state.get_event_context(chat_id, prompt_text) if should_include_event_context_func(prompt_text) else "",
        database_context=state.get_database_context(chat_id, prompt_text) if should_include_database_context_func(prompt_text) else "",
        reply_context=reply_context,
        self_model_text=state.get_self_model_context("jarvis") if include_entity_context else "",
        autobiographical_text=state.get_autobiographical_context(chat_id, query=prompt_text, limit=4) if include_entity_context else "",
        skill_memory_text=state.get_skill_memory_context(prompt_text, route_kind="codex_chat", limit=3) if include_entity_context else "",
        world_state_text=state.get_world_state_context(limit=8) if include_entity_context else "",
        drive_state_text=state.get_drive_context() if include_entity_context else "",
        user_memory_text=state.get_user_memory_context(chat_id, user_id=from_user.get("id"), reply_to_user_id=reply_to_user.get("id")),
        relation_memory_text=state.get_relation_memory_context(chat_id, user_id=from_user.get("id"), reply_to_user_id=reply_to_user.get("id"), query=prompt_text),
        chat_memory_text=state.get_chat_memory_context(chat_id, query=prompt_text),
        summary_memory_text=state.get_summary_memory_context(chat_id, limit=3),
    )
