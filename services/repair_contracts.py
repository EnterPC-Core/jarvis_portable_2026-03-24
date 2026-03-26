from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class FailureSignal:
    signal_code: str
    severity: str
    summary: str
    evidence: str
    confidence: float
    source: str
    suggested_playbook: str = ""


@dataclass(frozen=True)
class VerificationStep:
    step_id: str
    description: str
    required: bool = True


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

