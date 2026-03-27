import json
from typing import List

from services.failure_detectors import detect_failure_signals
from services.repair_contracts import (
    SELF_HEAL_STATE_CLASSIFIED,
    SELF_HEAL_STATE_DETECTED,
    SELF_HEAL_STATE_EXECUTING,
    SELF_HEAL_STATE_FAILED,
    SELF_HEAL_STATE_REPAIRED,
    SELF_HEAL_STATE_REPAIR_PLANNED,
    SELF_HEAL_STATE_VERIFYING,
    SelfHealingPlan,
)
from services.repair_playbooks import select_playbooks_for_classifications
from services.repair_state_tracker import choose_auto_repair_incident, should_send_auto_repair_report
from services.self_heal_classifier import classify_failures
from services.self_heal_executor import execute_repair_plan
from services.self_heal_policy import decide_repair_policy
from services.self_heal_verifier import capture_health_state, verify_repair


def run_auto_repair_loop(bridge: "TelegramBridge", *, source: str) -> str:
    runtime_snapshot = bridge.inspect_runtime_log()
    recent_errors = bridge.read_recent_log_highlights(limit=10)
    recent_routes = bridge.state.get_recent_request_diagnostics(limit=8)
    signals = detect_failure_signals(
        runtime_snapshot=runtime_snapshot,
        recent_errors=recent_errors,
        recent_routes=recent_routes,
        heartbeat_timeout_seconds=bridge.config.heartbeat_timeout_seconds,
        heartbeat_exists=bridge.heartbeat_path.exists(),
    )
    if not signals:
        return "AUTO SELF-HEAL\n\nАктивных failure signals нет."
    classifications = classify_failures(signals=signals, owner_autofix_enabled=True)
    playbooks = select_playbooks_for_classifications(classifications)
    lines: List[str] = ["AUTO SELF-HEAL"]
    handled = 0
    for classification in classifications:
        playbook = _pick_playbook(playbooks, classification.problem_type, classification.suggested_playbook)
        if playbook is None:
            lines.append(f"- skip {classification.problem_type}: no_playbook")
            continue
        policy = decide_repair_policy(classification.problem_type, owner_autofix_enabled=True)
        if not policy.allow_auto_repair:
            lines.append(f"- skip {classification.problem_type}: policy_blocked")
            continue
        decision = choose_auto_repair_incident(
            bridge,
            classification=classification,
            playbook_id=playbook.playbook_id,
            cooldown_seconds=bridge.config.auto_self_heal_cooldown_seconds,
            max_retries=bridge.config.auto_self_heal_max_retries,
        )
        if not decision.allowed:
            lines.append(f"- skip {classification.problem_type}: {decision.reason}")
            continue
        incident_id = decision.incident_id or bridge.state.record_self_heal_incident(
            problem_type=classification.problem_type,
            signal_code=classification.signal_code,
            state=SELF_HEAL_STATE_DETECTED,
            severity=classification.risk_level,
            summary=classification.summary,
            evidence=classification.evidence,
            risk_level=classification.risk_level,
            autonomy_level=policy.autonomy_level,
            source=source,
            confidence=classification.confidence,
            suggested_playbook=playbook.playbook_id,
        )
        if not decision.incident_id:
            bridge.state.update_self_heal_incident_state(
                incident_id,
                new_state=SELF_HEAL_STATE_CLASSIFIED,
                note=f"auto classified as {classification.problem_type}",
            )
        bridge.state.update_self_heal_incident_state(
            incident_id,
            new_state=SELF_HEAL_STATE_REPAIR_PLANNED,
            note=f"auto selected playbook {playbook.playbook_id}",
        )
        before_state = capture_health_state(bridge)
        plan = SelfHealingPlan(
            incident_id=incident_id,
            problem_type=classification.problem_type,
            playbook_id=playbook.playbook_id,
            autonomy_level=policy.autonomy_level,
            risk_level=policy.risk_level,
            actions=playbook.actions,
            verification_steps=playbook.verification_steps,
            rollback_steps=playbook.rollback_steps,
            require_owner_approval=False,
            dry_run=False,
        )
        bridge.state.update_self_heal_incident_state(
            incident_id,
            new_state=SELF_HEAL_STATE_EXECUTING,
            note=f"auto repair attempt {decision.attempt_number}/{bridge.config.auto_self_heal_max_retries}",
        )
        if playbook.playbook_id == "restart_runtime":
            _mark_restart_runtime_blocked(
                bridge,
                incident_id=incident_id,
                classification=classification,
                attempt_number=decision.attempt_number,
                reason="self-restart disabled",
            )
            lines.append(f"- incident={incident_id} problem={classification.problem_type} playbook={playbook.playbook_id} status=BLOCKED attempt={decision.attempt_number}/{bridge.config.auto_self_heal_max_retries}")
            handled += 1
            continue
        execution = execute_repair_plan(bridge, plan=plan)
        attempt_id = bridge.state.record_self_heal_attempt(
            incident_id=incident_id,
            playbook_id=playbook.playbook_id,
            state=SELF_HEAL_STATE_EXECUTING,
            status=execution.status,
            execution_summary=f"auto repair {classification.problem_type}: {execution.notes}",
            executed_steps=execution.executed_steps,
            failed_step=execution.failed_step,
            artifacts_changed=execution.artifacts_changed,
            verification_required=execution.verification_required,
            notes=execution.notes,
            stdout_log=execution.stdout_log,
            stderr_log=execution.stderr_log,
        )
        bridge.state.update_self_heal_incident_state(
            incident_id,
            new_state=SELF_HEAL_STATE_VERIFYING,
            note="auto verification started",
        )
        verification = verify_repair(
            bridge,
            playbook=playbook,
            before_state=before_state,
            execution_status=execution.status,
        )
        bridge.state.record_self_heal_verification(
            incident_id=incident_id,
            attempt_id=attempt_id,
            verified=verification.verified,
            before_state=dict(verification.before_state),
            after_state=dict(verification.after_state),
            confidence=verification.confidence,
            remaining_issues=verification.remaining_issues,
            regressions_detected=verification.regressions_detected,
            notes=verification.notes,
        )
        final_state = SELF_HEAL_STATE_REPAIRED if verification.verified else SELF_HEAL_STATE_FAILED
        bridge.state.update_self_heal_incident_state(
            incident_id,
            new_state=final_state,
            note="auto repair verification completed",
            verification_status="verified" if verification.verified else "failed",
        )
        if verification.verified:
            bridge.state.record_self_heal_lesson(
                incident_id=incident_id,
                lesson_key=f"{classification.problem_type}:{playbook.playbook_id}:auto",
                lesson_text="auto repair claims allowed only after verification passed",
                confidence=0.8,
            )
        elif (
            classification.problem_type in {"runtime_degraded", "failing_health_checks"}
            and playbook.playbook_id != "restart_runtime"
            and decision.attempt_number < bridge.config.auto_self_heal_max_retries
        ):
            _schedule_restart_escalation(
                bridge,
                incident_id=incident_id,
                classification=classification,
                before_state=dict(verification.after_state),
                attempt_number=decision.attempt_number + 1,
            )
        _notify_owner_auto_repair(
            bridge,
            incident_id=incident_id,
            classification=classification,
            playbook_id=playbook.playbook_id,
            before_state=before_state,
            verification=verification,
            attempt_number=decision.attempt_number,
        )
        lines.append(
            f"- incident={incident_id} problem={classification.problem_type} playbook={playbook.playbook_id} "
            f"status={'SUCCESS' if verification.verified else 'FAILED'} attempt={decision.attempt_number}/{bridge.config.auto_self_heal_max_retries}"
        )
        handled += 1
    if handled == 0:
        lines.append("Ничего не выполнено: cooldown/policy/dedup.")
    return "\n".join(lines)


