import unittest
import sqlite3
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
import time
from types import SimpleNamespace
from unittest.mock import patch

from handlers.telegram_handlers import TelegramMessageHandlers
from handlers.ui_handlers import UIHandlers
from handlers.command_dispatch import CommandDispatcher
from handlers.command_parsers import (
    parse_achievement_audit_command,
    parse_chat_deep_command,
    parse_chat_watch_command,
    parse_conflicts_command,
    parse_ownergraph_command,
    parse_reliable_command,
    parse_summary24h_command,
    parse_watchlist_command,
    parse_whats_happening_command,
    parse_whois_command,
)
from handlers.control_panel_renderer import ControlPanelRenderer
from services.admin_registry import render_admin_command_catalog
from enterprise_worker import extract_json_answer, get_worker_protected_paths, protect_prompt
from enterprise_server import PROTECTED_SERVER_CORE_PATHS
from owner.handlers import OwnerCommandService
from services.js_enterprise_service import JSEnterpriseService, JSEnterpriseServiceDeps
from services.runtime_service import RuntimeService, RuntimeServiceDeps
from services.text_route_service import TextRouteService, TextRouteServiceDeps
from services.context_assembly import build_attachment_context_bundle, build_text_context_bundle
from services.diagnostics_pipeline import derive_memory_used, enrich_self_check_report
from models.contracts import ContextBundle, RouteDecision, SelfCheckReport
from legacy_jarvis_adapter import LegacyJarvisAdapter
from rating_service import RatingService
from tg_codex_bridge import (
    BridgeState,
    OWNER_USER_ID,
    TelegramBridge,
    detect_local_chat_query,
    has_public_callback_access,
    has_public_command_access,
    is_explicit_runtime_restart_request,
    render_chat_troublemaker_summary,
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
    def _create_minimal_chat_events_schema(self, db_path: str) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS chat_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER,
                role TEXT NOT NULL,
                message_type TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                message_id INTEGER,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                chat_type TEXT,
                reply_to_message_id INTEGER,
                reply_to_user_id INTEGER,
                reply_to_username TEXT,
                forward_origin TEXT,
                has_media INTEGER,
                file_kind TEXT,
                is_edited INTEGER
            )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                expires_at INTEGER
            )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS moderation_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                active INTEGER,
                expires_at INTEGER
            )"""
            )
            conn.commit()

    def test_detect_local_chat_query_accepts_broader_chat_summary_phrases(self):
        self.assertTrue(detect_local_chat_query("Расскажи про чат Все педали подробнее"))
        self.assertTrue(detect_local_chat_query("Нужен весь контекст чата"))
        self.assertTrue(detect_local_chat_query("Разложи по полочкам что происходит в группе"))
        self.assertFalse(detect_local_chat_query("Расскажи про проект подробнее"))

    def test_diagnostics_memory_used_prioritizes_direct_grounding_layers(self):
        route_decision = RouteDecision(
            persona="enterprise",
            intent="chat_dynamics",
            chat_type="group",
            route_kind="codex_workspace",
            source_label="Enterprise",
            use_live=False,
            use_web=False,
            use_events=True,
            use_database=True,
            use_reply=True,
            use_workspace=True,
            guardrails=(),
            request_kind="chat_local_context",
        )
        context_bundle = ContextBundle(
            database_context="db facts",
            reply_context="reply facts",
            event_context="event facts",
            world_state_text="world facts",
            user_memory_text="user memory",
            relation_memory_text="relation memory",
            chat_memory_text="chat memory",
            summary_memory_text="summary memory",
        )

        self.assertEqual(
            derive_memory_used(context_bundle, route_decision),
            ("database_context", "reply_context", "chat_events", "world_state"),
        )

    def test_enriched_self_check_report_keeps_direct_grounding_in_memory_trace(self):
        route_decision = RouteDecision(
            persona="enterprise",
            intent="chat_dynamics",
            chat_type="group",
            route_kind="codex_workspace",
            source_label="Enterprise",
            use_live=False,
            use_web=False,
            use_events=True,
            use_database=True,
            use_reply=True,
            use_workspace=True,
            guardrails=(),
            request_kind="chat_local_context",
        )
        context_bundle = ContextBundle(
            database_context="db facts",
            reply_context="reply facts",
            event_context="event facts",
            world_state_text="world facts",
            user_memory_text="user memory",
            relation_memory_text="relation memory",
        )
        report = SelfCheckReport(
            outcome="ok",
            answer="grounded answer",
            flags=(),
            observed_basis=("chat_events",),
            mode="verified",
        )

        enriched = enrich_self_check_report(
            report,
            route_decision=route_decision,
            context_bundle=context_bundle,
        )

        self.assertEqual(
            enriched.memory_used,
            ("database_context", "reply_context", "chat_events", "world_state"),
        )

    def test_runtime_log_treats_status_edit_429_as_warning_not_severe(self):
        with TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "tg_codex_bridge.log"
            now_dt = datetime.utcnow()
            log_path.write_text(
                "\n".join(
                    [
                        f"[{now_dt.strftime('%Y-%m-%d %H:%M:%S')}] bot started",
                        f"[{(now_dt + timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')}] instance lock conflict lock_path=/tmp/tg_codex_bridge.lock: Another tg_codex_bridge.py instance is already running.",
                        f"[{(now_dt + timedelta(seconds=2)).strftime('%Y-%m-%d %H:%M:%S')}] failed to edit status message chat=-1003879607896 message_id=13023: telegram http 429: Too Many Requests: retry after 15",
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

    def test_runtime_log_ignores_expired_callback_query_errors(self):
        with TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "tg_codex_bridge.log"
            now_dt = datetime.utcnow()
            log_path.write_text(
                "\n".join(
                    [
                        f"[{now_dt.strftime('%Y-%m-%d %H:%M:%S')}] bot started",
                        f"[{(now_dt + timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')}] failed to answer callback query: telegram http 400: Bad Request: query is too old and response timeout expired or query ID is invalid",
                    ]
                ),
                encoding="utf-8",
            )

            snapshot = inspect_runtime_log(log_path)

        self.assertEqual(snapshot["warning_count"], 1)
        self.assertEqual(snapshot["session_warning_count"], 1)
        self.assertEqual(snapshot["severe_error_count"], 0)
        self.assertEqual(snapshot["session_severe_error_count"], 0)
        self.assertEqual(len(snapshot["recent_session_warning_lines"]), 1)

    def test_runtime_log_treats_enterprise_connection_refused_as_warning(self):
        with TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "tg_codex_bridge.log"
            now_dt = datetime.utcnow()
            log_path.write_text(
                "\n".join(
                    [
                        f"[{now_dt.strftime('%Y-%m-%d %H:%M:%S')}] bot started",
                        f"[{(now_dt + timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')}] не удалось связаться с Enterprise: <urlopen error [Errno 111] Connection refused>",
                    ]
                ),
                encoding="utf-8",
            )

            snapshot = inspect_runtime_log(log_path)

        self.assertEqual(snapshot["warning_count"], 1)
        self.assertEqual(snapshot["session_warning_count"], 1)
        self.assertEqual(snapshot["severe_error_count"], 0)
        self.assertEqual(snapshot["session_severe_error_count"], 0)
        self.assertEqual(len(snapshot["recent_session_warning_lines"]), 1)

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

    def test_runtime_risk_uses_current_session_errors_instead_of_full_day_tail(self):
        with sqlite3.connect(":memory:") as conn:
            conn.execute(
                """CREATE TABLE request_diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                outcome TEXT NOT NULL DEFAULT '',
                response_mode TEXT NOT NULL DEFAULT '',
                used_live INTEGER NOT NULL DEFAULT 0,
                tools_used TEXT NOT NULL DEFAULT '',
                route_kind TEXT NOT NULL DEFAULT '',
                memory_used TEXT NOT NULL DEFAULT ''
                )"""
            )
            now_ts = int(time.time())
            for _ in range(3):
                conn.execute(
                    "INSERT INTO request_diagnostics(created_at, outcome, response_mode, used_live, tools_used) VALUES(?, 'uncertain', 'inferred', 0, '')",
                    (now_ts - 60,),
                )
            conn.commit()

            recorded_scores = {}
            bridge = SimpleNamespace(
                state=SimpleNamespace(
                    db=conn,
                    db_lock=nullcontext(),
                    chat_tasks_in_progress={},
                    set_drive_score=lambda name, score, reason: recorded_scores.setdefault(name, (score, reason)),
                ),
            )
            service = RuntimeService(
                RuntimeServiceDeps(
                    log_func=lambda _message: None,
                    log_exception_func=lambda _message, _error, _limit: None,
                    doc_runtime_drift_markers=(),
                )
            )

            scores = service.recompute_drive_scores(
                bridge,
                {
                    "recent_errors_count": 0,
                    "recent_warning_count": 0,
                    "window_errors_count": 19,
                    "window_warning_count": 50,
                    "live_failures_count": 0,
                    "heartbeat_kill_count": 0,
                    "upgrade_active": 0,
                    "severe_error_age_seconds": 9000,
                    "heartbeat_kill_age_seconds": -1,
                    "git_dirty_count": 0,
                    "memory_due_count": 0,
                    "unresolved_tasks_count": 0,
                    "docs_drift_count": 0,
                },
            )

        self.assertEqual(scores["runtime_risk_pressure"], 0.0)
        self.assertEqual(scores["uncertainty_pressure"], 36.0)
        self.assertIn("errors_session=0", recorded_scores["runtime_risk_pressure"][1])
        self.assertIn("errors_24h=19", recorded_scores["runtime_risk_pressure"][1])

    def test_public_access_lists_keep_rating_and_appeal_entry_points(self):
        self.assertTrue(has_public_command_access("/start"))
        self.assertTrue(has_public_command_access("/rating"))
        self.assertTrue(has_public_command_access("/top"))
        self.assertTrue(has_public_command_access("/appeals"))
        self.assertTrue(has_public_command_access("/appeal прошу пересмотреть"))
        self.assertTrue(has_public_callback_access("ui:home"))
        self.assertTrue(has_public_callback_access("ui:achievements"))
        self.assertTrue(has_public_callback_access("ui:top:week"))
        self.assertTrue(has_public_callback_access("ui:top:week:2"))
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

    def test_owner_group_chat_watch_phrase_is_processed_without_explicit_persona(self):
        handled = []
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
            get_group_participant_priority=lambda *_args, **_kwargs: "owner",
            should_process_group_message=lambda *_args, **_kwargs: False,
            is_meaningful_group_request=lambda *_args, **_kwargs: True,
            is_ambient_group_chatter=lambda *_args, **_kwargs: False,
            should_consider_group_spontaneous_reply=lambda *_args, **_kwargs: False,
            owner_autofix_enabled=lambda: False,
            should_attempt_owner_autofix=lambda *_args, **_kwargs: False,
            handle_command=lambda _chat_id, _user_id, text, _message, allow_followup_text=False: handled.append((text, allow_followup_text)) or True,
            safe_send_text=lambda chat_id, text: sent_messages.append((chat_id, text)),
        )

        handler.handle_text_message(
            bridge,
            chat_id=-100,
            user_id=1,
            message={"text": "Что тут происходит?", "message_id": 12},
            chat_type="group",
        )

        self.assertEqual(sent_messages, [])
        self.assertEqual(handled, [("Что тут происходит?", False)])
        self.assertFalse(any("ignored" in row for row in logs))

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

    def test_non_owner_start_with_payload_still_opens_public_panel(self):
        opened_panels = []
        dispatcher = CommandDispatcher(owner_username="dmitry", public_help_text="public", mode_prompts={})
        bridge = SimpleNamespace(
            has_chat_access=lambda _authorized_user_ids, _user_id: False,
            state=SimpleNamespace(authorized_user_ids=set()),
            open_control_panel=lambda chat_id, user_id, section: opened_panels.append((chat_id, user_id, section)),
            safe_send_text=lambda *_args, **_kwargs: None,
            get_group_rules_text=lambda _message: "rules",
        )

        self.assertTrue(dispatcher.handle_command(bridge, 100, 2, "/start promo"))
        self.assertEqual(opened_panels, [(100, 2, "home")])

    def test_chat_watch_phrase_routes_to_recent_chat_report_handler(self):
        calls = []
        dispatcher = CommandDispatcher(owner_username="dmitry", public_help_text="public", mode_prompts={})
        bridge = SimpleNamespace(
            has_chat_access=lambda _authorized_user_ids, _user_id: True,
            state=SimpleNamespace(authorized_user_ids={1}),
            handle_recent_chat_report_command=lambda chat_id, user_id, text, message: calls.append((chat_id, user_id, text, message)) or True,
        )

        handled = dispatcher.handle_command(bridge, -100, 1, "что тут происходит", {"message_id": 55})

        self.assertTrue(handled)
        self.assertEqual(calls, [(-100, 1, "что тут происходит", {"message_id": 55})])

    def test_chat_watch_parser_accepts_punctuation(self):
        self.assertTrue(parse_chat_watch_command("Что тут происходит?"))
        self.assertTrue(parse_chat_watch_command("что здесь происходит!!!"))
        self.assertFalse(parse_chat_watch_command("что происходит в мире"))

    def test_owner_command_parsers_accept_payload_commands(self):
        self.assertEqual(parse_chat_deep_command("/chatdeep -100123"), "-100123")
        self.assertEqual(parse_whois_command("/whois @noise"), "@noise")
        self.assertEqual(parse_achievement_audit_command("/achaudit 20"), "20")
        self.assertEqual(parse_watchlist_command("/watchlist"), "")
        self.assertEqual(parse_reliable_command("/reliable -100123"), "-100123")
        self.assertEqual(parse_whats_happening_command("/whatshappening"), "")
        self.assertEqual(parse_summary24h_command("/summary24h -100123"), "-100123")
        self.assertEqual(parse_conflicts_command("/conflicts"), "")
        self.assertEqual(parse_ownergraph_command("/ownergraph"), "")

    def test_owner_dashboard_commands_route_to_bridge_handlers(self):
        calls = []
        dispatcher = CommandDispatcher(owner_username="dmitry", public_help_text="public", mode_prompts={})
        bridge = SimpleNamespace(
            has_chat_access=lambda _authorized_user_ids, _user_id: True,
            state=SimpleNamespace(authorized_user_ids={1}),
            handle_chat_deep_command=lambda chat_id, user_id, payload: calls.append(("chatdeep", chat_id, user_id, payload)) or True,
            handle_whois_command=lambda chat_id, user_id, payload, message: calls.append(("whois", chat_id, user_id, payload, message)) or True,
            handle_achievement_audit_command=lambda chat_id, user_id, payload: calls.append(("achaudit", chat_id, user_id, payload)) or True,
            handle_watchlist_command=lambda chat_id, user_id, payload: calls.append(("watchlist", chat_id, user_id, payload)) or True,
            handle_reliable_command=lambda chat_id, user_id, payload: calls.append(("reliable", chat_id, user_id, payload)) or True,
            handle_whats_happening_command=lambda chat_id, user_id, payload: calls.append(("whatshappening", chat_id, user_id, payload)) or True,
            handle_summary24h_command=lambda chat_id, user_id, payload: calls.append(("summary24h", chat_id, user_id, payload)) or True,
            handle_conflicts_command=lambda chat_id, user_id, payload: calls.append(("conflicts", chat_id, user_id, payload)) or True,
            handle_ownergraph_command=lambda chat_id, user_id, payload: calls.append(("ownergraph", chat_id, user_id, payload)) or True,
            parse_owner_report_command=lambda _text: False,
            parse_export_command=lambda _text: None,
            parse_portrait_command=lambda _text: None,
            parse_welcome_command=lambda _text: None,
            parse_mode_command=lambda _text: None,
        )

        self.assertTrue(dispatcher.handle_command(bridge, -100, 1, "/chatdeep -100777"))
        self.assertTrue(dispatcher.handle_command(bridge, -100, 1, "/whois @noise", {"message_id": 1}))
        self.assertTrue(dispatcher.handle_command(bridge, -100, 1, "/achaudit 20"))
        self.assertTrue(dispatcher.handle_command(bridge, -100, 1, "/watchlist"))
        self.assertTrue(dispatcher.handle_command(bridge, -100, 1, "/reliable -100777"))
        self.assertTrue(dispatcher.handle_command(bridge, -100, 1, "/whatshappening"))
        self.assertTrue(dispatcher.handle_command(bridge, -100, 1, "/summary24h -100777"))
        self.assertTrue(dispatcher.handle_command(bridge, -100, 1, "/conflicts"))
        self.assertTrue(dispatcher.handle_command(bridge, -100, 1, "/ownergraph"))

        self.assertEqual(
            calls,
            [
                ("chatdeep", -100, 1, "-100777"),
                ("whois", -100, 1, "@noise", {"message_id": 1}),
                ("achaudit", -100, 1, "20"),
                ("watchlist", -100, 1, ""),
                ("reliable", -100, 1, "-100777"),
                ("whatshappening", -100, 1, ""),
                ("summary24h", -100, 1, "-100777"),
                ("conflicts", -100, 1, ""),
                ("ownergraph", -100, 1, ""),
            ],
        )

    def test_chat_troublemaker_summary_flags_probable_noise_source(self):
        rows = [
            (1710000000, 11, "calm", "Calm", "", "user", "text", "Давайте по делу"),
            (1710000001, 22, "noise", "Noise", "", "user", "text", "АХАХ, какой бред"),
            (1710000002, 22, "noise", "Noise", "", "user", "text", "ЗАТКНИСЬ УЖЕ"),
            (1710000003, 22, "noise", "Noise", "", "user", "text", "ЗАТКНИСЬ УЖЕ"),
            (1710000004, 22, "noise", "Noise", "", "user", "text", "ЗАТКНИСЬ УЖЕ"),
        ]

        summary = render_chat_troublemaker_summary(rows)

        self.assertIn("@noise id=22", summary)
        self.assertIn("грубость/агрессия", summary)
        self.assertIn("повторы", summary)
        self.assertIn("не по всей истории чата", summary)

    def test_owner_chat_alert_detects_conflict_signal(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        set_meta_calls = []
        rows = [
            (1710000000, 11, "calm", "Calm", "", "user", "text", "Давайте по делу"),
            (1710000001, 22, "noise", "Noise", "", "user", "text", "АХАХ, какой бред"),
            (1710000002, 22, "noise", "Noise", "", "user", "text", "ЗАТКНИСЬ УЖЕ"),
            (1710000003, 22, "noise", "Noise", "", "user", "text", "ЗАТКНИСЬ УЖЕ"),
            (1710000004, 22, "noise", "Noise", "", "user", "text", "ЗАТКНИСЬ УЖЕ"),
        ]
        bridge.state = SimpleNamespace(
            get_recent_chat_rows=lambda chat_id, limit=80: rows,
            get_chat_title=lambda chat_id: "Все педали!",
            get_meta=lambda key, default="0": "0",
            set_meta=lambda key, value: set_meta_calls.append((key, value)),
            db_lock=nullcontext(),
            db=SimpleNamespace(execute=lambda *_args, **_kwargs: SimpleNamespace(fetchone=lambda: None)),
        )

        text = bridge.build_owner_chat_alert_text(-100123, now_ts=1710000300)

        self.assertIn("OWNER ALERT", text)
        self.assertIn("signal=конфликт/шум", text)
        self.assertIn("Все педали!", text)
        self.assertTrue(any(key == "owner_alert:conflict:-100123" for key, _value in set_meta_calls))

    def test_owner_chat_alert_detects_activity_spike_with_cooldown(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        set_meta_calls = []
        rows = [
            (
                1710001200 + index,
                100 + index % 3,
                f"user{index%3}",
                f"User{index%3}",
                "",
                "user",
                "text",
                f"Нейтральное длинное сообщение номер {index} без грубости",
            )
            for index in range(30)
        ]
        bridge.state = SimpleNamespace(
            get_recent_chat_rows=lambda chat_id, limit=80: rows,
            get_chat_title=lambda chat_id: "Активная группа",
            get_meta=lambda key, default="0": "0" if "owner_alert:activity" in key else default,
            set_meta=lambda key, value: set_meta_calls.append((key, value)),
            db_lock=nullcontext(),
            db=SimpleNamespace(execute=lambda *_args, **_kwargs: SimpleNamespace(fetchone=lambda: None)),
        )

        text = bridge.build_owner_chat_alert_text(-100555, now_ts=1710004200)

        self.assertIn("signal=всплеск активности", text)
        self.assertIn("user_messages_last_hour=30", text)
        self.assertTrue(any(key == "owner_alert:activity:-100555" for key, _value in set_meta_calls))

        bridge.state = SimpleNamespace(
            get_recent_chat_rows=lambda chat_id, limit=80: rows,
            get_chat_title=lambda chat_id: "Активная группа",
            get_meta=lambda key, default="0": "1710004100" if "owner_alert:activity" in key else default,
            set_meta=lambda key, value: set_meta_calls.append((key, value)),
            db_lock=nullcontext(),
            db=SimpleNamespace(execute=lambda *_args, **_kwargs: SimpleNamespace(fetchone=lambda: None)),
        )
        self.assertEqual(bridge.build_owner_chat_alert_text(-100555, now_ts=1710004200), "")

    def test_owner_chat_alert_detects_unanswered_questions(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        set_meta_calls = []
        rows = [
            (1710003000, 11, "asker", "Asker", "", "user", "text", "Ребята, что тут решили по батарейкам?"),
            (1710003060, 22, "other", "Other", "", "user", "text", "Я пока смотрю новый смартфон"),
            (1710003120, 33, "other2", "Other2", "", "user", "text", "Вообще камера интересная"),
        ]
        bridge.state = SimpleNamespace(
            get_recent_chat_rows=lambda chat_id, limit=80: rows,
            get_chat_title=lambda chat_id: "Вопросный чат",
            get_meta=lambda key, default="0": "0",
            set_meta=lambda key, value: set_meta_calls.append((key, value)),
            db_lock=nullcontext(),
            db=SimpleNamespace(execute=lambda *_args, **_kwargs: SimpleNamespace(fetchone=lambda: None)),
        )

        text = bridge.build_owner_chat_alert_text(-100777, now_ts=1710003600)

        self.assertIn("signal=вопросы без ответа", text)
        self.assertIn("unanswered_questions:", text)
        self.assertTrue(any(key == "owner_alert:unanswered:-100777" for key, _value in set_meta_calls))

    def test_chat_newcomer_summary_detects_recent_participant(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        bridge.state = SimpleNamespace(
            db_lock=nullcontext(),
            db=SimpleNamespace(
                execute=lambda *_args, **_kwargs: SimpleNamespace(
                    fetchone=lambda: {
                        "user_id": 55,
                        "username": "newguy",
                        "first_name": "New",
                        "last_name": "Guy",
                        "first_seen_at": 1710001000,
                        "last_seen_at": 1710003500,
                    }
                )
            ),
        )

        summary = bridge.get_chat_newcomer_summary(-100999, now_ts=1710003600)

        self.assertIn("newcomer_signal:", summary)
        self.assertIn("@newguy id=55", summary)

    def test_recent_chat_report_prompt_uses_chat_intelligence_structure(self):
        prompts = []
        sent_messages = []
        history = []
        events = []
        finished = []
        rows = [
            (1710000000, 11, "calm", "Calm", "", "user", "text", "Давайте по делу"),
            (1710000001, 22, "noise", "Noise", "", "user", "text", "АХАХ, какой бред"),
            (1710000002, 22, "noise", "Noise", "", "user", "text", "ЗАТКНИСЬ УЖЕ"),
            (1710000003, 22, "noise", "Noise", "", "user", "text", "ЗАТКНИСЬ УЖЕ"),
            (1710000004, None, "", "", "", "assistant", "answer", "Jarvis ответил"),
        ]
        state = SimpleNamespace(
            get_recent_chat_rows=lambda chat_id, limit=100: rows,
            append_history=lambda chat_id, role, text: history.append((chat_id, role, text)),
            get_chat_title=lambda chat_id, fallback: fallback or f"chat-{chat_id}",
            record_event=lambda chat_id, user_id, role, message_type, text: events.append((chat_id, user_id, role, message_type, text)),
            finish_chat_task=lambda chat_id: finished.append(chat_id),
        )
        bridge = SimpleNamespace(
            state=state,
            ask_codex=lambda chat_id, prompt, **kwargs: prompts.append((chat_id, prompt, kwargs)) or "report ready",
            safe_send_text=lambda chat_id, text, reply_to_message_id=None: sent_messages.append((chat_id, text, reply_to_message_id)),
        )

        TelegramBridge.run_recent_chat_report_task(
            bridge,
            chat_id=-100,
            user_id=OWNER_USER_ID,
            text="что тут происходит",
            message={"message_id": 77, "chat": {"type": "group", "title": "Test Chat"}},
        )

        self.assertEqual(len(prompts), 1)
        prompt = prompts[0][1]
        self.assertIn("1. Главная тема обсуждения", prompt)
        self.assertIn("2. Самые активные участники", prompt)
        self.assertIn("3. Где мнения расходятся", prompt)
        self.assertIn("4. Что подтверждено / что пока только предположение", prompt)
        self.assertIn("5. Что сейчас обсуждают practically", prompt)
        self.assertIn("Внутренние сигналы трения/шума для grounding", prompt)
        self.assertIn("@noise id=22", prompt)
        self.assertIn("только к этой выборке", prompt)
        self.assertEqual(len(sent_messages), 1)
        self.assertEqual(sent_messages[0][0], -100)
        self.assertEqual(sent_messages[0][2], 77)
        self.assertIn("report ready", sent_messages[0][1])
        self.assertIn("6. Границы и уверенность", sent_messages[0][1])
        self.assertIn("не по всей истории чата", sent_messages[0][1])
        self.assertIn("уверенность по активности участников", sent_messages[0][1])
        self.assertEqual(finished, [-100])

    def test_who_said_appends_scope_boundaries(self):
        sent_messages = []
        bridge = TelegramBridge.__new__(TelegramBridge)
        bridge.state = SimpleNamespace(
            search_events=lambda chat_id, query, limit=12: [
                (1710000000, 22, "noise", "Noise", "", "user", "text", "MAX это ломает"),
                (1710000001, 22, "noise", "Noise", "", "user", "text", "MAX это ломает"),
            ]
        )
        bridge.safe_send_text = lambda chat_id, text: sent_messages.append((chat_id, text))

        self.assertTrue(bridge.handle_who_said_command(-100, "MAX"))
        self.assertEqual(len(sent_messages), 1)
        self.assertIn("Границы ответа:", sent_messages[0][1])
        self.assertIn("локального поиска по chat_events", sent_messages[0][1])
        self.assertIn("не полный вывод по всей истории чата", sent_messages[0][1])

    def test_conflicts_text_appends_scope_boundaries(self):
        service = OwnerCommandService(
            owner_user_id=OWNER_USER_ID,
            is_owner_private_chat_func=lambda *_args, **_kwargs: True,
            memory_user_usage_text="",
            reflections_usage_text="",
            chat_digest_usage_text="",
        )
        bridge = SimpleNamespace(
            build_actor_name=lambda user_id, username, first_name, last_name, role: f"@{username}" if username else str(user_id),
            state=SimpleNamespace(
                get_recent_chat_rows=lambda chat_id, limit=80: [
                    (1710000000, 22, "noise", "Noise", "", "user", "text", "ЗАТКНИСЬ УЖЕ"),
                ],
                get_chat_title=lambda chat_id: "Test Chat",
                resolve_chat_user=lambda chat_id, raw: (22, "@noise"),
                db_lock=nullcontext(),
                db=SimpleNamespace(
                    execute=lambda *_args, **_kwargs: SimpleNamespace(fetchall=lambda: [])
                ),
            ),
        )

        text = service.render_conflicts_text(bridge, -100)

        self.assertIn("Границы ответа:", text)
        self.assertIn("последним 80 сообщениям", text)
        self.assertIn("эвристикой", text)

    def test_public_control_panel_keeps_rating_and_appeal_entry_points(self):
        renderer = ControlPanelRenderer(
            owner_user_id=1,
            owner_username="owner",
            public_home_text="stub",
            commands_list_text="",
            control_panel_sections={"home", "owner_root", "profile", "achievements", "top_week", "appeals"},
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
                render_achievements=lambda user_id: f"ach:{user_id}",
                render_top_all_time=lambda page=1: f"top-all:{page}",
                render_top_historical=lambda page=1: f"top-history:{page}",
                render_top_week=lambda page=1: f"top-week:{page}",
                render_top_day=lambda page=1: f"top-day:{page}",
                render_top_social=lambda page=1: f"top-social:{page}",
                render_top_season=lambda page=1: f"top-season:{page}",
                render_top_reactions_received=lambda page=1: f"top-reactions-received:{page}",
                render_top_reactions_given=lambda page=1: f"top-reactions-given:{page}",
                render_top_activity=lambda page=1: f"top-activity:{page}",
                render_top_behavior=lambda page=1: f"top-behavior:{page}",
                render_top_achievements=lambda page=1: f"top-achievements:{page}",
                render_top_messages=lambda page=1: f"top-messages:{page}",
                render_top_helpful=lambda page=1: f"top-helpful:{page}",
                render_top_streak=lambda page=1: f"top-streak:{page}",
            ),
        )

        text, markup = renderer.build_control_panel(bridge, 2, "home")
        profile_text, profile_markup = renderer.build_control_panel(bridge, 2, "profile")
        top_text, top_markup = renderer.build_control_panel(bridge, 2, "top_week")
        appeals_text, appeals_markup = renderer.build_control_panel(bridge, 2, "appeals")

        self.assertEqual(text, "stub")
        self.assertEqual(
            markup,
            {
                "inline_keyboard": [
                    [{"text": "Мой профиль", "callback_data": "ui:profile"}, {"text": "Все топы", "callback_data": "ui:top"}],
                    [{"text": "Достижения", "callback_data": "ui:achievements"}, {"text": "Рейтинг ачивок", "callback_data": "ui:top:achievements:1"}],
                    [{"text": "Реакции+", "callback_data": "ui:top:reactions:1"}, {"text": "За неделю", "callback_data": "ui:top:week:1"}],
                    [{"text": "Сообщения", "callback_data": "ui:top:messages:1"}, {"text": "Полезность", "callback_data": "ui:top:helpful:1"}],
                    [{"text": "Апелляции", "callback_data": "ui:appeals"}],
                ]
            },
        )
        self.assertIn("JARVIS • МОЙ ПРОФИЛЬ", profile_text)
        self.assertIn("profile:2", profile_text)
        self.assertEqual(profile_markup["inline_keyboard"][0][0]["callback_data"], "ui:top")
        self.assertEqual(profile_markup["inline_keyboard"][0][1]["callback_data"], "ui:achievements")
        self.assertEqual(top_text, "top-week:1")
        self.assertEqual(top_markup["inline_keyboard"][-1][0]["callback_data"], "ui:home")
        self.assertIn("JARVIS • АПЕЛЛЯЦИИ", appeals_text)
        self.assertEqual(appeals_markup["inline_keyboard"][0][0]["callback_data"], "ui:appeal:new")

    def test_public_top_menu_includes_reaction_and_extra_rating_sections(self):
        renderer = ControlPanelRenderer(
            owner_user_id=1,
            owner_username="owner",
            public_home_text="stub",
            commands_list_text="",
            control_panel_sections={"home", "profile", "top_menu", "top_reactions_received", "top_messages", "top_helpful", "top_streak"},
            has_chat_access_func=lambda _authorized_user_ids, _user_id: False,
            format_duration_seconds_func=lambda value: str(value),
            truncate_text_func=lambda text, limit: text[:limit],
            render_git_status_summary_func=lambda *_args, **_kwargs: "",
            render_git_last_commits_func=lambda *_args, **_kwargs: "",
            render_admin_command_catalog_func=lambda *_args, **_kwargs: "",
        )
        bridge = SimpleNamespace(
            state=SimpleNamespace(authorized_user_ids=set()),
            appeals=SimpleNamespace(get_case_snapshot=lambda _user_id: {}, get_user_appeals=lambda _user_id, limit=0: []),
            legacy=SimpleNamespace(
                render_dashboard_summary=lambda user_id: f"profile:{user_id}",
                render_achievements=lambda user_id: f"ach:{user_id}",
                render_top_all_time=lambda page=1: f"top-all:{page}",
                render_top_historical=lambda page=1: f"top-history:{page}",
                render_top_week=lambda page=1: f"top-week:{page}",
                render_top_day=lambda page=1: f"top-day:{page}",
                render_top_social=lambda page=1: f"top-social:{page}",
                render_top_season=lambda page=1: f"top-season:{page}",
                render_top_reactions_received=lambda page=1: f"top-reactions-received:{page}",
                render_top_reactions_given=lambda page=1: f"top-reactions-given:{page}",
                render_top_activity=lambda page=1: f"top-activity:{page}",
                render_top_behavior=lambda page=1: f"top-behavior:{page}",
                render_top_achievements=lambda page=1: f"top-achievements:{page}",
                render_top_messages=lambda page=1: f"top-messages:{page}",
                render_top_helpful=lambda page=1: f"top-helpful:{page}",
                render_top_streak=lambda page=1: f"top-streak:{page}",
            ),
        )

        menu_text, menu_markup = renderer.build_control_panel(bridge, 2, "top_menu")
        reactions_text, reactions_markup = renderer.build_control_panel(bridge, 2, "top_reactions_received", "2")

        self.assertIn("реакции полученные и отправленные", menu_text)
        flat_buttons = [button["text"] for row in menu_markup["inline_keyboard"] for button in row]
        self.assertIn("Реакции+", flat_buttons)
        self.assertIn("Реакции→", flat_buttons)
        self.assertIn("Активность", flat_buttons)
        self.assertIn("Поведение", flat_buttons)
        self.assertIn("Сообщения", flat_buttons)
        self.assertIn("Полезность", flat_buttons)
        self.assertIn("Стрик", flat_buttons)
        self.assertIn("Ачивки", flat_buttons)
        self.assertEqual(reactions_text, "top-reactions-received:2")
        self.assertIn("ui:top:reactions:1", [button["callback_data"] for row in reactions_markup["inline_keyboard"] for button in row])

    def test_public_top_callback_with_page_is_routed_to_section_payload(self):
        edits = []
        handler = UIHandlers(
            owner_user_id=1,
            access_denied_text="denied",
            ui_pending_appeal="await_appeal_text",
            ui_pending_approve_comment="await_appeal_approve_comment",
            ui_pending_reject_comment="await_appeal_reject_comment",
            ui_pending_close_comment="await_appeal_close_comment",
            admin_help_sections=set(),
            public_help_sections=set(),
            control_panel_sections={"top_week", "top_menu"},
        )
        bridge = SimpleNamespace(
            answer_callback_query=lambda _callback_query_id: None,
            log=lambda _message: None,
            has_chat_access=lambda _authorized_user_ids, _user_id: False,
            has_public_callback_access=lambda _data: True,
            state=SimpleNamespace(
                authorized_user_ids=set(),
                set_ui_session=lambda *_args, **_kwargs: None,
                get_ui_session=lambda _user_id: None,
            ),
            build_control_panel=lambda _user_id, section, payload="": (f"{section}:{payload}", {"inline_keyboard": []}),
            edit_inline_message=lambda chat_id, message_id, text, markup: edits.append((chat_id, message_id, text, markup)),
            is_message_not_modified_error=lambda _error: False,
            is_message_edit_recoverable_error=lambda _error: False,
        )

        handler.handle_callback_query(
            bridge,
            {
                "id": "cb1",
                "data": "ui:top:week:3",
                "message": {"chat": {"id": 100}, "message_id": 55},
                "from": {"id": 2},
            },
        )

        self.assertEqual(edits[0][2], "top_week:3")

    def test_reaction_sync_updates_received_metrics_for_message_author(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / "ratings.db")
            self._create_minimal_chat_events_schema(db_path)
            adapter = LegacyJarvisAdapter(db_path, bridge_db_path=db_path)
            with adapter.repository.connect() as conn:
                adapter.repository.ensure_profile(conn, 10, first_name="Author")
                adapter.repository.ensure_profile(conn, 20, first_name="Reactor")
                conn.execute(
                    """INSERT INTO chat_events
                    (chat_id, message_id, user_id, username, first_name, last_name, chat_type, role, message_type, text, reply_to_message_id, reply_to_user_id, reply_to_username, forward_origin, has_media, file_kind, is_edited)
                    VALUES (?, ?, ?, '', ?, '', 'supergroup', 'user', 'text', ?, NULL, NULL, '', '', 0, '', 0)""",
                    (-100, 501, 10, "Author", "hello"),
                )
                conn.commit()

            adapter.sync_reaction(-100, 20, 501, reactions_added=1)

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                author = conn.execute("SELECT reactions_received FROM progression_profiles WHERE user_id = 10").fetchone()
                reactor = conn.execute("SELECT reactions_given FROM progression_profiles WHERE user_id = 20").fetchone()
                received_event = conn.execute(
                    "SELECT COUNT(*) FROM score_events WHERE user_id = 10 AND chat_id = -100 AND source_message_id = 501 AND event_type = 'reaction_received'"
                ).fetchone()[0]

            self.assertEqual(author["reactions_received"], 1)
            self.assertEqual(reactor["reactions_given"], 1)
            self.assertEqual(received_event, 1)

    def test_reaction_received_backfill_recovers_missing_metrics_from_chat_events(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / "ratings.db")
            self._create_minimal_chat_events_schema(db_path)
            adapter = LegacyJarvisAdapter(db_path, bridge_db_path=db_path)
            with adapter.repository.connect() as conn:
                adapter.repository.ensure_profile(conn, 10, first_name="Author")
                adapter.repository.ensure_profile(conn, 20, first_name="Reactor")
                conn.execute(
                    """INSERT INTO chat_events
                    (chat_id, message_id, user_id, username, first_name, last_name, chat_type, role, message_type, text, reply_to_message_id, reply_to_user_id, reply_to_username, forward_origin, has_media, file_kind, is_edited)
                    VALUES (?, ?, ?, '', ?, '', 'supergroup', 'user', 'text', ?, NULL, NULL, '', '', 0, '', 0)""",
                    (-100, 777, 10, "Author", "hello"),
                )
                conn.execute(
                    """INSERT INTO chat_events
                    (chat_id, message_id, user_id, username, first_name, last_name, chat_type, role, message_type, text, reply_to_message_id, reply_to_user_id, reply_to_username, forward_origin, has_media, file_kind, is_edited)
                    VALUES (?, ?, ?, '', ?, '', 'supergroup', 'user', 'reaction', ?, NULL, NULL, '', '', 0, '', 0)""",
                    (-100, 777, 20, "Reactor", "[Реакция на message_id=777: 🔥]"),
                )
                conn.commit()

            adapter.repair_reaction_received_metrics()

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                author = conn.execute("SELECT reactions_received FROM progression_profiles WHERE user_id = 10").fetchone()
                received_event = conn.execute(
                    "SELECT COUNT(*) FROM score_events WHERE user_id = 10 AND chat_id = -100 AND source_message_id = 777 AND event_type = 'reaction_received'"
                ).fetchone()[0]

            self.assertEqual(author["reactions_received"], 1)
            self.assertEqual(received_event, 1)

    def test_reaction_repeat_on_same_message_counts_once(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / "ratings.db")
            self._create_minimal_chat_events_schema(db_path)
            adapter = LegacyJarvisAdapter(db_path, bridge_db_path=db_path)
            with adapter.repository.connect() as conn:
                adapter.repository.ensure_profile(conn, 10, first_name="Author")
                adapter.repository.ensure_profile(conn, 20, first_name="Reactor")
                conn.execute(
                    """INSERT INTO chat_events
                    (chat_id, message_id, user_id, username, first_name, last_name, chat_type, role, message_type, text, reply_to_message_id, reply_to_user_id, reply_to_username, forward_origin, has_media, file_kind, is_edited)
                    VALUES (?, ?, ?, '', ?, '', 'supergroup', 'user', 'text', ?, NULL, NULL, '', '', 0, '', 0)""",
                    (-100, 777, 10, "Author", "hello"),
                )
                conn.commit()

            adapter.sync_reaction(-100, 20, 777, reactions_added=1)
            adapter.sync_reaction(-100, 20, 777, reactions_added=1)

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                reactor = conn.execute("SELECT reactions_given FROM progression_profiles WHERE user_id = 20").fetchone()
                author = conn.execute("SELECT reactions_received FROM progression_profiles WHERE user_id = 10").fetchone()
                reaction_events = conn.execute(
                    "SELECT COUNT(*) FROM score_events WHERE user_id = 20 AND event_type = 'reaction_given' AND source_message_id = 777"
                ).fetchone()[0]
                links = conn.execute(
                    "SELECT COUNT(*) FROM reaction_links WHERE actor_user_id = 20 AND chat_id = -100 AND message_id = 777"
                ).fetchone()[0]

            self.assertEqual(reactor["reactions_given"], 1)
            self.assertEqual(author["reactions_received"], 1)
            self.assertEqual(reaction_events, 1)
            self.assertEqual(links, 1)

    def test_invalid_hidden_achievement_unlock_is_revoked_when_requirements_fail(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / "ratings.db")
            self._create_minimal_chat_events_schema(db_path)
            adapter = LegacyJarvisAdapter(db_path, bridge_db_path=db_path)
            now_ts = 1774718692
            with adapter.repository.connect() as conn:
                adapter.repository.ensure_profile(conn, 10, first_name="alex")
                conn.execute(
                    """UPDATE progression_profiles
                    SET msg_count = 31,
                        behavior_score = 100,
                        good_standing_days = 1,
                        updated_at = ?
                    WHERE user_id = 10""",
                    (now_ts,),
                )
                conn.execute(
                    """INSERT OR REPLACE INTO user_achievement_state
                    (user_id, code, progress_value, progress_target, unlocked_at, tier_achieved, last_evaluated_at)
                    VALUES (?, 'silent_guard', 100, 100, ?, 3, ?)""",
                    (10, now_ts, now_ts),
                )
                adapter.repository.record_score_event(
                    conn,
                    user_id=10,
                    chat_id=0,
                    event_type="achievement_unlock",
                    xp_delta=90,
                    score_delta=140,
                    reason="Тихий страж",
                    metadata={"code": "silent_guard", "rarity": "epic"},
                    created_at=now_ts,
                )
                conn.commit()

            adapter.repair_invalid_achievement_unlocks()

            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT unlocked_at, tier_achieved FROM user_achievement_state WHERE user_id = 10 AND code = 'silent_guard'"
                ).fetchone()
                event_count = conn.execute(
                    "SELECT COUNT(*) FROM score_events WHERE user_id = 10 AND event_type = 'achievement_unlock' AND metadata_json LIKE '%\"code\": \"silent_guard\"%'"
                ).fetchone()[0]

            self.assertIsNone(row[0])
            self.assertEqual(row[1], 0)
            self.assertEqual(event_count, 0)

    def test_metric_based_achievement_unlock_is_revoked_when_target_no_longer_met(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / "ratings.db")
            self._create_minimal_chat_events_schema(db_path)
            adapter = LegacyJarvisAdapter(db_path, bridge_db_path=db_path)
            now_ts = 1774718692
            with adapter.repository.connect() as conn:
                adapter.repository.ensure_profile(conn, 10, first_name="alex")
                conn.execute(
                    """UPDATE progression_profiles
                    SET reactions_given = 15,
                        msg_count = 25,
                        contribution_score = 30,
                        updated_at = ?
                    WHERE user_id = 10""",
                    (now_ts,),
                )
                conn.execute(
                    """INSERT OR REPLACE INTO user_achievement_state
                    (user_id, code, progress_value, progress_target, unlocked_at, tier_achieved, last_evaluated_at)
                    VALUES (?, 'warm_support', 15, 15, ?, 1, ?)""",
                    (10, now_ts, now_ts),
                )
                adapter.repository.record_score_event(
                    conn,
                    user_id=10,
                    chat_id=0,
                    event_type="achievement_unlock",
                    xp_delta=35,
                    score_delta=30,
                    reason="Тёплая поддержка",
                    metadata={"code": "warm_support", "rarity": "common"},
                    created_at=now_ts,
                )
                conn.commit()

            adapter.repair_invalid_achievement_unlocks()

            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT unlocked_at, tier_achieved FROM user_achievement_state WHERE user_id = 10 AND code = 'warm_support'"
                ).fetchone()
                event_count = conn.execute(
                    "SELECT COUNT(*) FROM score_events WHERE user_id = 10 AND event_type = 'achievement_unlock' AND metadata_json LIKE '%\"code\": \"warm_support\"%'"
                ).fetchone()[0]

            self.assertIsNone(row[0])
            self.assertEqual(row[1], 0)
            self.assertEqual(event_count, 0)

    def test_reaction_top_excludes_zero_rows_and_supports_pages_beyond_hundred(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / "ratings.db")
            self._create_minimal_chat_events_schema(db_path)
            adapter = LegacyJarvisAdapter(db_path, bridge_db_path=db_path)
            with adapter.repository.connect() as conn:
                for user_id in range(1, 123):
                    adapter.repository.ensure_profile(conn, user_id, first_name=f"User{user_id}")
                    conn.execute(
                        """UPDATE progression_profiles
                        SET reactions_received = ?, total_score = ?, level = 1, updated_at = strftime('%s','now')
                        WHERE user_id = ?""",
                        (123 - user_id, 1000 - user_id, user_id),
                    )
                adapter.repository.ensure_profile(conn, 999, first_name="Zero")
                conn.execute(
                    """UPDATE progression_profiles
                    SET reactions_received = 0, total_score = 9999, level = 1, updated_at = strftime('%s','now')
                    WHERE user_id = 999"""
                )
                conn.commit()

            rating = RatingService(adapter.repository)
            page_1 = rating.render_top_reactions_received(page=1)
            page_11 = rating.render_top_reactions_received(page=11)
            page_13 = rating.render_top_reactions_received(page=13)

            self.assertIn("1/13", page_1)
            self.assertIn("11/13", page_11)
            self.assertIn("13/13", page_13)
            self.assertIn("из 122.", page_1)
            self.assertNotIn("Zero", page_1)
            self.assertNotIn("Zero", page_13)

    def test_owner_command_catalog_includes_new_memory_and_moderation_commands(self):
        text = render_admin_command_catalog(owner_user_id=1, owner_username="owner")

        self.assertIn("/chatdeep [chat_id]", text)
        self.assertIn("/whois [@username|user_id]", text)
        self.assertIn("/whatshappening [chat_id]", text)
        self.assertIn("/summary24h [chat_id]", text)
        self.assertIn("/conflicts [chat_id]", text)
        self.assertIn("/ownergraph", text)
        self.assertIn("/welcome on|off|status", text)
        self.assertIn("/setwarnlimit <число>", text)

    def test_owner_root_panel_mentions_command_registry_and_files(self):
        renderer = ControlPanelRenderer(
            owner_user_id=1,
            owner_username="owner",
            public_home_text="stub",
            commands_list_text="",
            control_panel_sections={"home", "owner_root", "owner_memory", "owner_files", "owner_commands", "owner_overview", "owner_people", "owner_capabilities", "owner_automation", "owner_system_map"},
            has_chat_access_func=lambda _authorized_user_ids, _user_id: True,
            format_duration_seconds_func=lambda value: str(value),
            truncate_text_func=lambda text, limit: text[:limit],
            render_git_status_summary_func=lambda *_args, **_kwargs: "",
            render_git_last_commits_func=lambda *_args, **_kwargs: "",
            render_admin_command_catalog_func=lambda *_args, **_kwargs: "catalog",
        )
        bridge = SimpleNamespace(state=SimpleNamespace(authorized_user_ids={1}))

        text, markup = renderer.build_control_panel(bridge, 1, "owner_root")
        memory_text, _memory_markup = renderer.build_control_panel(bridge, 1, "owner_memory")
        overview_text, _overview_markup = renderer.build_control_panel(bridge, 1, "owner_overview")
        people_text, _people_markup = renderer.build_control_panel(bridge, 1, "owner_people")
        capabilities_text, _capabilities_markup = renderer.build_control_panel(bridge, 1, "owner_capabilities")
        automation_text, _automation_markup = renderer.build_control_panel(bridge, 1, "owner_automation")
        system_map_text, _system_map_markup = renderer.build_control_panel(bridge, 1, "owner_system_map")

        self.assertIn("Все команды", text)
        self.assertIn("Файлы и медиа", text)
        self.assertIn("Обзор чатов", text)
        self.assertIn("Люди и связи", text)
        self.assertIn("Что умеет Jarvis", text)
        self.assertIn("Авто-режимы и алерты", text)
        self.assertIn("Карта системы", text)
        flat_buttons = [button["text"] for row in markup["inline_keyboard"] for button in row]
        self.assertIn("Все команды", flat_buttons)
        self.assertIn("Файлы и медиа", flat_buttons)
        self.assertIn("Обзор чатов", flat_buttons)
        self.assertIn("Люди и связи", flat_buttons)
        self.assertIn("Что умеет Jarvis", flat_buttons)
        self.assertIn("Авто-режимы и алерты", flat_buttons)
        self.assertIn("Карта системы", flat_buttons)
        self.assertIn("/whatshappening", memory_text)
        self.assertIn("/chatdeep", memory_text)
        self.assertIn("/whatshappening", overview_text)
        self.assertIn("/ownergraph", people_text)
        self.assertIn("daily/weekly owner digests", capabilities_text)
        self.assertIn("вопросы без ответа", automation_text)
        self.assertIn("health-aware supervisor", system_map_text)

    def test_owner_runtime_panel_separates_current_session_and_24h_tail(self):
        renderer = ControlPanelRenderer(
            owner_user_id=1,
            owner_username="owner",
            public_home_text="stub",
            commands_list_text="",
            control_panel_sections={"home", "owner_runtime"},
            has_chat_access_func=lambda _authorized_user_ids, _user_id: True,
            format_duration_seconds_func=lambda value: str(value),
            truncate_text_func=lambda text, limit: text[:limit],
            render_git_status_summary_func=lambda *_args, **_kwargs: "",
            render_git_last_commits_func=lambda *_args, **_kwargs: "",
            render_admin_command_catalog_func=lambda *_args, **_kwargs: "catalog",
        )
        bridge = SimpleNamespace(
            state=SimpleNamespace(
                authorized_user_ids={1},
                get_meta=lambda _key, _default="0": "0",
            ),
            owner_autofix_enabled=lambda: False,
            refresh_world_state_registry=lambda *_args, **_kwargs: {
                "git_dirty_count": 34,
                "window_errors_count": 19,
                "window_warning_count": 50,
            },
            recompute_drive_scores=lambda _state: {
                "runtime_risk_pressure": 36.0,
                "uncertainty_pressure": 36.0,
            },
            inspect_runtime_log=lambda: {
                "restart_count": 52,
                "session_severe_error_count": 0,
                "session_warning_count": 0,
            },
            heartbeat_path=SimpleNamespace(exists=lambda: False),
            get_telegram_ping_text=lambda: "ok",
        )

        with patch("handlers.control_panel_renderer.collect_diagnostics_metrics", return_value=SimpleNamespace(degraded_count=3)):
            text, _markup = renderer.build_control_panel(bridge, 1, "owner_runtime")

        self.assertIn("Текущая сессия:", text)
        self.assertIn("Хвост за 24 часа:", text)
        self.assertIn("• Серьёзные ошибки после запуска: 0", text)
        self.assertIn("• Серьёзные ошибки: 19", text)
        self.assertIn("• Предупреждения: 50", text)

    def test_owner_live_watchlist_and_reliable_panels_render(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "memory.db"
            state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
            state.record_event(-1001, 42, "user", "text", "иди ты, это бред", reply_to_user_id=OWNER_USER_ID, first_name="Noise")
            state.record_event(-1001, 43, "user", "text", "проверь лог, там решение", first_name="Helper")
            state.refresh_participant_behavior_profile(42, chat_id=-1001)
            state.refresh_participant_behavior_profile(43, chat_id=-1001)
            renderer = ControlPanelRenderer(
                owner_user_id=OWNER_USER_ID,
                owner_username="dmitry",
                public_home_text="public",
                commands_list_text="commands",
                control_panel_sections={"owner_watchlist", "owner_reliable"},
                has_chat_access_func=lambda _authorized, _user_id: True,
                format_duration_seconds_func=lambda value: str(value),
                truncate_text_func=lambda text, limit: text[:limit],
                render_git_status_summary_func=lambda *_args, **_kwargs: "",
                render_git_last_commits_func=lambda *_args, **_kwargs: "",
                render_admin_command_catalog_func=lambda *_args, **_kwargs: "catalog",
            )
            bridge = SimpleNamespace(
                state=state,
                owner_handlers=SimpleNamespace(
                    render_watchlist_text=lambda _bridge, chat_id: f"watchlist:{chat_id}",
                    render_reliable_text=lambda _bridge, chat_id: f"reliable:{chat_id}",
                ),
            )
            watch_text, watch_markup = renderer.build_control_panel(bridge, OWNER_USER_ID, "owner_watchlist", "-1001")
            reliable_text, reliable_markup = renderer.build_control_panel(bridge, OWNER_USER_ID, "owner_reliable", "-1001")
            state.db.close()

        self.assertIn("watchlist:-1001", watch_text)
        self.assertIn("reliable:-1001", reliable_text)
        self.assertTrue(watch_markup["inline_keyboard"])
        self.assertTrue(reliable_markup["inline_keyboard"])

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

    def test_restart_runtime_digest_includes_enterprise_health_and_pending_jobs(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        meta = {
            "pending_enterprise_jobs": '[{"job_id":"abc","chat_id":-100,"delivery_chat_id":6102780373}]',
        }
        bridge.state = SimpleNamespace(get_meta=lambda key, default="": meta.get(key, default))
        bridge.config = SimpleNamespace(enterprise_server_base_url="http://127.0.0.1:8766")
        bridge.session = SimpleNamespace(get=lambda _url, timeout=2: SimpleNamespace(ok=True))

        text = TelegramBridge.build_restart_runtime_digest(bridge)

        self.assertIn("Enterprise server: ok", text)
        self.assertIn("Pending enterprise jobs: 1", text)
        self.assertIn("abc: source=-100 delivery=6102780373", text)

    def test_owner_contact_shortcut_does_not_override_reply_context(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        bridge.build_reply_context = lambda _chat_id, _message: "Reply target text: исходное сообщение"

        with patch("tg_codex_bridge.build_meta_identity_answer", return_value=""):
            with patch("tg_codex_bridge.build_owner_contact_reply", return_value="Привет, Дмитрий. На связи."):
                with patch("tg_codex_bridge.analyze_request_route", side_effect=RuntimeError("route-called")):
                    with self.assertRaisesRegex(RuntimeError, "route-called"):
                        TelegramBridge.ask_codex(
                            bridge,
                            chat_id=-100,
                            user_text="Привет",
                            user_id=OWNER_USER_ID,
                            chat_type="supergroup",
                            assistant_persona="jarvis",
                            message={"reply_to_message": {"message_id": 1}},
                        )

    def test_owner_cross_chat_memory_context_lists_active_chats_and_summaries(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "memory.db"
            state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
            state.record_event(-1001, OWNER_USER_ID, "user", "text", "Обсуждаем смартфоны и сеть")
            state.record_event(-1002, OWNER_USER_ID, "user", "text", "Тут про чат и модерацию")
            state.record_event(-1001, 42, "user", "text", "Я тоже тут обсуждаю смартфоны")
            state.record_event(-1002, 42, "user", "text", "И здесь тоже участвую")
            with state.db_lock:
                state.db.execute(
                    "INSERT INTO chat_runtime_cache(chat_id, chat_title, updated_at) VALUES(?, ?, strftime('%s','now')) ON CONFLICT(chat_id) DO UPDATE SET chat_title = excluded.chat_title, updated_at = excluded.updated_at",
                    (-1001, "Все педали!"),
                )
                state.db.execute(
                    "INSERT INTO chat_runtime_cache(chat_id, chat_title, updated_at) VALUES(?, ?, strftime('%s','now')) ON CONFLICT(chat_id) DO UPDATE SET chat_title = excluded.chat_title, updated_at = excluded.updated_at",
                    (-1002, "Technical"),
                )
                state.db.execute(
                    "INSERT INTO summary_snapshots(chat_id, scope, summary) VALUES(?, 'rolling', ?)",
                    (-1001, "В чате обсуждают смартфоны, связь и повседневный техно-флуд."),
                )
                state.db.execute(
                    "INSERT INTO summary_snapshots(chat_id, scope, summary) VALUES(?, 'rolling', ?)",
                    (-1002, "В группе много разговоров про правила, поведение и динамику участников."),
                )
                state.db.commit()

            text = state.get_owner_cross_chat_memory_context(limit=2)
            state.db.close()

        self.assertIn("Owner cross-chat memory:", text)
        self.assertIn("active_chat:", text)
        self.assertIn("Owner relation layer:", text)
        self.assertIn("recent_group_summary", text)

    def test_chat_profile_context_includes_title_and_top_speakers(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "memory.db"
            state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
            state.record_event(-1001, OWNER_USER_ID, "user", "text", "Сообщение от Дмитрия")
            state.record_event(-1001, 42, "user", "text", "Сообщение от участника")
            with state.db_lock:
                state.db.execute(
                    "INSERT INTO chat_runtime_cache(chat_id, chat_title, member_count, updated_at) VALUES(?, ?, ?, strftime('%s','now')) ON CONFLICT(chat_id) DO UPDATE SET chat_title = excluded.chat_title, member_count = excluded.member_count, updated_at = excluded.updated_at",
                    (-1001, "Все педали!", 61),
                )
                state.db.commit()

            text = state.get_chat_profile_context(-1001)
            state.db.close()

        self.assertIn("Group profile:", text)
        self.assertIn("title: Все педали!", text)
        self.assertIn("member_count: 61", text)
        self.assertIn("top_speakers:", text)

    def test_chat_dynamics_context_includes_tone_setters_and_dominance(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "memory.db"
            state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
            state.record_event(-1001, 42, "user", "text", "Jarvis тут странный стиль")
            state.record_event(-1001, 42, "user", "text", "Jarvis тут странный стиль")
            state.record_event(-1001, 42, "user", "text", "Jarvis тут странный стиль")
            state.record_event(-1001, 43, "user", "text", "ахах ну да")
            state.record_event(-1001, 44, "user", "text", "контекст чата важен")

            text = state.get_chat_dynamics_context(-1001, query="расскажи про чат подробнее")
            state.db.close()

        self.assertIn("tone_setters:", text)
        self.assertIn("dominance_signal:", text)
        self.assertIn("повторы и зацикливание", text)

    def test_group_deep_profile_is_persisted_and_visible_in_chat_profile(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "memory.db"
            state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
            state.record_event(-1001, OWNER_USER_ID, "user", "text", "Смартфоны, связь и тесты")
            state.record_event(-1001, 42, "user", "text", "ахах тут снова про смартфоны")
            with state.db_lock:
                state.db.execute(
                    "INSERT INTO chat_runtime_cache(chat_id, chat_title, member_count, updated_at) VALUES(?, ?, ?, strftime('%s','now')) ON CONFLICT(chat_id) DO UPDATE SET chat_title = excluded.chat_title, member_count = excluded.member_count, updated_at = excluded.updated_at",
                    (-1001, "Все педали!", 61),
                )
                state.db.commit()

            state.update_group_deep_profile(-1001)
            text = state.get_chat_profile_context(-1001)
            with state.db_lock:
                count_row = state.db.execute(
                    "SELECT COUNT(*) FROM summary_snapshots WHERE chat_id = ? AND scope = 'group_deep_profile'",
                    (-1001,),
                ).fetchone()
            state.db.close()

        self.assertGreaterEqual(int(count_row[0] or 0), 1)
        self.assertIn("Group deep profile:", text)
        self.assertIn("recurring_topics:", text)

    def test_participant_behavior_profile_tracks_conflict_and_helpfulness(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "memory.db"
            state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
            chat_id = -1001
            user_id = 42
            state.record_event(chat_id, user_id, "user", "text", "это херня, ты неправ", reply_to_user_id=OWNER_USER_ID)
            state.record_event(chat_id, user_id, "user", "text", "проверь лог, там решение и фикс", reply_to_user_id=None)
            state.record_event(chat_id, user_id, "user", "text", "это херня, ты неправ", reply_to_user_id=OWNER_USER_ID)
            state.record_event(chat_id, user_id, "user", "reaction", "[Реакция]")
            state.refresh_participant_behavior_profile(user_id, chat_id=chat_id)
            text = state.get_participant_behavior_context(chat_id, target_user_id=user_id)
            state.db.close()

        self.assertIn("Behavior profile:", text)
        self.assertIn("high_conflict", text)
        self.assertIn("owner_hostile", text)
        self.assertIn("Recent signals:", text)

    def test_whois_includes_behavior_profile_block(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "memory.db"
            state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
            chat_id = -1001
            user_id = 42
            state.record_event(chat_id, user_id, "user", "text", "иди ты, это бред", reply_to_user_id=OWNER_USER_ID, first_name="Noise")
            state.record_event(chat_id, user_id, "user", "text", "проверь лог и решение", first_name="Noise")
            bridge = SimpleNamespace(
                state=state,
                safe_send_text=lambda *_args, **_kwargs: None,
            )
            service = OwnerCommandService(
                owner_user_id=OWNER_USER_ID,
                is_owner_private_chat_func=lambda *_args, **_kwargs: True,
                memory_user_usage_text="",
                reflections_usage_text="",
                chat_digest_usage_text="",
            )
            text = service.render_whois_text(bridge, chat_id, user_id)
            state.db.close()

        self.assertIn("Behavior profile:", text)
        self.assertIn("Whois:", text)

    def test_chatdeep_includes_watchlist_and_reliable_blocks(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "memory.db"
            state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
            chat_id = -1001
            state.record_event(chat_id, 42, "user", "text", "иди ты, это бред", reply_to_user_id=OWNER_USER_ID, first_name="Noise")
            state.record_event(chat_id, 43, "user", "text", "проверь лог, там решение", first_name="Helper")
            state.refresh_participant_behavior_profile(42, chat_id=chat_id)
            state.refresh_participant_behavior_profile(43, chat_id=chat_id)
            bridge = SimpleNamespace(
                state=state,
                build_actor_name=lambda user_id, username, first_name, last_name, role: first_name or username or str(user_id),
            )
            service = OwnerCommandService(
                owner_user_id=OWNER_USER_ID,
                is_owner_private_chat_func=lambda *_args, **_kwargs: True,
                memory_user_usage_text="",
                reflections_usage_text="",
                chat_digest_usage_text="",
            )
            text = service.render_chat_deep_text(bridge, chat_id)
            state.db.close()

        self.assertIn("Watchlist", text)
        self.assertIn("Надёжные участники", text)

    def test_owner_alert_text_is_human_readable(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "memory.db"
            state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
            state.save_chat_title(-1001, "Все педали!")
            state.record_event(-1001, 42, "user", "text", "иди ты, это бред", first_name="Alex", username="alex")
            state.record_event(-1001, 43, "user", "text", "ахах ну ты даешь", first_name="Maks", username="maks")
            bridge = TelegramBridge.__new__(TelegramBridge)
            bridge.state = state
            text = TelegramBridge.build_owner_chat_alert_text(bridge, -1001, now_ts=int(time.time()))
            state.db.close()

        self.assertIn("Чат: Все педали!", text)
        self.assertIn("Сигнал:", text)
        self.assertIn("Кто активнее всего", text)

    def test_pending_enterprise_job_is_persisted_and_cleared(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        meta = {}
        task_updates = []
        task_events = []
        bridge.state = SimpleNamespace(
            get_meta=lambda key, default="": meta.get(key, default),
            set_meta=lambda key, value: meta.__setitem__(key, value),
            upsert_task_run=lambda **kwargs: task_updates.append(("upsert", kwargs)),
            get_task_run=lambda _task_id: {"chat_id": 1, "request_trace_id": "req-1"},
            update_task_run=lambda *args, **kwargs: task_updates.append(("update", args, kwargs)),
            record_task_event=lambda **kwargs: task_events.append(kwargs),
        )

        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "abc", "chat_id": 1})
        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "def", "chat_id": 2})
        self.assertIn('"job_id": "abc"', meta["pending_enterprise_jobs"])
        self.assertIn('"job_id": "def"', meta["pending_enterprise_jobs"])
        self.assertEqual(task_updates[0][0], "upsert")
        self.assertEqual(task_events[0]["phase"], "job_registered")

        TelegramBridge.clear_pending_enterprise_job(bridge, "abc")
        self.assertNotIn('"job_id": "abc"', meta["pending_enterprise_jobs"])
        self.assertIn('"job_id": "def"', meta["pending_enterprise_jobs"])

    def test_pending_enterprise_jobs_can_be_cleared_by_chat_after_delivery(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        meta = {}
        task_events = []
        bridge.state = SimpleNamespace(
            get_meta=lambda key, default="": meta.get(key, default),
            set_meta=lambda key, value: meta.__setitem__(key, value),
            upsert_task_run=lambda **_kwargs: None,
            get_task_run=lambda _task_id: {"chat_id": 1, "request_trace_id": "req-1"},
            update_task_run=lambda *args, **_kwargs: None,
            record_task_event=lambda **kwargs: task_events.append(kwargs),
        )

        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "abc", "chat_id": 1})
        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "def", "chat_id": 2})
        TelegramBridge.register_pending_enterprise_job(bridge, {"job_id": "ghi", "chat_id": 1})

        TelegramBridge.clear_pending_enterprise_jobs_for_chat(bridge, 1)

        self.assertNotIn('"job_id": "abc"', meta["pending_enterprise_jobs"])
        self.assertNotIn('"job_id": "ghi"', meta["pending_enterprise_jobs"])
        self.assertIn('"job_id": "def"', meta["pending_enterprise_jobs"])
        self.assertTrue(any(item["phase"] == "queue_cleanup" for item in task_events))

    def test_record_route_diagnostic_syncs_task_run_with_truth_markers(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        diagnostics_calls = []
        task_updates = []
        task_events = []
        bridge.live_gateway = SimpleNamespace(consume_records=lambda: [])
        bridge.state = SimpleNamespace(
            record_request_diagnostic=lambda **kwargs: diagnostics_calls.append(kwargs),
            update_task_run=lambda task_id, **kwargs: task_updates.append((task_id, kwargs)),
            record_task_event=lambda **kwargs: task_events.append(kwargs),
        )

        TelegramBridge.record_route_diagnostic(
            bridge,
            chat_id=77,
            user_id=5,
            route_decision=RouteDecision(
                persona="enterprise",
                intent="project_audit",
                chat_type="private",
                route_kind="codex_workspace",
                source_label="workspace",
                use_live=False,
                use_web=False,
                use_events=True,
                use_database=True,
                use_reply=False,
                use_workspace=True,
                guardrails=("truth-only",),
                request_kind="project",
            ),
            report=SelfCheckReport(
                outcome="uncertain",
                answer="Часть результатов подтверждена, часть требует проверки.",
                flags=("needs_followup",),
                observed_basis=("workspace",),
                uncertain_points=("missing verification",),
                mode="inferred",
            ),
            started_at=time.perf_counter(),
            query_text="Проведи аудит",
            request_trace_id="req-42",
            task_id="task-42",
        )

        self.assertEqual(diagnostics_calls[0]["task_id"], "task-42")
        self.assertEqual(task_updates[0][0], "task-42")
        self.assertEqual(task_updates[0][1]["verification_state"], "inferred")
        self.assertEqual(task_updates[0][1]["outcome"], "uncertain")
        self.assertEqual(task_events[0]["phase"], "route_diagnostic")

    def test_achievement_announcements_are_deduplicated_per_chat_user_and_code(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        meta = {}
        bridge.state = SimpleNamespace(
            get_meta=lambda key, default="": meta.get(key, default),
            set_meta=lambda key, value: meta.__setitem__(key, value),
        )

        unlocked = [
            {"code": "silent_guard", "name": "Тихий страж"},
            {"code": "starter_pack", "name": "Стартовый импульс"},
        ]
        first = TelegramBridge._filter_new_achievement_announcements(bridge, -1001, 42, unlocked, cooldown_seconds=3600)
        second = TelegramBridge._filter_new_achievement_announcements(bridge, -1001, 42, unlocked, cooldown_seconds=3600)
        other_chat = TelegramBridge._filter_new_achievement_announcements(bridge, -2002, 42, unlocked, cooldown_seconds=3600)

        self.assertEqual([item["code"] for item in first], ["silent_guard", "starter_pack"])
        self.assertEqual(second, [])
        self.assertEqual([item["code"] for item in other_chat], ["silent_guard", "starter_pack"])

    def test_achievement_reason_text_uses_russian_metric_labels(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = str(Path(tmp_dir) / "ratings.db")
            self._create_minimal_chat_events_schema(db_path)
            adapter = LegacyJarvisAdapter(db_path, bridge_db_path=db_path)
            definition = adapter.achievements.get_definition("hype_engine")
            self.assertIsNotNone(definition)

            reason = adapter.achievements.build_reason_text(
                definition,
                {"reactions_given": 86, "msg_count": 117},
                86,
                80,
            )

        self.assertEqual(reason, "поставленные реакции: 86/80; условия: сообщения: 117/60")

    def test_enterprise_group_answer_is_sent_to_owner_private_chat(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        sent_messages = []
        bridge.state = SimpleNamespace(
            append_history=lambda *_args, **_kwargs: None,
            record_event=lambda *_args, **_kwargs: None,
            finish_chat_task=lambda *_args, **_kwargs: None,
        )
        bridge.ask_codex = lambda *_args, **_kwargs: "Готово."
        bridge.consume_answer_delivered_via_status = lambda _chat_id: False
        bridge.safe_send_text = lambda chat_id, text, reply_to_message_id=None: sent_messages.append((chat_id, text, reply_to_message_id))
        bridge.clear_pending_enterprise_jobs_for_chat = lambda _chat_id: None
        bridge.mark_active_group_discussion = lambda *_args, **_kwargs: None
        bridge.grant_group_followup_window = lambda *_args, **_kwargs: None

        TelegramBridge.run_text_task(
            bridge,
            chat_id=-1002377918916,
            text="Проверь",
            user_id=OWNER_USER_ID,
            chat_type="supergroup",
            assistant_persona="enterprise",
            message={"message_id": 55},
        )

        self.assertEqual(sent_messages, [(OWNER_USER_ID, "Готово.", None)])

    def test_pending_enterprise_group_resume_is_sent_to_owner_private_chat(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        sent_messages = []
        cleared_jobs = []
        bridge.js_enterprise = SimpleNamespace(wait_for_job=lambda **_kwargs: "Отчёт из чата -1002377918916:\n\nГотово после рестарта.")
        bridge.state = SimpleNamespace(
            append_history=lambda *_args, **_kwargs: None,
            record_event=lambda *_args, **_kwargs: None,
        )
        bridge.consume_answer_delivered_via_status = lambda _chat_id: False
        bridge.safe_send_text = lambda chat_id, text: sent_messages.append((chat_id, text))
        bridge.clear_pending_enterprise_job = lambda job_id: cleared_jobs.append(job_id)

        TelegramBridge._resume_pending_enterprise_job(
            bridge,
            {
                "job_id": "abc",
                "chat_id": -1002377918916,
                "delivery_chat_id": OWNER_USER_ID,
                "initial_status": "running",
            },
        )

        self.assertEqual(sent_messages, [(OWNER_USER_ID, "Отчёт из чата -1002377918916:\n\nГотово после рестарта.")])
        self.assertEqual(cleared_jobs, ["abc"])

    def test_pending_enterprise_group_resume_uses_private_progress_chat(self):
        bridge = TelegramBridge.__new__(TelegramBridge)
        calls = []
        bridge.js_enterprise = SimpleNamespace(wait_for_job=lambda **kwargs: calls.append(kwargs) or "ok")
        bridge.state = SimpleNamespace(
            append_history=lambda *_args, **_kwargs: None,
            record_event=lambda *_args, **_kwargs: None,
        )
        bridge.consume_answer_delivered_via_status = lambda _chat_id: False
        bridge.safe_send_text = lambda *_args, **_kwargs: None
        bridge.clear_pending_enterprise_job = lambda _job_id: None

        TelegramBridge._resume_pending_enterprise_job(
            bridge,
            {
                "job_id": "abc",
                "chat_id": -1002377918916,
                "delivery_chat_id": OWNER_USER_ID,
                "progress_chat_id": OWNER_USER_ID,
                "initial_status": "running",
            },
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["progress_chat_id"], OWNER_USER_ID)

    def test_enterprise_group_progress_is_created_in_owner_private_chat(self):
        status_calls = []
        wait_calls = []
        deps = JSEnterpriseServiceDeps(
            build_codex_command_func=lambda **_kwargs: [],
            build_subprocess_env_func=lambda: {},
            heartbeat_guard_factory=lambda: nullcontext(),
            normalize_whitespace_func=lambda text: text.strip(),
            postprocess_answer_func=lambda answer, _latency: answer,
            build_codex_failure_answer_func=lambda **_kwargs: "fail",
            extract_usable_codex_stdout_func=lambda text: text,
            shorten_for_log_func=lambda text, _limit: text,
            log_func=lambda _text: None,
            send_chat_action_func=lambda *_args, **_kwargs: None,
            send_status_message_func=lambda chat_id, text: status_calls.append((chat_id, text)) or 321,
            edit_status_message_func=lambda *_args, **_kwargs: True,
            update_progress_status_func=lambda *_args, **_kwargs: None,
            finish_progress_status_func=lambda *_args, **_kwargs: None,
            codex_timeout=30,
            progress_update_seconds=0.1,
            jarvis_offline_text="offline",
            upgrade_timeout_text="timeout",
            enterprise_server_base_url="http://127.0.0.1:8766",
            register_pending_job_func=lambda payload: wait_calls.append(("register", payload)),
        )
        service = JSEnterpriseService(deps)
        service._post_json = lambda *_args, **_kwargs: {"job_id": "job-1"}  # type: ignore[method-assign]
        service.wait_for_job = lambda **kwargs: wait_calls.append(("wait", kwargs)) or "ok"  # type: ignore[method-assign]

        answer = service.run_with_progress(
            chat_id=-1002377918916,
            prompt="Проверь",
            initial_status="running",
            progress_style="enterprise",
            delivery_chat_id=OWNER_USER_ID,
        )

        self.assertEqual(answer, "ok")
        self.assertEqual(status_calls, [(OWNER_USER_ID, "running")])
        self.assertEqual(wait_calls[0][1]["progress_chat_id"], OWNER_USER_ID)
        self.assertEqual(wait_calls[1][1]["progress_chat_id"], OWNER_USER_ID)

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
