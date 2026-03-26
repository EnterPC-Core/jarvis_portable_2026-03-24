from dataclasses import dataclass
from typing import Dict, Tuple

from services.repair_contracts import (
    AUTONOMY_AUTO_WITH_VERIFICATION,
    AUTONOMY_FORBIDDEN,
    AUTONOMY_REQUIRE_OWNER_APPROVAL,
    AUTONOMY_SAFE_AUTO,
    RepairPolicyDecision,
)


@dataclass(frozen=True)
class ProblemPolicy:
    problem_type: str
    risk_level: str
    autonomy_level: str
    auto_repairable: bool
    rationale: str
    allowed_playbooks: Tuple[str, ...] = ()


SELF_HEAL_POLICY_MATRIX: Dict[str, ProblemPolicy] = {
    "runtime_down": ProblemPolicy("runtime_down", "high", AUTONOMY_REQUIRE_OWNER_APPROVAL, False, "runtime restart inside the same process needs explicit control", ("restart_runtime",)),
    "runtime_degraded": ProblemPolicy("runtime_degraded", "medium", AUTONOMY_SAFE_AUTO, True, "refreshing runtime state and health probes is safe", ("refresh_runtime_state", "recheck_health")),
    "broken_dependency": ProblemPolicy("broken_dependency", "high", AUTONOMY_REQUIRE_OWNER_APPROVAL, False, "install/upgrade dependency changes local environment", ("repair_import_path",)),
    "import_error": ProblemPolicy("import_error", "high", AUTONOMY_REQUIRE_OWNER_APPROVAL, False, "import fixes may require code/config changes", ("repair_import_path", "recheck_health")),
    "config_error": ProblemPolicy("config_error", "high", AUTONOMY_REQUIRE_OWNER_APPROVAL, False, "config drift can break auth/runtime semantics", ("recheck_health",)),
    "sqlite_error": ProblemPolicy("sqlite_error", "high", AUTONOMY_REQUIRE_OWNER_APPROVAL, False, "sqlite repair must preserve data and backups", ("recover_sqlite_lock", "repair_sqlite_schema")),
    "state_drift": ProblemPolicy("state_drift", "medium", AUTONOMY_AUTO_WITH_VERIFICATION, True, "state refresh and consistency verification are bounded", ("refresh_runtime_state", "resync_project_state")),
    "route_drift": ProblemPolicy("route_drift", "medium", AUTONOMY_AUTO_WITH_VERIFICATION, True, "route regressions can be checked with smoke/behavioral verification", ("audit_route_regression", "recheck_health")),
    "prompt_contract_break": ProblemPolicy("prompt_contract_break", "medium", AUTONOMY_REQUIRE_OWNER_APPROVAL, False, "prompt/contract changes affect semantics broadly", ("audit_route_regression",)),
    "live_provider_failed": ProblemPolicy("live_provider_failed", "medium", AUTONOMY_SAFE_AUTO, True, "provider health recheck and fallback switch are bounded", ("recover_failed_live_provider_config", "recheck_health")),
    "stale_world_state": ProblemPolicy("stale_world_state", "low", AUTONOMY_SAFE_AUTO, True, "refreshing world-state snapshots is safe", ("refresh_runtime_state",)),
    "attachment_pipeline_error": ProblemPolicy("attachment_pipeline_error", "medium", AUTONOMY_AUTO_WITH_VERIFICATION, True, "attachment path can be rechecked with local tests", ("recheck_health",)),
    "owner_command_failure": ProblemPolicy("owner_command_failure", "medium", AUTONOMY_AUTO_WITH_VERIFICATION, True, "owner surface can be validated with smoke checks", ("recheck_health",)),
    "environment_misconfiguration": ProblemPolicy("environment_misconfiguration", "high", AUTONOMY_REQUIRE_OWNER_APPROVAL, False, "environment changes touch local runtime semantics", ("fix_permissions", "recover_failed_live_provider_config")),
    "process_not_running": ProblemPolicy("process_not_running", "high", AUTONOMY_REQUIRE_OWNER_APPROVAL, False, "bringing a dead runtime up must be confirmed by owner", ("restart_runtime",)),
    "unhealthy_loop": ProblemPolicy("unhealthy_loop", "high", AUTONOMY_REQUIRE_OWNER_APPROVAL, False, "restart loops need operator visibility before intervention", ("restart_runtime", "recheck_health")),
    "failing_health_checks": ProblemPolicy("failing_health_checks", "medium", AUTONOMY_AUTO_WITH_VERIFICATION, True, "health rechecks and bounded verification are safe", ("recheck_health", "refresh_runtime_state")),
}


def decide_repair_policy(problem_type: str, *, owner_autofix_enabled: bool) -> RepairPolicyDecision:
    policy = SELF_HEAL_POLICY_MATRIX.get(
        problem_type,
        ProblemPolicy(problem_type, "high", AUTONOMY_FORBIDDEN, False, "unknown problem type is not safe to auto-repair"),
    )
    allow_auto_repair = owner_autofix_enabled and policy.auto_repairable and policy.autonomy_level in {
        AUTONOMY_SAFE_AUTO,
        AUTONOMY_AUTO_WITH_VERIFICATION,
    }
    return RepairPolicyDecision(
        problem_type=policy.problem_type,
        autonomy_level=policy.autonomy_level,
        risk_level=policy.risk_level,
        allow_auto_repair=allow_auto_repair,
        require_owner_approval=policy.autonomy_level == AUTONOMY_REQUIRE_OWNER_APPROVAL,
        dry_run_only=policy.autonomy_level in {AUTONOMY_REQUIRE_OWNER_APPROVAL, AUTONOMY_FORBIDDEN},
        forbidden=policy.autonomy_level == AUTONOMY_FORBIDDEN,
        rationale=policy.rationale,
    )