def finalize_pending_auto_restart(bridge: "TelegramBridge") -> str:
    raw = bridge.state.get_meta("auto_self_heal_pending_restart", "")
    if not raw:
        return "AUTO SELF-HEAL RESTART\n\nНет pending restart verification."
    try:
        payload = json.loads(raw)
    except ValueError:
        bridge.state.set_meta("auto_self_heal_pending_restart", "")
        return "AUTO SELF-HEAL RESTART\n\nPending restart payload повреждён."
    incident_id = int(payload.get("incident_id", 0) or 0)
    attempt_id = int(payload.get("attempt_id", 0) or 0)
    playbook_id = str(payload.get("playbook_id") or "restart_runtime")
    problem_type = str(payload.get("problem_type") or "runtime_degraded")
    signal_code = str(payload.get("signal_code") or "restart_runtime")
    attempt_number = int(payload.get("attempt_number", 1) or 1)
    before_state = dict(payload.get("before_state") or {})
    playbook = _pick_playbook_by_id(playbook_id)
    if playbook is None:
        bridge.state.set_meta("auto_self_heal_pending_restart", "")
        return f"AUTO SELF-HEAL RESTART\n\nНе найден playbook={playbook_id}"
    verification = verify_repair(
        bridge,
        playbook=playbook,
        before_state=before_state,
        execution_status="success",
    )
    bridge.state.record_self_heal_verification(
        incident_id=incident_id,
        attempt_id=attempt_id or None,
        verified=verification.verified,
        before_state=before_state,
        after_state=dict(verification.after_state),
        confidence=verification.confidence,
        remaining_issues=verification.remaining_issues,
        regressions_detected=verification.regressions_detected,
        notes="post-restart startup verification",
    )
    if attempt_id:
        bridge.state.update_self_heal_attempt(
            attempt_id,
            state=SELF_HEAL_STATE_VERIFYING,
            status="verified" if verification.verified else "failed",
            execution_summary=f"post-restart verification for incident {incident_id}",
            notes="startup finalized pending auto restart",
        )
    bridge.state.update_self_heal_incident_state(
        incident_id,
        new_state=SELF_HEAL_STATE_REPAIRED if verification.verified else SELF_HEAL_STATE_FAILED,
        note="startup finalized auto restart",
        verification_status="verified" if verification.verified else "failed",
    )
    if verification.verified:
        bridge.state.record_self_heal_lesson(
            incident_id=incident_id,
            lesson_key=f"{problem_type}:{playbook_id}:restart",
            lesson_text="restart path may be claimed only after startup marker and heartbeat verification",
            confidence=0.84,
        )
    classification = _SyntheticClassification(problem_type=problem_type, signal_code=signal_code)
    _notify_owner_auto_repair(
        bridge,
        incident_id=incident_id,
        classification=classification,
        playbook_id=playbook_id,
        before_state=before_state,
        verification=verification,
        attempt_number=attempt_number,
    )
    bridge.state.set_meta("auto_self_heal_pending_restart", "")
    return (
        "AUTO SELF-HEAL RESTART\n\n"
        f"incident={incident_id}\nplaybook={playbook_id}\n"
        f"verified={'yes' if verification.verified else 'no'}"
    )


