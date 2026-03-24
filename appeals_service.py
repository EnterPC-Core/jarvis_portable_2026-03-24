import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional


APPEAL_STATUS_NEW = "new"
APPEAL_STATUS_IN_REVIEW = "in_review"
APPEAL_STATUS_AUTO_APPROVED = "auto_approved"
APPEAL_STATUS_APPROVED = "approved"
APPEAL_STATUS_REJECTED = "rejected"
APPEAL_STATUS_CLOSED = "closed"

APPEAL_COOLDOWN_SECONDS = 6 * 3600
APPEAL_DUPLICATE_WINDOW_SECONDS = 12 * 3600
APPEAL_SPAM_WINDOW_SECONDS = 3 * 86400
APPEAL_MAX_PER_SPAM_WINDOW = 4


class AppealsService:
    def __init__(self, bridge_db_path: str, legacy_db_path: str) -> None:
        self.bridge_db_path = str(Path(bridge_db_path).expanduser())
        self.legacy_db_path = str(Path(legacy_db_path).expanduser())
        self.bridge_enabled = Path(self.bridge_db_path).exists()
        self.legacy_enabled = Path(self.legacy_db_path).exists()
        if self.bridge_enabled:
            self.ensure_schema()

    def _connect_bridge(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.bridge_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_legacy(self) -> Optional[sqlite3.Connection]:
        if not self.legacy_enabled:
            return None
        conn = sqlite3.connect(self.legacy_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_column(self, conn: sqlite3.Connection, table: str, name: str, type_name: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if name not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {type_name}")

    def ensure_schema(self) -> None:
        with self._connect_bridge() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS appeals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER,
                reason TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                status TEXT NOT NULL DEFAULT 'new',
                resolution TEXT NOT NULL DEFAULT '',
                moderator_id INTEGER,
                reviewed_at INTEGER,
                auto_result TEXT NOT NULL DEFAULT '',
                cooldown_until INTEGER NOT NULL DEFAULT 0
            )"""
            )
            self._ensure_column(conn, "appeals", "updated_at", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "appeals", "closed_at", "INTEGER")
            self._ensure_column(conn, "appeals", "decision_type", "TEXT NOT NULL DEFAULT 'manual'")
            self._ensure_column(conn, "appeals", "source_action", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "appeals", "review_comment", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "appeals", "snapshot_json", "TEXT NOT NULL DEFAULT '{}'")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS appeal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appeal_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                actor_id INTEGER,
                status_from TEXT NOT NULL DEFAULT '',
                status_to TEXT NOT NULL DEFAULT '',
                details TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_appeals_user_created_at ON appeals(user_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_appeals_status_created_at ON appeals(status, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_appeal_events_appeal_created_at ON appeal_events(appeal_id, created_at ASC)"
            )
            conn.commit()

    def _log_event(
        self,
        conn: sqlite3.Connection,
        appeal_id: int,
        user_id: int,
        event_type: str,
        *,
        actor_id: Optional[int] = None,
        status_from: str = "",
        status_to: str = "",
        details: str = "",
    ) -> None:
        conn.execute(
            """INSERT INTO appeal_events
            (appeal_id, user_id, event_type, actor_id, status_from, status_to, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (appeal_id, user_id, event_type, actor_id, status_from, status_to, details, int(time.time())),
        )

    def _fetch_case_snapshot(self, user_id: int, now_ts: int) -> Dict[str, object]:
        snapshot: Dict[str, object] = {
            "active_bans": [],
            "expired_bans": [],
            "active_mutes": [],
            "expired_mutes": [],
            "active_warnings": 0,
            "confirmed_violations": 0,
            "legacy_user_warnings": 0,
            "past_appeals": 0,
            "approved_appeals": 0,
            "rejected_appeals": 0,
            "has_active_sanctions": False,
            "sanction_history_count": 0,
            "grounds_present": False,
        }
        with self._connect_bridge() as conn:
            rows = conn.execute(
                """SELECT id, chat_id, action, reason, expires_at, created_at
                FROM moderation_actions
                WHERE user_id = ? AND action IN ('ban', 'mute') AND active = 1
                ORDER BY created_at DESC""",
                (user_id,),
            ).fetchall()
            for row in rows:
                expires_at = row["expires_at"]
                payload = {
                    "id": int(row["id"]),
                    "chat_id": int(row["chat_id"]),
                    "action": row["action"],
                    "reason": row["reason"] or "",
                    "expires_at": int(expires_at) if expires_at is not None else None,
                }
                is_expired = expires_at is not None and int(expires_at) <= now_ts
                if row["action"] == "ban":
                    (snapshot["expired_bans"] if is_expired else snapshot["active_bans"]).append(payload)
                else:
                    (snapshot["expired_mutes"] if is_expired else snapshot["active_mutes"]).append(payload)

            warning_row = conn.execute(
                """SELECT COUNT(*)
                FROM warnings
                WHERE user_id = ? AND (expires_at IS NULL OR expires_at > ?)""",
                (user_id, now_ts),
            ).fetchone()
            snapshot["active_warnings"] = int(warning_row[0] if warning_row else 0)

            sanctions_row = conn.execute(
                "SELECT COUNT(*) FROM moderation_actions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            snapshot["sanction_history_count"] = int(sanctions_row[0] if sanctions_row else 0)

            appeal_stats = conn.execute(
                """SELECT
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN status IN ('approved', 'auto_approved') THEN 1 ELSE 0 END) AS approved_count,
                    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count
                FROM appeals
                WHERE user_id = ?""",
                (user_id,),
            ).fetchone()
            if appeal_stats:
                snapshot["past_appeals"] = int(appeal_stats["total_count"] or 0)
                snapshot["approved_appeals"] = int(appeal_stats["approved_count"] or 0)
                snapshot["rejected_appeals"] = int(appeal_stats["rejected_count"] or 0)

        legacy = self._connect_legacy()
        if legacy is not None:
            with legacy:
                violation_row = legacy.execute(
                    """SELECT COUNT(*)
                    FROM violations
                    WHERE user_id = ? AND (
                        COALESCE(handled, 0) = 1
                        OR COALESCE(action_taken, '') != ''
                    )""",
                    (user_id,),
                ).fetchone()
                legacy_warning_row = legacy.execute(
                    "SELECT warnings FROM users WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
            snapshot["confirmed_violations"] = int(violation_row[0] if violation_row else 0)
            snapshot["legacy_user_warnings"] = int(legacy_warning_row[0] if legacy_warning_row else 0)
            legacy.close()

        snapshot["has_active_sanctions"] = bool(
            snapshot["active_bans"] or snapshot["active_mutes"] or int(snapshot["active_warnings"])
        )
        snapshot["grounds_present"] = bool(
            snapshot["has_active_sanctions"]
            or int(snapshot["confirmed_violations"])
            or int(snapshot["legacy_user_warnings"])
        )
        return snapshot

    def get_case_snapshot(self, user_id: int) -> Dict[str, object]:
        return self._fetch_case_snapshot(user_id, int(time.time()))

    def _find_recent_open_appeal(self, conn: sqlite3.Connection, user_id: int, now_ts: int) -> Optional[sqlite3.Row]:
        return conn.execute(
            """SELECT *
            FROM appeals
            WHERE user_id = ?
              AND status IN ('new', 'in_review')
              AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT 1""",
            (user_id, now_ts - APPEAL_DUPLICATE_WINDOW_SECONDS),
        ).fetchone()

    def _too_many_recent_appeals(self, conn: sqlite3.Connection, user_id: int, now_ts: int) -> bool:
        row = conn.execute(
            """SELECT COUNT(*)
            FROM appeals
            WHERE user_id = ? AND created_at >= ?""",
            (user_id, now_ts - APPEAL_SPAM_WINDOW_SECONDS),
        ).fetchone()
        return int(row[0] if row else 0) >= APPEAL_MAX_PER_SPAM_WINDOW

    def _reason_is_duplicate(self, conn: sqlite3.Connection, user_id: int, reason: str, now_ts: int) -> bool:
        cleaned = " ".join(reason.lower().split())
        if not cleaned:
            return False
        rows = conn.execute(
            """SELECT reason
            FROM appeals
            WHERE user_id = ? AND created_at >= ?
            ORDER BY created_at DESC LIMIT 5""",
            (user_id, now_ts - APPEAL_DUPLICATE_WINDOW_SECONDS),
        ).fetchall()
        for row in rows:
            old_value = " ".join((row["reason"] or "").lower().split())
            if old_value and old_value == cleaned:
                return True
        return False

    def _detect_source_action(self, snapshot: Dict[str, object]) -> str:
        if snapshot.get("active_bans"):
            return "ban"
        if snapshot.get("active_mutes"):
            return "mute"
        if int(snapshot.get("active_warnings", 0)) > 0:
            return "warning"
        if int(snapshot.get("confirmed_violations", 0)) > 0:
            return "violation"
        if snapshot.get("expired_bans") or snapshot.get("expired_mutes"):
            return "expired_sanction"
        return "unknown"

    def submit_appeal(self, user_id: int, chat_id: int, reason: str) -> Dict[str, object]:
        now_ts = int(time.time())
        if not self.bridge_enabled:
            return {"ok": False, "status": "disabled", "message": "Сервис апелляций недоступен."}

        cleaned_reason = " ".join((reason or "").split()).strip()
        if len(cleaned_reason) < 8:
            return {"ok": False, "status": "too_short", "message": "Опишите апелляцию чуть подробнее."}

        with self._connect_bridge() as conn:
            last_row = conn.execute(
                "SELECT created_at, cooldown_until FROM appeals WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if last_row:
                cooldown_until = int(last_row["cooldown_until"] or 0)
                if cooldown_until > now_ts:
                    remain = cooldown_until - now_ts
                    return {
                        "ok": False,
                        "status": "cooldown",
                        "message": f"Апелляцию можно подать позже. Кулдаун: {max(1, remain // 60)} мин.",
                    }

            if self._too_many_recent_appeals(conn, user_id, now_ts):
                return {
                    "ok": False,
                    "status": "rate_limited",
                    "message": "Слишком много апелляций за короткий период. Попробуйте позже.",
                }

            duplicate = self._find_recent_open_appeal(conn, user_id, now_ts)
            if duplicate:
                return {
                    "ok": False,
                    "status": "duplicate",
                    "message": f"У вас уже есть активная апелляция #{int(duplicate['id'])}. Дождитесь решения.",
                    "appeal_id": int(duplicate["id"]),
                }

            if self._reason_is_duplicate(conn, user_id, cleaned_reason, now_ts):
                return {
                    "ok": False,
                    "status": "duplicate_reason",
                    "message": "Похоже, такая апелляция уже отправлялась недавно.",
                }

            snapshot = self._fetch_case_snapshot(user_id, now_ts)
            source_action = self._detect_source_action(snapshot)
            active_bans = list(snapshot["active_bans"])
            expired_bans = list(snapshot["expired_bans"])
            active_mutes = list(snapshot["active_mutes"])
            expired_mutes = list(snapshot["expired_mutes"])
            confirmed_violations = int(snapshot["confirmed_violations"])
            active_warnings = int(snapshot["active_warnings"])
            legacy_warnings = int(snapshot["legacy_user_warnings"])

            auto_resolvable = (
                not active_bans
                and not active_mutes
                and not active_warnings
                and not confirmed_violations
                and not legacy_warnings
            ) or (
                (expired_bans or expired_mutes)
                and not active_bans
                and not active_mutes
                and not active_warnings
                and not confirmed_violations
                and not legacy_warnings
            )

            cooldown_until = now_ts + APPEAL_COOLDOWN_SECONDS
            snapshot_json = json.dumps(snapshot, ensure_ascii=False)

            if auto_resolvable:
                appeal_id = conn.execute(
                    """INSERT INTO appeals
                    (user_id, chat_id, reason, status, resolution, reviewed_at, auto_result, cooldown_until,
                     updated_at, closed_at, decision_type, source_action, review_comment, snapshot_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user_id,
                        chat_id,
                        cleaned_reason,
                        APPEAL_STATUS_AUTO_APPROVED,
                        "Автоматически одобрена: активных подтверждённых нарушений не найдено.",
                        now_ts,
                        "auto_release",
                        cooldown_until,
                        now_ts,
                        now_ts,
                        "automatic",
                        source_action,
                        "Система не нашла активных оснований для ограничения.",
                        snapshot_json,
                    ),
                ).lastrowid
                affected_actions = active_bans + expired_bans + active_mutes + expired_mutes
                for item in affected_actions:
                    conn.execute(
                        "UPDATE moderation_actions SET active = 0, completed_at = ? WHERE id = ?",
                        (now_ts, int(item["id"])),
                    )
                self._log_event(
                    conn,
                    int(appeal_id),
                    user_id,
                    "created",
                    status_to=APPEAL_STATUS_AUTO_APPROVED,
                    details=cleaned_reason,
                )
                self._log_event(
                    conn,
                    int(appeal_id),
                    user_id,
                    "auto_resolved",
                    status_from=APPEAL_STATUS_NEW,
                    status_to=APPEAL_STATUS_AUTO_APPROVED,
                    details="auto_release",
                )
                conn.commit()
                return {
                    "ok": True,
                    "status": APPEAL_STATUS_AUTO_APPROVED,
                    "message": "Апелляция одобрена автоматически. Ограничения сняты.",
                    "appeal_id": int(appeal_id),
                    "release_actions": [
                        {"chat_id": int(item["chat_id"]), "action": item["action"]}
                        for item in affected_actions
                    ],
                    "snapshot": snapshot,
                }

            appeal_id = conn.execute(
                """INSERT INTO appeals
                (user_id, chat_id, reason, status, auto_result, cooldown_until, updated_at, decision_type,
                 source_action, snapshot_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    chat_id,
                    cleaned_reason,
                    APPEAL_STATUS_NEW,
                    "manual_review_required",
                    cooldown_until,
                    now_ts,
                    "manual",
                    source_action,
                    snapshot_json,
                ),
            ).lastrowid
            self._log_event(
                conn,
                int(appeal_id),
                user_id,
                "created",
                status_to=APPEAL_STATUS_NEW,
                details=cleaned_reason,
            )
            conn.commit()
            return {
                "ok": True,
                "status": APPEAL_STATUS_NEW,
                "message": f"Апелляция #{int(appeal_id)} создана и отправлена на ручную проверку.",
                "appeal_id": int(appeal_id),
                "snapshot": snapshot,
            }

    def list_open_appeals(self, limit: int = 10) -> List[sqlite3.Row]:
        if not self.bridge_enabled:
            return []
        with self._connect_bridge() as conn:
            return conn.execute(
                """SELECT *
                FROM appeals
                WHERE status IN ('new', 'in_review')
                ORDER BY created_at ASC
                LIMIT ?""",
                (limit,),
            ).fetchall()

    def get_appeal(self, appeal_id: int) -> Optional[sqlite3.Row]:
        if not self.bridge_enabled:
            return None
        with self._connect_bridge() as conn:
            return conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()

    def get_appeal_events(self, appeal_id: int) -> List[sqlite3.Row]:
        if not self.bridge_enabled:
            return []
        with self._connect_bridge() as conn:
            return conn.execute(
                "SELECT * FROM appeal_events WHERE appeal_id = ? ORDER BY created_at ASC, id ASC",
                (appeal_id,),
            ).fetchall()

    def get_user_appeals(self, user_id: int, limit: int = 8) -> List[sqlite3.Row]:
        if not self.bridge_enabled:
            return []
        with self._connect_bridge() as conn:
            return conn.execute(
                "SELECT * FROM appeals WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()

    def render_open_appeals(self, limit: int = 10) -> str:
        rows = self.list_open_appeals(limit=limit)
        if not rows:
            return "Апелляции в очереди отсутствуют."
        lines = ["Апелляции в очереди:"]
        for row in rows:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(row["created_at"])))
            lines.append(
                f"#{int(row['id'])} user={int(row['user_id'])} status={row['status']} [{stamp}] {row['reason']}"
            )
        return "\n".join(lines)

    def mark_in_review(self, appeal_id: int, moderator_id: Optional[int]) -> Dict[str, object]:
        if not self.bridge_enabled:
            return {"ok": False, "message": "Сервис апелляций недоступен."}
        now_ts = int(time.time())
        with self._connect_bridge() as conn:
            row = conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()
            if not row:
                return {"ok": False, "message": "Апелляция не найдена."}
            if row["status"] not in {APPEAL_STATUS_NEW, APPEAL_STATUS_IN_REVIEW}:
                return {"ok": False, "message": f"Апелляция уже завершена со статусом {row['status']}."}
            previous = row["status"]
            conn.execute(
                """UPDATE appeals
                SET status = ?, moderator_id = ?, reviewed_at = ?, updated_at = ?
                WHERE id = ?""",
                (APPEAL_STATUS_IN_REVIEW, moderator_id, now_ts, now_ts, appeal_id),
            )
            self._log_event(
                conn,
                appeal_id,
                int(row["user_id"]),
                "in_review",
                actor_id=moderator_id,
                status_from=previous,
                status_to=APPEAL_STATUS_IN_REVIEW,
                details="manual review started",
            )
            conn.commit()
            return {"ok": True, "message": f"Апелляция #{appeal_id} переведена в review."}

    def resolve_appeal(self, appeal_id: int, moderator_id: int, approved: bool, resolution: str) -> Dict[str, object]:
        if not self.bridge_enabled:
            return {"ok": False, "message": "Сервис апелляций недоступен."}
        now_ts = int(time.time())
        with self._connect_bridge() as conn:
            row = conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()
            if not row:
                return {"ok": False, "message": "Апелляция не найдена."}
            if row["status"] in {APPEAL_STATUS_APPROVED, APPEAL_STATUS_REJECTED, APPEAL_STATUS_AUTO_APPROVED, APPEAL_STATUS_CLOSED}:
                return {"ok": False, "message": f"Апелляция уже закрыта со статусом {row['status']}."}

            status = APPEAL_STATUS_APPROVED if approved else APPEAL_STATUS_REJECTED
            clean_resolution = (resolution or "").strip()
            conn.execute(
                """UPDATE appeals
                SET status = ?, resolution = ?, moderator_id = ?, reviewed_at = ?, updated_at = ?,
                    closed_at = ?, decision_type = 'manual', review_comment = ?
                WHERE id = ?""",
                (status, clean_resolution, moderator_id, now_ts, now_ts, now_ts, clean_resolution, appeal_id),
            )
            release_actions: List[Dict[str, int]] = []
            if approved:
                actions = conn.execute(
                    """SELECT id, chat_id, action
                    FROM moderation_actions
                    WHERE user_id = ? AND action IN ('ban', 'mute') AND active = 1""",
                    (int(row["user_id"]),),
                ).fetchall()
                for item in actions:
                    conn.execute(
                        "UPDATE moderation_actions SET active = 0, completed_at = ? WHERE id = ?",
                        (now_ts, int(item["id"])),
                    )
                    release_actions.append(
                        {"chat_id": int(item["chat_id"]), "action": item["action"]}
                    )
            self._log_event(
                conn,
                appeal_id,
                int(row["user_id"]),
                "resolved",
                actor_id=moderator_id,
                status_from=row["status"],
                status_to=status,
                details=clean_resolution,
            )
            conn.commit()
            return {
                "ok": True,
                "status": status,
                "user_id": int(row["user_id"]),
                "chat_id": int(row["chat_id"] or 0),
                "appeal_id": appeal_id,
                "resolution": clean_resolution,
                "release_actions": release_actions,
                "message": f"Апелляция #{appeal_id}: {status}",
            }

    def close_appeal(self, appeal_id: int, moderator_id: int, comment: str = "") -> Dict[str, object]:
        if not self.bridge_enabled:
            return {"ok": False, "message": "Сервис апелляций недоступен."}
        now_ts = int(time.time())
        with self._connect_bridge() as conn:
            row = conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()
            if not row:
                return {"ok": False, "message": "Апелляция не найдена."}
            if row["status"] == APPEAL_STATUS_CLOSED:
                return {"ok": False, "message": "Апелляция уже закрыта."}
            conn.execute(
                """UPDATE appeals
                SET status = ?, moderator_id = ?, reviewed_at = ?, updated_at = ?, closed_at = ?,
                    review_comment = ?, resolution = CASE WHEN resolution = '' THEN ? ELSE resolution END
                WHERE id = ?""",
                (APPEAL_STATUS_CLOSED, moderator_id, now_ts, now_ts, now_ts, comment.strip(), comment.strip(), appeal_id),
            )
            self._log_event(
                conn,
                appeal_id,
                int(row["user_id"]),
                "closed",
                actor_id=moderator_id,
                status_from=row["status"],
                status_to=APPEAL_STATUS_CLOSED,
                details=comment.strip(),
            )
            conn.commit()
            return {"ok": True, "message": f"Апелляция #{appeal_id} закрыта.", "status": APPEAL_STATUS_CLOSED}
