from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from appeals_service import AppealsService
from moderation.moderation_models import AppealDecision, AppealRecord


@dataclass
class AppealsAdapter:
    service: AppealsService

    def submit(self, user_id: int, chat_id: int, reason: str) -> AppealRecord:
        result = self.service.submit_appeal(user_id, chat_id, reason)
        return AppealRecord(
            appeal_id=int(result.get("appeal_id", 0) or 0),
            user_id=user_id,
            status=str(result.get("status", "")),
            message=str(result.get("message", "")),
            source_action=str(result.get("source_action", "")),
        )

    def resolve(self, appeal_id: int, moderator_id: int, approved: bool, resolution: str) -> AppealDecision:
        self.service.resolve_appeal(appeal_id, moderator_id, approved, resolution)
        return AppealDecision(
            appeal_id=appeal_id,
            approved=approved,
            resolution=resolution,
            moderator_id=moderator_id,
        )
