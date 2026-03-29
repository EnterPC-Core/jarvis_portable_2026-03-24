from typing import Dict, List, Optional, TYPE_CHECKING


def upsert_task_run(
    state: "BridgeState",
    *,
    task_id: str,
    chat_id: int,
    user_id: Optional[int] = None,
    message_id: Optional[int] = None,
    delivery_chat_id: Optional[int] = None,
    progress_message_id: Optional[int] = None,
    request_trace_id: str = "",
    task_kind: str = "",
    route_kind: str = "",
    persona: str = "",
    request_kind: str = "",
    source: str = "",
    summary: str = "",
    status: str = "",
    approval_state: str = "",
    verification_state: str = "",
    outcome: str = "",
    evidence_text: str = "",
    error_text: str = "",
    tools_used: str = "",
    memory_used: str = "",
    truncate_text_func=None,
    normalize_whitespace_func=None,
) -> None:
    truncate_text = truncate_text_func
    normalize_whitespace = normalize_whitespace_func
    with state.db_lock:
        state.db.execute(
            """INSERT INTO task_runs(
                task_id, chat_id, user_id, message_id, delivery_chat_id, progress_message_id, request_trace_id,
                task_kind, route_kind, persona, request_kind, source, summary, status, approval_state,
                verification_state, outcome, evidence_text, error_text, tools_used, memory_used, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
            ON CONFLICT(task_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                user_id = excluded.user_id,
                message_id = CASE WHEN excluded.message_id IS NOT NULL AND excluded.message_id != 0 THEN excluded.message_id ELSE task_runs.message_id END,
                delivery_chat_id = CASE WHEN excluded.delivery_chat_id IS NOT NULL AND excluded.delivery_chat_id != 0 THEN excluded.delivery_chat_id ELSE task_runs.delivery_chat_id END,
                progress_message_id = CASE WHEN excluded.progress_message_id IS NOT NULL AND excluded.progress_message_id != 0 THEN excluded.progress_message_id ELSE task_runs.progress_message_id END,
                request_trace_id = CASE WHEN excluded.request_trace_id != '' THEN excluded.request_trace_id ELSE task_runs.request_trace_id END,
                task_kind = CASE WHEN excluded.task_kind != '' THEN excluded.task_kind ELSE task_runs.task_kind END,
                route_kind = CASE WHEN excluded.route_kind != '' THEN excluded.route_kind ELSE task_runs.route_kind END,
                persona = CASE WHEN excluded.persona != '' THEN excluded.persona ELSE task_runs.persona END,
                request_kind = CASE WHEN excluded.request_kind != '' THEN excluded.request_kind ELSE task_runs.request_kind END,
                source = CASE WHEN excluded.source != '' THEN excluded.source ELSE task_runs.source END,
                summary = CASE WHEN excluded.summary != '' THEN excluded.summary ELSE task_runs.summary END,
                status = CASE WHEN excluded.status != '' THEN excluded.status ELSE task_runs.status END,
                approval_state = CASE WHEN excluded.approval_state != '' THEN excluded.approval_state ELSE task_runs.approval_state END,
                verification_state = CASE WHEN excluded.verification_state != '' THEN excluded.verification_state ELSE task_runs.verification_state END,
                outcome = CASE WHEN excluded.outcome != '' THEN excluded.outcome ELSE task_runs.outcome END,
                evidence_text = CASE WHEN excluded.evidence_text != '' THEN excluded.evidence_text ELSE task_runs.evidence_text END,
                error_text = CASE WHEN excluded.error_text != '' THEN excluded.error_text ELSE task_runs.error_text END,
                tools_used = CASE WHEN excluded.tools_used != '' THEN excluded.tools_used ELSE task_runs.tools_used END,
                memory_used = CASE WHEN excluded.memory_used != '' THEN excluded.memory_used ELSE task_runs.memory_used END,
                updated_at = strftime('%s','now'),
                completed_at = CASE
                    WHEN excluded.status IN ('completed', 'failed', 'lost', 'timed_out', 'cancelled') THEN strftime('%s','now')
                    ELSE task_runs.completed_at
                END""",
            (
                truncate_text(task_id, 120),
                int(chat_id),
                user_id,
                int(message_id or 0) if message_id else None,
                int(delivery_chat_id or 0) if delivery_chat_id else None,
                int(progress_message_id or 0) if progress_message_id else None,
                truncate_text(request_trace_id, 80),
                truncate_text(task_kind, 80),
                truncate_text(route_kind, 80),
                truncate_text(persona, 40),
                truncate_text(request_kind, 40),
                truncate_text(source, 80),
                truncate_text(normalize_whitespace(summary), 500),
                truncate_text(status, 40),
                truncate_text(approval_state, 40),
                truncate_text(verification_state, 40),
                truncate_text(outcome, 40),
                truncate_text(normalize_whitespace(evidence_text), 900),
                truncate_text(normalize_whitespace(error_text), 600),
                truncate_text(tools_used, 300),
                truncate_text(memory_used, 300),
            ),
        )
        state.db.commit()


