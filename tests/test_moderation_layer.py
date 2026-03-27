import tempfile
import time
import unittest
from pathlib import Path

from anti_abuse_service import AntiAbuseService
from appeals_service import AppealsService
from bridge_repository import BridgeRepository
from history_service import HistoryService
from legacy_jarvis_adapter import LegacyJarvisAdapter
from moderation.anti_abuse import AntiAbuseAdapter
from moderation.appeals import AppealsAdapter
from moderation.moderation_models import ModerationContext, ModerationPolicy
from moderation.moderation_orchestrator import ModerationOrchestrator
from moderation.modlog import ModlogAdapter
from moderation.policy import ModerationTextPolicy
from moderation.sanctions import SanctionsAdapter
from moderation.warnings import WarningAdapter
from sanctions_service import SanctionsService

class ModerationLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.bridge_db = Path(self.tmpdir.name) / "bridge.sqlite3"
        self.legacy_db = Path(self.tmpdir.name) / "legacy.sqlite3"
        self.bridge_db.touch()
        self.legacy_db.touch()
        import sqlite3

        legacy_conn = sqlite3.connect(self.legacy_db)
        try:
            legacy_conn.execute(
                """CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                handled INTEGER NOT NULL DEFAULT 0,
                action_taken TEXT NOT NULL DEFAULT ''
            )"""
            )
            legacy_conn.execute(
                """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                warnings INTEGER NOT NULL DEFAULT 0
            )"""
            )
            legacy_conn.commit()
        finally:
            legacy_conn.close()
        self.repository = BridgeRepository(str(self.bridge_db))
        with self.repository.connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                created_by_user_id INTEGER,
                expires_at INTEGER,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS moderation_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                expires_at INTEGER,
                completed_at INTEGER,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )"""
            )
            conn.commit()
        self.history = HistoryService(self.repository)
        self.sanctions = SanctionsAdapter(SanctionsService(self.repository, self.history))
        self.appeals = AppealsAdapter(AppealsService(str(self.bridge_db), str(self.legacy_db)))
        self.anti_abuse = AntiAbuseAdapter(AntiAbuseService())
        self.warning_counter = {}
        self.warnings = WarningAdapter(self._add_warning, self._get_warning_count)
        self.orchestrator = ModerationOrchestrator(
            anti_abuse=self.anti_abuse,
            sanctions=self.sanctions,
            warnings=self.warnings,
            appeals=self.appeals,
            modlog=ModlogAdapter(str(self.bridge_db)),
            text_policy=ModerationTextPolicy(),
            policy=ModerationPolicy(),
            contains_profanity_func=lambda text: "нах" in text.lower() or "идиот" in text.lower(),
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def _add_warning(self, chat_id, user_id, reason, created_by_user_id, expires_at=None):
        key = (chat_id, user_id)
        self.warning_counter[key] = self.warning_counter.get(key, 0) + 1
        return self.warning_counter[key]

    def _get_warning_count(self, chat_id, user_id):
        return self.warning_counter.get((chat_id, user_id), 0)

    def test_duplicate_detection(self):
        now_ts = int(time.time())
        rows = [{"text": "купи это сейчас", "created_at": now_ts - 10}]
        score = self.anti_abuse.analyze_message("купи это сейчас", rows, now_ts)
        self.assertEqual(score.flag, "duplicate")
        self.assertEqual(score.multiplier, 0.0)

    def test_burst_detection(self):
        now_ts = int(time.time())
        rows = [{"text": f"msg{i}", "created_at": now_ts - 5} for i in range(6)]
        score = self.anti_abuse.analyze_message("новое сообщение", rows, now_ts)
        self.assertEqual(score.flag, "burst")

    def test_cooldown(self):
        remain = AntiAbuseService().cooldown_remaining_seconds(int(time.time()))
        self.assertGreaterEqual(remain, 1)

    def test_sanction_scoring(self):
        record = self.sanctions.sync_action(
            chat_id=1,
            user_id=42,
            action="mute",
            reason="spam",
            created_by_user_id=7,
            expires_at=int(time.time()) + 3600,
            source_ref="test",
        )
        self.assertEqual(record.points_delta, 80)

    def test_warn_escalation(self):
        policy = ModerationTextPolicy()
        self.assertEqual(policy.warn_escalation_action(1, ModerationPolicy(warn_limit=3)), "warn")
        self.assertEqual(policy.warn_escalation_action(3, ModerationPolicy(warn_limit=3)), "mute")

    def test_appeal_cooldown(self):
        first = self.appeals.submit(42, 100, "Прошу пересмотреть бан, это ошибка.")
        second = self.appeals.submit(42, 100, "Прошу пересмотреть бан, это ошибка.")
        self.assertIn(first.status, {"new", "auto_approved"})
        self.assertIn(second.status, {"cooldown", "duplicate", "duplicate_reason"})

    def test_appeal_duplicate_prevention(self):
        self.appeals.submit(77, 100, "Это первая апелляция по муту.")
        second = self.appeals.submit(77, 100, "Это первая апелляция по муту.")
        self.assertIn(second.status, {"cooldown", "duplicate", "duplicate_reason"})

    def test_moderation_compatibility_path(self):
        message = {"message_id": 10, "chat": {"title": "Test chat"}, "from": {"is_bot": False}}
        outcome = self.orchestrator.detect_auto_moderation(
            context=ModerationContext(
                chat_id=1,
                user_id=42,
                chat_type="group",
                chat_title="Test chat",
                message_id=10,
                text="ты идиот",
                recent_texts=("ты идиот",),
            ),
            message=message,
            bot_username="jarvis_3_0_bot",
            trigger_name="jarvis",
        )
        self.assertTrue(outcome.compatibility_used)
        self.assertIsNotNone(outcome.legacy_auto_decision)

    def test_separation_of_moderation_and_assistant_flows(self):
        notice = ModerationTextPolicy().format_public_notice(
            "user42",
            self.orchestrator.detect_auto_moderation(
                context=ModerationContext(
                    chat_id=1,
                    user_id=42,
                    chat_type="group",
                    chat_title="Test chat",
                    text="ты идиот",
                    recent_texts=("ты идиот",),
                ),
                message={"chat": {"title": "Test chat"}, "from": {"is_bot": False}},
                bot_username="jarvis_3_0_bot",
                trigger_name="jarvis",
            ).decision.action,
        )
        self.assertNotIn("источники", notice.lower())
        self.assertNotIn("следующий шаг", notice.lower())

    def test_modlog_summary(self):
        self.sanctions.sync_action(
            chat_id=1,
            user_id=88,
            action="warn",
            reason="flood",
            created_by_user_id=7,
            source_ref="manual",
        )
        rows = self.orchestrator.modlog.recent(limit=5)
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
