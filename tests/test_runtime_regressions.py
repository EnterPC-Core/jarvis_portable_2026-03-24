import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from handlers.telegram_handlers import TelegramMessageHandlers
from handlers.ui_handlers import UIHandlers
from handlers.command_dispatch import CommandDispatcher
from handlers.control_panel_renderer import ControlPanelRenderer
from enterprise_worker import extract_json_answer, get_worker_protected_paths, protect_prompt
from enterprise_server import PROTECTED_SERVER_CORE_PATHS
from services.js_enterprise_service import JSEnterpriseService, JSEnterpriseServiceDeps
from services.text_route_service import TextRouteService, TextRouteServiceDeps
from services.context_assembly import build_attachment_context_bundle, build_text_context_bundle
from tg_codex_bridge import (
    BridgeState,
    OWNER_USER_ID,
    TelegramBridge,
    has_public_callback_access,
    has_public_command_access,
    is_explicit_runtime_restart_request,
)
from utils.ops_utils import inspect_runtime_log
from utils.report_utils import render_bridge_runtime_watch


class _FakeState:
    history_limit = 2

    def get_history(self, _chat_id):
        return [("user", "one"), ("assistant", "two")]

    def get_summary(self, _chat_id):
        return "summary"

    def render_facts(self, _chat_id, query, limit):
        del query, limit
        return "facts"

    def get_event_context(self, _chat_id, _user_text):
        return "events"

    def get_database_context(self, _chat_id, _user_text):
        return "database"

    def get_self_model_context(self, _persona):
        return "self-model"

    def get_autobiographical_context(self, _chat_id, query, limit):
        del query, limit
        return "autobio"

    def get_skill_memory_context(self, _user_text, route_kind, limit):
        del route_kind, limit
        return "skills"

    def get_world_state_context(self, limit):
        del limit
        return "world"

    def get_drive_context(self):
        return "drives"

    def get_user_memory_context(self, _chat_id, user_id=None, reply_to_user_id=None):
        del user_id, reply_to_user_id
        return "user-memory"

    def get_relation_memory_context(self, _chat_id, user_id=None, reply_to_user_id=None, query=""):
        del user_id, reply_to_user_id, query
        return "relation-memory"

    def get_chat_memory_context(self, _chat_id, query=""):
        del query
        return "chat-memory"

    def get_summary_memory_context(self, _chat_id, limit=0):
        del limit
        return "summary-memory"


