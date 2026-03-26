from typing import Iterable, List

from services.failure_detectors import detect_failure_signals
from services.repair_contracts import (
    SELF_HEAL_STATE_AWAITING_APPROVAL,
    SELF_HEAL_STATE_CLASSIFIED,
    SELF_HEAL_STATE_DEGRADED_MANUAL_FOLLOWUP,
    SELF_HEAL_STATE_DETECTED,
    SELF_HEAL_STATE_EXECUTING,
    SELF_HEAL_STATE_FAILED,
    SELF_HEAL_STATE_REPAIRED,
    SELF_HEAL_STATE_REPAIR_PLANNED,
    SELF_HEAL_STATE_VERIFYING,
    FailureClassification,
    RepairLesson,
    SelfHealingPlan,
)
from services.repair_playbooks import render_playbook_summary, select_playbooks_for_classifications
from services.self_heal_classifier import classify_failures, render_failure_classifications
from services.self_heal_executor import execute_repair_plan
from services.self_heal_policy import decide_repair_policy
from services.self_heal_verifier import capture_health_state, verify_repair


def run_self_heal_cycle(
    bridge: "TelegramBridge",
    *,
    source: str,
    auto_execute: bool,
) -> str:
    runtime_snapshot = bridge.inspect_runtime_log()
    recent_errors = bridge.read_recent_log_highlights(limit=10)
    recent_routes = bridge.state.get_recent_request_diagnostics(limit=8)
    signals = detect_failure_signals(
        runtime_snapshot=runtime_snapshot,
        recent_errors=recent_errors,
        recent_routes=recent_routes,
        heartbeat_timeout_seconds=bridge.config.heartbeat_timeout_seconds,
    )
    classifications = classify_failures(signals=signals, owner_autofix_enabled=auto_execute)
    if not classifications:
        return "Self-heal: активных инцидентов не обнаружено."
    playbooks = select_playbooks_for_classifications(classifications)
    lines: List[str] = [render_failure_classifications(classifications), "", render_playbook_summary(playbooks)]
    for classification in classifications:
        if bridge.state.has_recent_self_heal_incident(classification.problem_type, classification.signal_code, window_seconds=900):
            continue
        incident_id = bridge.state.record_self_heal_incident(
            problem_type=classification.problem_type,
            signal_code=classification.signal_code,
            state=SELF_HEAL_STATE_DETECTED,
            severity=classification.risk_level,
            summary=classification.summary,
            evidence=classification.evidence,
            risk_level=classification.risk_level,
            autonomy_level=classification.autonomy_level,
            source=classification.source,
            confidence=classification.confidence,
            suggested_playbook=classification.suggested_playbook,
        )
        bridge.state.update_self_heal_incident_state(
            incident_id,
            new_state=SELF_HEAL_STATE_CLASSIFIED,
            note=f"classified as {classification.problem_type}",
        )
        playbook = _pick_playbook_for_classification(playbooks, classification)
        if playbook is None:
            bridge.state.update_self_heal_incident_state(
                incident_id,
                new_state=SELF_HEAL_STATE_DEGRADED_MANUAL_FOLLOWUP,
                note="no matching playbook",
            )
            continue
        policy = decide_repair_policy(classification.problem_type, owner_autofix_enabled=auto_execute)
        require_owner_approval = policy.require_owner_approval or policy.forbidden or not auto_execute
        plan = SelfHealingPlan(
            incident_id=incident_id,
            problem_type=classification.problem_type,
            playbook_id=playbook.playbook_id,
            autonomy_level=policy.autonomy_level,
            risk_level=policy.risk_level,
            actions=playbook.actions,
            verification_steps=playbook.verification_steps,
            rollback_steps=playbook.rollback_steps,
            require_owner_approval=require_owner_approval,
            dry_run=policy.dry_run_only or not policy.allow_auto_repair,
        )
        bridge.state.update_self_heal_incident_state(
            incident_id,
            new_state=SELF_HEAL_STATE_REPAIR_PLANNED if not plan.require_owner_approval else SELF_HEAL_STATE_AWAITING_APPROVAL,
            note=f"selected playbook {playbook.playbook_id}",
        )
        if plan.require_owner_approval:
            continue
        before_state = capture_health_state(bridge)
        bridge.state.update_self_heal_incident_state(incident_id, new_state=SELF_HEAL_STATE_EXECUTING, note="auto repair executing")
        execution = execute_repair_plan(bridge, plan=plan)
        attempt_id = bridge.state.record_self_heal_attempt(
            incident_id=incident_id,
            playbook_id=playbook.playbook_id,
            state=SELF_HEAL_STATE_EXECUTING,
            status=execution.status,
            execution_summary=f"{classification.problem_type}: {execution.notes}",
            executed_steps=execution.executed_steps,
            failed_step=execution.failed_step,
            artifacts_changed=execution.artifacts_changed,
            verification_required=execution.verification_required,
            notes=execution.notes,
            stdout_log=execution.stdout_log,
            stderr_log=execution.stderr_log,
        )
        bridge.state.update_self_heal_incident_state(incident_id, new_state=SELF_HEAL_STATE_VERIFYING, note="post-repair verification started")
        verification = verify_repair(bridge, playbook=playbook, before_state=before_state, execution_status=execution.status)
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
        if verification.verified:
            lesson = _build_repair_lesson(classification, playbook.playbook_id, verification.remaining_issues)
            bridge.state.record_self_heal_lesson(
                incident_id=incident_id,
                lesson_key=f"{classification.problem_type}:{playbook.playbook_id}",
                lesson_text=lesson.lesson_text,
                confidence=lesson.confidence,
            )
            bridge.state.update_self_heal_incident_state(
                incident_id,
                new_state=SELF_HEAL_STATE_REPAIRED,
                note="verification passed",
                verification_status="verified",
                lesson_text=lesson.lesson_text,
            )
        else:
            bridge.state.update_self_heal_incident_state(
                incident_id,
                new_state=SELF_HEAL_STATE_FAILED,
                note="verification failed",
                verification_status="failed",
            )
    recent_incidents = bridge.state.get_recent_self_heal_incidents(limit=6)
    bridge.state.upsert_world_state_entry(
        "self_heal_status",
        category="diagnostics",
        status="attention" if classifications else "ok",
        value_text=(
            f"signals={len(signals)}; classifications={len(classifications)}; "
            f"auto_execute={'yes' if auto_execute else 'no'}; recent_incidents={len(recent_incidents)}"
        ),
        value_number=float(len(classifications)),
        source=source,
        confidence=0.86,
        ttl_seconds=300,
        verification_method="self_heal_cycle",
        stale_flag=False,
    )
    if recent_incidents:
        lines.extend(["", "Recent self-heal incidents"])
        for row in recent_incidents:
            lines.append(
                f"- incident={int(row['id'])} problem={row['problem_type']} state={row['state']} playbook={row['suggested_playbook'] or '-'}"
            )
    return "\n".join(lines)


def _pick_playbook_for_classification(playbooks: Iterable["RepairPlaybook"], classification: FailureClassification):
    for playbook in playbooks:
        if playbook.playbook_id == classification.suggested_playbook or playbook.target_problem_type == classification.problem_type:
            return playbook
    return None


def _build_repair_lesson(classification: FailureClassification, playbook_id: str, remaining_issues: Iterable[str]) -> RepairLesson:
    suffix = "; ".join(remaining_issues) if remaining_issues else "verification clean"
    return RepairLesson(
        incident_id=0,
        lesson_key=f"{classification.problem_type}:{playbook_id}",
        lesson_text=(
            f"{classification.problem_type} -> {playbook_id}: "
            f"claims acceptable only after independent verification; outcome={suffix}"
        ),
        confidence=0.82,
    )


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.repair_playbooks import RepairPlaybook
    from tg_codex_bridge import TelegramBridge