def _notify_owner_auto_repair(
    bridge: "TelegramBridge",
    *,
    incident_id: int,
    classification: "FailureClassification",
    playbook_id: str,
    before_state: dict,
    verification: "PostRepairVerificationResult",
    attempt_number: int,
) -> None:
    result_status = "SUCCESS" if verification.verified else "FAILED"
    if not should_send_auto_repair_report(
        bridge,
        incident_id=incident_id,
        problem_type=classification.problem_type,
        playbook_id=playbook_id,
        result_status=result_status,
        cooldown_seconds=bridge.config.auto_self_heal_report_cooldown_seconds,
    ):
        return
    report = (
        "[SELF-HEAL]\n\n"
        f"Тип проблемы: {classification.signal_code}\n"
        f"Класс: {classification.problem_type}\n"
        f"Playbook: {playbook_id}\n"
        f"Действие: {', '.join(_short_steps_from_verification_source(playbook_id))}\n"
        f"Результат: {result_status}\n\n"
        "Проверка:\n"
        f"- было: {_render_health_state(before_state)}\n"
        f"- стало: {_render_health_state(dict(verification.after_state))}\n\n"
        f"Попытка: {attempt_number}/{bridge.config.auto_self_heal_max_retries}\n\n"
        + (
            "Проблема устранена автоматически"
            if verification.verified
            else "Авто-ремонт не помог, требуется вмешательство"
        )
    )
    bridge.notify_owner(report)


