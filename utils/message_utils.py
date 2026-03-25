from typing import Callable, List


def format_reaction_payload(reactions: List[dict]) -> str:
    parts: List[str] = []
    for reaction in reactions:
        if not isinstance(reaction, dict):
            continue
        if reaction.get("type") == "emoji" and reaction.get("emoji"):
            parts.append(str(reaction.get("emoji")))
            continue
        if reaction.get("type") == "custom_emoji" and reaction.get("custom_emoji_id"):
            parts.append(f"custom:{reaction.get('custom_emoji_id')}")
            continue
        if reaction.get("type") == "paid":
            parts.append("paid")
    return ", ".join(parts)


def build_service_actor_name(user: dict, build_actor_name_func: Callable[[object, str, str, str, str], str]) -> str:
    username = user.get("username") or ""
    first_name = user.get("first_name") or ""
    last_name = user.get("last_name") or ""
    user_id = user.get("id")
    return build_actor_name_func(user_id, username, first_name, last_name, "user")


def extract_forward_origin(message: dict, build_service_actor_name_func: Callable[[dict], str]) -> str:
    origin = message.get("forward_origin") or {}
    if not origin:
        return ""
    origin_type = origin.get("type") or ""
    if origin_type == "user":
        sender = origin.get("sender_user") or {}
        return build_service_actor_name_func(sender)
    if origin_type == "chat":
        sender_chat = origin.get("sender_chat") or {}
        title = sender_chat.get("title") or "chat"
        username = sender_chat.get("username") or ""
        return f"{title} @{username}".strip()
    if origin_type == "channel":
        chat = origin.get("chat") or {}
        title = chat.get("title") or "channel"
        username = chat.get("username") or ""
        author = origin.get("author_signature") or ""
        return " ".join(part for part in [title, f"@{username}" if username else "", author] if part).strip()
    if origin_type == "hidden_user":
        return origin.get("sender_user_name") or "hidden_user"
    return origin_type


def summarize_message_for_pin(message: dict, truncate_text_func: Callable[[str, int], str]) -> str:
    if message.get("text"):
        return truncate_text_func(message.get("text") or "", 140)
    if message.get("caption"):
        return truncate_text_func(message.get("caption") or "", 140)
    if message.get("photo"):
        return "фото"
    if message.get("voice"):
        return "голосовое"
    if message.get("video"):
        return "видео"
    if message.get("video_note"):
        return "кружок"
    if message.get("document"):
        return (message.get("document") or {}).get("file_name") or "документ"
    if message.get("sticker"):
        return "стикер"
    return "служебное сообщение"


def describe_message_media_kind(message: dict) -> str:
    if message.get("photo"):
        return "photo"
    if message.get("voice"):
        return "voice"
    if message.get("video"):
        return "video"
    if message.get("video_note"):
        return "video_note"
    if message.get("document"):
        document = message.get("document") or {}
        file_name = document.get("file_name") or "document"
        mime_type = document.get("mime_type") or ""
        return " ".join(part for part in [file_name, f"({mime_type})" if mime_type else ""] if part).strip()
    if message.get("sticker"):
        return "sticker"
    if message.get("animation"):
        return "gif"
    if message.get("audio"):
        return "audio"
    return ""


def format_reaction_count_payload(reactions: List[dict]) -> str:
    parts: List[str] = []
    for reaction in reactions:
        if not isinstance(reaction, dict):
            continue
        reaction_type = reaction.get("type") or {}
        count = reaction.get("total_count")
        if reaction_type.get("type") == "emoji" and reaction_type.get("emoji"):
            parts.append(f"{reaction_type.get('emoji')} x{count}")
            continue
        if reaction_type.get("type") == "custom_emoji" and reaction_type.get("custom_emoji_id"):
            parts.append(f"custom:{reaction_type.get('custom_emoji_id')} x{count}")
    return ", ".join(parts)
