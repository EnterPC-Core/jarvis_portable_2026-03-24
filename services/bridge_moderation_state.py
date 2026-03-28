import time
from typing import Dict, List, Optional, Tuple


def add_moderation_action(
    state: "BridgeState",
    chat_id: int,
    user_id: int,
    action: str,
    reason: str,
    created_by_user_id: Optional[int],
    expires_at: Optional[int] = None,
) -> None:
    with state.db_lock:
        state.db.execute(
            "INSERT INTO moderation_actions(chat_id, user_id, action, reason, created_by_user_id, expires_at) VALUES(?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, action, reason, created_by_user_id, expires_at),
        )
        state.db.commit()


def complete_moderation_action(state: "BridgeState", action_id: int) -> None:
    with state.db_lock:
        state.db.execute("UPDATE moderation_actions SET active = 0 WHERE id = ?", (action_id,))
        state.db.commit()


def deactivate_active_moderation(state: "BridgeState", chat_id: int, user_id: int, action: str) -> None:
    with state.db_lock:
        state.db.execute(
            "UPDATE moderation_actions SET active = 0 WHERE chat_id = ? AND user_id = ? AND action = ? AND active = 1",
            (chat_id, user_id, action),
        )
        state.db.commit()


def get_due_moderation_actions(state: "BridgeState", now_ts: int, limit: int = 20) -> List[Tuple[int, int, int, str]]:
    with state.db_lock:
        rows = state.db.execute(
            "SELECT id, chat_id, user_id, action FROM moderation_actions WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ? ORDER BY id ASC LIMIT ?",
            (now_ts, limit),
        ).fetchall()
    return [(int(row[0]), int(row[1]), int(row[2]), row[3]) for row in rows]


def get_latest_active_moderation(state: "BridgeState", chat_id: int) -> Optional[Tuple[int, int, str]]:
    with state.db_lock:
        row = state.db.execute(
            "SELECT id, user_id, action FROM moderation_actions WHERE chat_id = ? AND active = 1 ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
    if not row:
        return None
    return int(row[0]), int(row[1]), row[2] or ""


def get_active_moderations(state: "BridgeState", chat_id: int, limit: int = 10) -> List[Tuple[int, int, str, str]]:
    with state.db_lock:
        rows = state.db.execute(
            "SELECT id, user_id, action, reason FROM moderation_actions WHERE chat_id = ? AND active = 1 ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return [(int(row[0]), int(row[1]), row[2] or "", row[3] or "") for row in rows]


def get_managed_group_chat_ids(state: "BridgeState") -> List[int]:
    with state.db_lock:
        rows = state.db.execute(
            """SELECT DISTINCT chat_id
            FROM (
                SELECT chat_id FROM chat_events WHERE chat_type IN ('group', 'supergroup')
                UNION ALL
                SELECT chat_id FROM moderation_actions
                UNION ALL
                SELECT chat_id FROM warn_settings
                UNION ALL
                SELECT chat_id FROM welcome_settings
            )
            WHERE chat_id IS NOT NULL AND chat_id < 0
            ORDER BY chat_id"""
        ).fetchall()
    return [int(row[0]) for row in rows if row and row[0] is not None]


def add_warning(state: "BridgeState", chat_id: int, user_id: int, reason: str, created_by_user_id: Optional[int], expires_at: Optional[int] = None) -> int:
    with state.db_lock:
        state.db.execute(
            "DELETE FROM warnings WHERE expires_at IS NOT NULL AND expires_at <= strftime('%s','now')"
        )
        state.db.execute(
            "INSERT INTO warnings(chat_id, user_id, reason, created_by_user_id, expires_at) VALUES(?, ?, ?, ?, ?)",
            (chat_id, user_id, reason, created_by_user_id, expires_at),
        )
        count = state.db.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id = ? AND user_id = ? AND (expires_at IS NULL OR expires_at > strftime('%s','now'))",
            (chat_id, user_id),
        ).fetchone()[0]
        state.db.commit()
    return int(count)


def get_warning_count(state: "BridgeState", chat_id: int, user_id: int) -> int:
    with state.db_lock:
        state.db.execute(
            "DELETE FROM warnings WHERE expires_at IS NOT NULL AND expires_at <= strftime('%s','now')"
        )
        row = state.db.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id = ? AND user_id = ? AND (expires_at IS NULL OR expires_at > strftime('%s','now'))",
            (chat_id, user_id),
        ).fetchone()
        state.db.commit()
    return int(row[0]) if row else 0


def remove_last_warning(state: "BridgeState", chat_id: int, user_id: int) -> int:
    with state.db_lock:
        row = state.db.execute(
            "SELECT id FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id, user_id),
        ).fetchone()
        if not row:
            return 0
        state.db.execute("DELETE FROM warnings WHERE id = ?", (row[0],))
        count = state.db.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        ).fetchone()[0]
        state.db.commit()
    return int(count)


