from datetime import datetime
from typing import Callable, List, Optional, Set, Tuple


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
    mode_prompt = mode_prompts.get(mode, mode_prompts[default_mode_name])
    history_block = format_history(history, user_text, truncate_text_func, max_history_item_chars)
    intent = detect_intent_func(user_text)
    response_shape = response_shape_hint_func(intent)
    attachment_block = f"Attachment note:\n{attachment_note}\n\n" if attachment_note else ""
    summary_block = f"Chat summary:\n{truncate_text_func(summary_text, 1800)}\n\n" if summary_text else ""
    facts_block = f"Relevant facts:\n{truncate_text_func(facts_text, 1800)}\n\n" if facts_text else ""
    events_block = f"Relevant archived events:\n{truncate_text_func(event_context, 2600)}\n\n" if event_context and event_context != "История событий пуста." else ""
    database_block = f"Relevant database context:\n{truncate_text_func(database_context, 3200)}\n\n" if database_context else ""
    reply_block = f"Reply context:\n{truncate_text_func(reply_context, 2200)}\n\n" if reply_context else ""
    discussion_block = f"Current discussion context:\n{truncate_text_func(discussion_context, 9000)}\n\n" if discussion_context else ""
    persona_block = f"Persona note:\n{persona_note}\n\n" if persona_note else ""
    owner_block = f"Owner priority note:\n{owner_note}\n\n" if owner_note else ""
    web_block = f"Web context:\n{truncate_text_func(web_context, 3200)}\n\n" if web_context else ""
    route_block = f"Route summary:\n{truncate_text_func(route_summary, 1200)}\n\n" if route_summary else ""
    guardrail_block = f"Self-check and guardrails:\n{truncate_text_func(guardrail_note, 1600)}\n\n" if guardrail_note else ""
    self_model_block = f"Self model:\n{truncate_text_func(self_model_text, 2200)}\n\n" if self_model_text else ""
    autobiography_block = f"Autobiographical memory:\n{truncate_text_func(autobiographical_text, 2000)}\n\n" if autobiographical_text else ""
    skills_block = f"Skill memory:\n{truncate_text_func(skill_memory_text, 1800)}\n\n" if skill_memory_text else ""
    world_state_block = f"World state:\n{truncate_text_func(world_state_text, 1800)}\n\n" if world_state_text else ""
    drives_block = f"Drive pressures:\n{truncate_text_func(drive_state_text, 1600)}\n\n" if drive_state_text else ""
    user_memory_block = f"User memory:\n{truncate_text_func(user_memory_text, 1800)}\n\n" if user_memory_text else ""
    relation_memory_block = f"Relation memory:\n{truncate_text_func(relation_memory_text, 1800)}\n\n" if relation_memory_text else ""
    chat_memory_block = f"Chat memory:\n{truncate_text_func(chat_memory_text, 1800)}\n\n" if chat_memory_text else ""
    summary_memory_block = f"Summary memory:\n{truncate_text_func(summary_memory_text, 1800)}\n\n" if summary_memory_text else ""
    identity_block = ""
    if include_identity_prompt:
        identity_block = (
            "Identity:\n"
            f"Ты отвечаешь от лица {identity_label}. Не называй себя ботом и не описывай внутреннюю реализацию.\n\n"
        )
    return (
        f"System:\n{base_system_prompt}\n\n"
        f"{identity_block}"
        f"{persona_block}"
        f"{owner_block}"
        f"{route_block}"
        f"{guardrail_block}"
        f"{self_model_block}"
        f"{autobiography_block}"
        f"{skills_block}"
        f"{world_state_block}"
        f"{drives_block}"
        f"{user_memory_block}"
        f"{relation_memory_block}"
        f"{chat_memory_block}"
        f"{summary_memory_block}"
        f"Mode:\n{mode_prompt}\n\n"
        f"Intent:\n{intent}\n\n"
        f"Response shape:\n{response_shape}\n\n"
        f"{attachment_block}"
        f"{summary_block}"
        f"{facts_block}"
        f"{web_block}"
        f"{database_block}"
        f"{reply_block}"
        f"{discussion_block}"
        f"Relevant chat context:\n{history_block}\n\n"
        f"{events_block}"
        f"User message:\n{user_text}\n\n"
        "Сформируй финальный ответ пользователю."
    )


