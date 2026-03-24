import time
from difflib import SequenceMatcher
from typing import Dict, Sequence

from bridge_repository import safe_int


class AntiAbuseService:
    def analyze_message(self, text: str, recent_rows: Sequence[object], now_ts: int) -> Dict[str, object]:
        normalized = " ".join((text or "").lower().split())
        if not normalized:
            return {"multiplier": 0.0, "flag": "empty", "penalty": 0}

        multiplier = 1.0
        penalty = 0
        flag = ""

        if len(normalized) < 3:
            return {"multiplier": 0.0, "flag": "too_short", "penalty": 2}

        duplicates = 0
        for row in recent_rows:
            old_text = " ".join((getattr(row, "__getitem__", lambda x: row[x])("text") if hasattr(row, "__getitem__") else "").lower().split())
            created_at = safe_int(row["created_at"] if hasattr(row, "__getitem__") else 0)
            delta = max(0, now_ts - created_at)
            similarity = SequenceMatcher(None, normalized, old_text).ratio() if old_text else 0.0
            if old_text and similarity >= 0.96:
                duplicates += 1
                if delta <= 120:
                    multiplier *= 0.0
                    flag = "duplicate"
            elif old_text and similarity >= 0.85 and delta <= 60:
                multiplier *= 0.4
                flag = "near_duplicate"
        if duplicates >= 2:
            multiplier = 0.0
            penalty += 5
            flag = flag or "duplicate_burst"

        burst_count = sum(1 for row in recent_rows if now_ts - safe_int(row["created_at"] if hasattr(row, "__getitem__") else 0) <= 20)
        if burst_count >= 5:
            multiplier *= 0.35
            penalty += 3
            flag = flag or "burst"

        if normalized.count("?") >= 6 or normalized.count("!") >= 6:
            multiplier *= 0.65
            penalty += 1
            flag = flag or "noisy"

        if len(set(normalized.split())) <= 2 and len(normalized) <= 28:
            multiplier *= 0.2
            penalty += 2
            flag = flag or "low_entropy"

        return {
            "multiplier": max(0.0, min(1.0, multiplier)),
            "flag": flag,
            "penalty": penalty,
        }

    def cooldown_remaining_seconds(self, last_created_at: int, min_spacing_seconds: int = 45) -> int:
        return max(0, min_spacing_seconds - max(0, int(time.time()) - last_created_at))