def reset_warnings(state: "BridgeState", chat_id: int, user_id: int) -> None:
    with state.db_lock:
        state.db.execute("DELETE FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        state.db.commit()


def get_warn_settings(state: "BridgeState", chat_id: int) -> Tuple[int, str, int]:
    with state.db_lock:
        row = state.db.execute(
            "SELECT warn_limit, warn_mode, warn_expire_seconds FROM warn_settings WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    if not row:
        return 3, "mute", 0
    return int(row[0]), row[1], int(row[2] or 0)


def set_warn_limit(state: "BridgeState", chat_id: int, warn_limit: int) -> None:
    with state.db_lock:
        state.db.execute(
            "INSERT INTO warn_settings(chat_id, warn_limit, warn_mode, warn_expire_seconds) VALUES(?, ?, COALESCE((SELECT warn_mode FROM warn_settings WHERE chat_id = ?), 'mute'), COALESCE((SELECT warn_expire_seconds FROM warn_settings WHERE chat_id = ?), 0)) ON CONFLICT(chat_id) DO UPDATE SET warn_limit = excluded.warn_limit",
            (chat_id, warn_limit, chat_id, chat_id),
        )
        state.db.commit()


def set_warn_mode(state: "BridgeState", chat_id: int, warn_mode: str) -> None:
    with state.db_lock:
        state.db.execute(
            "INSERT INTO warn_settings(chat_id, warn_limit, warn_mode, warn_expire_seconds) VALUES(?, COALESCE((SELECT warn_limit FROM warn_settings WHERE chat_id = ?), 3), ?, COALESCE((SELECT warn_expire_seconds FROM warn_settings WHERE chat_id = ?), 0)) ON CONFLICT(chat_id) DO UPDATE SET warn_mode = excluded.warn_mode",
            (chat_id, chat_id, warn_mode, chat_id),
        )
        state.db.commit()


def set_warn_time(state: "BridgeState", chat_id: int, warn_expire_seconds: int) -> None:
    with state.db_lock:
        state.db.execute(
            "INSERT INTO warn_settings(chat_id, warn_limit, warn_mode, warn_expire_seconds) VALUES(?, COALESCE((SELECT warn_limit FROM warn_settings WHERE chat_id = ?), 3), COALESCE((SELECT warn_mode FROM warn_settings WHERE chat_id = ?), 'mute'), ?) ON CONFLICT(chat_id) DO UPDATE SET warn_expire_seconds = excluded.warn_expire_seconds",
            (chat_id, chat_id, chat_id, warn_expire_seconds),
        )
        state.db.commit()


def get_warning_rows(state: "BridgeState", chat_id: int, user_id: int, limit: int = 5) -> List[Tuple[int, str]]:
    with state.db_lock:
        rows = state.db.execute(
            "SELECT created_at, reason FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, user_id, limit),
        ).fetchall()
    return [(int(row[0]), row[1] or "") for row in rows]


def get_welcome_settings(state: "BridgeState", chat_id: int, *, default_template: str) -> Tuple[bool, str]:
    with state.db_lock:
        row = state.db.execute(
            "SELECT enabled, template FROM welcome_settings WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    if not row:
        return False, default_template
    return bool(row[0]), row[1] or default_template


def set_welcome_enabled(state: "BridgeState", chat_id: int, enabled: bool, *, default_template: str) -> None:
    with state.db_lock:
        state.db.execute(
            "INSERT INTO welcome_settings(chat_id, enabled, template) VALUES(?, ?, COALESCE((SELECT template FROM welcome_settings WHERE chat_id = ?), ?)) ON CONFLICT(chat_id) DO UPDATE SET enabled = excluded.enabled",
            (chat_id, 1 if enabled else 0, chat_id, default_template),
        )
        state.db.commit()


def set_welcome_template(state: "BridgeState", chat_id: int, template: str) -> None:
    with state.db_lock:
        state.db.execute(
            "INSERT INTO welcome_settings(chat_id, enabled, template) VALUES(?, COALESCE((SELECT enabled FROM welcome_settings WHERE chat_id = ?), 0), ?) ON CONFLICT(chat_id) DO UPDATE SET template = excluded.template",
            (chat_id, chat_id, template),
        )
        state.db.commit()


def reset_welcome_template(state: "BridgeState", chat_id: int, *, default_template: str) -> None:
    with state.db_lock:
        state.db.execute(
            "INSERT INTO welcome_settings(chat_id, enabled, template) VALUES(?, COALESCE((SELECT enabled FROM welcome_settings WHERE chat_id = ?), 0), ?) ON CONFLICT(chat_id) DO UPDATE SET template = excluded.template",
            (chat_id, chat_id, default_template),
        )
        state.db.commit()


def try_start_upgrade(state: "BridgeState", chat_id: int) -> bool:
    with state.upgrade_lock:
        if state.global_upgrade_active or chat_id in state.upgrade_in_progress:
            return False
        state.global_upgrade_active = True
        state.upgrade_in_progress.add(chat_id)
        return True


def finish_upgrade(state: "BridgeState", chat_id: int) -> None:
    with state.upgrade_lock:
        state.upgrade_in_progress.discard(chat_id)
        state.global_upgrade_active = False


def try_start_chat_task(state: "BridgeState", chat_id: int) -> bool:
    with state.chat_task_lock:
        if chat_id in state.chat_tasks_in_progress:
            return False
        state.chat_tasks_in_progress.add(chat_id)
        return True


def finish_chat_task(state: "BridgeState", chat_id: int) -> None:
    with state.chat_task_lock:
        state.chat_tasks_in_progress.discard(chat_id)


def is_duplicate_message(
    state: "BridgeState",
    chat_id: int,
    message_id: Optional[int],
    *,
    max_seen_messages: int,
) -> bool:
    if message_id is None:
        return False
    key = (chat_id, message_id)
    if key in state.seen_message_keys:
        return True
    state.seen_message_keys[key] = time.time()
    state.seen_message_keys.move_to_end(key)
    while len(state.seen_message_keys) > max_seen_messages:
        state.seen_message_keys.popitem(last=False)
    return False


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import BridgeState
