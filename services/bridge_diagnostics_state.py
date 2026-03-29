import json
import sqlite3
from typing import List, Optional, Sequence, TYPE_CHECKING


def record_request_diagnostic(
    state: "BridgeState",
    chat_id: int,
    user_id: Optional[int],
    chat_type: str,
    persona: str,
    intent: str,
    route_kind: str,
    source_label: str,
    request_kind: str,
    used_live: bool,
    used_web: bool,
    used_events: bool,
    used_database: bool,
    used_reply: bool,
    used_workspace: bool,
    guardrails: str,
    outcome: str,
    response_mode: str,
    sources: str,
    tools_used: str,
    memory_used: str,
    confidence: float,
    freshness: str,
    notes: str,
    latency_ms: int,
    query_text: str,
    request_trace_id: str = "",
    task_id: str = "",
    *,
    truncate_text_func,
    normalize_whitespace_func,
) -> None:
    with state.db_lock:
        state.db.execute(
            """INSERT INTO request_diagnostics(
                chat_id, user_id, chat_type, persona, intent, route_kind, source_label,
                used_live, used_web, used_events, used_database, used_reply, used_workspace,
                guardrails, outcome, request_kind, response_mode, sources, tools_used, memory_used,
                confidence, freshness, notes, latency_ms, query_text, request_trace_id, task_id
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chat_id,
                user_id,
                chat_type,
                persona,
                intent,
                route_kind,
                source_label,
                1 if used_live else 0,
                1 if used_web else 0,
                1 if used_events else 0,
                1 if used_database else 0,
                1 if used_reply else 0,
                1 if used_workspace else 0,
                guardrails,
                outcome,
                truncate_text_func(request_kind, 40),
                truncate_text_func(response_mode, 40),
                truncate_text_func(sources, 400),
                truncate_text_func(tools_used, 400),
                truncate_text_func(memory_used, 400),
                max(0.0, min(1.0, float(confidence))),
                truncate_text_func(freshness, 80),
                truncate_text_func(normalize_whitespace_func(notes), 600),
                max(0, int(latency_ms)),
                truncate_text_func(normalize_whitespace_func(query_text), 900),
                truncate_text_func(request_trace_id, 80),
                truncate_text_func(task_id, 120),
            ),
        )
        state.db.commit()


def get_recent_request_diagnostics(
    state: "BridgeState",
    limit: int = 8,
    chat_id: Optional[int] = None,
) -> List[sqlite3.Row]:
    effective_limit = max(1, min(30, int(limit)))
    with state.db_lock:
        if chat_id is None:
            rows = state.db.execute(
                """SELECT created_at, chat_id, user_id, chat_type, persona, intent, route_kind, source_label,
                          used_live, used_web, used_events, used_database, used_reply, used_workspace,
                          guardrails, outcome, latency_ms, query_text
                   FROM request_diagnostics
                   ORDER BY id DESC
                   LIMIT ?""",
                (effective_limit,),
            ).fetchall()
        else:
            rows = state.db.execute(
                """SELECT created_at, chat_id, user_id, chat_type, persona, intent, route_kind, source_label,
                          used_live, used_web, used_events, used_database, used_reply, used_workspace,
                          guardrails, outcome, latency_ms, query_text
                   FROM request_diagnostics
                   WHERE chat_id = ?
                   ORDER BY id DESC
                   LIMIT ?""",
                (chat_id, effective_limit),
            ).fetchall()
    return rows


def record_repair_journal(
    state: "BridgeState",
    *,
    signal_code: str,
    playbook_id: str,
    status: str,
    summary: str,
    evidence: str = "",
    verification_result: str = "",
    notes: str = "",
    truncate_text_func,
    normalize_whitespace_func,
) -> None:
    with state.db_lock:
        state.db.execute(
            """INSERT INTO repair_journal(
                signal_code, playbook_id, status, summary, evidence, verification_result, notes
            ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (
                truncate_text_func(signal_code, 80),
                truncate_text_func(playbook_id, 120),
                truncate_text_func(status, 40),
                truncate_text_func(normalize_whitespace_func(summary), 300),
                truncate_text_func(normalize_whitespace_func(evidence), 500),
                truncate_text_func(normalize_whitespace_func(verification_result), 300),
                truncate_text_func(normalize_whitespace_func(notes), 500),
            ),
        )
        state.db.commit()


def get_recent_repair_journal(state: "BridgeState", limit: int = 8) -> List[sqlite3.Row]:
    effective_limit = max(1, min(20, int(limit)))
    with state.db_lock:
        return state.db.execute(
            """SELECT created_at, signal_code, playbook_id, status, summary, evidence, verification_result, notes
               FROM repair_journal
               ORDER BY id DESC
               LIMIT ?""",
            (effective_limit,),
        ).fetchall()


def has_recent_self_heal_incident(
    state: "BridgeState",
    problem_type: str,
    signal_code: str,
    window_seconds: int = 900,
) -> bool:
    with state.db_lock:
        row = state.db.execute(
            """SELECT 1 FROM self_heal_incidents
               WHERE problem_type = ? AND signal_code = ?
                 AND updated_at >= strftime('%s','now') - ?
               ORDER BY id DESC
               LIMIT 1""",
            (problem_type, signal_code, max(60, int(window_seconds))),
        ).fetchone()
    return row is not None


def record_self_heal_incident(
    state: "BridgeState",
    *,
    problem_type: str,
    signal_code: str,
    state_value: str,
    severity: str,
    summary: str,
    evidence: str,
    risk_level: str,
    autonomy_level: str,
    source: str,
    confidence: float,
    suggested_playbook: str = "",
    truncate_text_func,
    normalize_whitespace_func,
) -> int:
    with state.db_lock:
        cursor = state.db.execute(
            """INSERT INTO self_heal_incidents(
                problem_type, signal_code, state, severity, summary, evidence, risk_level, autonomy_level,
                source, confidence, suggested_playbook
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                truncate_text_func(problem_type, 80),
                truncate_text_func(signal_code, 80),
                truncate_text_func(state_value, 40),
                truncate_text_func(severity, 40),
                truncate_text_func(normalize_whitespace_func(summary), 300),
                truncate_text_func(normalize_whitespace_func(evidence), 600),
                truncate_text_func(risk_level, 40),
                truncate_text_func(autonomy_level, 40),
                truncate_text_func(source, 80),
                max(0.0, min(1.0, float(confidence))),
                truncate_text_func(suggested_playbook, 120),
            ),
        )
        incident_id = int(cursor.lastrowid or 0)
        state.db.execute(
            """INSERT INTO self_heal_transitions(incident_id, from_state, to_state, note)
               VALUES(?, ?, ?, ?)""",
            (incident_id, "", truncate_text_func(state_value, 40), "incident detected"),
        )
        state.db.commit()
    return incident_id


def update_self_heal_incident_state(
    state: "BridgeState",
    incident_id: int,
    *,
    new_state: str,
    note: str = "",
    verification_status: str = "",
    lesson_text: str = "",
    truncate_text_func,
    normalize_whitespace_func,
) -> None:
    with state.db_lock:
        current = state.db.execute(
            "SELECT state FROM self_heal_incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()
        previous_state = str(current["state"] or "") if current else ""
        state.db.execute(
            """UPDATE self_heal_incidents
               SET state = ?, verification_status = CASE WHEN ? != '' THEN ? ELSE verification_status END,
                   lesson_text = CASE WHEN ? != '' THEN ? ELSE lesson_text END,
                   updated_at = strftime('%s','now')
               WHERE id = ?""",
            (
                truncate_text_func(new_state, 40),
                verification_status,
                truncate_text_func(verification_status, 80),
                lesson_text,
                truncate_text_func(normalize_whitespace_func(lesson_text), 600),
                incident_id,
            ),
        )
        state.db.execute(
            """INSERT INTO self_heal_transitions(incident_id, from_state, to_state, note)
               VALUES(?, ?, ?, ?)""",
            (
                incident_id,
                truncate_text_func(previous_state, 40),
                truncate_text_func(new_state, 40),
                truncate_text_func(normalize_whitespace_func(note), 300),
            ),
        )
        state.db.commit()


def record_self_heal_attempt(
    state: "BridgeState",
    *,
    incident_id: int,
    playbook_id: str,
    state_value: str,
    status: str,
    execution_summary: str,
    executed_steps: Sequence[str] = (),
    failed_step: str = "",
    artifacts_changed: Sequence[str] = (),
    verification_required: bool = True,
    notes: str = "",
    stdout_log: Sequence[str] = (),
    stderr_log: Sequence[str] = (),
    truncate_text_func,
) -> int:
    with state.db_lock:
        cursor = state.db.execute(
            """INSERT INTO self_heal_attempts(
                incident_id, playbook_id, state, status, execution_summary, executed_steps_json, failed_step,
                artifacts_changed_json, verification_required, notes, stdout_json, stderr_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                incident_id,
                truncate_text_func(playbook_id, 120),
                truncate_text_func(state_value, 40),
                truncate_text_func(status, 40),
                truncate_text_func(execution_summary, 400),
                truncate_text_func(json.dumps(list(executed_steps), ensure_ascii=False), 4000),
                truncate_text_func(failed_step, 120),
                truncate_text_func(json.dumps(list(artifacts_changed), ensure_ascii=False), 2000),
                1 if verification_required else 0,
                truncate_text_func(notes, 800),
                truncate_text_func(json.dumps(list(stdout_log), ensure_ascii=False), 4000),
                truncate_text_func(json.dumps(list(stderr_log), ensure_ascii=False), 4000),
            ),
        )
        state.db.commit()
    return int(cursor.lastrowid or 0)


def update_self_heal_attempt(
    state: "BridgeState",
    attempt_id: int,
    *,
    state_value: str = "",
    status: str = "",
    execution_summary: str = "",
    notes: str = "",
    truncate_text_func,
    normalize_whitespace_func,
) -> None:
    with state.db_lock:
        current = state.db.execute(
            """SELECT state, status, execution_summary, notes
               FROM self_heal_attempts
               WHERE id = ?""",
            (attempt_id,),
        ).fetchone()
        if current is None:
            return
        state.db.execute(
            """UPDATE self_heal_attempts
               SET state = ?, status = ?, execution_summary = ?, notes = ?
               WHERE id = ?""",
            (
                truncate_text_func(state_value or str(current["state"] or ""), 40),
                truncate_text_func(status or str(current["status"] or ""), 40),
                truncate_text_func(normalize_whitespace_func(execution_summary or str(current["execution_summary"] or "")), 400),
                truncate_text_func(normalize_whitespace_func(notes or str(current["notes"] or "")), 800),
                attempt_id,
            ),
        )
        state.db.commit()


def record_self_heal_verification(
    state: "BridgeState",
    *,
    incident_id: int,
    attempt_id: Optional[int],
    verified: bool,
    before_state: dict,
    after_state: dict,
    confidence: float,
    remaining_issues: Sequence[str] = (),
    regressions_detected: Sequence[str] = (),
    notes: str = "",
    truncate_text_func,
    normalize_whitespace_func,
) -> int:
    with state.db_lock:
        cursor = state.db.execute(
            """INSERT INTO self_heal_verifications(
                incident_id, attempt_id, verified, before_state_json, after_state_json, confidence,
                remaining_issues_json, regressions_json, notes
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                incident_id,
                attempt_id,
                1 if verified else 0,
                truncate_text_func(json.dumps(before_state, ensure_ascii=False, sort_keys=True), 4000),
                truncate_text_func(json.dumps(after_state, ensure_ascii=False, sort_keys=True), 4000),
                max(0.0, min(1.0, float(confidence))),
                truncate_text_func(json.dumps(list(remaining_issues), ensure_ascii=False), 2000),
                truncate_text_func(json.dumps(list(regressions_detected), ensure_ascii=False), 2000),
                truncate_text_func(normalize_whitespace_func(notes), 800),
            ),
        )
        state.db.commit()
    return int(cursor.lastrowid or 0)


def record_self_heal_lesson(
    state: "BridgeState",
    *,
    incident_id: int,
    lesson_key: str,
    lesson_text: str,
    confidence: float = 0.5,
    truncate_text_func,
    normalize_whitespace_func,
) -> int:
    with state.db_lock:
        cursor = state.db.execute(
            """INSERT INTO self_heal_lessons(incident_id, lesson_key, lesson_text, confidence)
               VALUES(?, ?, ?, ?)""",
            (
                incident_id,
                truncate_text_func(lesson_key, 120),
                truncate_text_func(normalize_whitespace_func(lesson_text), 800),
                max(0.0, min(1.0, float(confidence))),
            ),
        )
        state.db.commit()
    return int(cursor.lastrowid or 0)


def get_recent_self_heal_incidents(state: "BridgeState", limit: int = 8) -> List[sqlite3.Row]:
    effective_limit = max(1, min(20, int(limit)))
    with state.db_lock:
        return state.db.execute(
            """SELECT id, problem_type, signal_code, state, severity, summary, evidence, risk_level,
                      autonomy_level, source, confidence, suggested_playbook, verification_status, lesson_text, created_at, updated_at
               FROM self_heal_incidents
               ORDER BY id DESC
               LIMIT ?""",
            (effective_limit,),
        ).fetchall()


def get_self_heal_incident(state: "BridgeState", incident_id: int) -> Optional[sqlite3.Row]:
    with state.db_lock:
        row = state.db.execute(
            """SELECT id, problem_type, signal_code, state, severity, summary, evidence, risk_level,
                      autonomy_level, source, confidence, suggested_playbook, verification_status, lesson_text, created_at, updated_at
               FROM self_heal_incidents
               WHERE id = ?""",
            (incident_id,),
        ).fetchone()
    return row


def find_recent_self_heal_incident(
    state: "BridgeState",
    problem_type: str,
    signal_code: str,
    window_seconds: int = 3600,
) -> Optional[sqlite3.Row]:
    with state.db_lock:
        row = state.db.execute(
            """SELECT id, problem_type, signal_code, state, severity, summary, evidence, risk_level,
                      autonomy_level, source, confidence, suggested_playbook, verification_status, lesson_text, created_at, updated_at
               FROM self_heal_incidents
               WHERE problem_type = ? AND signal_code = ?
                 AND updated_at >= strftime('%s','now') - ?
               ORDER BY id DESC
               LIMIT 1""",
            (problem_type, signal_code, max(60, int(window_seconds))),
        ).fetchone()
    return row


def count_self_heal_attempts(state: "BridgeState", incident_id: int) -> int:
    with state.db_lock:
        row = state.db.execute(
            "SELECT COUNT(*) FROM self_heal_attempts WHERE incident_id = ?",
            (incident_id,),
        ).fetchone()
    return int(row[0] or 0) if row else 0


def get_world_state_rows(
    state: "BridgeState",
    category: str = "",
    limit: int = 10,
) -> List[sqlite3.Row]:
    effective_limit = max(1, min(30, int(limit)))
    with state.db_lock:
        if category:
            rows = state.db.execute(
                """SELECT state_key, category, status, value_text, value_number, source, confidence,
                          ttl_seconds, verification_method, stale_flag, updated_at
                   FROM world_state_registry
                   WHERE category = ?
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (category, effective_limit),
            ).fetchall()
        else:
            rows = state.db.execute(
                """SELECT state_key, category, status, value_text, value_number, source, confidence,
                          ttl_seconds, verification_method, stale_flag, updated_at
                   FROM world_state_registry
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (effective_limit,),
            ).fetchall()
    return rows


if TYPE_CHECKING:
    from tg_codex_bridge import BridgeState
