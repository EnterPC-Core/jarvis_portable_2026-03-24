from typing import Optional


class UIHandlers:
    def __init__(
        self,
        *,
        owner_user_id: int,
        access_denied_text: str,
        ui_pending_appeal: str,
        ui_pending_approve_comment: str,
        ui_pending_reject_comment: str,
        ui_pending_close_comment: str,
        admin_help_sections: set[str],
        public_help_sections: set[str],
        control_panel_sections: set[str],
    ) -> None:
        self.owner_user_id = owner_user_id
        self.access_denied_text = access_denied_text
        self.ui_pending_appeal = ui_pending_appeal
        self.ui_pending_approve_comment = ui_pending_approve_comment
        self.ui_pending_reject_comment = ui_pending_reject_comment
        self.ui_pending_close_comment = ui_pending_close_comment
        self.admin_help_sections = admin_help_sections
        self.public_help_sections = public_help_sections
        self.control_panel_sections = control_panel_sections

    def open_control_panel(self, bridge: "TelegramBridge", chat_id: int, user_id: int, section: str = "home", payload: str = "") -> None:
        text, markup = bridge.build_control_panel(user_id, section, payload)
        message_id = bridge.send_inline_message(chat_id, text, markup)
        if message_id is not None:
            bridge.state.set_ui_session(user_id, chat_id, int(message_id), section)

    def edit_control_panel(self, bridge: "TelegramBridge", chat_id: int, user_id: int, message_id: int, section: str = "home", payload: str = "") -> None:
        text, markup = bridge.build_control_panel(user_id, section, payload)
        try:
            bridge.edit_inline_message(chat_id, message_id, text, markup)
            bridge.state.set_ui_session(user_id, chat_id, message_id, section)
        except Exception as error:
            if bridge.is_message_not_modified_error(error):
                bridge.state.set_ui_session(user_id, chat_id, message_id, section)
                return
            if bridge.is_message_edit_recoverable_error(error):
                new_message_id = bridge.send_inline_message(chat_id, text, markup)
                if new_message_id is not None:
                    bridge.state.set_ui_session(user_id, chat_id, int(new_message_id), section)
                    return
            raise

    def handle_ui_pending_input(self, bridge: "TelegramBridge", chat_id: int, user_id: int, text: str) -> bool:
        session = bridge.state.get_ui_session(user_id)
        if not session:
            return False
        pending_action = session["pending_action"] or ""
        pending_payload = session["pending_payload"] or ""
        if not pending_action:
            return False
        if text.strip().lower() == "/cancel":
            bridge.state.clear_ui_pending(user_id)
            bridge.safe_send_text(chat_id, "Сценарий отменен.")
            return True
        if pending_action == self.ui_pending_appeal:
            bridge.state.clear_ui_pending(user_id)
            result = bridge.appeals.submit_appeal(user_id, chat_id, text)
            bridge.state.record_event(chat_id, user_id, "assistant", f"appeal_{result.get('status', 'unknown')}", text)
            bridge.safe_send_text(chat_id, str(result.get("message", "Апелляция обработана.")))
            if result.get("status") == "auto_approved":
                bridge.process_appeal_release_actions(
                    user_id,
                    result.get("release_actions", []),
                    "appeal_auto_release",
                    f"[appeal auto approved user_id={user_id}]",
                )
            elif result.get("status") == "new":
                snapshot = result.get("snapshot", {})
                bridge.notify_owner(
                    f"Новая апелляция #{result.get('appeal_id')}\n"
                    f"user_id={user_id}\n"
                    f"Причина: {text}\n"
                    f"Активные баны: {len(snapshot.get('active_bans', []))}\n"
                    f"Активные муты: {len(snapshot.get('active_mutes', []))}\n"
                    f"Подтвержденные нарушения: {snapshot.get('confirmed_violations', 0)}"
                )
            return True
        if pending_action in {self.ui_pending_approve_comment, self.ui_pending_reject_comment, self.ui_pending_close_comment} and pending_payload.isdigit():
            appeal_id = int(pending_payload)
            bridge.state.clear_ui_pending(user_id)
            if pending_action == self.ui_pending_close_comment:
                result = bridge.appeals.close_appeal(appeal_id, user_id, text)
                bridge.safe_send_text(chat_id, str(result.get("message", "Готово.")))
                return True
            approved = pending_action == self.ui_pending_approve_comment
            result = bridge.appeals.resolve_appeal(appeal_id, user_id, approved=approved, resolution=text)
            bridge.safe_send_text(chat_id, str(result.get("message", f"Статус: {result.get('status', 'unknown')}")))
            if result.get("ok"):
                target_user_id = int(result["user_id"])
                if approved:
                    bridge.process_appeal_release_actions(
                        target_user_id,
                        result.get("release_actions", []),
                        "appeal_manual_release",
                        f"[appeal approved #{appeal_id}]",
                    )
                    bridge.safe_send_text(target_user_id, f"Ваша апелляция #{appeal_id} одобрена.\n{text}")
                else:
                    bridge.safe_send_text(target_user_id, f"Ваша апелляция #{appeal_id} отклонена.\n{text}")
            return True
        return False

    def handle_callback_query(self, bridge: "TelegramBridge", callback_query: dict) -> None:
        callback_query_id = callback_query.get("id")
        data = (callback_query.get("data") or "").strip()
        message = callback_query.get("message") or {}
        chat_id = ((message.get("chat") or {}).get("id"))
        message_id = message.get("message_id")
        from_user = callback_query.get("from") or {}
        user_id = from_user.get("id")
        if callback_query_id:
            try:
                bridge.answer_callback_query(callback_query_id)
            except Exception as error:
                bridge.log(f"failed to answer callback query: {error}")
        if chat_id is None or message_id is None:
            return
        user_has_full_access = bridge.has_chat_access(bridge.state.authorized_user_ids, user_id)
        if user_id is not None and not user_has_full_access:
            if not bridge.has_public_callback_access(data):
                bridge.safe_send_text(chat_id, self.access_denied_text)
                return
        if data.startswith("ui:") and user_id is not None:
            parts = data.split(":")
            try:
                if data == "ui:home":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "home")
                    return
                if len(parts) == 3 and parts[1] == "panel":
                    target_section = parts[2].strip()
                    if target_section in self.control_panel_sections:
                        self.edit_control_panel(bridge, chat_id, user_id, int(message_id), target_section)
                        return
                if user_id == self.owner_user_id and len(parts) == 4 and parts[1] == "selfheal" and parts[2] == "view":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "owner_selfheal", parts[3])
                    return
                if user_id == self.owner_user_id and len(parts) == 4 and parts[1] == "selfheal" and parts[2] == "approve":
                    bridge.handle_self_heal_approve_command(chat_id, user_id, parts[3])
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "owner_selfheal", parts[3])
                    return
                if user_id == self.owner_user_id and len(parts) == 4 and parts[1] == "selfheal" and parts[2] == "deny":
                    bridge.handle_self_heal_deny_command(chat_id, user_id, parts[3])
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "owner_selfheal", parts[3])
                    return
                if data == "ui:profile":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "profile")
                    return
                if data == "ui:achievements":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "achievements")
                    return
                if data == "ui:top":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "top_menu")
                    return
                if len(parts) == 3 and parts[1] == "top":
                    mapping = {
                        "all": "top_all",
                        "history": "top_history",
                        "week": "top_week",
                        "day": "top_day",
                        "social": "top_social",
                        "season": "top_season",
                    }
                    section = mapping.get(parts[2], "top_menu")
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), section)
                    return
                if data == "ui:appeals":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "appeals")
                    return
                if data == "ui:appeal:history":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "appeal_history")
                    return
                if data == "ui:appeal:new":
                    bridge.state.set_ui_session(user_id, chat_id, int(message_id), "appeals", self.ui_pending_appeal)
                    bridge.edit_inline_message(
                        chat_id,
                        int(message_id),
                        "JARVIS • НОВАЯ АПЕЛЛЯЦИЯ\n\n"
                        "Следующим сообщением отправьте текст апелляции.\n"
                        "Проверка пройдет по базе: активные санкции, предупреждения, подтвержденные нарушения, история прошлых решений.\n\n"
                        "Если оснований нет, система снимет ограничение автоматически.",
                        {"inline_keyboard": [[{"text": "Назад", "callback_data": "ui:appeals"}]]},
                    )
                    return
                if user_id == self.owner_user_id and data == "ui:adm:queue":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "admin_appeals")
                    return
                if user_id == self.owner_user_id and data == "ui:adm:moderation":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "admin_moderation")
                    return
                if user_id == self.owner_user_id and len(parts) == 4 and parts[1] == "adm" and parts[2] == "view":
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "admin_appeal_detail", parts[3])
                    return
                if user_id == self.owner_user_id and len(parts) == 4 and parts[1] == "adm" and parts[2] == "review":
                    result = bridge.appeals.mark_in_review(int(parts[3]), user_id)
                    bridge.safe_send_text(chat_id, str(result.get("message", "Готово.")))
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "admin_appeal_detail", parts[3])
                    return
                if user_id == self.owner_user_id and len(parts) == 4 and parts[1] == "adm" and parts[2] in {"approve", "reject"}:
                    approved = parts[2] == "approve"
                    appeal_id = int(parts[3])
                    result = bridge.appeals.resolve_appeal(
                        appeal_id,
                        user_id,
                        approved=approved,
                        resolution="Одобрено модератором." if approved else "Отклонено модератором.",
                    )
                    bridge.safe_send_text(chat_id, str(result.get("message", "Готово.")))
                    if result.get("ok"):
                        target_user_id = int(result["user_id"])
                        if approved:
                            bridge.process_appeal_release_actions(
                                target_user_id,
                                result.get("release_actions", []),
                                "appeal_manual_release",
                                f"[appeal approved #{appeal_id}]",
                            )
                            bridge.safe_send_text(target_user_id, f"Ваша апелляция #{appeal_id} одобрена.")
                        else:
                            bridge.safe_send_text(target_user_id, f"Ваша апелляция #{appeal_id} отклонена.")
                    self.edit_control_panel(bridge, chat_id, user_id, int(message_id), "admin_appeals")
                    return
                if user_id == self.owner_user_id and len(parts) == 4 and parts[1] == "adm" and parts[2] in {"approvec", "rejectc", "closec"}:
                    pending_map = {
                        "approvec": self.ui_pending_approve_comment,
                        "rejectc": self.ui_pending_reject_comment,
                        "closec": self.ui_pending_close_comment,
                    }
                    bridge.state.set_ui_session(user_id, chat_id, int(message_id), "admin_appeal_detail", pending_map[parts[2]], parts[3])
                    bridge.edit_inline_message(
                        chat_id,
                        int(message_id),
                        f"JARVIS • КОММЕНТАРИЙ К АПЕЛЛЯЦИИ #{parts[3]}\n\n"
                        "Следующим сообщением отправьте комментарий модератора.",
                        {"inline_keyboard": [[{"text": "Назад", "callback_data": f"ui:adm:view:{parts[3]}"}]]},
                    )
                    return
            except Exception as error:
                if bridge.is_request_exception(error):
                    bridge.log(f"ui callback telegram error chat={chat_id} message_id={message_id}: {error}")
                    return
                bridge.log_exception(f"ui callback error chat={chat_id} message_id={message_id}", error, limit=8)
                bridge.safe_send_text(chat_id, "Не удалось обновить окно.")
                return
        if not data.startswith("help:") or user_id is None:
            return
        section = data.split(":", 1)[1].strip() or "main"
        if bridge.has_chat_access(bridge.state.authorized_user_ids, user_id):
            if section not in self.admin_help_sections:
                section = "main"
        else:
            if section not in self.public_help_sections:
                section = "public"
        try:
            bridge.edit_inline_message(
                chat_id,
                int(message_id),
                bridge.build_help_panel_text(section),
                bridge.build_help_panel_markup(section),
            )
        except Exception as error:
            if bridge.is_message_not_modified_error(error):
                return
            if bridge.is_message_edit_recoverable_error(error):
                bridge.send_inline_message(
                    chat_id,
                    bridge.build_help_panel_text(section),
                    bridge.build_help_panel_markup(section),
                )
                return
            bridge.log(f"failed to edit help panel chat={chat_id} message_id={message_id}: {error}")


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
