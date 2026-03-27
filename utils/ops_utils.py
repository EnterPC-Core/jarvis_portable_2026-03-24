import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional


def is_error_log_line(lowered_line: str) -> bool:
    if not lowered_line:
        return False
    ignore_markers = (
        "config loaded",
        "bot started",
        "stt model loaded",
        "stt model prewarmed",
        "incoming text",
        "incoming reaction",
        "received termination signal",
        "process exiting reason=signal:sigterm",
        "bridge exited status=0",
        "exchange lookup failed",
        "exchange yahoo lookup failed",
        "exchange open.er lookup failed",
        "url fetch failed",
        "codex degraded",
    )
    if any(marker in lowered_line for marker in ignore_markers):
        return False
    error_markers = (
        " error",
        "error:",
        "failed",
        "traceback",
        "unexpected",
        "exception",
        "timed out",
        "timeout expired",
    )
    return any(marker in lowered_line for marker in error_markers)


def read_recent_log_highlights(
    log_path: Path,
    normalize_whitespace_func: Callable[[str], str],
    truncate_text_func: Callable[[str, int], str],
    limit: int = 8,
    window_seconds: int = 86400,
) -> List[str]:
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    now_ts = int(time.time())
    cutoff = now_ts - max(60, window_seconds)
    matched: List[str] = []
    current_event_ts: Optional[int] = None
    for line in reversed(lines[-800:]):
        line_ts = parse_log_timestamp(line)
        if line_ts is not None:
            current_event_ts = line_ts
        if current_event_ts is not None and current_event_ts < cutoff:
            continue
        lowered = line.lower()
        if line.startswith("[") and is_error_log_line(lowered):
            matched.append(truncate_text_func(normalize_whitespace_func(line), 220))
        if len(matched) >= limit:
            break
    return list(reversed(matched))


def parse_log_timestamp(line: str) -> Optional[int]:
    if not line.startswith("[") or "]" not in line:
        return None
    try:
        stamp = line[1:20]
        return int(datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timestamp())
    except ValueError:
        return None


def inspect_runtime_log(log_path: Path, window_seconds: int = 86400) -> Dict[str, object]:
    snapshot: Dict[str, object] = {
        "restart_count": 0,
        "heartbeat_kill_count": 0,
        "termination_signal_count": 0,
        "network_error_count": 0,
        "codex_error_count": 0,
        "codex_degraded_count": 0,
        "lock_conflict_count": 0,
        "severe_error_count": 0,
        "warning_count": 0,
        "last_restart_line": "",
        "last_restart_at": 0,
        "last_severe_error_at": 0,
        "last_warning_at": 0,
        "last_heartbeat_kill_at": 0,
        "recent_error_lines": [],
        "recent_warning_lines": [],
    }
    if not log_path.exists():
        return snapshot
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return snapshot
    now_ts = int(time.time())
    cutoff = now_ts - max(60, window_seconds)
    warning_markers = (
        "exchange lookup failed",
        "exchange yahoo lookup failed",
        "exchange open.er lookup failed",
        "url fetch failed",
    )
    severe_lines: List[str] = []
    warning_lines: List[str] = []
    current_event_ts: Optional[int] = None
    for line in lines:
        line_ts = parse_log_timestamp(line)
        if line_ts is not None:
            current_event_ts = line_ts
        if current_event_ts is not None and current_event_ts < cutoff:
            continue
        lowered = line.lower()
        is_timestamped = line.startswith("[")
        if "bridge exited" in lowered:
            snapshot["restart_count"] = int(snapshot["restart_count"]) + 1
            snapshot["last_restart_line"] = line
            snapshot["last_restart_at"] = line_ts or int(snapshot["last_restart_at"])
        if "heartbeat stale" in lowered:
            snapshot["heartbeat_kill_count"] = int(snapshot["heartbeat_kill_count"]) + 1
            snapshot["last_heartbeat_kill_at"] = line_ts or int(snapshot["last_heartbeat_kill_at"])
        if "received termination signal" in lowered:
            snapshot["termination_signal_count"] = int(snapshot["termination_signal_count"]) + 1
        if "network error in main loop" in lowered:
            snapshot["network_error_count"] = int(snapshot["network_error_count"]) + 1
        if "codex error" in lowered:
            snapshot["codex_error_count"] = int(snapshot["codex_error_count"]) + 1
        if "codex degraded" in lowered:
            snapshot["codex_degraded_count"] = int(snapshot["codex_degraded_count"]) + 1
            snapshot["warning_count"] = int(snapshot["warning_count"]) + 1
            snapshot["last_warning_at"] = line_ts or int(snapshot["last_warning_at"])
            warning_lines.append(line)
            continue
        if "instance lock conflict" in lowered:
            snapshot["lock_conflict_count"] = int(snapshot["lock_conflict_count"]) + 1
        if any(marker in lowered for marker in warning_markers):
            snapshot["warning_count"] = int(snapshot["warning_count"]) + 1
            snapshot["last_warning_at"] = line_ts or int(snapshot["last_warning_at"])
            warning_lines.append(line)
            continue
        if is_timestamped and is_error_log_line(lowered):
            snapshot["severe_error_count"] = int(snapshot["severe_error_count"]) + 1
            snapshot["last_severe_error_at"] = line_ts or int(snapshot["last_severe_error_at"])
            severe_lines.append(line)
    snapshot["recent_error_lines"] = severe_lines[-8:]
    snapshot["recent_warning_lines"] = warning_lines[-8:]
    return snapshot


