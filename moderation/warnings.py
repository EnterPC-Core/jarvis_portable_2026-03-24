from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from moderation.moderation_models import WarningRecord


@dataclass
class WarningAdapter:
    add_warning_func: Callable[[int, int, str, Optional[int], Optional[int]], int]
    get_warning_count_func: Callable[[int, int], int]

    def add_warning(self, chat_id: int, user_id: int, reason: str, created_by_user_id: Optional[int], expires_at: Optional[int] = None) -> WarningRecord:
        count = self.add_warning_func(chat_id, user_id, reason, created_by_user_id, expires_at)
        return WarningRecord(chat_id=chat_id, user_id=user_id, count=count, reason=reason, expires_at=expires_at)

    def get_warning_count(self, chat_id: int, user_id: int) -> int:
        return int(self.get_warning_count_func(chat_id, user_id))
