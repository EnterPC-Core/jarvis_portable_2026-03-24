from requests.exceptions import RequestException


def handle_telegram_update(bridge: "TelegramBridge", item: dict) -> None:
    callback_query = item.get("callback_query")
    if callback_query:
        bridge.handle_callback_query(callback_query)
        return

    reaction_update = item.get("message_reaction") or item.get("message_reaction_count")
    if reaction_update:
        handle_reaction_update(bridge, reaction_update)
        return

    message = item.get("message") or item.get("edited_message")
    is_edited_message = item.get("edited_message") is not None
    if not message:
        return

    chat = message.get("chat") or {}
    from_user = message.get("from") or {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    user_id = from_user.get("id")
    chat_type = (chat.get("type") or "").lower()

    if chat_id is None:
        return

    if not is_edited_message and bridge.state.is_duplicate_message(chat_id, message_id):
        bridge.log(f"duplicate skipped chat={chat_id} message_id={message_id}")
        return

    if message.get("video"):
        bridge.log(f"video ignored chat={chat_id} user={user_id} message_id={message_id}")
        return

    if bridge.should_record_incoming_event(chat_id, user_id, message, chat_type):
        bridge.record_incoming_event(chat_id, user_id, message)
    if chat_type in {"group", "supergroup"} and message.get("photo") and user_id is not None and not (from_user.get("is_bot") or False):
        bridge.maybe_start_silent_photo_analysis(chat_id, user_id, message)
    bridge.maybe_refresh_chat_participants_snapshot(chat_id, chat_type)

    if message.get("new_chat_members"):
        bridge.handle_new_chat_members(chat_id, message)
        return

    raw_text = (message.get("text") or "").strip()
    if message.get("text") and bridge.maybe_handle_owner_moderation_override(chat_id, user_id, raw_text, message, chat_type):
        return
    if message.get("text") and bridge.maybe_apply_auto_moderation(chat_id, user_id, message, chat_type):
        return
    if not bridge.has_chat_access(bridge.state.authorized_user_ids, user_id):
        public_access_func = getattr(bridge, "has_public_command_access", None)
        guest_allowed = public_access_func(raw_text) if callable(public_access_func) else False
        if not guest_allowed and chat_type in {"group", "supergroup"} and message.get("text"):
            guest_allowed = (
                bridge.is_group_spontaneous_reply_candidate(chat_id, message, raw_text)
                or bridge.is_group_followup_message(chat_id, message, raw_text)
                or bridge.is_group_discussion_continuation(chat_id, message, raw_text)
            )
        if not guest_allowed:
            if chat_type == "private":
                bridge.log(f"blocked private non-owner user_id={user_id} chat_id={chat_id}")
            else:
                bridge.log(f"blocked user_id={user_id} chat_id={chat_id}")
            return
        message["_access_granted"] = True
    else:
        message["_access_granted"] = True

    try:
        if message.get("text"):
            bridge.handle_text_message(chat_id, user_id, message, chat_type)
            return
        if message.get("document"):
            bridge.handle_document_message(chat_id, user_id, message, chat_type)
            return
        if message.get("photo"):
            bridge.handle_photo_message(chat_id, user_id, message)
            return
        if message.get("voice"):
            return
        if message.get("animation"):
            return
        if any(message.get(key) for key in ["sticker", "document", "video", "video_note", "audio", "contact", "location", "new_chat_members", "left_chat_member", "pinned_message", "new_chat_title", "new_chat_photo"]):
            return
        bridge.safe_send_text(chat_id, bridge.UNSUPPORTED_FILE_REPLY)
    except RequestException as error:
        bridge.log(f"telegram error while handling message chat={chat_id}: {error}")
        bridge.safe_send_text(chat_id, "Не удалось обработать сообщение из-за ошибки Telegram API.")
    except Exception as error:
        bridge.log_exception(f"message handling error chat={chat_id}", error, limit=6)
        bridge.safe_send_text(chat_id, "Не удалось обработать сообщение. Попробуй еще раз.")


def handle_reaction_update(bridge: "TelegramBridge", reaction_update: dict) -> None:
    chat = reaction_update.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return

    actor = reaction_update.get("user") or {}
    actor_chat = reaction_update.get("actor_chat") or {}
    user_id = actor.get("id")
    username = actor.get("username") or ""
    first_name = actor.get("first_name") or actor_chat.get("title") or ""
    last_name = actor.get("last_name") or ""
    chat_type = (chat.get("type") or "")
    message_id = reaction_update.get("message_id")
    old_reactions = bridge.format_reaction_payload(reaction_update.get("old_reaction") or [])
    new_reactions = bridge.format_reaction_payload(reaction_update.get("new_reaction") or [])

    if not new_reactions and reaction_update.get("reactions") is not None:
        new_reactions = bridge.format_reaction_count_payload(reaction_update.get("reactions") or [])

    if not new_reactions and not old_reactions:
        return

    if new_reactions:
        content = f"[Реакция на message_id={message_id}: {new_reactions}]"
    else:
        content = f"[Реакция снята с message_id={message_id}: было {old_reactions}]"

    bridge.state.record_event(
        chat_id,
        user_id,
        "user",
        "reaction",
        content,
        message_id,
        username,
        first_name,
        last_name,
        chat_type,
    )
    if user_id is not None:
        try:
            new_count = len(reaction_update.get("new_reaction") or [])
            old_count = len(reaction_update.get("old_reaction") or [])
            reaction_delta = max(0, new_count - old_count)
            if reaction_delta == 0 and new_count == 0 and old_count == 0 and reaction_update.get("reactions") is not None:
                reaction_delta = max(len(reaction_update.get("reactions") or []), 0)
            if reaction_delta > 0:
                reaction_result = bridge.legacy.sync_reaction(int(chat_id), int(user_id), int(message_id or 0), reactions_added=reaction_delta)
                actor_unlocked = reaction_result.get("actor_unlocked") or []
                if actor_unlocked:
                    actor_unlocked = bridge._filter_new_achievement_announcements(int(chat_id), int(user_id), actor_unlocked)
                    display_name = (first_name or username or str(user_id)).strip()
                    announce_text = bridge.legacy.achievements.format_unlock_announcement(display_name, actor_unlocked)
                    if announce_text:
                        bridge.safe_send_text(int(chat_id), announce_text)
        except Exception as error:
            bridge.log_exception(f"legacy reaction sync failed chat={chat_id} user={user_id}", error, limit=6)
    bridge.log(f"incoming reaction chat={chat_id} user={user_id} message_id={message_id} value={bridge.shorten_for_log(content)}")


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
