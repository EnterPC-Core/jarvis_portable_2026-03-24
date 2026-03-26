import subprocess
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from services.repair_contracts import PostRepairVerificationResult, RepairPlaybook, VerificationStep


def capture_health_state(bridge: "TelegramBridge") -> Dict[str, object]:
    heartbeat_exists = bridge.heartbeat_path.exists()
    heartbeat_age = -1.0
    if heartbeat_exists:
        try:
            heartbeat_age = max(0.0, time.time() - bridge.heartbeat_path.stat().st_mtime)
        except OSError:
            heartbeat_age = -1.0
    process_count = _count_bridge_processes(bridge.script_path.name)
    runtime_snapshot = bridge.inspect_runtime_log()
    diagnostics_rows = bridge.state.get_recent_request_diagnostics(limit=8)
    degraded_routes = sum(1 for row in diagnostics_rows if str(row["outcome"] or "").strip().lower() not in {"", "ok"})
    world_state_rows = bridge.state.get_world_state_rows(limit=8)
    stale_world_state = sum(int(row["stale_flag"] or 0) for row in world_state_rows)
    return {
        "heartbeat_exists": heartbeat_exists,
        "heartbeat_age_seconds": round(heartbeat_age, 1) if heartbeat_age >= 0 else -1.0,
        "process_count": process_count,
        "severe_error_count": int(runtime_snapshot.get("severe_error_count", 0) or 0),
        "warning_count": int(runtime_snapshot.get("warning_count", 0) or 0),
        "degraded_routes": degraded_routes,
        "stale_world_state": stale_world_state,
    }


def verify_repair(
    bridge: "TelegramBridge",
    *,
    playbook: RepairPlaybook,
    before_state: Dict[str, object],
    execution_status: str,
) -> PostRepairVerificationResult:
    after_state = capture_health_state(bridge)
    remaining_issues: List[str] = []
    regressions: List[str] = []
    if execution_status not in {"success", "partial"}:
        remaining_issues.append(f"execution_status={execution_status}")
    for step in playbook.verification_steps:
        issue = _verify_step(step, after_state, bridge)
        if issue:
            remaining_issues.append(issue)
    if int(after_state.get("severe_error_count", 0)) > int(before_state.get("severe_error_count", 0)):
        regressions.append("severe_error_count_increased")
    if int(after_state.get("degraded_routes", 0)) > int(before_state.get("degraded_routes", 0)):
        regressions.append("degraded_routes_increased")
    verified = not remaining_issues and not regressions
    confidence = 0.92 if verified else 0.42
    if remaining_issues:
        confidence -= min(0.24, 0.06 * len(remaining_issues))
    if regressions:
        confidence -= min(0.28, 0.08 * len(regressions))
    return PostRepairVerificationResult(
        verified=verified,
        before_state=before_state,
        after_state=after_state,
        confidence=max(0.0, min(1.0, confidence)),
        remaining_issues=tuple(remaining_issues),
        regressions_detected=tuple(regressions),
        notes="post-repair verifier uses independent health/probe checks, not command exit code only",
    )


def _verify_step(step: VerificationStep, after_state: Dict[str, object], bridge: "TelegramBridge") -> str:
    kind = step.verifier_kind
    if kind == "heartbeat_fresh":
        if not after_state.get("heartbeat_exists"):
            return "heartbeat_missing"
        if float(after_state.get("heartbeat_age_seconds", -1)) > float(bridge.config.heartbeat_timeout_seconds):
            return "heartbeat_stale"
        return ""
    if kind == "process_alive":
        if int(after_state.get("process_count", 0)) != 1:
            return f"unexpected_process_count={after_state.get('process_count', 0)}"
        return ""
    if kind == "startup_marker":
        recent_errors = bridge.read_recent_log_highlights(limit=1)
        if recent_errors and "bot started" not in bridge.log_path.read_text(encoding="utf-8", errors="ignore")[-1000:]:
            return "startup_marker_missing"
        return ""
    if kind == "world_state_fresh":
        if int(after_state.get("stale_world_state", 0)) > 0:
            return f"stale_world_state={after_state.get('stale_world_state', 0)}"
        return ""
    if kind == "smoke_check":
        return _run_check(bridge.script_path.parent, ("python3", "tools/smoke_check.py"), "smoke_check")
    if kind == "behavioral_check":
        return _run_check(bridge.script_path.parent, ("python3", "tools/behavioral_check.py"), "behavioral_check")
    if kind == "route_health":
        if int(after_state.get("degraded_routes", 0)) >= 3:
            return f"degraded_routes={after_state.get('degraded_routes', 0)}"
        return ""
    if kind == "sqlite_probe":
        if int(after_state.get("severe_error_count", 0)) > 0:
            return "sqlite_probe_not_clean"
        return ""
    return ""


def _run_check(workdir: Path, command: Tuple[str, ...], label: str) -> str:
    try:
        result = subprocess.run(command, cwd=workdir, capture_output=True, text=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"{label}_unavailable:{error}"
    if result.returncode != 0:
        details = (result.stdout or result.stderr or "").strip().splitlines()
        tail = details[-1] if details else f"exit={result.returncode}"
        return f"{label}_failed:{tail}"
    return ""


def _count_bridge_processes(script_name: str) -> int:
    try:
        result = subprocess.run(
            ["ps", "-ef"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    count = 0
    marker = f"python3 {script_name}"
    for line in (result.stdout or "").splitlines():
        if marker in line and "grep" not in line:
            count += 1
    return count


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
