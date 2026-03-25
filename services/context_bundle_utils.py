from typing import Any, Callable


def should_include_entity_context(
    *,
    persona: str,
    use_workspace: bool,
    query_text: str,
    is_owner_chat: bool,
    detect_local_chat_query_func: Callable[[str], bool],
) -> bool:
    return (
        persona == "enterprise"
        or use_workspace
        or detect_local_chat_query_func(query_text)
        or is_owner_chat
    )


def build_context_bundle(context_bundle_factory: Callable[..., Any], **kwargs: str) -> Any:
    return context_bundle_factory(**kwargs)
