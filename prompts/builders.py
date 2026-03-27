from typing import Callable, List, Set, Tuple

from prompts.profile_loader import load_runtime_profile, normalize_prompt_profile_name


def dedupe_history(items: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen: Set[Tuple[str, str]] = set()
    result: List[Tuple[str, str]] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def extract_keywords(text: str) -> Set[str]:
    words: List[str] = []
    for raw_word in text.lower().replace("\n", " ").split():
        word = "".join(ch for ch in raw_word if ch.isalnum() or ch in {"_", "-"})
        if len(word) >= 4:
            words.append(word)
    return set(words[:12])


def is_simple_greeting(text: str) -> bool:
    cleaned = " ".join((text or "").lower().strip().split())
    if not cleaned:
        return False
    greetings = {
        "привет",
        "здарова",
        "здравствуйте",
        "здравствуй",
        "добрый день",
        "доброе утро",
        "добрый вечер",
        "хай",
        "hello",
        "hi",
        "hey",
    }
    return cleaned in greetings


def format_history(
    history: List[Tuple[str, str]],
    user_text: str,
    truncate_text_func: Callable[[str, int], str],
    max_history_item_chars: int,
) -> str:
    if not history:
        return "No prior context."

    keywords = extract_keywords(user_text)
    relevant: List[Tuple[str, str]] = []
    fallback: List[Tuple[str, str]] = history[-6:]

    for role, content in history:
        shortened = truncate_text_func(content, max_history_item_chars)
        lowered = shortened.lower()
        if not keywords or any(keyword in lowered for keyword in keywords):
            relevant.append((role, shortened))

    selected = dedupe_history(relevant[-8:] + fallback)
    if not selected:
        selected = fallback

    lines: List[str] = []
    for role, content in selected[-10:]:
        label = "User" if role == "user" else "Jarvis"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def build_prompt(
    *,
    mode: str,
    history: List[Tuple[str, str]],
    user_text: str,
    mode_prompts: dict,
    default_mode_name: str,
    base_system_prompt: str,
    detect_intent_func: Callable[[str], str],
    response_shape_hint_func: Callable[[str], str],
    truncate_text_func: Callable[[str, int], str],
    max_history_item_chars: int,
    attachment_note: str = "",
    summary_text: str = "",
    facts_text: str = "",
    event_context: str = "",
    database_context: str = "",
    reply_context: str = "",
    discussion_context: str = "",
    identity_label: str = "Jarvis",
    include_identity_prompt: bool = True,
    persona_note: str = "",
    owner_note: str = "",
    web_context: str = "",
    route_summary: str = "",
    guardrail_note: str = "",
    self_model_text: str = "",
    autobiographical_text: str = "",
    skill_memory_text: str = "",
    world_state_text: str = "",
    drive_state_text: str = "",
    user_memory_text: str = "",
    relation_memory_text: str = "",
    chat_memory_text: str = "",
    summary_memory_text: str = "",
) -> str:
    del (
        mode_prompts,
        detect_intent_func,
        response_shape_hint_func,
        base_system_prompt,
    )
    profile = load_runtime_profile(mode, default=default_mode_name)
    system_prefix = f"{profile.system_prompt}\n\n" if profile.system_prompt else ""
    if is_simple_greeting(user_text):
        return (
            f"{system_prefix}"
            f"User message:\n{user_text}\n\n"
            "Ответь естественно и коротко."
        )
    if profile.name == "enterprise":
        history_block = format_history(history, user_text, truncate_text_func, max_history_item_chars)
        user_memory_block = f"User profile:\n{truncate_text_func(user_memory_text, 900)}\n\n" if user_memory_text else ""
        del (
            attachment_note,
            summary_text,
            facts_text,
            event_context,
            database_context,
            reply_context,
            discussion_context,
            identity_label,
            include_identity_prompt,
            persona_note,
            owner_note,
            web_context,
            route_summary,
            guardrail_note,
            self_model_text,
            autobiographical_text,
            skill_memory_text,
            world_state_text,
            drive_state_text,
            relation_memory_text,
            chat_memory_text,
            summary_memory_text,
            truncate_text_func,
            max_history_item_chars,
        )
        return (
            f"{system_prefix}"
            f"{user_memory_block}"
            f"Relevant chat context:\n{history_block}\n\n"
            f"User message:\n{user_text}"
        )
    history_block = format_history(history, user_text, truncate_text_func, max_history_item_chars)
    attachment_block = f"Attachment note:\n{attachment_note}\n\n" if attachment_note else ""
    reply_block = f"Reply context:\n{truncate_text_func(reply_context, 2200)}\n\n" if reply_context else ""
    user_memory_block = f"User profile:\n{truncate_text_func(user_memory_text, 900)}\n\n" if user_memory_text else ""
    del route_summary, guardrail_note
    del identity_label, include_identity_prompt, persona_note, owner_note
    return (
        f"{system_prefix}"
        f"{attachment_block}"
        f"{reply_block}"
        f"{user_memory_block}"
        f"Relevant chat context:\n{history_block}\n\n"
        f"User message:\n{user_text}\n\n"
        "Ответь пользователю."
    )


def resolve_prompt_profile_name(mode: str, default_mode_name: str) -> str:
    return normalize_prompt_profile_name(mode, default=default_mode_name)


def build_fts_query(text: str) -> str:
    words = []
    for raw_word in (text or "").lower().replace("\n", " ").split():
        word = "".join(ch for ch in raw_word if ch.isalnum() or ch in {"_", "-"})
        if len(word) >= 2:
            words.append(word)
    if not words:
        cleaned = (text or "").strip().lower()
        return f'"{cleaned}"' if cleaned else ""
    return " AND ".join(f'"{word}"' for word in words[:8])
