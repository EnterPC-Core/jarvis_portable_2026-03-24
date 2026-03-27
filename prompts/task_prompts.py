from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple


def build_upgrade_request_prompt(task: str) -> str:
    cleaned_task = (task or "").strip()
    return (
        "Enterprise\n\n"
        "Задача:\n"
        f"{cleaned_task}\n\n"
        "Внеси изменение аккуратно и минимально. Сохрани рабочее состояние проекта."
    )


def build_grammar_fix_prompt(text: str) -> str:
    return (
        "Enterprise\n\n"
        "Исправь только орфографию, пунктуацию и явные грамматические ошибки. "
        "Не меняй смысл, стиль и структуру. Верни только итоговый текст.\n\n"
        f"Текст:\n{text}"
    )


def build_voice_cleanup_prompt(text: str, context_terms: str = "") -> str:
    terms_block = f"\nТермины: {context_terms}" if context_terms else ""
    return (
        "Enterprise\n\n"
        "Исправь только явные ошибки распознавания речи. "
        "Ничего не додумывай и не перефразируй. Верни только очищенную расшифровку."
        f"{terms_block}\n\n"
        f"Сырая расшифровка:\n{text}"
    )


def build_voice_transcription_prompt(source_path: Path, language: str, initial_prompt: str) -> str:
    hint_block = f"\nКонтекст: {initial_prompt}" if initial_prompt else ""
    return (
        "Enterprise\n\n"
        "Расшифруй голосовое сообщение и верни только текст без комментариев.\n"
        f"Файл: {source_path}\n"
        f"Язык: {language}"
        f"{hint_block}"
    )


def build_portrait_prompt(label: str, context: str) -> str:
    return (
        "Enterprise\n\n"
        "Сделай краткий поведенческий портрет участника по реальным сообщениям. "
        "Не выдумывай скрытые факты.\n\n"
        f"Участник: {label}\n\n"
        f"Данные:\n{context}"
    )


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
    events_block = "\n".join(lines)
    return (
        "Enterprise\n\n"
        "Собери компактную summary-memory сводку по чату: 4-7 коротких строк, только наблюдаемые факты.\n\n"
        f"chat_id={chat_id}\n\n"
        f"Текущая summary:\n{truncate_text_func(current_summary, 800) or 'пока нет'}\n\n"
        f"Facts:\n{facts_block}\n\n"
        f"Последние события:\n{events_block}"
    )


def build_ai_user_memory_prompt(
    profile_label: str,
    rows: List[Tuple[int, Optional[int], str, str, str, str, str]],
    heuristic_context: str,
    truncate_text_func: Callable[[str, int], str],
) -> str:
    lines: List[str] = []
    for created_at, _user_id, _username, _first_name, _last_name, message_type, content in rows[-14:]:
        stamp = datetime.fromtimestamp(created_at).strftime("%m-%d %H:%M") if created_at else "--:--"
        lines.append(f"[{stamp}] ({message_type}) {truncate_text_func(content, 220)}")
    messages_block = "\n".join(lines)
    return (
        "Enterprise\n\n"
        "Собери user-memory summary по участнику: 3-5 коротких предложений, только по реальным сообщениям.\n\n"
        f"Участник: {profile_label}\n\n"
        f"Текущий профиль:\n{truncate_text_func(heuristic_context, 700) or 'пока нет'}\n\n"
        f"Сообщения:\n{messages_block}"
    )