def build_portrait_prompt(label: str, context: str) -> str:
    return (
        "Ты делаешь краткий поведенческий портрет участника чата по его реальным сообщениям. "
        "Не выдумывай биографию, диагнозы, политические взгляды, психологические расстройства или скрытые факты. "
        "Опирайся только на наблюдаемую манеру общения, темы, тон, частотные интересы и роль в чате. "
        "Структура ответа: 1) краткий портрет, 2) стиль общения, 3) типичные темы, 4) что важно учитывать в диалоге с ним. "
        f"Участник: {label}\n\nДанные из чата:\n{context}"
    )


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


def build_ai_chat_memory_prompt(
    chat_id: int,
    rows: List[Tuple[int, Optional[int], str, str, str, str, str, str]],
    current_summary: str,
    facts: List[str],
    build_actor_name_func: Callable[[Optional[int], str, str, str, str], str],
    truncate_text_func: Callable[[str, int], str],
) -> str:
    lines: List[str] = []
    for created_at, user_id, username, first_name, last_name, role, message_type, content in rows[-32:]:
        stamp = datetime.fromtimestamp(created_at).strftime("%m-%d %H:%M") if created_at else "--:--"
        actor = build_actor_name_func(user_id, username or "", first_name or "", last_name or "", role)
        lines.append(f"[{stamp}] {actor} ({message_type}): {truncate_text_func(content, 220)}")
    facts_block = "\n".join(f"- {truncate_text_func(fact, 140)}" for fact in facts[:5]) or "- нет"
    return (
        "Сделай компактную summary-memory сводку по Telegram-чату на русском.\n"
        "Нужно 4-7 коротких строк, без воды.\n"
        "Только наблюдаемые факты: темы, активные участники, повторяющиеся мотивы, что важно помнить дальше.\n"
        "Не выдумывай скрытые мотивы, диагнозы или биографию.\n"
        "Если есть remembered facts, учитывай их как отдельный слой.\n\n"
        f"chat_id={chat_id}\n\n"
        f"Текущая rolling summary:\n{truncate_text_func(current_summary, 800) or 'пока нет'}\n\n"
        f"Remembered facts:\n{facts_block}\n\n"
        "Последние события:\n"
        + "\n".join(lines)
    )


def build_ai_user_memory_prompt(
    profile_label: str,
    rows: List[Tuple[int, Optional[int], str, str, str, str, str]],
    heuristic_context: str,
    truncate_text_func: Callable[[str, int], str],
) -> str:
    lines: List[str] = []
    for created_at, user_id, username, first_name, last_name, message_type, content in rows[-14:]:
        stamp = datetime.fromtimestamp(created_at).strftime("%m-%d %H:%M") if created_at else "--:--"
        lines.append(f"[{stamp}] ({message_type}) {truncate_text_func(content, 220)}")
    return (
        "Сделай user-memory summary по участнику чата на русском.\n"
        "Формат: 3-5 коротких предложений.\n"
        "Опирайся только на реальные сообщения.\n"
        "Нужно зафиксировать: стиль общения, типичные темы, полезные особенности для будущих ответов.\n"
        "Не придумывай личные факты, диагнозы, политику или скрытые намерения.\n\n"
        f"Участник: {profile_label}\n\n"
        f"Текущий эвристический профиль:\n{truncate_text_func(heuristic_context, 700) or 'пока нет'}\n\n"
        "Сообщения:\n"
        + "\n".join(lines)
    )
