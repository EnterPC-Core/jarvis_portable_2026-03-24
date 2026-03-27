from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from moderation.moderation_models import SanctionRecord
from sanctions_service import SanctionsService


@dataclass
class SanctionsAdapter:
    service: SanctionsService

    def sync_action(
        self,
        *,
        chat_id: int,
        user_id: int,
        action: str,
        reason: str,
        created_by_user_id: Optional[int],
        expires_at: Optional[int] = None,
        source_ref: str = "",
    ) -> SanctionRecord:
        result = self.service.sync_moderation_event(
            chat_id=chat_id,
            user_id=user_id,
            action=action,
            reason=reason,
            created_by_user_id=created_by_user_id,
            expires_at=expires_at,
            source_ref=source_ref,
        )
        del result
        return SanctionRecord(
            chat_id=chat_id,
            user_id=user_id,
            action=action,
            reason=reason,
            points_delta=int(self.service.PENALTIES.get(action, 0)),
            expires_at=expires_at,
            status="released" if action in {"unban", "unmute", "appeal_auto_release", "appeal_manual_release"} else "active",
        )