def is_operational_log_line(lowered_line: str, category: str = "all") -> bool:
    if not lowered_line:
        return False
    category_markers = {
        "restart": (
            "restart requested",
            "bridge exited",
        ),
        "access": (
            "blocked user_id",
        ),
        "system": (
            "restart requested",
            "bridge exited",
        ),
        "all": (
            "restart requested",
            "bridge exited",
            "blocked user_id",
        ),
    }
    markers = category_markers.get(category, category_markers["all"])
    return any(marker in lowered_line for marker in markers)


def read_recent_operational_highlights(
    log_path: Path,
    normalize_whitespace_func: Callable[[str], str],
    truncate_text_func: Callable[[str, int], str],
    limit: int = 8,
    category: str = "all",
    window_seconds: int = 86400,
) -> List[str]:
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    now_ts = int(time.time())
    cutoff = now_ts - max(60, window_seconds)
    matched: List[str] = []
    current_event_ts: Optional[int] = None
    for line in reversed(lines[-1000:]):
        line_ts = parse_log_timestamp(line)
        if line_ts is not None:
            current_event_ts = line_ts
        if current_event_ts is not None and current_event_ts < cutoff:
            continue
        lowered = line.lower()
        if is_operational_log_line(lowered, category=category):
            matched.append(truncate_text_func(normalize_whitespace_func(line), 220))
        if len(matched) >= limit:
            break
    return list(reversed(matched))


def run_git_command(
    repo_path: Path,
    args: List[str],
    build_subprocess_env_func: Callable[[], dict],
    normalize_whitespace_func: Callable[[str], str],
    timeout_seconds: int = 20,
) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path)] + args,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=build_subprocess_env_func(),
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        return f"git command failed: {error}"
    output = normalize_whitespace_func((result.stdout or "").strip() or (result.stderr or "").strip())
    if result.returncode != 0:
        return output or f"git exited with code {result.returncode}"
    return output or "Нет вывода."


def render_git_status_summary(
    repo_path: Path,
    run_git_command_func: Callable[[Path, List[str], int], str],
) -> str:
    branch = run_git_command_func(repo_path, ["branch", "--show-current"], 20)
    status = run_git_command_func(repo_path, ["status", "--short"], 20)
    remote = run_git_command_func(repo_path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], 20)
    lines = ["Git status", f"Repo: {repo_path}", f"Branch: {branch}"]
    if remote and "fatal:" not in remote and "git command failed" not in remote:
        lines.append(f"Upstream: {remote}")
    if not status or status == "Нет вывода.":
        lines.append("Worktree: clean")
    else:
        lines.append("Изменения:")
        lines.extend(f"- {line}" for line in status.splitlines()[:20])
    return "\n".join(lines)


def render_git_last_commits(
    repo_path: Path,
    run_git_command_func: Callable[[Path, List[str], int], str],
    limit: int = 5,
) -> str:
    output = run_git_command_func(repo_path, ["log", f"-{limit}", "--pretty=format:%h %ad %s", "--date=short"], 20)
    if not output or output.startswith("fatal:") or output.startswith("git command failed:"):
        return f"Последние коммиты получить не удалось.\n{output}"
    return "Последние коммиты:\n" + "\n".join(f"- {line}" for line in output.splitlines())