def update_task_run(
    state: "BridgeState",
    task_id: str,
    *,
    status: str = "",
    approval_state: str = "",
    verification_state: str = "",
    outcome: str = "",
    evidence_text: str = "",
    error_text: str = "",
    progress_message_id: Optional[int] = None,
    tools_used: str = "",
    memory_used: str = "",
    truncate_text_func=None,
    normalize_whitespace_func=None,
) -> None:
    truncate_text = truncate_text_func
    normalize_whitespace = normalize_whitespace_func
    assignments = ["updated_at = strftime('%s','now')"]
    params: List[object] = []
    if status:
        assignments.append("status = ?")
        params.append(truncate_text(status, 40))
        if status in {"completed", "failed", "lost", "timed_out", "cancelled"}:
            assignments.append("completed_at = strftime('%s','now')")
    if approval_state:
        assignments.append("approval_state = ?")
        params.append(truncate_text(approval_state, 40))
    if verification_state:
        assignments.append("verification_state = ?")
        params.append(truncate_text(verification_state, 40))
    if outcome:
        assignments.append("outcome = ?")
        params.append(truncate_text(outcome, 40))
    if evidence_text:
        assignments.append("evidence_text = ?")
        params.append(truncate_text(normalize_whitespace(evidence_text), 900))
    if error_text:
        assignments.append("error_text = ?")
        params.append(truncate_text(normalize_whitespace(error_text), 600))
    if progress_message_id is not None:
        assignments.append("progress_message_id = ?")
        params.append(int(progress_message_id or 0))
    if tools_used:
        assignments.append("tools_used = ?")
        params.append(truncate_text(tools_used, 300))
    if memory_used:
        assignments.append("memory_used = ?")
        params.append(truncate_text(memory_used, 300))
    if len(assignments) == 1:
        return
    params.append(truncate_text(task_id, 120))
    with state.db_lock:
        state.db.execute(
            f"UPDATE task_runs SET {', '.join(assignments)} WHERE task_id = ?",
            tuple(params),
        )
        state.db.commit()


def get_task_run(state: "BridgeState", task_id: str):
    with state.db_lock:
        return state.db.execute(
            """SELECT task_id, chat_id, user_id, message_id, delivery_chat_id, progress_message_id, request_trace_id,
                      task_kind, route_kind, persona, request_kind, source, summary, status, approval_state,
                      verification_state, outcome, evidence_text, error_text, tools_used, memory_used,
                      created_at, updated_at, completed_at
               FROM task_runs
               WHERE task_id = ?""",
            (task_id,),
        ).fetchone()


def find_latest_task_id_by_request_trace(state: "BridgeState", request_trace_id: str) -> str:
    if not (request_trace_id or "").strip():
        return ""
    with state.db_lock:
        row = state.db.execute(
            "SELECT task_id FROM task_runs WHERE request_trace_id = ? ORDER BY updated_at DESC, created_at DESC LIMIT 1",
            (request_trace_id.strip(),),
        ).fetchone()
    return str(row[0] or "") if row else ""


def get_recent_task_rows(state: "BridgeState", chat_id: int, limit: int = 6):
    with state.db_lock:
        return state.db.execute(
            """SELECT task_id, task_kind, route_kind, status, verification_state, outcome, summary,
                      evidence_text, error_text, updated_at, completed_at
               FROM task_runs
               WHERE chat_id = ?
               ORDER BY updated_at DESC, created_at DESC
               LIMIT ?""",
            (chat_id, max(1, min(20, int(limit)))),
        ).fetchall()


def record_task_event(
    state: "BridgeState",
    *,
    task_id: str,
    chat_id: int,
    request_trace_id: str = "",
    phase: str,
    status: str,
    detail: str = "",
    evidence_text: str = "",
    truncate_text_func,
    normalize_whitespace_func,
) -> None:
    with state.db_lock:
        state.db.execute(
            """INSERT INTO task_events(task_id, request_trace_id, chat_id, phase, status, detail, evidence_text)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (
                truncate_text_func(task_id, 120),
                truncate_text_func(request_trace_id, 80),
                int(chat_id or 0),
                truncate_text_func(phase, 60),
                truncate_text_func(status, 40),
                truncate_text_func(normalize_whitespace_func(detail), 300),
                truncate_text_func(normalize_whitespace_func(evidence_text), 900),
            ),
        )
        state.db.commit()


def get_recent_task_events(state: "BridgeState", chat_id: int, limit: int = 8):
    with state.db_lock:
        return state.db.execute(
            """SELECT task_id, request_trace_id, phase, status, detail, evidence_text, created_at
               FROM task_events
               WHERE chat_id = ?
               ORDER BY id DESC
               LIMIT ?""",
            (chat_id, max(1, min(20, int(limit)))),
        ).fetchall()


def get_task_context(state: "BridgeState", chat_id: int, limit: int = 4, *, truncate_text_func) -> str:
    rows = get_recent_task_rows(state, chat_id, limit=max(2, limit))
    event_rows = get_recent_task_events(state, chat_id, limit=max(4, limit * 2))
    if not rows and not event_rows:
        return ""
    lines = ["Task continuity:"]
    for row in rows[: max(1, limit)]:
        status = str(row["status"] or "-")
        verification = str(row["verification_state"] or "-")
        outcome = str(row["outcome"] or "-")
        descriptor = str(row["route_kind"] or row["task_kind"] or row["task_id"] or "-")
        lines.append(f"- {descriptor}: status={status}; verification={verification}; outcome={outcome}")
        evidence = str(row["evidence_text"] or row["error_text"] or row["summary"] or "").strip()
        if evidence:
            lines.append(f"  {truncate_text_func(evidence, 180)}")
    seen_events = set()
    for row in event_rows[: max(2, limit)]:
        event_key = (
            str(row["task_id"] or ""),
            str(row["phase"] or ""),
            str(row["status"] or ""),
            str(row["detail"] or ""),
        )
        if event_key in seen_events:
            continue
        seen_events.add(event_key)
        descriptor = str(row["task_id"] or row["request_trace_id"] or "-")
        lines.append(
            f"- event {descriptor}: phase={str(row['phase'] or '-')}; status={str(row['status'] or '-')}"
        )
        detail = str(row["detail"] or row["evidence_text"] or "").strip()
        if detail:
            lines.append(f"  {truncate_text_func(detail, 180)}")
    return "\n".join(lines)


if TYPE_CHECKING:
    from tg_codex_bridge import BridgeState
