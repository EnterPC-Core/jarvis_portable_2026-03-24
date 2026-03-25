import subprocess
from pathlib import Path
from typing import Callable, List


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
) -> List[str]:
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    matched: List[str] = []
    for line in reversed(lines[-300:]):
        lowered = line.lower()
        if is_error_log_line(lowered):
            matched.append(truncate_text_func(normalize_whitespace_func(line), 220))
        if len(matched) >= limit:
            break
    return list(reversed(matched))


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
) -> List[str]:
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    matched: List[str] = []
    for line in reversed(lines[-400:]):
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
