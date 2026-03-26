import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from utils.ops_utils import inspect_runtime_log, read_recent_log_highlights, read_recent_operational_highlights
from utils.text_utils import normalize_whitespace, truncate_text


@dataclass(frozen=True)
class RuntimeServiceDeps:
    log_func: Callable[[str], None]
    log_exception_func: Callable[[str, Exception, int], None]
    doc_runtime_drift_markers: tuple[str, ...]


class RuntimeService:
    def __init__(self, deps: RuntimeServiceDeps) -> None:
        self.deps = deps

    def refresh_world_state_registry(self, bridge: "TelegramBridge", source: str = "runtime_tick", chat_id: Optional[int] = None) -> Dict[str, object]:
        del chat_id
        repo_path = bridge.script_path.parent
        try:
            git_status = subprocess.run(
                ["git", "-C", str(repo_path), "status", "--porcelain"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            dirty_lines = [line.strip() for line in git_status.stdout.splitlines() if line.strip()]
        except Exception as error:
            self.deps.log_exception_func("world-state git status failed", error, limit=6)
            dirty_lines = []
        runtime_snapshot = inspect_runtime_log(bridge.log_path)
        recent_errors = read_recent_log_highlights(bridge.log_path, normalize_whitespace, truncate_text, limit=12)
        recent_events = read_recent_operational_highlights(bridge.log_path, normalize_whitespace, truncate_text, limit=12, category="all")
        memory_due = len(bridge.state.get_chats_due_for_memory_refresh(limit=20))
        docs_drift_lines = [
            line for line in dirty_lines
            if any(marker in line for marker in self.deps.doc_runtime_drift_markers)
        ]
        with bridge.state.db_lock:
            live_failures = bridge.state.db.execute(
                """SELECT COUNT(*) FROM request_diagnostics
                WHERE created_at >= strftime('%s','now') - 86400
                  AND used_live = 1
                  AND outcome IN ('error', 'uncertain')"""
            ).fetchone()[0]
            web_failures = bridge.state.db.execute(
                """SELECT COUNT(*) FROM request_diagnostics
                WHERE created_at >= strftime('%s','now') - 86400
                  AND used_web = 1
                  AND outcome IN ('error', 'uncertain')"""
            ).fetchone()[0]
            unresolved_tasks = bridge.state.db.execute(
                """SELECT COUNT(*) FROM autobiographical_memory
                WHERE open_state != 'closed'"""
            ).fetchone()[0]
        last_backup_raw = bridge.state.get_meta("last_backup_ts", "0")
        try:
            last_backup_value = float(last_backup_raw or "0")
        except ValueError:
            last_backup_value = 0.0
        backup_age_hours = ((time.time() - last_backup_value) / 3600.0) if last_backup_value > 0 else -1.0
        now_ts = int(time.time())
        severe_errors_count = int(runtime_snapshot.get("severe_error_count", 0))
        warning_count = int(runtime_snapshot.get("warning_count", 0))
        restart_count = int(runtime_snapshot.get("restart_count", 0))
        heartbeat_kill_count = int(runtime_snapshot.get("heartbeat_kill_count", 0))
        last_severe_error_at = int(runtime_snapshot.get("last_severe_error_at", 0) or 0)
        last_heartbeat_kill_at = int(runtime_snapshot.get("last_heartbeat_kill_at", 0) or 0)
        severe_error_age_seconds = max(0, now_ts - last_severe_error_at) if last_severe_error_at else -1
        heartbeat_kill_age_seconds = max(0, now_ts - last_heartbeat_kill_at) if last_heartbeat_kill_at else -1
        state_payload = {
            "git_dirty_count": len(dirty_lines),
            "recent_errors_count": severe_errors_count,
            "recent_warning_count": warning_count,
            "recent_events_count": len(recent_events),
            "live_failures_count": int(live_failures or 0),
            "web_failures_count": int(web_failures or 0),
            "memory_due_count": memory_due,
            "docs_drift_count": len(docs_drift_lines),
            "unresolved_tasks_count": int(unresolved_tasks or 0),
            "backup_age_hours": round(backup_age_hours, 1) if backup_age_hours >= 0 else -1.0,
            "upgrade_active": 1 if bridge.state.global_upgrade_active else 0,
            "chat_tasks_active": len(bridge.state.chat_tasks_in_progress),
            "restart_count": restart_count,
            "heartbeat_kill_count": heartbeat_kill_count,
            "severe_error_age_seconds": severe_error_age_seconds,
            "heartbeat_kill_age_seconds": heartbeat_kill_age_seconds,
        }
        if (
            (severe_errors_count and 0 <= severe_error_age_seconds <= 7200)
            or (heartbeat_kill_count and 0 <= heartbeat_kill_age_seconds <= 7200)
        ):
            runtime_status = "risk"
        elif restart_count or warning_count or bridge.state.global_upgrade_active:
            runtime_status = "attention"
        else:
            runtime_status = "ok"
        git_status_text = "dirty" if dirty_lines else "clean"
        bridge.state.upsert_world_state_entry(
            "runtime_health",
            category="runtime",
            status=runtime_status,
            value_text=(
                f"errors={severe_errors_count}; warnings={warning_count}; restarts={restart_count}; "
                f"heartbeat_kills={heartbeat_kill_count}; events={len(recent_events)}; memory_due={memory_due}; "
                f"last_error_age_s={severe_error_age_seconds if severe_error_age_seconds >= 0 else 'n/a'}; "
                f"upgrade_active={'yes' if bridge.state.global_upgrade_active else 'no'}"
            ),
            value_number=float(severe_errors_count),
            source=source,
            confidence=0.92,
            ttl_seconds=120,
            verification_method="local_runtime_log_probe",
            stale_flag=False,
        )
        bridge.state.upsert_world_state_entry(
            "git_state",
            category="project",
            status=git_status_text,
            value_text="\n".join(dirty_lines[:8]) if dirty_lines else "worktree clean",
            value_number=float(len(dirty_lines)),
            source=source,
            confidence=0.96,
            ttl_seconds=300,
            verification_method="git_status_porcelain",
            stale_flag=False,
        )
        bridge.state.upsert_world_state_entry(
            "live_source_health",
            category="live",
            status="attention" if int(live_failures or 0) else "ok",
            value_text=f"recent_live_failures={int(live_failures or 0)}; recent_web_failures={int(web_failures or 0)}",
            value_number=float(int(live_failures or 0)),
            source=source,
            confidence=0.78,
            ttl_seconds=900,
            verification_method="request_diagnostics_rollup",
            stale_flag=bool(int(live_failures or 0) >= 3),
        )
        bridge.state.upsert_world_state_entry(
            "doc_runtime_drift",
            category="sync",
            status="attention" if docs_drift_lines else "ok",
            value_text="\n".join(docs_drift_lines[:6]) if docs_drift_lines else "docs/runtime backfills synced",
            value_number=float(len(docs_drift_lines)),
            source=source,
        )
        bridge.state.upsert_world_state_entry(
            "owner_priority_state",
            category="owner",
            status="attention" if int(unresolved_tasks or 0) else "ok",
            value_text=f"open_tasks={int(unresolved_tasks or 0)}; backup_age_hours={round(backup_age_hours, 1) if backup_age_hours >= 0 else 'n/a'}",
            value_number=float(int(unresolved_tasks or 0)),
            source=source,
        )
        if source in {"startup", "owner_report", "reflection", "upgrade", "runtime_error"} or recent_errors or docs_drift_lines:
            summary = (
                f"runtime={runtime_status}; git={git_status_text}; live_failures={int(live_failures or 0)}; web_failures={int(web_failures or 0)}; "
                f"open_tasks={int(unresolved_tasks or 0)}; docs_drift={len(docs_drift_lines)}"
            )
            bridge.state.add_world_state_snapshot(source, summary, state_payload)
        return state_payload

    def recompute_drive_scores(self, bridge: "TelegramBridge", operational_state: Optional[Dict[str, object]] = None) -> Dict[str, float]:
        state_payload = operational_state or self.refresh_world_state_registry(bridge, "drive_recompute")
        with bridge.state.db_lock:
            uncertain_rows = bridge.state.db.execute(
                """SELECT COUNT(*) FROM request_diagnostics
                WHERE created_at >= strftime('%s','now') - 86400
                  AND outcome IN ('uncertain', 'error')"""
            ).fetchone()[0]
        uncertainty_score = min(100.0, float(int(uncertain_rows or 0) * 12))
        inconsistency_score = min(100.0, float(int(state_payload.get("git_dirty_count", 0)) * 10))
        stale_memory_score = min(100.0, float(int(state_payload.get("memory_due_count", 0)) * 18))
        unresolved_task_score = min(100.0, float(int(state_payload.get("unresolved_tasks_count", 0)) * 20 + len(bridge.state.chat_tasks_in_progress) * 12))
        doc_sync_score = min(100.0, float(int(state_payload.get("docs_drift_count", 0)) * 25))
        severe_error_age_seconds = int(state_payload.get("severe_error_age_seconds", -1) or -1)
        heartbeat_kill_age_seconds = int(state_payload.get("heartbeat_kill_age_seconds", -1) or -1)
        fresh_runtime_penalty = 0.0
        if 0 <= severe_error_age_seconds <= 7200:
            fresh_runtime_penalty += 30.0
        if 0 <= heartbeat_kill_age_seconds <= 7200:
            fresh_runtime_penalty += 30.0
        runtime_risk_score = min(
            100.0,
            float(
                int(state_payload.get("recent_errors_count", 0)) * 3
                + int(state_payload.get("recent_warning_count", 0)) * 2
                + int(state_payload.get("live_failures_count", 0)) * 10
                + int(state_payload.get("heartbeat_kill_count", 0)) * 6
                + int(state_payload.get("upgrade_active", 0)) * 12
                + fresh_runtime_penalty
            ),
        )
        scores = {
            "uncertainty_pressure": uncertainty_score,
            "inconsistency_pressure": inconsistency_score,
            "stale_memory_pressure": stale_memory_score,
            "unresolved_task_pressure": unresolved_task_score,
            "doc_sync_pressure": doc_sync_score,
            "runtime_risk_pressure": runtime_risk_score,
        }
        reasons = {
            "uncertainty_pressure": f"recent uncertain/error routes={int(uncertain_rows or 0)}",
            "inconsistency_pressure": f"git dirty entries={int(state_payload.get('git_dirty_count', 0))}",
            "stale_memory_pressure": f"chats due for refresh={int(state_payload.get('memory_due_count', 0))}",
            "unresolved_task_pressure": f"open tasks={int(state_payload.get('unresolved_tasks_count', 0))}; active_chat_tasks={len(bridge.state.chat_tasks_in_progress)}",
            "doc_sync_pressure": f"docs/runtime drift entries={int(state_payload.get('docs_drift_count', 0))}",
            "runtime_risk_pressure": (
                f"errors={int(state_payload.get('recent_errors_count', 0))}; "
                f"warnings={int(state_payload.get('recent_warning_count', 0))}; "
                f"live_failures={int(state_payload.get('live_failures_count', 0))}; "
                f"heartbeat_kills={int(state_payload.get('heartbeat_kill_count', 0))}; "
                f"upgrade_active={int(state_payload.get('upgrade_active', 0))}"
            ),
        }
        for drive_name, score in scores.items():
            bridge.state.set_drive_score(drive_name, score, reasons[drive_name])
        return scores


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
