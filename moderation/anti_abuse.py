from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

from anti_abuse_service import AntiAbuseService
from moderation.moderation_models import AntiAbuseScore


@dataclass
class AntiAbuseAdapter:
    service: AntiAbuseService

    def analyze_message(self, text: str, recent_rows: Sequence[object], now_ts: int | None = None) -> AntiAbuseScore:
        current_ts = int(now_ts or time.time())
        raw = self.service.analyze_message(text, recent_rows, current_ts)
        last_created_at = 0
        if recent_rows:
            last_row = recent_rows[-1]
            try:
                last_created_at = int(last_row["created_at"])
            except Exception:
                last_created_at = 0
        return AntiAbuseScore(
            multiplier=float(raw.get("multiplier", 0.0)),
            penalty=int(raw.get("penalty", 0)),
            flag=str(raw.get("flag", "") or ""),
            cooldown_remaining_seconds=self.service.cooldown_remaining_seconds(last_created_at) if last_created_at else 0,
        )
