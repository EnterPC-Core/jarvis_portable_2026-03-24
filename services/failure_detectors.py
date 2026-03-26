import time
from typing import Iterable, List, Mapping, Optional

from services.repair_contracts import FailureSignal


def detect_failure_signals(
    *,
    runtime_snapshot: Mapping[str, object],
    recent_errors: Iterable[str],
    recent_routes: Iterable[Mapping[str, object]],
    heartbeat_timeout_seconds: int,
    now_ts: Optional[int] = None,
) -> List[FailureSignal]:
    now = int(now_ts or time.time())
    signals: List[FailureSignal] = []
    error_lines = [str(item) for item in recent_errors if str(item).strip()]
    severe_error_count = int(runtime_snapshot.get("severe_error_count", 0) or 0)
    restart_count = int(runtime_snapshot.get("restart_count", 0) or 0)
    heartbeat_kill_count = int(runtime_snapshot.get("heartbeat_kill_count", 0) or 0)
    warning_count = int(runtime_snapshot.get("warning_count", 0) or 0)
    last_restart_at = int(runtime_snapshot.get("last_restart_at", 0) or 0)
    if restart_count >= 3 and last_restart_at and now - last_restart_at <= max(3600, heartbeat_timeout_seconds * 4):
        signals.append(
            FailureSignal(
                signal_code="restart_loop",
                severity="high",
                summary="Bridge похоже входит в цикл рестартов.",
                evidence=f"restart_count={restart_count}; last_restart_at={last_restart_at}",
                confidence=0.88,
                source="runtime_log",
                suggested_playbook="restart_bridge_runtime",
            )
        )
    if heartbeat_kill_count > 0:
        signals.append(
            FailureSignal(
                signal_code="heartbeat_stale",
                severity="high",
                summary="Supervisor уже убивал bridge из-за stale heartbeat.",
                evidence=f"heartbeat_kill_count={heartbeat_kill_count}",
                confidence=0.92,
                source="runtime_log",
                suggested_playbook="restart_bridge_runtime",
            )
        )
    if any("sqlite3.operationalerror" in line.lower() and ("no such table" in line.lower() or "values for" in line.lower()) for line in error_lines):
        signals.append(
            FailureSignal(
                signal_code="sqlite_schema_mismatch",
                severity="high",
                summary="Обнаружена SQLite schema mismatch ошибка.",
                evidence=next((line for line in error_lines if "sqlite3.OperationalError" in line), error_lines[0] if error_lines else ""),
                confidence=0.95,
                source="runtime_log",
                suggested_playbook="repair_sqlite_schema",
            )
        )
    if warning_count >= 3 and any("lookup failed" in line.lower() for line in error_lines):
        signals.append(
            FailureSignal(
                signal_code="live_provider_degraded",
                severity="medium",
                summary="Live providers деградировали: серия lookup failures.",
                evidence=f"warning_count={warning_count}",
                confidence=0.76,
                source="runtime_log",
                suggested_playbook="stabilize_live_providers",
            )
        )
    degraded_routes = 0
    for row in recent_routes:
        outcome = str(row["outcome"] or "").strip().lower()
        route_kind = str(row["route_kind"] or "")
        if outcome not in {"ok", ""} and route_kind:
            degraded_routes += 1
    if degraded_routes >= 3:
        signals.append(
            FailureSignal(
                signal_code="route_regression",
                severity="medium",
                summary="В последних route diagnostics видно несколько деградировавших маршрутов.",
                evidence=f"degraded_routes={degraded_routes}",
                confidence=0.7,
                source="request_diagnostics",
                suggested_playbook="audit_route_regression",
            )
        )
    if severe_error_count > 0 and not signals:
        signals.append(
            FailureSignal(
                signal_code="severe_runtime_errors",
                severity="medium",
                summary="В хвосте лога есть severe runtime errors.",
                evidence=f"severe_error_count={severe_error_count}",
                confidence=0.64,
                source="runtime_log",
                suggested_playbook="audit_route_regression",
            )
        )
    return signals


def render_failure_signals(signals: Iterable[FailureSignal]) -> str:
    items = list(signals)
    if not items:
        return "Failure signals: подтверждённых инцидентов сейчас не обнаружено."
    lines = ["Failure signals"]
    for item in items:
        lines.append(
            f"- {item.signal_code} severity={item.severity} confidence={item.confidence:.2f} source={item.source}"
        )
        lines.append(f"  {item.summary}")
        if item.evidence:
            lines.append(f"  evidence={item.evidence}")
        if item.suggested_playbook:
            lines.append(f"  suggested_playbook={item.suggested_playbook}")
    return "\n".join(lines)