def _render_health_state(state: dict) -> str:
    return (
        f"heartbeat_age={state.get('heartbeat_age_seconds', -1)}s; "
        f"processes={state.get('process_count', 0)}; "
        f"severe_errors={state.get('severe_error_count', 0)}; "
        f"degraded_routes={state.get('degraded_routes', 0)}; "
        f"stale_world_state={state.get('stale_world_state', 0)}"
    )


def _pick_playbook(playbooks: list, problem_type: str, suggested_playbook: str):
    for playbook in playbooks:
        if playbook.playbook_id == suggested_playbook or playbook.target_problem_type == problem_type:
            return playbook
    return None


def _pick_playbook_by_id(playbook_id: str):
    from services.repair_playbooks import REPAIR_PLAYBOOKS

    for playbook in REPAIR_PLAYBOOKS:
        if playbook.playbook_id == playbook_id:
            return playbook
    return None


def _short_steps_from_verification_source(playbook_id: str) -> tuple:
    mapping = {
        "refresh_runtime_state": ("refresh_runtime_state", "reinitialize_heartbeat"),
        "recheck_health": ("run_smoke_check", "run_behavioral_check", "refresh_runtime_state"),
        "recover_failed_live_provider_config": ("refresh_runtime_state", "run_smoke_check"),
        "recover_sqlite_lock": ("inspect_sqlite_state", "run_smoke_check", "run_behavioral_check"),
        "reinitialize_missing_runtime_artifact": ("reinitialize_heartbeat", "refresh_runtime_state"),
        "restart_runtime": ("request_restart", "startup_marker", "heartbeat_fresh"),
    }
    return mapping.get(playbook_id, (playbook_id,))


def _prepare_pending_auto_restart(
    bridge: "TelegramBridge",
    *,
    incident_id: int,
    attempt_id: int,
    classification: "FailureClassification",
    playbook_id: str,
    before_state: dict,
    attempt_number: int,
) -> None:
    bridge.state.set_meta(
        "auto_self_heal_pending_restart",
        json.dumps(
            {
                "incident_id": incident_id,
                "attempt_id": attempt_id,
                "problem_type": classification.problem_type,
                "signal_code": classification.signal_code,
                "playbook_id": playbook_id,
                "before_state": before_state,
                "attempt_number": attempt_number,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )


def _schedule_restart_escalation(
    bridge: "TelegramBridge",
    *,
    incident_id: int,
    classification: "FailureClassification",
    before_state: dict,
    attempt_number: int,
) -> None:
    del before_state
    _mark_restart_runtime_blocked(
        bridge,
        incident_id=incident_id,
        classification=classification,
        attempt_number=attempt_number,
        reason="restart escalation suppressed because self-restart is disabled",
    )


def _mark_restart_runtime_blocked(
    bridge: "TelegramBridge",
    *,
    incident_id: int,
    classification: "FailureClassification",
    attempt_number: int,
    reason: str,
) -> None:
    bridge.state.record_self_heal_attempt(
        incident_id=incident_id,
        playbook_id="restart_runtime",
        state=SELF_HEAL_STATE_EXECUTING,
        status="blocked_restart_disabled",
        execution_summary=f"restart suppressed for {classification.problem_type}",
        executed_steps=("request_restart_blocked",),
        verification_required=False,
        notes=reason,
    )
    bridge.state.update_self_heal_incident_state(
        incident_id,
        new_state=SELF_HEAL_STATE_FAILED,
        note=f"{reason}; attempt {attempt_number}/{bridge.config.auto_self_heal_max_retries}",
        verification_status="failed",
    )


class _SyntheticClassification:
    def __init__(self, *, problem_type: str, signal_code: str) -> None:
        self.problem_type = problem_type
        self.signal_code = signal_code


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.repair_contracts import FailureClassification, PostRepairVerificationResult
    from tg_codex_bridge import TelegramBridge
