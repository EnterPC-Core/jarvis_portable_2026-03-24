from typing import Callable, List, Set, Tuple

from prompts.profile_loader import load_runtime_profile, normalize_prompt_profile_name


def render_block(label: str, text: str, *, truncate_text_func: Callable[[str, int], str], limit: int) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    return f"{label}:\n{truncate_text_func(cleaned, limit)}\n\n"


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
        return "Предыдущего контекста нет."

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
        label = "Пользователь" if role == "user" else "Jarvis"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def format_enterprise_history(
    history: List[Tuple[str, str]],
    user_text: str,
    truncate_text_func: Callable[[str, int], str],
    max_history_item_chars: int,
) -> str:
    if not history:
        return "Предыдущего контекста нет."

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
        label = "Пользователь" if role == "user" else "Jarvis"
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
    del mode_prompts, base_system_prompt, detect_intent_func, response_shape_hint_func
    profile = load_runtime_profile(mode, default=default_mode_name)
    system_prefix = f"{profile.system_prompt}\n\n" if profile.system_prompt else ""
    if is_simple_greeting(user_text):
        return (
            f"{system_prefix}"
            f"Запрос:\n{user_text}\n\n"
            "Ответь естественно и коротко."
        )
    if profile.name == "enterprise":
        history_block = format_enterprise_history(history, user_text, truncate_text_func, max_history_item_chars)
        summary_block = render_block("Сводка", summary_text, truncate_text_func=truncate_text_func, limit=700)
        facts_block = render_block("Факты", facts_text, truncate_text_func=truncate_text_func, limit=900)
        web_block = render_block("Внешние данные", web_context, truncate_text_func=truncate_text_func, limit=1800)
        event_block = render_block("События", event_context, truncate_text_func=truncate_text_func, limit=1300)
        database_block = render_block("База", database_context, truncate_text_func=truncate_text_func, limit=1000)
        self_model_block = render_block("Состояние", self_model_text, truncate_text_func=truncate_text_func, limit=600)
        autobiographical_block = render_block("Автобиография", autobiographical_text, truncate_text_func=truncate_text_func, limit=700)
        skill_block = render_block("Навыки", skill_memory_text, truncate_text_func=truncate_text_func, limit=700)
        drive_block = render_block("Драйвы", drive_state_text, truncate_text_func=truncate_text_func, limit=500)
        user_memory_block = render_block("Профиль пользователя", user_memory_text, truncate_text_func=truncate_text_func, limit=320)
        reply_block = render_block("Ответ на сообщение", reply_context, truncate_text_func=truncate_text_func, limit=900)
        discussion_block = render_block("Текущая ветка", discussion_context, truncate_text_func=truncate_text_func, limit=1000)
        task_block = render_block("Непрерывность задачи", task_context_text, truncate_text_func=truncate_text_func, limit=1100)
        world_state_block = render_block("Состояние мира", world_state_text, truncate_text_func=truncate_text_func, limit=700)
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
            f"Контекст диалога:\n{history_block}\n\n"
            f"Запрос:\n{user_text}"
        )
    history_block = format_history(history, user_text, truncate_text_func, max_history_item_chars)
    attachment_block = render_block("Вложение", attachment_note, truncate_text_func=truncate_text_func, limit=1200)
    summary_block = render_block("Сводка", summary_text, truncate_text_func=truncate_text_func, limit=800)
    facts_block = render_block("Факты", facts_text, truncate_text_func=truncate_text_func, limit=1200)
    web_block = render_block("Внешние данные", web_context, truncate_text_func=truncate_text_func, limit=1600)
    event_block = render_block("События", event_context, truncate_text_func=truncate_text_func, limit=1600)
    database_block = render_block("База", database_context, truncate_text_func=truncate_text_func, limit=1200)
    reply_block = render_block("Ответ на сообщение", reply_context, truncate_text_func=truncate_text_func, limit=2200)
    discussion_block = render_block("Текущая ветка", discussion_context, truncate_text_func=truncate_text_func, limit=2600)
    self_model_block = render_block("Состояние", self_model_text, truncate_text_func=truncate_text_func, limit=500)
    autobiographical_block = render_block("Автобиография", autobiographical_text, truncate_text_func=truncate_text_func, limit=600)
    skill_block = render_block("Навыки", skill_memory_text, truncate_text_func=truncate_text_func, limit=700)
    world_state_block = render_block("Состояние мира", world_state_text, truncate_text_func=truncate_text_func, limit=700)
    drive_block = render_block("Драйвы", drive_state_text, truncate_text_func=truncate_text_func, limit=500)
    user_memory_block = render_block("Профиль пользователя", user_memory_text, truncate_text_func=truncate_text_func, limit=900)
    relation_memory_block = render_block("Связи", relation_memory_text, truncate_text_func=truncate_text_func, limit=1400)
    chat_memory_block = render_block("Память чата", chat_memory_text, truncate_text_func=truncate_text_func, limit=1800)
    summary_memory_block = render_block("Память сводок", summary_memory_text, truncate_text_func=truncate_text_func, limit=1000)
    task_block = render_block("Непрерывность задачи", task_context_text, truncate_text_func=truncate_text_func, limit=1200)
    memory_trace_block = f"{truncate_text_func(memory_trace_text, 500)}\n\n" if memory_trace_text else ""
    del identity_label, include_identity_prompt, persona_note, owner_note
    return (
        f"{system_prefix}"
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
        f"Контекст диалога:\n{history_block}\n\n"
        f"Запрос:\n{user_text}\n\n"
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
