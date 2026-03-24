import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


class BridgeRepository:
    def __init__(self, bridge_db_path: str) -> None:
        self.bridge_db_path = str(Path(bridge_db_path).expanduser())
        self.enabled = bool(self.bridge_db_path)
        if self.enabled:
            self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.bridge_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_column(self, conn: sqlite3.Connection, table: str, name: str, type_name: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if name not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {type_name}")

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS progression_profiles (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                msg_count INTEGER NOT NULL DEFAULT 0,
                reactions_given INTEGER NOT NULL DEFAULT 0,
                reactions_received INTEGER NOT NULL DEFAULT 0,
                activity_score INTEGER NOT NULL DEFAULT 0,
                contribution_score INTEGER NOT NULL DEFAULT 0,
                achievement_score INTEGER NOT NULL DEFAULT 0,
                behavior_score INTEGER NOT NULL DEFAULT 100,
                moderation_penalty INTEGER NOT NULL DEFAULT 0,
                total_xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 0,
                prestige INTEGER NOT NULL DEFAULT 0,
                rank_name TEXT NOT NULL DEFAULT 'Наблюдатель',
                rank_badge TEXT NOT NULL DEFAULT '🌫️',
                status_label TEXT NOT NULL DEFAULT 'Новичок',
                total_score INTEGER NOT NULL DEFAULT 0,
                weekly_score INTEGER NOT NULL DEFAULT 0,
                monthly_score INTEGER NOT NULL DEFAULT 0,
                season_id TEXT NOT NULL DEFAULT '',
                season_score INTEGER NOT NULL DEFAULT 0,
                dynamic_score INTEGER NOT NULL DEFAULT 0,
                helpful_messages INTEGER NOT NULL DEFAULT 0,
                meaningful_messages INTEGER NOT NULL DEFAULT 0,
                long_messages INTEGER NOT NULL DEFAULT 0,
                media_messages INTEGER NOT NULL DEFAULT 0,
                replied_messages INTEGER NOT NULL DEFAULT 0,
                unique_days INTEGER NOT NULL DEFAULT 0,
                streak_days INTEGER NOT NULL DEFAULT 0,
                best_streak INTEGER NOT NULL DEFAULT 0,
                clean_streak_days INTEGER NOT NULL DEFAULT 0,
                good_standing_days INTEGER NOT NULL DEFAULT 0,
                last_message_at INTEGER NOT NULL DEFAULT 0,
                first_seen_at INTEGER NOT NULL DEFAULT 0,
                last_day_key TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL DEFAULT 0
            )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS achievement_catalog (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                badge TEXT NOT NULL,
                rarity TEXT NOT NULL,
                category TEXT NOT NULL,
                metric TEXT NOT NULL,
                target_value INTEGER NOT NULL DEFAULT 1,
                tier INTEGER NOT NULL DEFAULT 1,
                hidden INTEGER NOT NULL DEFAULT 0,
                chain_code TEXT NOT NULL DEFAULT '',
                reward_xp INTEGER NOT NULL DEFAULT 0,
                reward_score INTEGER NOT NULL DEFAULT 0,
                reward_badge TEXT NOT NULL DEFAULT '',
                is_seasonal INTEGER NOT NULL DEFAULT 0,
                is_status INTEGER NOT NULL DEFAULT 0,
                is_prestige INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT ''
            )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS user_achievement_state (
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                progress_value INTEGER NOT NULL DEFAULT 0,
                progress_target INTEGER NOT NULL DEFAULT 0,
                unlocked_at INTEGER,
                tier_achieved INTEGER NOT NULL DEFAULT 0,
                last_evaluated_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, code)
            )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS score_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL DEFAULT 0,
                source_message_id INTEGER,
                event_type TEXT NOT NULL,
                xp_delta INTEGER NOT NULL DEFAULT 0,
                score_delta INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                abuse_flag TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS moderation_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                reason TEXT NOT NULL DEFAULT '',
                created_by_user_id INTEGER,
                points_delta INTEGER NOT NULL DEFAULT 0,
                expires_at INTEGER,
                resolved_at INTEGER,
                source_ref TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_score_events_user_created_at ON score_events(user_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_score_events_type_created_at ON score_events(event_type, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_achievement_state_user_unlock ON user_achievement_state(user_id, unlocked_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_journal_user_created_at ON moderation_journal(user_id, created_at DESC)")
            self._ensure_column(conn, "appeals", "snapshot_json", "TEXT NOT NULL DEFAULT '{}'")
            conn.commit()

    def ensure_profile(self, conn: sqlite3.Connection, user_id: int, username: str = "", first_name: str = "") -> None:
        now_ts = int(time.time())
        conn.execute(
            """INSERT OR IGNORE INTO progression_profiles
            (user_id, username, first_name, season_id, first_seen_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username or "", first_name or "", self.current_season_id(now_ts), now_ts, now_ts),
        )
        conn.execute(
            """UPDATE progression_profiles
            SET username = CASE WHEN ? != '' THEN ? ELSE username END,
                first_name = CASE WHEN ? != '' THEN ? ELSE first_name END,
                updated_at = ?
            WHERE user_id = ?""",
            (username or "", username or "", first_name or "", first_name or "", now_ts, user_id),
        )

    def record_score_event(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: int,
        chat_id: int,
        event_type: str,
        xp_delta: int,
        score_delta: int,
        reason: str,
        source_message_id: Optional[int] = None,
        metadata: Optional[Dict[str, object]] = None,
        abuse_flag: str = "",
        created_at: Optional[int] = None,
    ) -> None:
        conn.execute(
            """INSERT INTO score_events
            (user_id, chat_id, source_message_id, event_type, xp_delta, score_delta, reason, metadata_json, abuse_flag, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                chat_id,
                source_message_id,
                event_type,
                xp_delta,
                score_delta,
                reason,
                json.dumps(metadata or {}, ensure_ascii=False),
                abuse_flag,
                created_at or int(time.time()),
            ),
        )

    def upsert_moderation_journal(
        self,
        conn: sqlite3.Connection,
        *,
        chat_id: int,
        user_id: int,
        action: str,
        status: str,
        reason: str,
        created_by_user_id: Optional[int],
        points_delta: int,
        expires_at: Optional[int] = None,
        resolved_at: Optional[int] = None,
        source_ref: str = "",
        metadata: Optional[Dict[str, object]] = None,
    ) -> None:
        conn.execute(
            """INSERT INTO moderation_journal
            (chat_id, user_id, action, status, reason, created_by_user_id, points_delta, expires_at, resolved_at, source_ref, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chat_id,
                user_id,
                action,
                status,
                reason,
                created_by_user_id,
                points_delta,
                expires_at,
                resolved_at,
                source_ref,
                json.dumps(metadata or {}, ensure_ascii=False),
                int(time.time()),
                int(time.time()),
            ),
        )

    @staticmethod
    def current_day_key(ts: int) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(ts))

    @staticmethod
    def current_week_key(ts: int) -> str:
        return time.strftime("%Y-W%W", time.gmtime(ts))

    @staticmethod
    def current_month_key(ts: int) -> str:
        return time.strftime("%Y-%m", time.gmtime(ts))

    @staticmethod
    def current_season_id(ts: int) -> str:
        g = time.gmtime(ts)
        quarter = ((g.tm_mon - 1) // 3) + 1
        return f"{g.tm_year}-Q{quarter}"

    def aggregate_recent_scores(self, conn: sqlite3.Connection, user_id: int, since_ts: int, event_type: Optional[str] = None) -> int:
        if event_type:
            row = conn.execute(
                "SELECT COALESCE(SUM(score_delta), 0) FROM score_events WHERE user_id = ? AND created_at >= ? AND event_type = ?",
                (user_id, since_ts, event_type),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(score_delta), 0) FROM score_events WHERE user_id = ? AND created_at >= ?",
                (user_id, since_ts),
            ).fetchone()
        return safe_int(row[0] if row else 0)

    def aggregate_recent_xp(self, conn: sqlite3.Connection, user_id: int, since_ts: int) -> int:
        row = conn.execute(
            "SELECT COALESCE(SUM(xp_delta), 0) FROM score_events WHERE user_id = ? AND created_at >= ?",
            (user_id, since_ts),
        ).fetchone()
        return safe_int(row[0] if row else 0)

    def count_unlocked_achievements(self, conn: sqlite3.Connection, user_id: int) -> int:
        row = conn.execute(
            "SELECT COUNT(*) FROM user_achievement_state WHERE user_id = ? AND unlocked_at IS NOT NULL",
            (user_id,),
        ).fetchone()
        return safe_int(row[0] if row else 0)

