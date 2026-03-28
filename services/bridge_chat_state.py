import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple


def get_history(state: "BridgeState", chat_id: int) -> Deque[Tuple[str, str]]:
    with state.db_lock:
        rows = state.db.execute(
            "SELECT role, text FROM chat_history WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, state.history_limit),
        ).fetchall()
    history = deque(maxlen=state.history_limit)
    for role, text in reversed(rows):
        history.append((role, text))
    return history


def get_summary(state: "BridgeState", chat_id: int) -> str:
    with state.db_lock:
        row = state.db.execute(
            "SELECT summary FROM chat_summaries WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    return row[0] if row and row[0] else ""


def update_summary(
    state: "BridgeState",
    chat_id: int,
    *,
    truncate_text_func,
    build_actor_name_func,
) -> None:
    history = list(state.get_history(chat_id))[-12:]
    with state.db_lock:
        event_rows = state.db.execute(
            "SELECT created_at, user_id, username, first_name, last_name, role, message_type, text FROM chat_events WHERE chat_id = ? ORDER BY id DESC LIMIT 24",
            (chat_id,),
        ).fetchall()
        fact_rows = state.db.execute(
            "SELECT fact FROM memory_facts WHERE chat_id = ? ORDER BY id DESC LIMIT 8",
            (chat_id,),
        ).fetchall()
    if not history and not event_rows and not fact_rows:
        return
    lines = []
    for role, content in history:
        label = "User" if role == "user" else "Jarvis"
        lines.append(f"{label}: {truncate_text_func(content, 180)}")
    event_rows = list(reversed(event_rows))
    if event_rows:
        actor_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}
        for created_at, user_id, username, first_name, last_name, role, message_type, text in event_rows:
            actor = build_actor_name_func(user_id, username or "", first_name or "", last_name or "", role)
            actor_counts[actor] = actor_counts.get(actor, 0) + 1
            type_counts[message_type] = type_counts.get(message_type, 0) + 1
        top_actors = ", ".join(f"{name}={count}" for name, count in sorted(actor_counts.items(), key=lambda item: (-item[1], item[0]))[:4])
        top_types = ", ".join(f"{name}={count}" for name, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[:5])
        if top_actors:
            lines.append(f"Top actors: {top_actors}")
        if top_types:
            lines.append(f"Event mix: {top_types}")
    if fact_rows:
        lines.append("Pinned facts:")
        for row in fact_rows[:4]:
            lines.append(f"- {truncate_text_func(row[0] or '', 140)}")
    summary = truncate_text_func("\n".join(lines), 1800)
    with state.db_lock:
        state.db.execute(
            "INSERT INTO chat_summaries(chat_id, summary, updated_at) VALUES(?, ?, strftime('%s','now')) ON CONFLICT(chat_id) DO UPDATE SET summary = excluded.summary, updated_at = excluded.updated_at",
            (chat_id, summary),
        )
        recent_snapshot = state.db.execute(
            "SELECT summary, created_at FROM summary_snapshots WHERE chat_id = ? AND scope = 'rolling' ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        should_snapshot = True
        if recent_snapshot:
            previous_summary = recent_snapshot[0] or ""
            previous_ts = int(recent_snapshot[1] or 0)
            if previous_summary == summary and previous_ts >= int(time.time()) - 1800:
                should_snapshot = False
        if should_snapshot:
            state.db.execute(
                "INSERT INTO summary_snapshots(chat_id, scope, summary) VALUES(?, 'rolling', ?)",
                (chat_id, summary),
            )
        state.db.commit()


def add_fact(state: "BridgeState", chat_id: int, fact: str, created_by_user_id: Optional[int], *, normalize_whitespace_func) -> None:
    cleaned = normalize_whitespace_func(fact)
    if not cleaned:
        return
    with state.db_lock:
        state.db.execute(
            "INSERT INTO memory_facts(chat_id, created_by_user_id, fact) VALUES(?, ?, ?)",
            (chat_id, created_by_user_id, cleaned),
        )
        state.db.commit()


def get_facts(state: "BridgeState", chat_id: int, query: str = "", limit: int = 12, *, extract_keywords_func) -> List[str]:
    with state.db_lock:
        rows = state.db.execute(
            "SELECT fact FROM memory_facts WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, max(limit * 3, 36)),
        ).fetchall()
    facts = [row[0] for row in rows]
    if query:
        keywords = extract_keywords_func(query)
        if keywords:
            filtered = [fact for fact in facts if any(keyword in fact.lower() for keyword in keywords)]
            if filtered:
                facts = filtered
    return list(reversed(facts[:limit]))


def render_facts(state: "BridgeState", chat_id: int, query: str = "", limit: int = 12, *, truncate_text_func, extract_keywords_func) -> str:
    facts = get_facts(state, chat_id, query=query, limit=limit, extract_keywords_func=extract_keywords_func)
    if not facts:
        return ""
    return "\n".join(f"- {truncate_text_func(fact, 240)}" for fact in facts)


def get_mode(state: "BridgeState", chat_id: int, *, normalize_mode_func) -> str:
    with state.db_lock:
        row = state.db.execute(
            "SELECT mode FROM chat_modes WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    if not row or not row[0]:
        return state.default_mode
    return normalize_mode_func(row[0])


def set_mode(state: "BridgeState", chat_id: int, mode: str) -> None:
    with state.db_lock:
        state.db.execute(
            "INSERT INTO chat_modes(chat_id, mode) VALUES(?, ?) ON CONFLICT(chat_id) DO UPDATE SET mode = excluded.mode",
            (chat_id, mode),
        )
        state.db.commit()


def reset_chat(state: "BridgeState", chat_id: int) -> None:
    with state.db_lock:
        state.db.execute("DELETE FROM chat_history WHERE chat_id = ?", (chat_id,))
        state.db.execute("DELETE FROM chat_modes WHERE chat_id = ?", (chat_id,))
        state.db.execute("DELETE FROM chat_events WHERE chat_id = ?", (chat_id,))
        state.db.execute("DELETE FROM chat_summaries WHERE chat_id = ?", (chat_id,))
        state.db.execute("DELETE FROM memory_facts WHERE chat_id = ?", (chat_id,))
        state.db.commit()


def append_history(state: "BridgeState", chat_id: int, role: str, text: str, *, normalize_whitespace_func) -> None:
    cleaned = normalize_whitespace_func(text)
    if not cleaned:
        return
    with state.db_lock:
        state.db.execute(
            "INSERT INTO chat_history(chat_id, role, text) VALUES(?, ?, ?)",
            (chat_id, role, cleaned),
        )
        state.db.commit()
    state.update_summary(chat_id)


def update_event_text(
    state: "BridgeState",
    chat_id: int,
    message_id: Optional[int],
    text: str,
    *,
    message_type: Optional[str] = None,
    has_media: Optional[int] = None,
    file_kind: Optional[str] = None,
    normalize_whitespace_func,
) -> bool:
    cleaned = normalize_whitespace_func(text)
    if message_id is None or not cleaned:
        return False
    with state.db_lock:
        row = state.db.execute(
            "SELECT id FROM chat_events WHERE chat_id = ? AND message_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id, message_id),
        ).fetchone()
        if not row:
            return False
        event_id = int(row[0])
        updates = ["text = ?"]
        params: List[object] = [cleaned]
        if message_type is not None:
            updates.append("message_type = ?")
            params.append(message_type)
        if has_media is not None:
            updates.append("has_media = ?")
            params.append(has_media)
        if file_kind is not None:
            updates.append("file_kind = ?")
            params.append(file_kind)
        params.extend([chat_id, event_id])
        state.db.execute(
            f"UPDATE chat_events SET {', '.join(updates)} WHERE chat_id = ? AND id = ?",
            tuple(params),
        )
        state.db.execute("DELETE FROM chat_events_fts WHERE rowid = ?", (event_id,))
        state.db.execute("INSERT INTO chat_events_fts(rowid, text) VALUES(?, ?)", (event_id, cleaned))
        state.db.commit()
    return True


def record_event(
    state: "BridgeState",
    chat_id: int,
    user_id: Optional[int],
    role: str,
    message_type: str,
    text: str,
    *,
    message_id: Optional[int] = None,
    username: str = "",
    first_name: str = "",
    last_name: str = "",
    chat_type: str = "",
    reply_to_message_id: Optional[int] = None,
    reply_to_user_id: Optional[int] = None,
    reply_to_username: str = "",
    forward_origin: str = "",
    has_media: int = 0,
    file_kind: str = "",
    is_edited: int = 0,
    normalize_whitespace_func,
) -> None:
    cleaned = normalize_whitespace_func(text)
    if not cleaned:
        return
    with state.db_lock:
        cursor = state.db.execute(
            "INSERT INTO chat_events(chat_id, message_id, user_id, username, first_name, last_name, chat_type, role, message_type, text, reply_to_message_id, reply_to_user_id, reply_to_username, forward_origin, has_media, file_kind, is_edited) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chat_id, message_id, user_id, username, first_name, last_name, chat_type, role, message_type, cleaned, reply_to_message_id, reply_to_user_id, reply_to_username, forward_origin, has_media, file_kind, is_edited),
        )
        row_id = cursor.lastrowid
        state.db.execute("INSERT INTO chat_events_fts(rowid, text) VALUES(?, ?)", (row_id, cleaned))
        state.db.commit()


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import BridgeState
