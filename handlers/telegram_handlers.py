from threading import Thread
from typing import Optional


class TelegramMessageHandlers:
    def __init__(self, *, owner_user_id: int, safe_mode_reply: str) -> None:
        self.owner_user_id = owner_user_id
        self.safe_mode_reply = safe_mode_reply

    def handle_text_message(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], message: dict, chat_type: str = "private") -> None:
        raw_text = (message.get("text") or "").strip()
        text = bridge.normalize_incoming_text(raw_text, bridge.bot_username)
        assistant_persona, text = bridge.extract_assistant_persona(text)
        if assistant_persona and not text:
            text = raw_text
        if chat_type == "private" and user_id == self.owner_user_id:
            assistant_persona = "enterprise"
        spontaneous_group_reply = False
        active_group_followup = False
        active_group_discussion = False
        direct_group_help_request = False
        bridge.log(f"incoming text chat={chat_id} type={chat_type} user={user_id} text={bridge.shorten_for_log(raw_text)}")

        if chat_type in {"group", "supergroup"} and user_id != self.owner_user_id:
            bridge.log(
                f"group non-owner ignored chat={chat_id} user={user_id} "
                f"text={bridge.shorten_for_log(raw_text)}"
            )
            return

        if (
            chat_type == "private"
            and user_id is not None
            and user_id != self.owner_user_id
            and bridge.contains_profanity(raw_text)
        ):
            bridge.enforce_private_profanity_global_ban(chat_id, user_id, raw_text, message)
            return

        if chat_type in {"group", "supergroup"}:
            if user_id != self.owner_user_id and bridge.is_group_discussion_rate_limited(chat_id, user_id):
                bridge.log(f"group discussion rate-limited chat={chat_id} user={user_id} text={bridge.shorten_for_log(raw_text)}")
                return
            active_group_followup = bridge.is_group_followup_message(chat_id, message, raw_text)
            active_group_discussion = bridge.is_group_discussion_continuation(chat_id, message, raw_text)
            should_handle_as_bot = bridge.should_process_group_message(message, raw_text)
            if (
                user_id == self.owner_user_id
                and assistant_persona not in {"enterprise", "jarvis"}
                and not raw_text.startswith("/")
                and not active_group_followup
                and not active_group_discussion
                and not should_handle_as_bot
            ):
                bridge.log(
                    f"owner group message without explicit persona ignored chat={chat_id} user={user_id} "
                    f"text={bridge.shorten_for_log(raw_text)}"
                )
                return
            participant_priority = bridge.get_group_participant_priority(chat_id, message)
            meaningful_group_request = bridge.is_meaningful_group_request(message, raw_text)
            ambient_group_chatter = bridge.is_ambient_group_chatter(message, raw_text)
            if ambient_group_chatter and not active_group_followup and not active_group_discussion and user_id != self.owner_user_id:
                return
            if (
                should_handle_as_bot
                and user_id is not None
                and user_id != self.owner_user_id
                and not bridge.has_chat_access(bridge.state.authorized_user_ids, user_id)
                and bridge.is_group_spontaneous_reply_candidate(chat_id, message, raw_text)
                and meaningful_group_request
            ):
                direct_group_help_request = True
                assistant_persona = assistant_persona or "jarvis"
            elif should_handle_as_bot and user_id is not None and user_id != self.owner_user_id and not meaningful_group_request and not active_group_followup and not active_group_discussion:
                bridge.log(
                    f"group direct trigger suppressed chat={chat_id} user={user_id} "
                    f"priority={participant_priority} text={bridge.shorten_for_log(raw_text)}"
                )
                return
            if not should_handle_as_bot and not active_group_followup and not active_group_discussion:
                if bridge.should_consider_group_spontaneous_reply(chat_id, message, raw_text):
                    bridge.log(
                        f"group spontaneous reply accepted chat={chat_id} user={user_id} "
                        f"message_id={message.get('message_id')} score={bridge.compute_group_spontaneous_reply_score(raw_text)} "
                        f"priority={participant_priority}"
                    )
                    assistant_persona = assistant_persona or "jarvis"
                    spontaneous_group_reply = True
                else:
                    if bridge.owner_autofix_enabled() and bridge.should_attempt_owner_autofix(raw_text, message):
                        author_label = bridge.build_user_autofix_label(message.get("from") or {})
                        worker = Thread(
                            target=bridge.run_owner_autofix_task,
                            args=(chat_id, message.get("message_id"), raw_text, author_label),
                            daemon=True,
                        )
                        worker.start()
                    return
            elif direct_group_help_request:
                bridge.log(
                    f"group direct help reply accepted chat={chat_id} user={user_id} "
                    f"message_id={message.get('message_id')} score={bridge.compute_group_spontaneous_reply_score(raw_text)} "
                    f"priority={participant_priority}"
                )
                spontaneous_group_reply = True
            elif active_group_discussion:
                assistant_persona = assistant_persona or "jarvis"

        if not text:
            bridge.safe_send_text(chat_id, "Нужен текстовый запрос.")
            return

        if chat_type == "private" and user_id is not None and not raw_text.startswith("/"):
            if bridge.handle_owner_console_session_input(chat_id, user_id, raw_text):
                return
            if bridge.handle_ui_pending_input(chat_id, user_id, raw_text):
                return

        if bridge.handle_command(chat_id, user_id, text, message, allow_followup_text=(spontaneous_group_reply or active_group_followup or active_group_discussion)):
            return

        if bridge.config.safe_chat_only and bridge.is_dangerous_request(text) and not bridge.can_owner_use_workspace_mode(user_id, chat_type, assistant_persona):
            bridge.safe_send_text(chat_id, self.safe_mode_reply)
            return

        if not bridge.state.try_start_chat_task(chat_id):
            bridge.log(f"chat task busy chat={chat_id} type={chat_type} user={user_id} text={bridge.shorten_for_log(raw_text)}")
            bridge.safe_send_text(chat_id, "Предыдущий запрос ещё обрабатывается.")
            return

        if chat_type in {"group", "supergroup"} and user_id != self.owner_user_id:
            if not bridge.record_group_discussion_turn(chat_id, user_id):
                bridge.state.finish_chat_task(chat_id)
                bridge.log(f"group discussion turn blocked chat={chat_id} user={user_id} text={bridge.shorten_for_log(raw_text)}")
                return

        bridge.send_chat_action(chat_id, "typing")
        worker = Thread(
            target=bridge.run_text_task,
            args=(chat_id, text, user_id, chat_type, assistant_persona, message, spontaneous_group_reply),
            daemon=True,
        )
        worker.start()

    def handle_photo_message(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], message: dict) -> None:
        photos = message.get("photo") or []
        caption = (message.get("caption") or "").strip()
        bridge.log(f"incoming photo chat={chat_id} user={user_id} caption={bridge.shorten_for_log(caption)}")
        chat = message.get("chat") or {}
        chat_type = (chat.get("type") or "private").lower()

        if chat_type in {"group", "supergroup"} and user_id != self.owner_user_id:
            bridge.log(f"group non-owner photo ignored chat={chat_id} user={user_id}")
            return

        if not photos:
            bridge.safe_send_text(chat_id, "Изображение не удалось прочитать.")
            return

        best_photo = max(photos, key=lambda item: item.get("file_size", 0))
        file_id = best_photo.get("file_id")
        if not file_id:
            bridge.safe_send_text(chat_id, "Не удалось получить файл изображения.")
            return

        if not bridge.state.try_start_chat_task(chat_id):
            bridge.safe_send_text(chat_id, "Предыдущий запрос ещё обрабатывается.")
            return

        bridge.safe_send_status(chat_id, "Анализирую изображение...")
        worker = Thread(
            target=bridge.run_photo_task,
            args=(chat_id, file_id, caption, message),
            daemon=True,
        )
        worker.start()

    def handle_document_message(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], message: dict, chat_type: str) -> None:
        document = message.get("document") or {}
        file_id = document.get("file_id")
        caption = (message.get("caption") or "").strip()
        file_name = document.get("file_name") or "document"
        bridge.log(f"incoming document chat={chat_id} user={user_id} file={bridge.shorten_for_log(file_name)} caption={bridge.shorten_for_log(caption)}")

        if chat_type in {"group", "supergroup"} and user_id != self.owner_user_id:
            bridge.log(f"group non-owner document ignored chat={chat_id} user={user_id} file={bridge.shorten_for_log(file_name)}")
            return

        if not file_id:
            bridge.safe_send_text(chat_id, "Не удалось получить файл документа.")
            return

        save_target = bridge.parse_sd_save_command(caption)
        if save_target is not None:
            if not bridge.is_owner_private_chat(user_id, chat_id):
                bridge.safe_send_text(chat_id, "Команда доступна только владельцу в личном чате.")
                return
            bridge.handle_sd_save_command(chat_id, user_id, save_target, message)
            return
        if chat_type in {"group", "supergroup"}:
            should_handle_as_bot = bridge.should_process_group_message(message, caption or file_name)
            if not should_handle_as_bot:
                return
        if not bridge.state.try_start_chat_task(chat_id):
            bridge.safe_send_text(chat_id, "Предыдущий запрос ещё обрабатывается.")
            return
        bridge.safe_send_status(chat_id, "Смотрю файл...")
        worker = Thread(
            target=bridge.run_document_task,
            args=(chat_id, file_id, document, caption, message),
            daemon=True,
        )
        worker.start()

    def handle_voice_message(self, bridge: "TelegramBridge", chat_id: int, user_id: Optional[int], message: dict) -> None:
        try:
            voice = message.get("voice") or {}
            file_id = voice.get("file_id")
            duration = voice.get("duration")
            chat = message.get("chat") or {}
            chat_type = (chat.get("type") or "private").lower()
            bridge.log(f"incoming voice chat={chat_id} user={user_id} duration={duration}")

            if chat_type in {"group", "supergroup"} and user_id != self.owner_user_id:
                bridge.log(f"group non-owner voice ignored chat={chat_id} user={user_id}")
                return

            if not file_id:
                bridge.safe_send_text(chat_id, "Не удалось получить голосовое сообщение.")
                return

            if chat_type in {"group", "supergroup"}:
                if not bridge.should_process_group_message(message, "") and user_id != self.owner_user_id:
                    bridge.log(f"voice trigger not found chat={chat_id} file_id={file_id}")
                    return

            if not bridge.state.try_start_chat_task(chat_id):
                bridge.safe_send_text(chat_id, "Предыдущий запрос ещё обрабатывается.")
                return

            worker = Thread(
                target=bridge.run_voice_task,
                args=(chat_id, user_id, file_id, message),
                daemon=True,
            )
            worker.start()
        except Exception as error:
            bridge.log_exception(f"voice handler failed chat={chat_id}", error, limit=8)
            bridge.safe_send_text(chat_id, "Ошибка при обработке голосового. Детали записаны в лог.")

    def build_voice_initial_prompt(self, bridge: "TelegramBridge", chat_id: int, strict_trigger: bool = False) -> str:
        terms = bridge.state.get_voice_prompt_terms(chat_id, limit=28)
        joined_terms = ", ".join(terms[:28])
        if strict_trigger:
            return (
                "Это русское голосовое сообщение для Telegram-чата. "
                "Распознавай слова и имена максимально точно. "
                "Особенно важно корректно распознавать имя Джарвис. "
                f"Возможные слова и имена: {joined_terms}."
            )
        return (
            "Это русское голосовое сообщение для Telegram-чата. "
            "Сохраняй имена, названия и термины без искажений. "
            f"Возможные слова и имена: {joined_terms}."
        )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
