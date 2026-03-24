import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from achievements_service import AchievementsService
from anti_abuse_service import AntiAbuseService
from bridge_repository import BridgeRepository, safe_int
from history_service import HistoryService
from rating_service import RatingService, get_level_name
from sanctions_service import SanctionsService


def analyze_message_quality(text: str) -> int:
    normalized = " ".join((text or "").lower().split())
    if len(normalized) < 4:
        return 0
    score = 1
    if len(normalized) >= 80:
        score += 1
    if len(normalized) >= 220:
        score += 1
    if any(token in normalized for token in ("http://", "https://", "решение", "ошибка", "проверь", "совет", "источник")):
        score += 1
    return min(score, 4)


class LegacyJarvisAdapter:
    def __init__(self, db_path: str, bridge_db_path: str = "") -> None:
        target_db_path = bridge_db_path or db_path
        self.legacy_db_path = str(Path(db_path).expanduser())
        self.repository = BridgeRepository(target_db_path)
        self.history = HistoryService(self.repository)
        self.anti_abuse = AntiAbuseService()
        self.achievements = AchievementsService(self.repository)
        self.rating = RatingService(self.repository)
        self.sanctions = SanctionsService(self.repository, self.history)
        self.enabled = self.repository.enabled
        self.bridge_enabled = self.repository.enabled
        if self.enabled:
            self.bootstrap_from_existing_events()
            self.merge_legacy_profiles()

    def _connect_legacy(self) -> Optional[sqlite3.Connection]:
        if not self.legacy_db_path or not Path(self.legacy_db_path).exists():
            return None
        conn = sqlite3.connect(self.legacy_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def bootstrap_from_existing_events(self) -> None:
        migrated_user_ids: List[int] = []
        with self.repository.connect() as conn:
            existing_profiles = safe_int(conn.execute("SELECT COUNT(*) FROM progression_profiles").fetchone()[0])
            if existing_profiles > 0:
                return
            rows = conn.execute(
                """SELECT
                    user_id,
                    MAX(COALESCE(username, '')) AS username,
                    MAX(COALESCE(first_name, '')) AS first_name,
                    COUNT(*) AS msg_count,
                    SUM(CASE WHEN LENGTH(text) >= 80 THEN 1 ELSE 0 END) AS meaningful_messages,
                    SUM(CASE WHEN LENGTH(text) >= 220 THEN 1 ELSE 0 END) AS long_messages,
                    SUM(CASE WHEN has_media = 1 THEN 1 ELSE 0 END) AS media_messages,
                    SUM(CASE WHEN reply_to_user_id IS NOT NULL THEN 1 ELSE 0 END) AS replied_messages,
                    COUNT(DISTINCT strftime('%Y-%m-%d', created_at, 'unixepoch')) AS unique_days,
                    MIN(created_at) AS first_seen_at,
                    MAX(created_at) AS last_message_at
                FROM chat_events
                WHERE user_id IS NOT NULL AND role = 'user'
                GROUP BY user_id"""
            ).fetchall()
            for row in rows:
                user_id = safe_int(row["user_id"])
                if user_id == 0:
                    continue
                self.repository.ensure_profile(conn, user_id, username=row["username"] or "", first_name=row["first_name"] or "")
                migrated_user_ids.append(user_id)
                msg_count = safe_int(row["msg_count"])
                meaningful = safe_int(row["meaningful_messages"])
                long_messages = safe_int(row["long_messages"])
                media_messages = safe_int(row["media_messages"])
                replied = safe_int(row["replied_messages"])
                unique_days = safe_int(row["unique_days"])
                contribution_score = meaningful * 6 + long_messages * 4 + replied * 3
                activity_score = msg_count * 2 + media_messages
                total_xp = msg_count * 2 + meaningful * 3 + long_messages * 5
                level = min(15, total_xp // 120)
                rank_name = "Наблюдатель"
                rank_badge = "🌫️"
                conn.execute(
                    """UPDATE progression_profiles
                    SET msg_count = ?, meaningful_messages = ?, long_messages = ?, media_messages = ?,
                        replied_messages = ?, unique_days = ?, streak_days = ?, best_streak = ?,
                        good_standing_days = ?, activity_score = ?, contribution_score = ?,
                        total_xp = ?, level = ?, status_label = ?, first_seen_at = ?, last_message_at = ?, updated_at = ?
                    WHERE user_id = ?""",
                    (
                        msg_count,
                        meaningful,
                        long_messages,
                        media_messages,
                        replied,
                        unique_days,
                        1 if msg_count > 0 else 0,
                        max(1, min(unique_days, 7)) if msg_count > 0 else 0,
                        unique_days,
                        activity_score,
                        contribution_score,
                        total_xp,
                        level,
                        get_level_name(level),
                        safe_int(row["first_seen_at"]),
                        safe_int(row["last_message_at"]),
                        int(time.time()),
                        user_id,
                    ),
                )
            conn.commit()
        for user_id in migrated_user_ids:
            self.achievements.evaluate(user_id, self.history.build_snapshot(user_id))
            self.rating.recalculate_profile(user_id)

    def merge_legacy_profiles(self) -> None:
        legacy = self._connect_legacy()
        if legacy is None:
            return
        try:
            with legacy:
                users_exists = legacy.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
                ).fetchone()
                if not users_exists:
                    return
                legacy_count = safe_int(legacy.execute("SELECT COUNT(*) FROM users").fetchone()[0])
                if legacy_count == 0:
                    return
                game_stats_exists = legacy.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='user_game_stats'"
                ).fetchone() is not None
                achievement_rows = {
                    safe_int(row["user_id"]): safe_int(row["cnt"])
                    for row in legacy.execute(
                        "SELECT user_id, COUNT(*) AS cnt FROM achievements GROUP BY user_id"
                    ).fetchall()
                } if legacy.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='achievements'").fetchone() else {}
                stats_rows = {}
                if game_stats_exists:
                    stats_rows = {
                        safe_int(row["user_id"]): row
                        for row in legacy.execute("SELECT * FROM user_game_stats").fetchall()
                    }
                user_rows = legacy.execute(
                    """SELECT user_id, username, first_name, msg_count, reputation, experience, level,
                              warnings, spam_offense_count, joined_at
                       FROM users"""
                ).fetchall()
            migrated_ids: List[int] = []
            with self.repository.connect() as conn:
                bridge_ids = {
                    safe_int(row["user_id"])
                    for row in conn.execute("SELECT user_id FROM progression_profiles").fetchall()
                }
                for row in user_rows:
                    user_id = safe_int(row["user_id"])
                    if user_id == 0 or user_id in bridge_ids:
                        continue
                    self.repository.ensure_profile(conn, user_id, username=row["username"] or "", first_name=row["first_name"] or "")
                    stats = stats_rows.get(user_id)
                    msg_count = safe_int(row["msg_count"])
                    reputation = safe_int(row["reputation"])
                    experience = safe_int(row["experience"])
                    warnings = safe_int(row["warnings"])
                    spam_offenses = safe_int(row["spam_offense_count"])
                    helpful_messages = safe_int(stats["helpful_messages"] if stats else 0)
                    long_messages = safe_int(stats["long_messages"] if stats else 0)
                    unique_days = safe_int(stats["unique_days"] if stats else 0)
                    streak_days = safe_int(stats["streak_days"] if stats else 0)
                    best_streak = safe_int(stats["best_streak"] if stats else 0)
                    season_points = safe_int(stats["season_points"] if stats else 0)
                    behavior_score = safe_int(stats["behavior_score"] if stats else max(0, 100 - warnings * 6 - spam_offenses * 8))
                    contribution_score = reputation * 3 + helpful_messages * 6
                    activity_score = msg_count * 2 + long_messages * 2
                    achievement_score = achievement_rows.get(user_id, 0) * 30
                    dynamic_score = contribution_score + activity_score + behavior_score
                    joined_at = safe_int(row["joined_at"] or 0) or int(time.time())
                    conn.execute(
                        """UPDATE progression_profiles
                        SET msg_count = ?, activity_score = ?, contribution_score = ?, achievement_score = ?,
                            behavior_score = ?, moderation_penalty = ?, total_xp = ?, level = ?, prestige = ?,
                            weekly_score = ?, monthly_score = ?, season_score = ?, dynamic_score = ?,
                            helpful_messages = ?, meaningful_messages = ?, long_messages = ?,
                            unique_days = ?, streak_days = ?, best_streak = ?, good_standing_days = ?,
                            first_seen_at = ?, last_message_at = ?, updated_at = ?
                        WHERE user_id = ?""",
                        (
                            msg_count,
                            activity_score,
                            contribution_score,
                            achievement_score,
                            behavior_score,
                            warnings * 10 + spam_offenses * 15,
                            experience,
                            safe_int(row["level"]),
                            max(0, experience // 12000),
                            0,
                            0,
                            season_points,
                            dynamic_score,
                            helpful_messages,
                            helpful_messages,
                            long_messages,
                            unique_days,
                            streak_days,
                            best_streak,
                            max(0, unique_days - warnings),
                            joined_at,
                            int(time.time()),
                            int(time.time()),
                            user_id,
                        ),
                    )
                    self.repository.record_score_event(
                        conn,
                        user_id=user_id,
                        chat_id=0,
                        event_type="legacy_import",
                        xp_delta=experience,
                        score_delta=max(0, contribution_score + achievement_score + activity_score - warnings * 10 - spam_offenses * 15),
                        reason="legacy profile import",
                        metadata={"source": "legacy_users"},
                        created_at=joined_at,
                    )
                    migrated_ids.append(user_id)
                conn.commit()
            for user_id in migrated_ids:
                profile = self._load_profile(user_id) or {}
                historical_ts = safe_int(profile.get("first_seen_at") or profile.get("last_message_at") or 0) or int(time.time())
                self.achievements.evaluate(
                    user_id,
                    self.history.build_snapshot(user_id),
                    awarded_at=historical_ts,
                    metadata_extra={"source": "legacy_bootstrap"},
                )
                self.rating.recalculate_profile(user_id)
        finally:
            legacy.close()

    def _load_profile(self, user_id: int) -> Optional[Dict[str, object]]:
        with self.repository.connect() as conn:
            row = conn.execute("SELECT * FROM progression_profiles WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return {key: row[key] for key in row.keys()}

    def sync_message(
        self,
        chat_id: int,
        message_id: int,
        user_id: int,
        username: str,
        first_name: str,
        text: str,
    ) -> List[Tuple[str, str]]:
        if not self.enabled or not text.strip():
            return []
        now_ts = int(time.time())
        day_key = self.repository.current_day_key(now_ts)
        with self.repository.connect() as conn:
            self.repository.ensure_profile(conn, user_id, username=username, first_name=first_name)
            existing = conn.execute(
                "SELECT 1 FROM score_events WHERE user_id = ? AND chat_id = ? AND source_message_id = ? AND event_type = 'message'",
                (user_id, chat_id, message_id),
            ).fetchone()
            if existing:
                return []
            profile = conn.execute("SELECT * FROM progression_profiles WHERE user_id = ?", (user_id,)).fetchone()
            recent = self.history.recent_messages(user_id, limit=6)
            abuse = self.anti_abuse.analyze_message(text, recent, now_ts)
            quality = analyze_message_quality(text)
            helpful = 1 if quality >= 3 else 0
            meaningful = 1 if quality >= 2 else 0
            long_message = 1 if len(text.strip()) >= 220 else 0
            replied = 1 if text.count("@") or "\n" in text else 0
            xp_gain = int(round((2 + quality * 2 + long_message) * float(abuse["multiplier"])))
            score_gain = int(round((3 + quality * 3 + helpful * 4 + replied * 2) * float(abuse["multiplier"])))
            contribution_gain = helpful * 8 + meaningful * 4 + replied * 3
            activity_gain = max(1, int(round((2 + len(text.strip()) // 120) * max(0.3, float(abuse["multiplier"])))))
            last_day_key = (profile["last_day_key"] if profile else "") or ""
            streak_days = safe_int(profile["streak_days"] if profile else 0)
            unique_days = safe_int(profile["unique_days"] if profile else 0)
            good_standing = safe_int(profile["good_standing_days"] if profile else 0)
            if not last_day_key:
                streak_days = 1
                unique_days = 1
                good_standing = 1
            elif last_day_key == day_key:
                pass
            else:
                previous_day = self.repository.current_day_key(now_ts - 86400)
                streak_days = streak_days + 1 if last_day_key == previous_day else 1
                unique_days += 1
                snapshot = self.history.build_snapshot(user_id)
                good_standing = good_standing + 1 if snapshot["active_bans"] == 0 and snapshot["active_mutes"] == 0 and snapshot["active_warnings"] == 0 else 0
            best_streak = max(streak_days, safe_int(profile["best_streak"] if profile else 0))
            behavior_score = max(0, min(100, safe_int(profile["behavior_score"] if profile else 100) - safe_int(abuse["penalty"])))
            conn.execute(
                """UPDATE progression_profiles
                SET msg_count = msg_count + 1,
                    activity_score = activity_score + ?,
                    contribution_score = contribution_score + ?,
                    behavior_score = ?,
                    helpful_messages = helpful_messages + ?,
                    meaningful_messages = meaningful_messages + ?,
                    long_messages = long_messages + ?,
                    replied_messages = replied_messages + ?,
                    unique_days = ?,
                    streak_days = ?,
                    best_streak = ?,
                    clean_streak_days = CASE WHEN ? >= 90 THEN clean_streak_days + 1 ELSE 0 END,
                    good_standing_days = ?,
                    last_message_at = ?,
                    last_day_key = ?,
                    updated_at = ?
                WHERE user_id = ?""",
                (
                    activity_gain,
                    contribution_gain,
                    behavior_score,
                    helpful,
                    meaningful,
                    long_message,
                    replied,
                    unique_days,
                    streak_days,
                    best_streak,
                    behavior_score,
                    good_standing,
                    now_ts,
                    day_key,
                    now_ts,
                    user_id,
                ),
            )
            self.repository.record_score_event(
                conn,
                user_id=user_id,
                chat_id=chat_id,
                source_message_id=message_id,
                event_type="message",
                xp_delta=xp_gain,
                score_delta=score_gain,
                reason="message activity",
                metadata={"quality": quality, "length": len(text.strip())},
                abuse_flag=str(abuse["flag"]),
                created_at=now_ts,
            )
            conn.commit()
        snapshot = self.history.build_snapshot(user_id)
        unlocked = self.achievements.evaluate(user_id, snapshot)
        self.rating.recalculate_profile(user_id)
        return unlocked

    def sync_reaction(self, chat_id: int, user_id: int, message_id: int, reactions_added: int = 1) -> None:
        if not self.enabled or user_id is None:
            return
        with self.repository.connect() as conn:
            self.repository.ensure_profile(conn, user_id)
            conn.execute(
                """UPDATE progression_profiles
                SET reactions_given = reactions_given + ?,
                    contribution_score = contribution_score + ?,
                    updated_at = ?
                WHERE user_id = ?""",
                (reactions_added, reactions_added * 2, int(time.time()), user_id),
            )
            self.repository.record_score_event(
                conn,
                user_id=user_id,
                chat_id=chat_id,
                source_message_id=message_id,
                event_type="reaction_given",
                xp_delta=1,
                score_delta=reactions_added * 2,
                reason="reaction",
                metadata={"reactions_added": reactions_added},
            )
            conn.commit()
        self.rating.recalculate_profile(user_id)

    def sync_moderation_event(
        self,
        *,
        chat_id: int,
        user_id: int,
        action: str,
        reason: str,
        created_by_user_id: Optional[int],
        expires_at: Optional[int] = None,
        source_ref: str = "",
    ) -> None:
        self.sanctions.sync_moderation_event(
            chat_id=chat_id,
            user_id=user_id,
            action=action,
            reason=reason,
            created_by_user_id=created_by_user_id,
            expires_at=expires_at,
            source_ref=source_ref,
        )
        snapshot = self.history.build_snapshot(user_id)
        self.achievements.evaluate(user_id, snapshot)
        self.rating.recalculate_profile(user_id)

    def render_rating(self, user_id: int) -> Optional[str]:
        return self.rating.render_rating(user_id)

    def render_top_all_time(self) -> str:
        return self.rating.render_top_all_time()

    def render_top_historical(self) -> str:
        return self.rating.render_top_historical()

    def render_top_week(self) -> str:
        return self.rating.render_top_week()

    def render_top_day(self) -> str:
        return self.rating.render_top_day()

    def render_top_social(self) -> str:
        return self.rating.render_top_social()

    def render_top_season(self) -> str:
        return self.rating.render_top_season()

    def render_stats(self) -> str:
        return self.rating.render_stats()

    def render_dashboard_summary(self, user_id: int) -> str:
        profile = self._load_profile(user_id)
        if not profile:
            return "Профиль еще не сформирован. Напишите несколько сообщений в чате."
        return (
            f"{profile['rank_badge']} {profile.get('first_name') or profile.get('username') or user_id}\n"
            f"Score: {safe_int(profile['total_score']):,} | LV {safe_int(profile['level'])} {get_level_name(safe_int(profile['level']))}\n"
            f"XP: {safe_int(profile['total_xp']):,} | Вклад: {safe_int(profile['contribution_score'])} | Поведение: {safe_int(profile['behavior_score'])}/100\n"
            f"Сезон: {safe_int(profile['season_score'])} | Динамика: {safe_int(profile['dynamic_score'])}"
        )

    def render_achievements(self, user_id: int) -> str:
        profile = self._load_profile(user_id)
        if not profile:
            return "❌ Вы еще не зарегистрированы!"
        snapshot = self.history.build_snapshot(user_id)
        display_name = str(profile.get("first_name") or profile.get("username") or user_id)
        return self.achievements.render(user_id, snapshot, display_name)
