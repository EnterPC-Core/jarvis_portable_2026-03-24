import re
from difflib import SequenceMatcher
from typing import Optional, Tuple


def extract_assistant_persona(text: str, normalize_whitespace_func) -> Tuple[str, str]:
    cleaned = normalize_whitespace_func(text)
    if not cleaned:
        return "", ""
    prefixes = [
        ("jarvis", "jarvis"),
        ("джарвис", "jarvis"),
        ("джервис", "jarvis"),
        ("enterprise", "enterprise"),
        ("энтерапрайз", "enterprise"),
        ("энтерпрайз", "enterprise"),
    ]

    def _match_persona(candidate: str) -> Tuple[str, str]:
        lowered = candidate.lower()
        for prefix, persona in prefixes:
            if lowered == prefix:
                return persona, ""
            if lowered.startswith(f"{prefix} "):
                return persona, candidate[len(prefix):].strip()
            if lowered.startswith(f"{prefix}:") or lowered.startswith(f"{prefix},") or lowered.startswith(f"{prefix}-") or lowered.startswith(f"{prefix}?") or lowered.startswith(f"{prefix}!"):
                return persona, candidate[len(prefix) + 1:].strip()
        return "", candidate

    persona, remainder = _match_persona(cleaned)
    if persona:
        return persona, remainder

    labeled_match = re.match(r"^[^:\n]{1,40}:\s*(.+)$", cleaned)
    if labeled_match:
        persona, remainder = _match_persona(labeled_match.group(1).strip())
        if persona:
            return persona, remainder
    return "", cleaned


def should_process_group_message(
    message: dict,
    text: str,
    bot_username: str,
    trigger_name: str,
    extract_assistant_persona_func,
    default_trigger_name: str,
    bot_user_id: Optional[int] = None,
    allow_owner_reply: bool = False,
) -> bool:
    del allow_owner_reply
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.startswith("/"):
        return True

    assistant_persona, _ = extract_assistant_persona_func(stripped)
    if assistant_persona:
        return True

    reply_to = message.get("reply_to_message") or {}
    reply_from = reply_to.get("from") or {}
    reply_username = (reply_from.get("username") or "").lower()
    reply_user_id = reply_from.get("id")
    if reply_from.get("is_bot") and ((bot_username and reply_username == bot_username) or (bot_user_id is not None and reply_user_id == bot_user_id)):
        return True

    lowered = stripped.lower()
    trigger = (trigger_name or default_trigger_name).lower()
    trigger_prefixes = (
        f"{trigger}:",
        f"{trigger},",
        f"{trigger} ",
        f"{trigger}?",
        f"{trigger}!",
        f"{trigger}.",
    )
    if trigger and (lowered == trigger or lowered.startswith(trigger_prefixes)):
        return True

    if bot_username and f"@{bot_username}" in lowered:
        return True
    return False


def contains_voice_trigger_name(text: str, trigger_name: str, bot_username: str, default_trigger_name: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False

    variants = {
        (trigger_name or default_trigger_name).strip().lower(),
        default_trigger_name.lower(),
        "джарвис",
        "джервис",
    }
    if bot_username:
        variants.add(bot_username.strip().lower())

    compact = re.sub(r"\s+", " ", lowered)
    for variant in variants:
        if not variant:
            continue
        pattern = rf"(?<![\w@]){re.escape(variant)}(?![\w@])"
        if re.search(pattern, compact, flags=re.IGNORECASE):
            return True
    tokens = re.findall(r"[a-zа-яё]+", compact, flags=re.IGNORECASE)
    for token in tokens:
        normalized = token.lower().replace("ё", "е")
        if len(normalized) < 4:
            continue
        if SequenceMatcher(None, normalized, "джарвис").ratio() >= 0.62:
            return True
        if SequenceMatcher(None, normalized, "jarvis").ratio() >= 0.72:
            return True
    return False


def normalize_incoming_text(text: str, bot_username: str) -> str:
    cleaned = (text or "").strip()
    if bot_username:
        cleaned = cleaned.replace(f"@{bot_username}", "")
        cleaned = cleaned.replace(f"@{bot_username.capitalize()}", "")
    return cleaned.strip(" ,:\n\t")
