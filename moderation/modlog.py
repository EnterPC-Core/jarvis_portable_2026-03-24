from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import List

from moderation.moderation_models import ModerationDiagnostics, SanctionRecord


@dataclass
class ModlogAdapter:
    db_path: str

    def recent(self, limit: int = 10) -> List[SanctionRecord]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT chat_id, user_id, action, reason, points_delta, expires_at, status
                FROM moderation_journal
                ORDER BY created_at DESC
                LIMIT ?""",
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return [
            SanctionRecord(
                chat_id=int(row["chat_id"]),
                user_id=int(row["user_id"]),
                action=row["action"] or "",
                reason=row["reason"] or "",
                points_delta=int(row["points_delta"] or 0),
                expires_at=int(row["expires_at"]) if row["expires_at"] is not None else None,
                status=row["status"] or "active",
            )
            for row in rows
        ]

    def diagnostics(self) -> ModerationDiagnostics:
        return ModerationDiagnostics(source="moderation_journal", notes=())
