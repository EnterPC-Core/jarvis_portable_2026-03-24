import html
import re
from difflib import SequenceMatcher
from typing import Callable, Optional, Set, Tuple

from utils.chat_text import contains_voice_trigger_name as _contains_voice_trigger_name
from utils.chat_text import normalize_incoming_text as _normalize_incoming_text
from utils.chat_text import should_process_group_message as _should_process_group_message
from utils.help_utils import build_help_panel_markup as _build_help_panel_markup
from utils.help_utils import build_help_panel_text as _build_help_panel_text


PROFANITY_PATTERN = re.compile(
    r"(?:^|[^а-яёa-z0-9_])("
    r"ху(?:й|е|ё|и|я|ю|л|яц|ес)"
    r"|пизд"
    r"|еб(?:а|о|у|л|н|т|и|ё)"
    r"|ёб(?:а|о|у|л|н|т|и)"
    r"|бля(?:д|т)?"
    r"|наху"
    r"|уеб"
    r"|муд[ао]"
    r"|долбо[её]б"
    r")[\w-]*",
    re.IGNORECASE,
)


def can_owner_use_workspace_mode(user_id: Optional[int], chat_type: str, assistant_persona: str, *, owner_user_id: int) -> bool:
    return user_id == owner_user_id and chat_type in {"private", "group", "supergroup"} and assistant_persona == "enterprise"


def is_owner_private_chat(user_id: Optional[int], chat_id: int, *, owner_user_id: int) -> bool:
    return user_id == owner_user_id and chat_id > 0


def has_chat_access(_authorized_user_ids: Set[int], user_id: Optional[int], *, owner_user_id: int) -> bool:
    return user_id == owner_user_id


def has_public_command_access(text: str, *, allowed_commands: Set[str]) -> bool:
    return (text or "").strip() in allowed_commands


def has_public_callback_access(data: str, *, allowed_callbacks: Set[str]) -> bool:
    return (data or "").strip() in allowed_callbacks


def contains_profanity(text: str) -> bool:
    cleaned = (text or "").lower().replace("ё", "е")
    cleaned = re.sub(r"[^0-9a-zа-я_ -]+", " ", cleaned)
    return bool(PROFANITY_PATTERN.search(cleaned))


def should_attempt_owner_autofix(text: str, message: dict) -> bool:
    cleaned = (text or "").strip()
    if not cleaned or cleaned.startswith("/"):
        return False
    if message.get("edit_date"):
        return False
    if len(cleaned) < 4:
        return False
    lowered = cleaned.lower()
    if lowered.startswith("jarvis") or "@test_aipc_bot" in lowered:
        return False
    if "http://" in lowered or "https://" in lowered:
        return False
    return any(ch.isalpha() for ch in cleaned)


def build_help_panel_text(
    section: str,
    *,
    owner_username: str,
    owner_user_id: int,
    public_help_text: str,
    public_achievements_help_text: str,
    public_appeal_help_text: str,
) -> str:
    return _build_help_panel_text(
        section,
        owner_username=owner_username,
        owner_user_id=owner_user_id,
        public_help_text=public_help_text,
        public_achievements_help_text=public_achievements_help_text,
        public_appeal_help_text=public_appeal_help_text,
    )


def build_help_panel_markup(section: str) -> dict:
    return _build_help_panel_markup(section)


def build_welcome_text(template: str, user: dict, chat_title: str, *, default_template: str) -> str:
    first_name = (user.get("first_name") or "").strip()
    last_name = (user.get("last_name") or "").strip()
    username = (user.get("username") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip() or username or "друг"
    values = {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "username": f"@{username}" if username else "",
        "chat_title": chat_title or "",
    }
    try:
        return (template or default_template).format(**values).strip()
    except KeyError:
        return (template or default_template).strip()


def build_user_autofix_label(user: dict) -> str:
    first_name = (user.get("first_name") or "").strip()
    last_name = (user.get("last_name") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip() or "Пользователь"
    username = (user.get("username") or "").strip().lstrip("@")
    user_id = user.get("id")
    escaped_name = html.escape(full_name)
    if username:
        return f"{escaped_name} (@{html.escape(username)})"
    if user_id:
        return f'<a href="tg://user?id={int(user_id)}">{escaped_name}</a>'
    return escaped_name


def should_process_group_message(
    message: dict,
    text: str,
    bot_username: str,
    trigger_name: str,
    *,
    owner_user_id: int,
    owner_username: str,
    extract_assistant_persona_func: Callable[[str], Tuple[str, str]],
    default_trigger_name: str,
    bot_user_id: Optional[int] = None,
    allow_owner_reply: bool = False,
) -> bool:
    stripped = (text or "").strip()
    from_user = message.get("from") or {}
    user_id = from_user.get("id")
    owner_aliases = {"дмитрий", "дима", "dmitry", "dima"}
    normalized_owner_username = owner_username.strip().lstrip("@").lower()
    if normalized_owner_username:
        owner_aliases.add(normalized_owner_username)
    lowered = stripped.lower()
    owner_prefixes: Tuple[str, ...] = tuple(
        prefix
        for alias in owner_aliases
        for prefix in (f"{alias}:", f"{alias},", f"{alias} ", f"{alias}?", f"{alias}!", f"{alias}.")
    )
    if user_id == owner_user_id and lowered:
        if lowered in owner_aliases or lowered.startswith(owner_prefixes):
            return True
    return _should_process_group_message(
        message,
        text,
        bot_username,
        trigger_name,
        extract_assistant_persona_func,
        default_trigger_name,
        bot_user_id=bot_user_id,
        allow_owner_reply=allow_owner_reply,
    )


def contains_voice_trigger_name(text: str, trigger_name: str, bot_username: str, *, default_trigger_name: str) -> bool:
    return _contains_voice_trigger_name(text, trigger_name, bot_username, default_trigger_name)


def normalize_incoming_text(text: str, bot_username: str) -> str:
    return _normalize_incoming_text(text, bot_username)
