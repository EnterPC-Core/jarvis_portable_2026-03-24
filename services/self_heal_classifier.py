from typing import Iterable, List, Mapping

from services.repair_contracts import FailureClassification, FailureSignal
from services.self_heal_policy import decide_repair_policy


SIGNAL_TO_PROBLEM_TYPE = {
    "restart_loop": "unhealthy_loop",
    "heartbeat_stale": "runtime_degraded",
    "sqlite_schema_mismatch": "sqlite_error",
    "live_provider_degraded": "live_provider_failed",
    "route_regression": "route_drift",
    "severe_runtime_errors": "runtime_degraded",
}


def classify_failures(
    *,
    signals: Iterable[FailureSignal],
    owner_autofix_enabled: bool,
) -> List[FailureClassification]:
    items: List[FailureClassification] = []
    for signal in signals:
        problem_type = signal.problem_type or SIGNAL_TO_PROBLEM_TYPE.get(signal.signal_code, "failing_health_checks")
        policy = decide_repair_policy(problem_type, owner_autofix_enabled=owner_autofix_enabled)
        items.append(
            FailureClassification(
                problem_type=problem_type,
                signal_code=signal.signal_code,
                summary=signal.summary,
                verification_hint=_verification_hint_for_problem(problem_type),
                risk_level=policy.risk_level,
                autonomy_level=policy.autonomy_level,
                auto_repairable=policy.allow_auto_repair,
                evidence=signal.evidence,
                confidence=signal.confidence,
                source=signal.source,
                suggested_playbook=signal.suggested_playbook,
                notes=policy.rationale,
            )
        )
    return items


def _verification_hint_for_problem(problem_type: str) -> str:
    hints = {
        "runtime_down": "confirm process state and startup markers before claiming success",
        "runtime_degraded": "refresh world-state and verify heartbeat/process health",
        "sqlite_error": "verify schema/lock state and run smoke+behavioral checks",
        "route_drift": "verify with routing smoke and recent route diagnostics",
        "live_provider_failed": "verify provider freshness and fallback status",
        "stale_world_state": "verify world-state timestamps and stale flags",
        "owner_command_failure": "verify owner command output path via smoke tests",
        "failing_health_checks": "re-run health checks and compare before/after",
    }
    return hints.get(problem_type, "verify before/after state independently")


def render_failure_classifications(classifications: Iterable[FailureClassification]) -> str:
    items = list(classifications)
    if not items:
        return "Failure classifier: подтверждённых классификаций нет."
    lines = ["Failure classifier"]
    for item in items:
        lines.append(
            f"- problem={item.problem_type} signal={item.signal_code} risk={item.risk_level} autonomy={item.autonomy_level}"
        )
        lines.append(f"  {item.summary}")
        lines.append(f"  verify={item.verification_hint}")
        if item.evidence:
            lines.append(f"  evidence={item.evidence}")
    return "\n".join(lines)
