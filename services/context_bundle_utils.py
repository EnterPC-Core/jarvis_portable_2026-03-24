from typing import Any, Callable, Iterable, Tuple

from models.contracts import MemoryContextItem


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


def collect_memory_context_items(items: Iterable[MemoryContextItem], *, max_items: int = 6) -> Tuple[MemoryContextItem, ...]:
    seen_keys = set()
    normalized = []
    for item in sorted(items, key=lambda entry: (entry.priority, entry.layer)):
        text = (item.text or "").strip()
        if not text:
            continue
        dedupe_key = (item.layer.strip().lower(), text[:160].strip().lower())
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        normalized.append(item)
        if len(normalized) >= max(1, max_items):
            break
    return tuple(normalized)


def render_memory_trace(items: Iterable[MemoryContextItem]) -> str:
    collected = collect_memory_context_items(items, max_items=8)
    if not collected:
        return ""
    return "Memory trace: " + " -> ".join(
        f"{item.layer}" if not item.source else f"{item.layer}[{item.source}]"
        for item in collected
    )
