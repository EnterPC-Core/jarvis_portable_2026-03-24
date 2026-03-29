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


def format_enterprise_history(
    history: List[Tuple[str, str]],
    user_text: str,
    truncate_text_func: Callable[[str, int], str],
    max_history_item_chars: int,
) -> str:
    if not history:
        return "No prior context."

    lowered_query = (user_text or "").lower()
    heavy_markers = (
        "проект",
        "код",
        "ошиб",
        "исправ",
        "рефактор",
        "debug",
        "fix",
        "audit",
        "traceback",
        "stack",
        "лог",
        "repo",
        "git",
        "deploy",
        "runtime",
        "модерац",
        "памят",
        "архитект",
    )
    is_heavy_request = len(user_text or "") >= 140 or any(marker in lowered_query for marker in heavy_markers)
    expanded_limit = max(max_history_item_chars, 1600 if is_heavy_request else 700)
    keywords = extract_keywords(user_text)
    relevant: List[Tuple[str, str]] = []
    fallback: List[Tuple[str, str]] = history[-16:] if is_heavy_request else history[-6:]

    for role, content in history:
        shortened = truncate_text_func(content, expanded_limit)
        lowered = shortened.lower()
        if not keywords or any(keyword in lowered for keyword in keywords):
            relevant.append((role, shortened))

    selected = dedupe_history((relevant[-20:] if is_heavy_request else relevant[-8:]) + fallback)
    if not selected:
        selected = fallback

    lines: List[str] = []
    for role, content in selected[-24:] if is_heavy_request else selected[-10:]:
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
    task_context_text: str = "",
    memory_trace_text: str = "",
) -> str:
    del mode_prompts, base_system_prompt
    profile = load_runtime_profile(mode, default=default_mode_name)
    system_prefix = f"{profile.system_prompt}\n\n" if profile.system_prompt else ""
    intent = detect_intent_func(user_text)
    response_shape_hint = response_shape_hint_func(intent)
    if is_simple_greeting(user_text):
        return (
            f"{system_prefix}"
            f"User message:\n{user_text}\n\n"
            "Ответь естественно и коротко."
        )
    if profile.name == "enterprise":
        history_block = format_enterprise_history(history, user_text, truncate_text_func, max_history_item_chars)
        summary_block = f"Summary:\n{truncate_text_func(summary_text, 700)}\n\n" if summary_text else ""
        facts_block = f"Facts:\n{truncate_text_func(facts_text, 900)}\n\n" if facts_text else ""
        web_block = f"Web context:\n{truncate_text_func(web_context, 1800)}\n\n" if web_context else ""
        event_block = f"Event context:\n{truncate_text_func(event_context, 1300)}\n\n" if event_context else ""
        database_block = f"Database context:\n{truncate_text_func(database_context, 1000)}\n\n" if database_context else ""
        self_model_block = f"Self model:\n{truncate_text_func(self_model_text, 600)}\n\n" if self_model_text else ""
        autobiographical_block = f"Autobiographical memory:\n{truncate_text_func(autobiographical_text, 700)}\n\n" if autobiographical_text else ""
        skill_block = f"Skill memory:\n{truncate_text_func(skill_memory_text, 700)}\n\n" if skill_memory_text else ""
        drive_block = f"Drive state:\n{truncate_text_func(drive_state_text, 500)}\n\n" if drive_state_text else ""
        user_memory_block = f"User profile:\n{truncate_text_func(user_memory_text, 320)}\n\n" if user_memory_text else ""
        relation_memory_block = f"Relation memory:\n{truncate_text_func(relation_memory_text, 700)}\n\n" if relation_memory_text else ""
        chat_memory_block = f"Chat memory:\n{truncate_text_func(chat_memory_text, 800)}\n\n" if chat_memory_text else ""
        summary_memory_block = f"Summary memory:\n{truncate_text_func(summary_memory_text, 700)}\n\n" if summary_memory_text else ""
        reply_block = f"Reply context:\n{truncate_text_func(reply_context, 900)}\n\n" if reply_context else ""
        discussion_block = f"Discussion context:\n{truncate_text_func(discussion_context, 1000)}\n\n" if discussion_context else ""
        task_block = f"Task continuity:\n{truncate_text_func(task_context_text, 1100)}\n\n" if task_context_text else ""
        world_state_block = f"World state:\n{truncate_text_func(world_state_text, 700)}\n\n" if world_state_text else ""
        route_block = f"Route contract:\n{truncate_text_func(route_summary, 500)}\n\n" if route_summary else ""
        guardrail_block = f"Guardrails:\n{truncate_text_func(guardrail_note, 500)}\n\n" if guardrail_note else ""
        memory_trace_block = f"{truncate_text_func(memory_trace_text, 500)}\n\n" if memory_trace_text else ""
        del (
            attachment_note,
            summary_text,
            facts_text,
            event_context,
            database_context,
            identity_label,
            include_identity_prompt,
            persona_note,
            owner_note,
            task_context_text,
            memory_trace_text,
            truncate_text_func,
            max_history_item_chars,
        )
        return (
            f"{system_prefix}"
            f"Response contract:\n{response_shape_hint}\n\n"
            f"{route_block}"
            f"{guardrail_block}"
            f"{summary_block}"
            f"{facts_block}"
            f"{web_block}"
            f"{reply_block}"
            f"{event_block}"
            f"{database_block}"
            f"{discussion_block}"
            f"{self_model_block}"
            f"{autobiographical_block}"
            f"{skill_block}"
            f"{drive_block}"
            f"{task_block}"
            f"{world_state_block}"
            f"{memory_trace_block}"
            f"{user_memory_block}"
            f"{relation_memory_block}"
            f"{chat_memory_block}"
            f"{summary_memory_block}"
            f"Relevant chat context:\n{history_block}\n\n"
            f"User message:\n{user_text}"
        )
    history_block = format_history(history, user_text, truncate_text_func, max_history_item_chars)
    attachment_block = f"Attachment note:\n{attachment_note}\n\n" if attachment_note else ""
    summary_block = f"Summary:\n{truncate_text_func(summary_text, 800)}\n\n" if summary_text else ""
    facts_block = f"Facts:\n{truncate_text_func(facts_text, 1200)}\n\n" if facts_text else ""
    web_block = f"Web context:\n{truncate_text_func(web_context, 1600)}\n\n" if web_context else ""
    event_block = f"Event context:\n{truncate_text_func(event_context, 1600)}\n\n" if event_context else ""
    database_block = f"Database context:\n{truncate_text_func(database_context, 1200)}\n\n" if database_context else ""
    reply_block = f"Reply context:\n{truncate_text_func(reply_context, 2200)}\n\n" if reply_context else ""
    discussion_block = f"Discussion context:\n{truncate_text_func(discussion_context, 2600)}\n\n" if discussion_context else ""
    self_model_block = f"Self model:\n{truncate_text_func(self_model_text, 500)}\n\n" if self_model_text else ""
    autobiographical_block = f"Autobiographical memory:\n{truncate_text_func(autobiographical_text, 600)}\n\n" if autobiographical_text else ""
    skill_block = f"Skill memory:\n{truncate_text_func(skill_memory_text, 700)}\n\n" if skill_memory_text else ""
    world_state_block = f"World state:\n{truncate_text_func(world_state_text, 700)}\n\n" if world_state_text else ""
    drive_block = f"Drive state:\n{truncate_text_func(drive_state_text, 500)}\n\n" if drive_state_text else ""
    user_memory_block = f"User profile:\n{truncate_text_func(user_memory_text, 900)}\n\n" if user_memory_text else ""
    relation_memory_block = (
        f"Relation memory:\n{truncate_text_func(relation_memory_text, 1400)}\n\n" if relation_memory_text else ""
    )
    chat_memory_block = f"Chat memory:\n{truncate_text_func(chat_memory_text, 1800)}\n\n" if chat_memory_text else ""
    summary_memory_block = (
        f"Summary memory:\n{truncate_text_func(summary_memory_text, 1000)}\n\n" if summary_memory_text else ""
    )
    task_block = f"Task continuity:\n{truncate_text_func(task_context_text, 1200)}\n\n" if task_context_text else ""
    memory_trace_block = f"{truncate_text_func(memory_trace_text, 500)}\n\n" if memory_trace_text else ""
    route_block = f"Route contract:\n{truncate_text_func(route_summary, 500)}\n\n" if route_summary else ""
    guardrail_block = f"Guardrails:\n{truncate_text_func(guardrail_note, 500)}\n\n" if guardrail_note else ""
    del identity_label, include_identity_prompt, persona_note, owner_note
    return (
        f"{system_prefix}"
        f"Response contract:\n{response_shape_hint}\n\n"
        f"{route_block}"
        f"{guardrail_block}"
        f"{attachment_block}"
        f"{summary_block}"
        f"{facts_block}"
        f"{web_block}"
        f"{reply_block}"
        f"{event_block}"
        f"{database_block}"
        f"{discussion_block}"
        f"{self_model_block}"
        f"{autobiographical_block}"
        f"{skill_block}"
        f"{world_state_block}"
        f"{drive_block}"
        f"{task_block}"
        f"{memory_trace_block}"
        f"{user_memory_block}"
        f"{relation_memory_block}"
        f"{chat_memory_block}"
        f"{summary_memory_block}"
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