class RuntimeRegressionTests(unittest.TestCase):
    def test_runtime_log_treats_status_edit_429_as_warning_not_severe(self):
        with TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "tg_codex_bridge.log"
            log_path.write_text(
                "\n".join(
                    [
                        "[2026-03-27 17:39:40] bot started",
                        "[2026-03-27 17:39:48] instance lock conflict lock_path=/tmp/tg_codex_bridge.lock: Another tg_codex_bridge.py instance is already running.",
                        "[2026-03-27 17:39:52] failed to edit status message chat=-1003879607896 message_id=13023: telegram http 429: Too Many Requests: retry after 15",
                    ]
                ),
                encoding="utf-8",
            )

            snapshot = inspect_runtime_log(log_path)

        self.assertEqual(snapshot["lock_conflict_count"], 1)
        self.assertEqual(snapshot["warning_count"], 1)
        self.assertEqual(snapshot["session_warning_count"], 1)
        self.assertEqual(snapshot["severe_error_count"], 0)
        self.assertEqual(snapshot["session_severe_error_count"], 0)
        self.assertEqual(len(snapshot["recent_session_warning_lines"]), 1)
        self.assertIn("failed to edit status message", snapshot["recent_session_warning_lines"][0])

    def test_runtime_watch_renders_lock_conflicts(self):
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            heartbeat_path = root / "tg_codex_bridge.heartbeat"
            bridge_log_path = root / "tg_codex_bridge.log"
            supervisor_log_path = root / "supervisor_boot.log"
            heartbeat_path.write_text("", encoding="utf-8")
            bridge_log_path.write_text("[2026-03-27 17:39:52] failed to edit status message chat=1 message_id=2: telegram http 429: Too Many Requests: retry after 15\n", encoding="utf-8")
            supervisor_log_path.write_text("[2026-03-27 17:39:47] bridge pid=18004 exited status=75 due to lock conflict; stopping supervisor to avoid restart loop\n", encoding="utf-8")

            report = render_bridge_runtime_watch(
                psutil_module=None,
                format_bytes_func=lambda value: f"{value}B",
                truncate_text_func=lambda text, _limit: text,
                heartbeat_path=heartbeat_path,
                bridge_log_path=bridge_log_path,
                supervisor_log_path=supervisor_log_path,
                runtime_log_snapshot={
                    "restart_count": 1,
                    "session_restart_count": 0,
                    "lock_conflict_count": 3,
                    "heartbeat_kill_count": 0,
                    "termination_signal_count": 0,
                    "severe_error_count": 0,
                    "session_severe_error_count": 0,
                    "warning_count": 1,
                    "session_warning_count": 1,
                    "codex_degraded_count": 0,
                    "codex_error_count": 0,
                    "network_error_count": 0,
                    "last_restart_line": "",
                    "recent_session_error_lines": [],
                    "recent_error_lines": [],
                    "recent_session_warning_lines": [],
                    "recent_warning_lines": [],
                },
            )

        self.assertIn("Lock conflicts за 24ч: 3", report)

    def test_public_access_lists_keep_rating_and_appeal_entry_points(self):
        self.assertTrue(has_public_command_access("/start"))
        self.assertTrue(has_public_command_access("/rating"))
        self.assertTrue(has_public_command_access("/top"))
        self.assertTrue(has_public_command_access("/appeals"))
        self.assertTrue(has_public_command_access("/appeal прошу пересмотреть"))
        self.assertTrue(has_public_callback_access("ui:home"))
        self.assertTrue(has_public_callback_access("ui:top:week"))
        self.assertTrue(has_public_callback_access("ui:appeals"))
        self.assertFalse(has_public_command_access("/help"))
        self.assertFalse(has_public_callback_access("help:public"))

    def test_group_non_owner_text_is_silently_ignored(self):
        sent_messages = []
        logs = []
        handler = TelegramMessageHandlers(owner_user_id=1, safe_mode_reply="safe")
        bridge = SimpleNamespace(
            normalize_incoming_text=lambda text, _bot_username: text,
            extract_assistant_persona=lambda text: ("jarvis", text),
            bot_username="jarvis_bot",
            log=lambda message: logs.append(message),
            shorten_for_log=lambda text: text,
            safe_send_text=lambda chat_id, text: sent_messages.append((chat_id, text)),
        )

        handler.handle_text_message(
            bridge,
            chat_id=-100,
            user_id=2,
            message={"text": "Jarvis, ответь", "message_id": 10},
            chat_type="group",
        )

        self.assertEqual(sent_messages, [])
        self.assertTrue(any("group non-owner ignored" in row for row in logs))

    def test_owner_group_explicit_jarvis_starts_jarvis_task(self):
        started = []
        logs = []
        handler = TelegramMessageHandlers(owner_user_id=1, safe_mode_reply="safe")
        bridge = SimpleNamespace(
            normalize_incoming_text=lambda text, _bot_username: text,
            extract_assistant_persona=lambda text: ("jarvis", "проверь память"),
            bot_username="jarvis_bot",
            log=lambda message: logs.append(message),
            shorten_for_log=lambda text: text,
            contains_profanity=lambda _text: False,
            is_group_discussion_rate_limited=lambda *_args, **_kwargs: False,
            is_group_followup_message=lambda *_args, **_kwargs: False,
            is_group_discussion_continuation=lambda *_args, **_kwargs: False,
            get_group_participant_priority=lambda *_args, **_kwargs: "owner",
            should_process_group_message=lambda *_args, **_kwargs: True,
            is_meaningful_group_request=lambda *_args, **_kwargs: True,
            is_ambient_group_chatter=lambda *_args, **_kwargs: False,
            should_consider_group_spontaneous_reply=lambda *_args, **_kwargs: False,
            owner_autofix_enabled=lambda: False,
            should_attempt_owner_autofix=lambda *_args, **_kwargs: False,
            handle_command=lambda *_args, **_kwargs: False,
            config=SimpleNamespace(safe_chat_only=False),
            is_dangerous_request=lambda _text: False,
            can_owner_use_workspace_mode=lambda *_args, **_kwargs: True,
            state=SimpleNamespace(try_start_chat_task=lambda _chat_id: True),
            send_chat_action=lambda *_args, **_kwargs: None,
            safe_send_text=lambda *_args, **_kwargs: None,
            run_text_task=lambda *args, **_kwargs: started.append(args),
        )

        with patch("handlers.telegram_handlers.Thread") as thread_cls:
            thread_cls.side_effect = lambda target, args=(), daemon=None: SimpleNamespace(start=lambda: target(*args))
            handler.handle_text_message(
                bridge,
                chat_id=-100,
                user_id=1,
                message={"text": "Jarvis, проверь память", "message_id": 10},
                chat_type="group",
            )

        self.assertEqual(len(started), 1)
        self.assertEqual(started[0][1], "проверь память")
        self.assertEqual(started[0][4], "jarvis")
        self.assertFalse(any("ignored" in row for row in logs))

    def test_owner_group_explicit_enterprise_starts_enterprise_task(self):
        started = []
        logs = []
        handler = TelegramMessageHandlers(owner_user_id=1, safe_mode_reply="safe")
        bridge = SimpleNamespace(
            normalize_incoming_text=lambda text, _bot_username: text,
            extract_assistant_persona=lambda text: ("enterprise", "проверь память"),
            bot_username="jarvis_bot",
            log=lambda message: logs.append(message),
            shorten_for_log=lambda text: text,
            contains_profanity=lambda _text: False,
            is_group_discussion_rate_limited=lambda *_args, **_kwargs: False,
            is_group_followup_message=lambda *_args, **_kwargs: False,
            is_group_discussion_continuation=lambda *_args, **_kwargs: False,
            get_group_participant_priority=lambda *_args, **_kwargs: "owner",
            should_process_group_message=lambda *_args, **_kwargs: True,
            is_meaningful_group_request=lambda *_args, **_kwargs: True,
            is_ambient_group_chatter=lambda *_args, **_kwargs: False,
            should_consider_group_spontaneous_reply=lambda *_args, **_kwargs: False,
            owner_autofix_enabled=lambda: False,
            should_attempt_owner_autofix=lambda *_args, **_kwargs: False,
            handle_command=lambda *_args, **_kwargs: False,
            config=SimpleNamespace(safe_chat_only=False),
            is_dangerous_request=lambda _text: False,
            can_owner_use_workspace_mode=lambda *_args, **_kwargs: True,
            state=SimpleNamespace(try_start_chat_task=lambda _chat_id: True),
            send_chat_action=lambda *_args, **_kwargs: None,
            safe_send_text=lambda *_args, **_kwargs: None,
            run_text_task=lambda *args, **_kwargs: started.append(args),
        )

        with patch("handlers.telegram_handlers.Thread") as thread_cls:
            thread_cls.side_effect = lambda target, args=(), daemon=None: SimpleNamespace(start=lambda: target(*args))
            handler.handle_text_message(
                bridge,
                chat_id=-100,
                user_id=1,
                message={"text": "Enterprise, проверь память", "message_id": 11},
                chat_type="group",
            )

        self.assertEqual(len(started), 1)
        self.assertEqual(started[0][1], "проверь память")
        self.assertEqual(started[0][4], "enterprise")
        self.assertFalse(any("ignored" in row for row in logs))

    def test_owner_group_message_without_persona_stays_silent(self):
        sent_messages = []
        logs = []
        handler = TelegramMessageHandlers(owner_user_id=1, safe_mode_reply="safe")
        bridge = SimpleNamespace(
            normalize_incoming_text=lambda text, _bot_username: text,
            extract_assistant_persona=lambda text: ("", text),
            bot_username="jarvis_bot",
            log=lambda message: logs.append(message),
            shorten_for_log=lambda text: text,
            contains_profanity=lambda _text: False,
            is_group_discussion_rate_limited=lambda *_args, **_kwargs: False,
            is_group_followup_message=lambda *_args, **_kwargs: False,
            is_group_discussion_continuation=lambda *_args, **_kwargs: False,
            should_process_group_message=lambda *_args, **_kwargs: False,
            safe_send_text=lambda chat_id, text: sent_messages.append((chat_id, text)),
        )

        handler.handle_text_message(
            bridge,
            chat_id=-100,
            user_id=1,
            message={"text": "проверь память", "message_id": 12},
            chat_type="group",
        )

        self.assertEqual(sent_messages, [])
        self.assertTrue(any("owner group message without explicit persona ignored" in row for row in logs))

    def test_owner_group_bare_jarvis_ping_is_not_treated_as_empty_text(self):
        started = []
        sent_messages = []
        handler = TelegramMessageHandlers(owner_user_id=1, safe_mode_reply="safe")
        bridge = SimpleNamespace(
            normalize_incoming_text=lambda text, _bot_username: text,
            extract_assistant_persona=lambda text: ("jarvis", ""),
            bot_username="jarvis_bot",
            log=lambda _message: None,
            shorten_for_log=lambda text: text,
            contains_profanity=lambda _text: False,
            is_group_discussion_rate_limited=lambda *_args, **_kwargs: False,
            is_group_followup_message=lambda *_args, **_kwargs: False,
            is_group_discussion_continuation=lambda *_args, **_kwargs: False,
            get_group_participant_priority=lambda *_args, **_kwargs: "owner",
            should_process_group_message=lambda *_args, **_kwargs: True,
            is_meaningful_group_request=lambda *_args, **_kwargs: True,
            is_ambient_group_chatter=lambda *_args, **_kwargs: False,
            should_consider_group_spontaneous_reply=lambda *_args, **_kwargs: False,
            owner_autofix_enabled=lambda: False,
            should_attempt_owner_autofix=lambda *_args, **_kwargs: False,
            handle_command=lambda *_args, **_kwargs: False,
            config=SimpleNamespace(safe_chat_only=False),
            is_dangerous_request=lambda _text: False,
            can_owner_use_workspace_mode=lambda *_args, **_kwargs: True,
            state=SimpleNamespace(try_start_chat_task=lambda _chat_id: True),
            send_chat_action=lambda *_args, **_kwargs: None,
            safe_send_text=lambda chat_id, text: sent_messages.append((chat_id, text)),
            run_text_task=lambda *args, **_kwargs: started.append(args),
        )

        with patch("handlers.telegram_handlers.Thread") as thread_cls:
            thread_cls.side_effect = lambda target, args=(), daemon=None: SimpleNamespace(start=lambda: target(*args))
            handler.handle_text_message(
                bridge,
                chat_id=-100,
                user_id=1,
                message={"text": "Jarvis?", "message_id": 13},
                chat_type="group",
            )

        self.assertEqual(sent_messages, [])
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0][1], "Jarvis?")
        self.assertEqual(started[0][4], "jarvis")

    def test_owner_group_reply_to_bot_message_is_processed_without_explicit_persona(self):
        started = []
        sent_messages = []
        handler = TelegramMessageHandlers(owner_user_id=1, safe_mode_reply="safe")
        bridge = SimpleNamespace(
            normalize_incoming_text=lambda text, _bot_username: text,
            extract_assistant_persona=lambda text: ("", text),
            bot_username="jarvis_bot",
            log=lambda _message: None,
            shorten_for_log=lambda text: text,
            contains_profanity=lambda _text: False,
            is_group_discussion_rate_limited=lambda *_args, **_kwargs: False,
            is_group_followup_message=lambda *_args, **_kwargs: True,
            is_group_discussion_continuation=lambda *_args, **_kwargs: False,
            get_group_participant_priority=lambda *_args, **_kwargs: "owner",
            should_process_group_message=lambda *_args, **_kwargs: True,
            is_meaningful_group_request=lambda *_args, **_kwargs: True,
            is_ambient_group_chatter=lambda *_args, **_kwargs: False,
            should_consider_group_spontaneous_reply=lambda *_args, **_kwargs: False,
            owner_autofix_enabled=lambda: False,
            should_attempt_owner_autofix=lambda *_args, **_kwargs: False,
            handle_command=lambda *_args, **_kwargs: False,
            config=SimpleNamespace(safe_chat_only=False),
            is_dangerous_request=lambda _text: False,
            can_owner_use_workspace_mode=lambda *_args, **_kwargs: True,
            state=SimpleNamespace(try_start_chat_task=lambda _chat_id: True),
            send_chat_action=lambda *_args, **_kwargs: None,
            safe_send_text=lambda chat_id, text: sent_messages.append((chat_id, text)),
            run_text_task=lambda *args, **_kwargs: started.append(args),
        )

        with patch("handlers.telegram_handlers.Thread") as thread_cls:
            thread_cls.side_effect = lambda target, args=(), daemon=None: SimpleNamespace(start=lambda: target(*args))
            handler.handle_text_message(
                bridge,
                chat_id=-100,
                user_id=1,
                message={
                    "text": "посмотри выше",
                    "message_id": 14,
                    "reply_to_message": {"message_id": 9},
                },
                chat_type="group",
            )

        self.assertEqual(sent_messages, [])
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0][1], "посмотри выше")

    def test_private_non_owner_noise_is_not_recorded_before_block(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        recorded = []
        bridge.state = SimpleNamespace(
            is_duplicate_message=lambda _chat_id, _message_id: False,
            authorized_user_ids=set(),
        )
        bridge.record_incoming_event = lambda chat_id, user_id, message: recorded.append((chat_id, user_id, message.get("text")))
        bridge.maybe_refresh_chat_participants_snapshot = lambda _chat_id, _chat_type: None
        bridge.maybe_handle_owner_moderation_override = lambda _chat_id, _user_id, _raw_text, _message, _chat_type: False
        bridge.maybe_apply_auto_moderation = lambda _chat_id, _user_id, _message, _chat_type: False
        bridge.is_group_spontaneous_reply_candidate = lambda *_args, **_kwargs: False
        bridge.is_group_followup_message = lambda *_args, **_kwargs: False
        bridge.is_group_discussion_continuation = lambda *_args, **_kwargs: False
        bridge.handle_text_message = lambda *_args, **_kwargs: self.fail("blocked private guest message must not reach text handler")
        bridge.safe_send_text = lambda *_args, **_kwargs: None
        bridge.should_record_incoming_event = TelegramBridge.should_record_incoming_event.__get__(bridge, TelegramBridge)

        bridge.handle_update(
            {
                "message": {
                    "message_id": 10,
                    "chat": {"id": 2, "type": "private"},
                    "from": {"id": 2, "is_bot": False},
                    "text": "просто пишу от фонаря",
                }
            }
        )

        self.assertEqual(recorded, [])

    def test_private_non_owner_public_command_is_blocked_before_dispatch(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        recorded = []
        bridge.state = SimpleNamespace(
            is_duplicate_message=lambda _chat_id, _message_id: False,
            authorized_user_ids=set(),
        )
        bridge.record_incoming_event = lambda chat_id, user_id, message: recorded.append((chat_id, user_id, message.get("text")))
        bridge.maybe_refresh_chat_participants_snapshot = lambda _chat_id, _chat_type: None
        bridge.maybe_handle_owner_moderation_override = lambda _chat_id, _user_id, _raw_text, _message, _chat_type: False
        bridge.maybe_apply_auto_moderation = lambda _chat_id, _user_id, _message, _chat_type: False
        bridge.is_group_spontaneous_reply_candidate = lambda *_args, **_kwargs: False
        bridge.is_group_followup_message = lambda *_args, **_kwargs: False
        bridge.is_group_discussion_continuation = lambda *_args, **_kwargs: False
        bridge.handle_text_message = lambda *_args, **_kwargs: self.fail("blocked private guest command must not reach text handler")
        bridge.safe_send_text = lambda *_args, **_kwargs: None
        bridge.should_record_incoming_event = TelegramBridge.should_record_incoming_event.__get__(bridge, TelegramBridge)

        bridge.handle_update(
            {
                "message": {
                    "message_id": 11,
                    "chat": {"id": 2, "type": "private"},
                    "from": {"id": 2, "is_bot": False},
                    "text": "/start",
                }
            }
        )

        self.assertEqual(recorded, [])

    def test_unauthorized_callback_is_ignored_without_access_denied_reply(self):
        sent_messages = []
        logs = []
        answered_callbacks = []
        handler = UIHandlers(
            owner_user_id=1,
            access_denied_text="denied",
            ui_pending_appeal="await_appeal_text",
            ui_pending_approve_comment="await_appeal_approve_comment",
            ui_pending_reject_comment="await_appeal_reject_comment",
            ui_pending_close_comment="await_appeal_close_comment",
            admin_help_sections=set(),
            public_help_sections=set(),
            control_panel_sections=set(),
        )
        bridge = SimpleNamespace(
            answer_callback_query=lambda callback_query_id: answered_callbacks.append(callback_query_id),
            log=lambda message: logs.append(message),
            has_chat_access=lambda _authorized_user_ids, _user_id: False,
            has_public_callback_access=lambda _data: False,
            safe_send_text=lambda chat_id, text: sent_messages.append((chat_id, text)),
            state=SimpleNamespace(authorized_user_ids=set()),
        )

        handler.handle_callback_query(
            bridge,
            {
                "id": "cb1",
                "data": "ui:home",
                "message": {"chat": {"id": 100}, "message_id": 55},
                "from": {"id": 2},
            },
        )

        self.assertEqual(answered_callbacks, ["cb1"])
        self.assertEqual(sent_messages, [])
        self.assertTrue(any("callback ignored for non-owner" in row for row in logs))

    def test_non_owner_start_and_appeals_open_public_panels_but_help_and_rules_stay_silent(self):
        opened_panels = []
        sent_messages = []
        dispatcher = CommandDispatcher(owner_username="dmitry", public_help_text="public", mode_prompts={})
        bridge = SimpleNamespace(
            has_chat_access=lambda _authorized_user_ids, _user_id: False,
            state=SimpleNamespace(authorized_user_ids=set()),
            open_control_panel=lambda chat_id, user_id, section: opened_panels.append((chat_id, user_id, section)),
            safe_send_text=lambda chat_id, text: sent_messages.append((chat_id, text)),
            get_group_rules_text=lambda _message: "rules",
        )

        self.assertTrue(dispatcher.handle_command(bridge, 100, 2, "/start"))
        self.assertTrue(dispatcher.handle_command(bridge, 100, 2, "/appeals"))
        self.assertTrue(dispatcher.handle_command(bridge, 100, 2, "/help"))
        self.assertTrue(dispatcher.handle_command(bridge, 100, 2, "/rules"))

        self.assertEqual(opened_panels, [(100, 2, "home"), (100, 2, "appeals")])
        self.assertEqual(sent_messages, [])

    def test_public_control_panel_keeps_rating_and_appeal_entry_points(self):
        renderer = ControlPanelRenderer(
            owner_user_id=1,
            owner_username="owner",
            public_home_text="stub",
            commands_list_text="",
            control_panel_sections={"home", "owner_root", "profile", "top_week", "appeals"},
            has_chat_access_func=lambda _authorized_user_ids, _user_id: False,
            format_duration_seconds_func=lambda value: str(value),
            truncate_text_func=lambda text, limit: text[:limit],
            render_git_status_summary_func=lambda *_args, **_kwargs: "",
            render_git_last_commits_func=lambda *_args, **_kwargs: "",
            render_admin_command_catalog_func=lambda *_args, **_kwargs: "",
        )
        bridge = SimpleNamespace(
            state=SimpleNamespace(authorized_user_ids=set()),
            appeals=SimpleNamespace(
                get_case_snapshot=lambda _user_id: {
                    "active_bans": [],
                    "active_mutes": [],
                    "active_warnings": 0,
                    "confirmed_violations": 0,
                    "legacy_user_warnings": 0,
                    "past_appeals": 0,
                },
                get_user_appeals=lambda _user_id, limit=0: [],
            ),
            legacy=SimpleNamespace(
                render_dashboard_summary=lambda user_id: f"profile:{user_id}",
                render_top_all_time=lambda: "top-all",
                render_top_historical=lambda: "top-history",
                render_top_week=lambda: "top-week",
                render_top_day=lambda: "top-day",
                render_top_social=lambda: "top-social",
                render_top_season=lambda: "top-season",
            ),
        )

        text, markup = renderer.build_control_panel(bridge, 2, "home")
        profile_text, profile_markup = renderer.build_control_panel(bridge, 2, "profile")
        top_text, top_markup = renderer.build_control_panel(bridge, 2, "top_week")
        appeals_text, appeals_markup = renderer.build_control_panel(bridge, 2, "appeals")

        self.assertEqual(text, "stub")
        self.assertEqual(markup, {"inline_keyboard": [[{"text": "Мой профиль", "callback_data": "ui:profile"}, {"text": "Топы", "callback_data": "ui:top"}], [{"text": "Апелляции", "callback_data": "ui:appeals"}]]})
        self.assertIn("JARVIS • МОЙ ПРОФИЛЬ", profile_text)
        self.assertIn("profile:2", profile_text)
        self.assertEqual(profile_markup["inline_keyboard"][0][0]["callback_data"], "ui:top")
        self.assertEqual(top_text, "top-week")
        self.assertEqual(top_markup["inline_keyboard"][-1][0]["callback_data"], "ui:home")
        self.assertIn("JARVIS • АПЕЛЛЯЦИИ", appeals_text)
        self.assertEqual(appeals_markup["inline_keyboard"][0][0]["callback_data"], "ui:appeal:new")

    def test_memory_refresh_queue_skips_non_owner_private_chats(self):
        with NamedTemporaryFile(suffix=".db") as tmp:
            state = BridgeState(history_limit=4, default_mode="jarvis", db_path=tmp.name)
            try:
                for index in range(3):
                    state.record_event(
                        2,
                        2,
                        "user",
                        "text",
                        f"guest private {index}",
                        message_id=index + 1,
                        chat_type="private",
                    )
                for index in range(3):
                    state.record_event(
                        -100,
                        2,
                        "user",
                        "text",
                        f"group {index}",
                        message_id=100 + index,
                        chat_type="group",
                    )

                due = state.get_chats_due_for_memory_refresh(limit=5, min_new_events=1, min_gap_seconds=0)
            finally:
                state.db.close()

        self.assertTrue(any(chat_id == -100 for chat_id, _last_event_id, _new_events in due))
        self.assertFalse(any(chat_id == 2 for chat_id, _last_event_id, _new_events in due))
        self.assertFalse(any(chat_id > 0 and chat_id != OWNER_USER_ID for chat_id, _last_event_id, _new_events in due))

    def test_owner_auto_moderation_report_exposes_recommended_decision(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        bridge.state = SimpleNamespace(get_chat_title=lambda _chat_id, fallback_title="": fallback_title or "cached chat")
        message = {"chat": {"title": "Test chat"}, "text": "Тестовое нарушение"}
        decision = SimpleNamespace(
            severity="high",
            public_reason="оскорбления",
            code="abuse.direct",
            mute_seconds=3600,
            suggested_owner_action="Оставить мут и проверить предысторию.",
        )

        report = bridge.render_auto_moderation_owner_report(
            chat_id=-100,
            message=message,
            target_user_id=42,
            target_label="@user",
            decision=decision,
            applied_action="mute",
        )

        self.assertIn("OWNER REPORT • AUTO MODERATION", report)
        self.assertIn("Решение владельца:", report)
        self.assertIn("Оставить мут и проверить предысторию.", report)

    def test_chat_title_is_cached_and_restored_from_runtime_cache(self):
        with NamedTemporaryFile(suffix=".db") as tmp:
            state = BridgeState(history_limit=4, default_mode="jarvis", db_path=tmp.name)
            try:
                bridge = TelegramBridge.__new__(TelegramBridge)
                bridge.state = state
                bridge.sync_legacy_jarvis = lambda _message: None

                TelegramBridge.record_incoming_event(
                    bridge,
                    chat_id=-100123,
                    user_id=42,
                    message={
                        "message_id": 1,
                        "chat": {"id": -100123, "type": "supergroup", "title": "Все педали!"},
                        "from": {"id": 42, "username": "tester", "first_name": "Test", "is_bot": False},
                        "text": "Привет",
                    },
                )

                self.assertEqual(state.get_chat_title(-100123), "Все педали!")
                self.assertEqual(state.get_chat_title(-100123, ""), "Все педали!")

                message_without_title = {"chat": {"id": -100123, "type": "supergroup"}, "text": "Нарушение"}
                report = TelegramBridge.render_auto_moderation_owner_report(
                    bridge,
                    chat_id=-100123,
                    message=message_without_title,
                    target_user_id=7,
                    target_label="@user",
                    decision=SimpleNamespace(
                        severity="medium",
                        public_reason="спам",
                        code="spam.test",
                        mute_seconds=0,
                        suggested_owner_action="Проверить.",
                    ),
                    applied_action="warn",
                )

                self.assertIn("• Чат: Все педали!", report)
            finally:
                state.db.close()

    def test_json_progress_keeps_only_last_agent_message_as_final_answer(self):
        service = JSEnterpriseService(
            JSEnterpriseServiceDeps(
                send_status_message_func=lambda *_args, **_kwargs: 1,
                build_codex_command_func=lambda **_kwargs: [],
                heartbeat_guard_factory=lambda: SimpleNamespace(__enter__=lambda self: self, __exit__=lambda self, exc_type, exc, tb: False),
                build_subprocess_env_func=lambda: {},
                send_chat_action_func=lambda *_args, **_kwargs: None,
                update_progress_status_func=lambda *_args, **_kwargs: None,
                log_func=lambda *_args, **_kwargs: None,
                edit_status_message_func=lambda *_args, **_kwargs: True,
                finish_progress_status_func=lambda *_args, **_kwargs: None,
                normalize_whitespace_func=lambda text: " ".join((text or "").split()),
                postprocess_answer_func=lambda text, _latency_ms: text,
                build_codex_failure_answer_func=lambda *_args, **_kwargs: "fail",
                extract_usable_codex_stdout_func=lambda _stdout: "",
                shorten_for_log_func=lambda text, _limit=0: text,
                jarvis_offline_text="offline",
                upgrade_timeout_text="timeout",
                codex_timeout=30,
                progress_update_seconds=1.0,
                enterprise_worker_path=Path("/tmp/enterprise_worker.py"),
            )
        )

        service._format_json_event({"type": "thread.started"})
        first = service.deps.normalize_whitespace_func("Комментарий 1")
        second = service.deps.normalize_whitespace_func("Финальный ответ")
        self.assertEqual(first, "Комментарий 1")
        self.assertEqual(second, "Финальный ответ")

    def test_enterprise_zero_timeout_disables_fallback_codex_timeout(self):
        self.assertIsNone(JSEnterpriseService._resolve_timeout(0, 180))
        self.assertIsNone(JSEnterpriseService._resolve_timeout(-1, 180))
        self.assertEqual(JSEnterpriseService._resolve_timeout(None, 180), 180)
        self.assertEqual(JSEnterpriseService._resolve_timeout(240, 180), 240)

    def test_private_enterprise_keeps_status_feed_and_sends_answer_separately(self):
        service = TextRouteService(
            TextRouteServiceDeps(
                build_prompt_func=lambda **_kwargs: "prompt",
                log_func=lambda _message: None,
                default_chat_route_timeout=60,
            )
        )

        bridge = SimpleNamespace(
            build_text_context_bundle=lambda **_kwargs: SimpleNamespace(
                reply_context="",
                web_context="",
                user_memory_text="user",
                relation_memory_text="",
                chat_memory_text="",
                summary_memory_text="",
                summary_text="",
                facts_text="",
                event_context="",
                database_context="",
                discussion_context="",
                route_summary="",
                guardrail_note="",
                self_model_text="",
                autobiographical_text="",
                skill_memory_text="",
                world_state_text="",
                drive_state_text="",
            ),
            is_group_followup_message=lambda *_args, **_kwargs: False,
            state=SimpleNamespace(get_history=lambda _chat_id: [("user", "hi")]),
            config=SimpleNamespace(codex_timeout=180),
        )
        route_decision = SimpleNamespace(persona="enterprise", route_kind="codex_workspace")

        preparation = service.prepare(
            bridge,
            chat_id=1,
            user_text="Проверь",
            route_decision=route_decision,
            user_id=1,
            message=None,
            reply_context="",
            spontaneous_group_reply=False,
            initial_status_message_id=10,
            chat_type="private",
        )

        self.assertFalse(preparation.replace_status_with_answer)

    def test_context_assembly_uses_entity_context_keyword_contract(self):
        captured = {}

        def context_bundle_factory(**kwargs):
            return kwargs

        def should_include_entity_context_func(**kwargs):
            captured.update(kwargs)
            return True

        route_decision = SimpleNamespace(
            persona="enterprise",
            use_workspace=False,
            route_kind="codex_workspace",
        )
        bundle = build_text_context_bundle(
            context_bundle_factory=context_bundle_factory,
            state=_FakeState(),
            chat_id=42,
            user_text="Проверь проект",
            route_decision=route_decision,
            user_id=6102780373,
            message={"reply_to_message": {"from": {"id": 11}}},
            reply_context="reply",
            active_group_followup=False,
            detect_local_chat_query_func=lambda _text: False,
            should_include_database_context_func=lambda _text: True,
            is_owner_private_chat_func=lambda _user_id, _chat_id: False,
            build_current_discussion_context_func=lambda *_args, **_kwargs: "discussion",
            build_route_summary_text_func=lambda _route: "route-summary",
            build_guardrail_note_func=lambda _route: "guardrails",
            should_include_entity_context_func=should_include_entity_context_func,
        )

        self.assertEqual(captured["persona"], "enterprise")
        self.assertEqual(captured["query_text"], "Проверь проект")
        self.assertFalse(captured["use_workspace"])
        self.assertIn("continuity", bundle["route_summary"].lower())
        self.assertEqual(bundle["self_model_text"], "self-model")
        self.assertEqual(bundle["database_context"], "database")

    def test_attachment_context_bundle_uses_active_persona_and_discussion_contract(self):
        bundle = build_attachment_context_bundle(
            context_bundle_factory=lambda **kwargs: kwargs,
            state=_FakeState(),
            chat_id=42,
            prompt_text="Разбери фото",
            persona="enterprise",
            message={"from": {"id": 6102780373}, "reply_to_message": {"from": {"id": 11}}},
            reply_context="reply",
            build_current_discussion_context_func=lambda *_args, **_kwargs: "discussion",
            build_route_summary_text_func=lambda persona: f"route:{persona}",
            build_guardrail_note_func=lambda persona: f"guard:{persona}",
            should_include_event_context_func=lambda _text: True,
            should_include_database_context_func=lambda _text: True,
        )

        self.assertEqual(bundle["discussion_context"], "discussion")
        self.assertEqual(bundle["route_summary"], "route:enterprise")
        self.assertEqual(bundle["guardrail_note"], "guard:enterprise")
        self.assertEqual(bundle["self_model_text"], "self-model")

    def test_webapp_html_accepts_screen_text_and_prompt_value(self):
        html_text = TelegramBridge.build_webapp_html(
            SimpleNamespace(),
            screen_text="runtime ok",
            prompt_value="diagnose",
            auto_refresh_seconds=0,
        )

        self.assertIn("runtime ok", html_text)
        self.assertIn('value="diagnose"', html_text)
        self.assertIn("/enterprise-console/api/jobs/", html_text)

    def test_short_codex_failure_returns_formatted_error_instead_of_empty_text(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        bridge.build_codex_command = lambda **_kwargs: ["codex"]

        with patch("tg_codex_bridge.subprocess.run") as run_mock:
            run_mock.return_value = SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="OpenAI Codex v0.116.0\nError: model provider unavailable",
            )
            answer = TelegramBridge.run_codex_short(bridge, "ping", timeout_seconds=10)

        self.assertTrue(answer.startswith("Ошибка Enterprise Core:\n"))
        self.assertIn("model provider unavailable", answer)

    def test_restart_process_is_suppressed_without_exit_or_exec(self):
        bridge = TelegramBridge.__new__(TelegramBridge)

        with patch("tg_codex_bridge.log") as log_mock, patch("tg_codex_bridge.os.execv") as execv_mock:
            TelegramBridge.restart_process(bridge)

        execv_mock.assert_not_called()
        log_mock.assert_called_once()
        self.assertIn("self-restart is disabled", log_mock.call_args.args[0])

    def test_owner_restart_command_reports_disabled_restart_and_keeps_process_alive(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        sent_messages = []
        recorded_events = []
        bridge.safe_send_text = lambda chat_id, text: sent_messages.append((chat_id, text))
        bridge.state = SimpleNamespace(record_autobiographical_event=lambda **kwargs: recorded_events.append(kwargs))

        handled = TelegramBridge.handle_restart_command(bridge, chat_id=77, user_id=OWNER_USER_ID)

        self.assertTrue(handled)
        self.assertEqual(len(recorded_events), 1)
        self.assertEqual(sent_messages[0][0], 77)
        self.assertIn("Self-restart отключён", sent_messages[0][1])

    def test_restart_request_detector_accepts_plain_russian_phrases(self):
        self.assertTrue(is_explicit_runtime_restart_request("сделай рестарт"))
        self.assertTrue(is_explicit_runtime_restart_request("перезапусти бота"))
        self.assertTrue(is_explicit_runtime_restart_request("рестарт супервизора"))
        self.assertTrue(is_explicit_runtime_restart_request("restart supervisor"))
        self.assertFalse(is_explicit_runtime_restart_request("покажи статус бота"))

    def test_pending_enterprise_job_is_persisted_and_cleared(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        meta = {}
        bridge.state = SimpleNamespace(
            get_meta=lambda key, default="": meta.get(key, default),
            set_meta=lambda key, value: meta.__setitem__(key, value),
        )

        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "abc", "chat_id": 1})
        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "def", "chat_id": 2})
        self.assertIn('"job_id": "abc"', meta["pending_enterprise_jobs"])
        self.assertIn('"job_id": "def"', meta["pending_enterprise_jobs"])

        TelegramBridge.clear_pending_enterprise_job(bridge, "abc")
        self.assertNotIn('"job_id": "abc"', meta["pending_enterprise_jobs"])
        self.assertIn('"job_id": "def"', meta["pending_enterprise_jobs"])

    def test_pending_enterprise_jobs_can_be_cleared_by_chat_after_delivery(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        meta = {}
        bridge.state = SimpleNamespace(
            get_meta=lambda key, default="": meta.get(key, default),
            set_meta=lambda key, value: meta.__setitem__(key, value),
        )

        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "abc", "chat_id": 1})
        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "def", "chat_id": 2})
        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "ghi", "chat_id": 1})

        TelegramBridge.clear_pending_enterprise_jobs_for_chat(bridge, 1)

        self.assertNotIn('"job_id": "abc"', meta["pending_enterprise_jobs"])
        self.assertNotIn('"job_id": "ghi"', meta["pending_enterprise_jobs"])
        self.assertIn('"job_id": "def"', meta["pending_enterprise_jobs"])

    def test_enterprise_worker_extracts_final_agent_message_from_json_stream(self):
        stream = "\n".join(
            [
                '{"type":"thread.started","thread_id":"t1"}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"Сначала проверяю состояние."}}',
                '{"type":"item.completed","item":{"type":"command_execution","command":"echo ok"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"Рестарт прошёл успешно."}}',
            ]
        )

        self.assertEqual(extract_json_answer(stream), "Рестарт прошёл успешно.")

    def test_enterprise_worker_uses_server_protected_paths_from_payload(self):
        payload = {"protected_paths": ["enterprise_server.py", "run_jarvis_supervisor.sh"]}
        self.assertEqual(
            get_worker_protected_paths(payload),
            ("enterprise_server.py", "run_jarvis_supervisor.sh"),
        )

    def test_enterprise_worker_prompt_allows_rest_of_workspace(self):
        text = protect_prompt("Проверь проект", {"protected_paths": ["enterprise_server.py"]})
        self.assertIn("не имеет права менять server-core", text)
        self.assertIn("Всё остальное в repo/workspace разрешено", text)
        self.assertIn("- enterprise_server.py", text)

    def test_enterprise_server_protected_paths_match_minimal_server_core(self):
        self.assertIn("enterprise_server.py", PROTECTED_SERVER_CORE_PATHS)
        self.assertIn("enterprise_worker.py", PROTECTED_SERVER_CORE_PATHS)
        self.assertIn("run_jarvis_supervisor.sh", PROTECTED_SERVER_CORE_PATHS)
        self.assertIn("restart_jarvis_supervisor.sh", PROTECTED_SERVER_CORE_PATHS)
        self.assertNotIn("tests/test_runtime_regressions.py", PROTECTED_SERVER_CORE_PATHS)
        self.assertNotIn("README.md", PROTECTED_SERVER_CORE_PATHS)


if __name__ == "__main__":
    unittest.main()
