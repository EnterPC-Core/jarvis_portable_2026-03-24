import subprocess
from pathlib import Path
from typing import List, Tuple

from services.repair_contracts import RepairAction, RepairExecutionResult, SelfHealingPlan


ALLOWED_COMMANDS: Tuple[Tuple[str, ...], ...] = (
    ("python3", "tools/smoke_check.py"),
    ("python3", "tools/behavioral_check.py"),
)
ALLOWED_PATH_PREFIXES: Tuple[str, ...] = (
    "tools/",
    "data/runtime_backups/",
)
PROTECTED_FILES: Tuple[str, ...] = (
    ".env",
    "jarvis_memory.db",
    "tg_codex_bridge.py",
    "run_jarvis_supervisor.sh",
)


def execute_repair_plan(
    bridge: "TelegramBridge",
    *,
    plan: SelfHealingPlan,
) -> RepairExecutionResult:
    executed_steps: List[str] = []
    stdout_log: List[str] = []
    stderr_log: List[str] = []
    artifacts_changed: List[str] = []
    failed_step = ""
    if plan.dry_run:
        return RepairExecutionResult(
            status="partial",
            executed_steps=tuple(action.action_id for action in plan.actions),
            verification_required=True,
            notes="dry-run only; no repair actions executed",
        )
    for action in plan.actions:
        executed_steps.append(action.action_id)
        if action.action_kind == "internal":
            success, note, artifact = _run_internal_action(bridge, action)
            if note:
                stdout_log.append(note)
            if artifact:
                artifacts_changed.append(artifact)
            if not success and not action.allow_failure:
                failed_step = action.action_id
                return RepairExecutionResult(
                    status="failed",
                    executed_steps=tuple(executed_steps),
                    failed_step=failed_step,
                    artifacts_changed=tuple(artifacts_changed),
                    verification_required=True,
                    notes="internal action failed",
                    stdout_log=tuple(stdout_log),
                    stderr_log=tuple(stderr_log),
                )
            continue
        if action.action_kind == "command":
            success, out_lines, err_lines = _run_allowed_command(bridge.script_path.parent, action)
            stdout_log.extend(out_lines)
            stderr_log.extend(err_lines)
            if not success and not action.allow_failure:
                failed_step = action.action_id
                return RepairExecutionResult(
                    status="failed",
                    executed_steps=tuple(executed_steps),
                    failed_step=failed_step,
                    artifacts_changed=tuple(artifacts_changed),
                    verification_required=True,
                    notes="command action failed",
                    stdout_log=tuple(stdout_log),
                    stderr_log=tuple(stderr_log),
                )
    status = "success" if not failed_step else "partial"
    return RepairExecutionResult(
        status=status,
        executed_steps=tuple(executed_steps),
        failed_step=failed_step,
        artifacts_changed=tuple(dict.fromkeys(artifacts_changed)),
        verification_required=True,
        notes="repair plan executed within bounded allowlist",
        stdout_log=tuple(stdout_log[-20:]),
        stderr_log=tuple(stderr_log[-20:]),
    )


def _run_internal_action(bridge: "TelegramBridge", action: RepairAction) -> Tuple[bool, str, str]:
    if action.action_id == "refresh_runtime_state":
        bridge.refresh_world_state_registry("self_heal")
        bridge.recompute_drive_scores()
        return True, "world-state refreshed", "world_state_registry"
    if action.action_id == "reinitialize_heartbeat":
        bridge.beat_heartbeat()
        return True, "heartbeat refreshed", str(bridge.heartbeat_path)
    if action.action_id == "inspect_sqlite_state":
        bridge.state.get_status_snapshot(bridge.config.backup_chat_id)
        return True, "sqlite snapshot captured", ""
    if action.action_id == "request_restart":
        return False, "restart requires explicit owner approval path", ""
    return False, f"unsupported internal action: {action.action_id}", ""


def _run_allowed_command(workdir: Path, action: RepairAction) -> Tuple[bool, List[str], List[str]]:
    command = tuple(action.command)
    if command not in ALLOWED_COMMANDS:
        return False, [], [f"command not allowed: {' '.join(command)}"]
    try:
        result = subprocess.run(
            list(command),
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=max(1, int(action.timeout_seconds)),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, [], [f"{action.action_id} unavailable: {error}"]
    stdout_lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
    stderr_lines = [line for line in (result.stderr or "").splitlines() if line.strip()]
    return result.returncode == 0, stdout_lines[-10:], stderr_lines[-10:]


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
