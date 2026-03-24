import json
import time
from typing import Dict, List

from bridge_repository import BridgeRepository, safe_int


class HistoryService:
    def __init__(self, repository: BridgeRepository) -> None:
        self.repository = repository

    def build_snapshot(self, user_id: int) -> Dict[str, int]:
        now_ts = int(time.time())
        snapshot: Dict[str, int] = {
            "user_id": user_id,
            "msg_count": 0,
            "reactions_given": 0,
            "reactions_received": 0,
            "activity_score": 0,
            "contribution_score": 0,
            "achievement_score": 0,
            "behavior_score": 100,
            "moderation_penalty": 0,
            "total_xp": 0,
            "level": 0,
            "prestige": 0,
            "total_score": 0,
            "weekly_score": 0,
            "monthly_score": 0,
            "season_score": 0,
            "dynamic_score": 0,
            "helpful_messages": 0,
            "meaningful_messages": 0,
            "long_messages": 0,
            "media_messages": 0,
            "replied_messages": 0,
            "unique_days": 0,
            "streak_days": 0,
            "best_streak": 0,
            "clean_streak_days": 0,
            "good_standing_days": 0,
            "active_warnings": 0,
            "active_bans": 0,
            "active_mutes": 0,
            "confirmed_violations": 0,
            "sanction_history_count": 0,
            "approved_appeals": 0,
            "rejected_appeals": 0,
            "past_appeals": 0,
            "unlocked_achievements": 0,
            "account_age_days": 0,
        }
        with self.repository.connect() as conn:
            profile = conn.execute("SELECT * FROM progression_profiles WHERE user_id = ?", (user_id,)).fetchone()
            if profile:
                for key in snapshot:
                    if key in profile.keys():
                        snapshot[key] = safe_int(profile[key])
                first_seen = safe_int(profile["first_seen_at"])
                if first_seen:
                    snapshot["account_age_days"] = max(1, ((now_ts - first_seen) // 86400) + 1)

            warning_row = conn.execute(
                "SELECT COUNT(*) FROM warnings WHERE user_id = ? AND (expires_at IS NULL OR expires_at > ?)",
                (user_id, now_ts),
            ).fetchone()
            snapshot["active_warnings"] = safe_int(warning_row[0] if warning_row else 0)

            action_rows = conn.execute(
                """SELECT action, active, expires_at, COUNT(*) AS cnt
                FROM moderation_actions
                WHERE user_id = ?
                GROUP BY action, active, expires_at IS NOT NULL AND expires_at > ?""",
                (user_id, now_ts),
            ).fetchall()
            for row in action_rows:
                if safe_int(row["active"]) != 1:
                    continue
                action = row["action"] or ""
                if action == "ban":
                    snapshot["active_bans"] += safe_int(row["cnt"])
                if action == "mute":
                    snapshot["active_mutes"] += safe_int(row["cnt"])

            sanction_count = conn.execute(
                "SELECT COUNT(*) FROM moderation_actions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            snapshot["sanction_history_count"] = safe_int(sanction_count[0] if sanction_count else 0)

            appeal_row = conn.execute(
                """SELECT COUNT(*) AS total_count,
                          SUM(CASE WHEN status IN ('approved','auto_approved') THEN 1 ELSE 0 END) AS approved_count,
                          SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count
                FROM appeals WHERE user_id = ?""",
                (user_id,),
            ).fetchone()
            if appeal_row:
                snapshot["past_appeals"] = safe_int(appeal_row["total_count"])
                snapshot["approved_appeals"] = safe_int(appeal_row["approved_count"])
                snapshot["rejected_appeals"] = safe_int(appeal_row["rejected_count"])

            snapshot["unlocked_achievements"] = self.repository.count_unlocked_achievements(conn, user_id)
        return snapshot

    def recent_messages(self, user_id: int, limit: int = 6) -> List[object]:
        with self.repository.connect() as conn:
            return conn.execute(
                """SELECT text, created_at
                FROM chat_events
                WHERE user_id = ? AND role = 'user' AND message_type IN ('text','caption','edited_text','edited_caption')
                ORDER BY id DESC LIMIT ?""",
                (user_id, limit),
            ).fetchall()

    def render_behavior_summary(self, user_id: int) -> str:
        snapshot = self.build_snapshot(user_id)
        return (
            f"Поведение: {snapshot['behavior_score']}/100\n"
            f"Активные санкции: ban={snapshot['active_bans']} mute={snapshot['active_mutes']} warn={snapshot['active_warnings']}\n"
            f"История санкций: {snapshot['sanction_history_count']} | Апелляции: +{snapshot['approved_appeals']} / -{snapshot['rejected_appeals']}"
        )

    def build_appeal_snapshot_json(self, user_id: int) -> str:
        return json.dumps(self.build_snapshot(user_id), ensure_ascii=False)

