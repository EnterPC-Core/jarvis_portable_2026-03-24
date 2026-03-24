import time
from typing import Dict, Optional

from bridge_repository import BridgeRepository, safe_int
from history_service import HistoryService


class SanctionsService:
    PENALTIES = {
        "warn": 18,
        "dwarn": 20,
        "swarn": 14,
        "mute": 80,
        "tmute": 65,
        "ban": 150,
        "tban": 120,
        "unmute": -20,
        "unban": -40,
        "appeal_auto_release": -30,
        "appeal_manual_release": -20,
    }

    def __init__(self, repository: BridgeRepository, history_service: HistoryService) -> None:
        self.repository = repository
        self.history_service = history_service

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
    ) -> Dict[str, int]:
        now_ts = int(time.time())
        points_delta = self.PENALTIES.get(action, 0)
        status = "released" if action in {"unban", "unmute", "appeal_auto_release", "appeal_manual_release"} else "active"
        with self.repository.connect() as conn:
            self.repository.ensure_profile(conn, user_id)
            self.repository.upsert_moderation_journal(
                conn,
                chat_id=chat_id,
                user_id=user_id,
                action=action,
                status=status,
                reason=reason,
                created_by_user_id=created_by_user_id,
                points_delta=points_delta,
                expires_at=expires_at,
                resolved_at=now_ts if status == "released" else None,
                source_ref=source_ref,
                metadata={"action": action, "reason": reason},
            )
            if points_delta:
                self.repository.record_score_event(
                    conn,
                    user_id=user_id,
                    chat_id=chat_id,
                    event_type=f"moderation_{action}",
                    xp_delta=0,
                    score_delta=-points_delta,
                    reason=reason or action,
                    metadata={"action": action},
                    abuse_flag="moderation",
                    created_at=now_ts,
                )
            profile = conn.execute("SELECT behavior_score, moderation_penalty FROM progression_profiles WHERE user_id = ?", (user_id,)).fetchone()
            current_behavior = safe_int(profile["behavior_score"] if profile else 100)
            current_penalty = safe_int(profile["moderation_penalty"] if profile else 0)
            behavior_delta = 6 if status == "released" else -max(4, min(28, points_delta // 5 if points_delta else 8))
            conn.execute(
                """UPDATE progression_profiles
                SET behavior_score = ?,
                    moderation_penalty = ?,
                    updated_at = ?
                WHERE user_id = ?""",
                (
                    max(0, min(100, current_behavior + behavior_delta)),
                    max(0, current_penalty + max(0, points_delta)),
                    now_ts,
                    user_id,
                ),
            )
            conn.commit()
        return self.history_service.build_snapshot(user_id)

