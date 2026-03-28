#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tg_codex_bridge import BridgeState
DEFAULT_DB_PATH = PROJECT_ROOT / "jarvis_memory.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild group/supergroup memory from existing chat_events without touching bridge runtime."
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="Path to SQLite memory DB.",
    )
    parser.add_argument(
        "--chat-id",
        type=int,
        action="append",
        dest="chat_ids",
        help="Restrict refresh to specific chat_id. May be passed multiple times.",
    )
    return parser.parse_args()


def get_group_chats(db: sqlite3.Connection, filter_chat_ids: Optional[Sequence[int]]) -> List[Tuple[int, int]]:
    params: List[object] = []
    where = "WHERE chat_type IN ('group', 'supergroup')"
    if filter_chat_ids:
        placeholders = ",".join("?" for _ in filter_chat_ids)
        where += f" AND chat_id IN ({placeholders})"
        params.extend(int(chat_id) for chat_id in filter_chat_ids)
    rows = db.execute(
        f"""
        SELECT chat_id, MAX(id) AS max_event_id
        FROM chat_events
        {where}
        GROUP BY chat_id
        ORDER BY chat_id
        """,
        params,
    ).fetchall()
    return [(int(row[0]), int(row[1] or 0)) for row in rows]


def rebuild_participants(state: BridgeState, chat_id: int) -> int:
    rows = state.db.execute(
        """
        SELECT
            user_id,
            COALESCE(MAX(NULLIF(username, '')), '') AS username,
            COALESCE(MAX(NULLIF(first_name, '')), '') AS first_name,
            COALESCE(MAX(NULLIF(last_name, '')), '') AS last_name,
            MIN(created_at) AS first_seen_at,
            MAX(created_at) AS last_seen_at
        FROM chat_events
        WHERE chat_id = ? AND role = 'user' AND user_id IS NOT NULL
        GROUP BY user_id
        """,
        (chat_id,),
    ).fetchall()
    count = 0
    with state.db_lock:
        for row in rows:
            state.db.execute(
                """
                INSERT INTO chat_participants(
                    chat_id, user_id, username, first_name, last_name, is_bot, is_admin, last_status,
                    first_seen_at, last_seen_at, last_join_at, last_leave_at
                ) VALUES(?, ?, ?, ?, ?, 0, 0, '', ?, ?, NULL, NULL)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    username = CASE WHEN excluded.username != '' THEN excluded.username ELSE chat_participants.username END,
                    first_name = CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE chat_participants.first_name END,
                    last_name = CASE WHEN excluded.last_name != '' THEN excluded.last_name ELSE chat_participants.last_name END,
                    first_seen_at = MIN(chat_participants.first_seen_at, excluded.first_seen_at),
                    last_seen_at = MAX(chat_participants.last_seen_at, excluded.last_seen_at)
                """,
                (
                    chat_id,
                    int(row["user_id"]),
                    row["username"] or "",
                    row["first_name"] or "",
                    row["last_name"] or "",
                    int(row["first_seen_at"] or 0),
                    int(row["last_seen_at"] or 0),
                ),
            )
            count += 1
        state.db.commit()
    return count


def refresh_user_profiles(state: BridgeState, chat_id: int) -> int:
    rows = state.db.execute(
        """
        SELECT user_id, username, first_name, last_name
        FROM chat_participants
        WHERE chat_id = ?
        ORDER BY last_seen_at DESC
        """,
        (chat_id,),
    ).fetchall()
    refreshed = 0
    for row in rows:
        state.refresh_user_memory_profile(
            chat_id,
            int(row["user_id"]),
            username=row["username"] or "",
            first_name=row["first_name"] or "",
            last_name=row["last_name"] or "",
        )
        refreshed += 1
    return refreshed


def get_chat_title(state: BridgeState, chat_id: int) -> str:
    row = state.db.execute(
        "SELECT chat_title FROM chat_runtime_cache WHERE chat_id = ?",
        (chat_id,),
    ).fetchone()
    if row and row["chat_title"]:
        return str(row["chat_title"])
    return ""


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).resolve()
    state = BridgeState(history_limit=12, default_mode="jarvis", db_path=str(db_path))
    chats = get_group_chats(state.db, args.chat_ids)
    if not chats:
        print("No group chats found.")
        return 0

    for chat_id, max_event_id in chats:
        title = get_chat_title(state, chat_id)
        participant_count = rebuild_participants(state, chat_id)
        profiles_count = refresh_user_profiles(state, chat_id)
        relation_done = state.refresh_relation_memory(chat_id)
        state.update_summary(chat_id)
        state.update_group_deep_profile(chat_id)
        state.mark_memory_refresh(
            chat_id,
            max_event_id,
            summary_refreshed=True,
            users_refreshed=profiles_count > 0,
        )
        summary_count_row = state.db.execute(
            "SELECT COUNT(*) FROM summary_snapshots WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        deep_profile_row = state.db.execute(
            "SELECT COUNT(*) FROM summary_snapshots WHERE chat_id = ? AND scope = 'group_deep_profile'",
            (chat_id,),
        ).fetchone()
        relation_count_row = state.db.execute(
            "SELECT COUNT(*) FROM relation_memory WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        print(
            f"chat_id={chat_id} title={title or '<empty>'} "
            f"participants={participant_count} user_profiles={profiles_count} "
            f"relations={int(relation_count_row[0] or 0)} relation_refresh={'yes' if relation_done else 'no'} "
            f"summaries={int(summary_count_row[0] or 0)} deep_profiles={int(deep_profile_row[0] or 0)}"
        )

    state.db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
