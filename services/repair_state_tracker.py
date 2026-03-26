import time
from dataclasses import dataclass
from typing import Optional

from services.repair_contracts import (
    SELF_HEAL_STATE_AWAITING_APPROVAL,
    SELF_HEAL_STATE_DEGRADED_MANUAL_FOLLOWUP,
    SELF_HEAL_STATE_FAILED,
    SELF_HEAL_STATE_REPAIRED,
)


SAFE_AUTO_PLAYBOOK_IDS = {
    "refresh_runtime_state",
    "recheck_health",
    "recover_failed_live_provider_config",
    "restart_runtime",
    "recover_sqlite_lock",
    "reinitialize_missing_runtime_artifact",
}


@dataclass(frozen=True)
class AutoRepairDecision:
    allowed: bool
    reason: str
    incident_id: int = 0
    attempt_number: int = 0


def choose_auto_repair_incident(
    bridge: "TelegramBridge",
    *,
    classification: "FailureClassification",
    playbook_id: str,
    cooldown_seconds: int,
    max_retries: int,
) -> AutoRepairDecision:
    if playbook_id not in SAFE_AUTO_PLAYBOOK_IDS:
        return AutoRepairDecision(False, f"playbook_not_safe_auto:{playbook_id}")
    incident = bridge.state.find_recent_self_heal_incident(
        classification.problem_type,
        classification.signal_code,
        window_seconds=max(cooldown_seconds * 6, 3600),
    )
    if incident is None:
        return AutoRepairDecision(True, "new_incident", 0, 1)
    incident_id = int(incident["id"])
    state = str(incident["state"] or "")
    attempts = bridge.state.count_self_heal_attempts(incident_id)
    age_seconds = max(0, int(time.time()) - int(incident["updated_at"] or 0))
    if state == SELF_HEAL_STATE_REPAIRED:
        return AutoRepairDecision(False, "already_repaired", incident_id, attempts)
    if state == SELF_HEAL_STATE_DEGRADED_MANUAL_FOLLOWUP:
        return AutoRepairDecision(False, "manual_followup_required", incident_id, attempts)
    if state == SELF_HEAL_STATE_AWAITING_APPROVAL:
        return AutoRepairDecision(False, "awaiting_owner_approval", incident_id, attempts)
    if attempts >= max_retries:
        return AutoRepairDecision(False, "max_retries_reached", incident_id, attempts)
    if age_seconds < cooldown_seconds:
        return AutoRepairDecision(False, f"cooldown_active:{cooldown_seconds - age_seconds}s", incident_id, attempts)
    return AutoRepairDecision(True, "retry_allowed", incident_id, attempts + 1)


def should_send_auto_repair_report(
    bridge: "TelegramBridge",
    *,
    incident_id: int,
    problem_type: str,
    playbook_id: str,
    result_status: str,
    cooldown_seconds: int,
) -> bool:
    signature = f"{problem_type}:{playbook_id}:{result_status}:{incident_id}"
    last_text = bridge.state.get_meta("auto_self_heal_report_signature", "")
    last_at_raw = bridge.state.get_meta("auto_self_heal_report_ts", "0")
    try:
        last_at = int(last_at_raw or "0")
    except ValueError:
        last_at = 0
    now = int(time.time())
    if last_text == signature and now - last_at < max(60, cooldown_seconds):
        return False
    bridge.state.set_meta("auto_self_heal_report_signature", signature)
    bridge.state.set_meta("auto_self_heal_report_ts", str(now))
    return True


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.repair_contracts import FailureClassification
    from tg_codex_bridge import TelegramBridge
