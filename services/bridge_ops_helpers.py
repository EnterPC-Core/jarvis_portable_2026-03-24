from pathlib import Path
from typing import Callable, Dict, List

from utils.ops_utils import (
    inspect_runtime_log as _inspect_runtime_log,
    is_error_log_line as _is_error_log_line,
    is_operational_log_line as _is_operational_log_line,
    read_recent_log_highlights as _read_recent_log_highlights,
    read_recent_operational_highlights as _read_recent_operational_highlights,
    render_git_last_commits as _render_git_last_commits,
    render_git_status_summary as _render_git_status_summary,
    run_git_command as _run_git_command,
)


def read_recent_log_highlights(
    log_path: Path,
    *,
    normalize_whitespace_func: Callable[[str], str],
    truncate_text_func: Callable[[str, int], str],
    limit: int = 8,
) -> List[str]:
    return _read_recent_log_highlights(log_path, normalize_whitespace_func, truncate_text_func, limit)


def is_error_log_line(lowered_line: str) -> bool:
    return _is_error_log_line(lowered_line)


def read_recent_operational_highlights(
    log_path: Path,
    *,
    normalize_whitespace_func: Callable[[str], str],
    truncate_text_func: Callable[[str, int], str],
    limit: int = 8,
    category: str = "all",
) -> List[str]:
    return _read_recent_operational_highlights(
        log_path,
        normalize_whitespace_func,
        truncate_text_func,
        limit,
        category,
    )


def is_operational_log_line(lowered_line: str, category: str = "all") -> bool:
    return _is_operational_log_line(lowered_line, category)


def inspect_runtime_log(log_path: Path, window_seconds: int = 86400) -> Dict[str, object]:
    return _inspect_runtime_log(log_path, window_seconds)


def run_git_command(
    repo_path: Path,
    args: List[str],
    *,
    build_subprocess_env_func: Callable[[], Dict[str, str]],
    normalize_whitespace_func: Callable[[str], str],
    timeout_seconds: int = 20,
) -> str:
    return _run_git_command(repo_path, args, build_subprocess_env_func, normalize_whitespace_func, timeout_seconds)


def render_git_status_summary(
    repo_path: Path,
    *,
    run_git_command_func: Callable[[Path, List[str], int], str],
) -> str:
    return _render_git_status_summary(repo_path, run_git_command_func)


def render_git_last_commits(
    repo_path: Path,
    *,
    run_git_command_func: Callable[[Path, List[str], int], str],
    limit: int = 5,
) -> str:
    return _render_git_last_commits(repo_path, run_git_command_func, limit)
