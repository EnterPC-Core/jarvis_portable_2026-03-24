from dataclasses import dataclass
from typing import Any, Tuple


AUTONOMY_SAFE_AUTO = "SAFE_AUTO"
AUTONOMY_AUTO_WITH_VERIFICATION = "AUTO_WITH_VERIFICATION"
AUTONOMY_REQUIRE_OWNER_APPROVAL = "REQUIRE_OWNER_APPROVAL"
AUTONOMY_FORBIDDEN = "FORBIDDEN"

SELF_HEAL_STATE_DETECTED = "detected"
SELF_HEAL_STATE_CLASSIFIED = "classified"
SELF_HEAL_STATE_REPAIR_PLANNED = "repair_planned"
SELF_HEAL_STATE_AWAITING_APPROVAL = "awaiting_approval"
SELF_HEAL_STATE_EXECUTING = "executing"
SELF_HEAL_STATE_VERIFYING = "verifying"
SELF_HEAL_STATE_REPAIRED = "repaired"
SELF_HEAL_STATE_FAILED = "failed"
SELF_HEAL_STATE_ROLLED_BACK = "rolled_back"
SELF_HEAL_STATE_DEGRADED_MANUAL_FOLLOWUP = "degraded_manual_followup"


@dataclass(frozen=True)
class FailureSignal:
    signal_code: str
    severity: str
    summary: str
    evidence: str
    confidence: float
    source: str
    suggested_playbook: str = ""
    problem_type: str = ""
    detection_method: str = ""
    auto_repairable: bool = False


@dataclass(frozen=True)
class VerificationStep:
    step_id: str
    description: str
    required: bool = True
    verifier_kind: str = "generic"


@dataclass(frozen=True)
class RepairAction:
    action_id: str
    description: str
    action_kind: str = "internal"
    command: Tuple[str, ...] = ()
    timeout_seconds: int = 30
    allow_failure: bool = False
    notes: str = ""


@dataclass(frozen=True)
class RepairPlaybook:
    playbook_id: str
    title: str
    allowed_actions: Tuple[str, ...]
    required_prechecks: Tuple[str, ...]
    verification_steps: Tuple[VerificationStep, ...]
    rollback_steps: Tuple[str, ...]
    claim_policy: str
    handles_signals: Tuple[str, ...]
    target_problem_type: str = ""
    preconditions: Tuple[str, ...] = ()
    actions: Tuple[RepairAction, ...] = ()
    expected_effect: str = ""
    timeout_seconds: int = 60
    retry_policy: str = "no_retry"
    risk_level: str = "low"
    autonomy_level: str = AUTONOMY_REQUIRE_OWNER_APPROVAL


@dataclass(frozen=True)
class FailureClassification:
    problem_type: str
    signal_code: str
    summary: str
    verification_hint: str
    risk_level: str
    autonomy_level: str
    auto_repairable: bool
    evidence: str
    confidence: float
    source: str
    suggested_playbook: str = ""
    notes: str = ""


@dataclass(frozen=True)
class RepairPolicyDecision:
    problem_type: str
    autonomy_level: str
    risk_level: str
    allow_auto_repair: bool
    require_owner_approval: bool
    dry_run_only: bool
    forbidden: bool
    rationale: str


@dataclass(frozen=True)
class SelfHealingPlan:
    incident_id: int
    problem_type: str
    playbook_id: str
    autonomy_level: str
    risk_level: str
    actions: Tuple[RepairAction, ...]
    verification_steps: Tuple[VerificationStep, ...]
    rollback_steps: Tuple[str, ...]
    require_owner_approval: bool
    dry_run: bool = False


@dataclass(frozen=True)
class RepairExecutionResult:
    status: str
    executed_steps: Tuple[str, ...]
    failed_step: str = ""
    artifacts_changed: Tuple[str, ...] = ()
    verification_required: bool = True
    notes: str = ""
    stdout_log: Tuple[str, ...] = ()
    stderr_log: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PostRepairVerificationResult:
    verified: bool
    before_state: Any
    after_state: Any
    confidence: float
    remaining_issues: Tuple[str, ...] = ()
    regressions_detected: Tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class IncidentRecord:
    problem_type: str
    signal_code: str
    state: str
    severity: str
    summary: str
    evidence: str
    risk_level: str
    autonomy_level: str
    source: str
    confidence: float
    suggested_playbook: str = ""


@dataclass(frozen=True)
class RepairAttempt:
    incident_id: int
    playbook_id: str
    state: str
    status: str
    summary: str
    execution_notes: str = ""


@dataclass(frozen=True)
class RepairLesson:
    incident_id: int
    lesson_key: str
    lesson_text: str
    confidence: float = 0.5
