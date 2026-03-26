from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class DiagnosticsMetrics:
    window_seconds: int
    total_requests: int
    verified_count: int
    inferred_count: int
    insufficient_count: int
    degraded_count: int
    live_stale_count: int
    live_failed_count: int
    runtime_probe_count: int
    self_check_issue_count: int
    prevented_false_claim_count: int
    route_counts: Tuple[Tuple[str, int], ...]
    memory_counts: Tuple[Tuple[str, int], ...]


def _split_csv_counts(raw_rows: List[Tuple[str, int]], *, limit: int = 6) -> Tuple[Tuple[str, int], ...]:
    counts: Dict[str, int] = {}
    for raw_value, row_count in raw_rows:
        for part in (raw_value or "").split(","):
            cleaned = part.strip()
            if not cleaned:
                continue
            counts[cleaned] = counts.get(cleaned, 0) + int(row_count or 0)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(ranked[:limit])


def collect_diagnostics_metrics(
    state: "BridgeState",
    *,
    window_seconds: int = 86400,
    chat_id: Optional[int] = None,
) -> DiagnosticsMetrics:
    effective_window = max(300, int(window_seconds))
    filters = ["created_at >= strftime('%s','now') - ?"]
    params: List[object] = [effective_window]
    if chat_id is not None:
        filters.append("chat_id = ?")
        params.append(int(chat_id))
    where_clause = " AND ".join(filters)
    with state.db_lock:
        row = state.db.execute(
            f"""SELECT
                    COUNT(*) AS total_requests,
                    SUM(CASE WHEN response_mode = 'verified' THEN 1 ELSE 0 END) AS verified_count,
                    SUM(CASE WHEN response_mode = 'inferred' THEN 1 ELSE 0 END) AS inferred_count,
                    SUM(CASE WHEN response_mode = 'insufficient' THEN 1 ELSE 0 END) AS insufficient_count,
                    SUM(CASE WHEN outcome IN ('uncertain', 'error') THEN 1 ELSE 0 END) AS degraded_count,
                    SUM(CASE WHEN used_live = 1 AND (freshness LIKE '%stale%' OR freshness = 'stale') THEN 1 ELSE 0 END) AS live_stale_count,
                    SUM(CASE WHEN used_live = 1 AND outcome IN ('uncertain', 'error') THEN 1 ELSE 0 END) AS live_failed_count,
                    SUM(CASE WHEN request_kind = 'runtime' OR tools_used LIKE '%direct_runtime_probe%' THEN 1 ELSE 0 END) AS runtime_probe_count,
                    SUM(CASE WHEN outcome != 'ok' OR response_mode != 'verified' THEN 1 ELSE 0 END) AS self_check_issue_count,
                    SUM(CASE WHEN response_mode = 'insufficient' AND guardrails != '' THEN 1 ELSE 0 END) AS prevented_false_claim_count
                FROM request_diagnostics
                WHERE {where_clause}""",
            tuple(params),
        ).fetchone()
        route_rows = state.db.execute(
            f"""SELECT route_kind, COUNT(*) AS hits
                FROM request_diagnostics
                WHERE {where_clause}
                GROUP BY route_kind
                ORDER BY hits DESC, route_kind ASC
                LIMIT 6""",
            tuple(params),
        ).fetchall()
        memory_rows = state.db.execute(
            f"""SELECT memory_used, COUNT(*) AS hits
                FROM request_diagnostics
                WHERE {where_clause} AND memory_used != ''
                GROUP BY memory_used
                ORDER BY hits DESC, memory_used ASC
                LIMIT 20""",
            tuple(params),
        ).fetchall()
    route_counts = tuple((str(item[0] or "-"), int(item[1] or 0)) for item in route_rows)
    memory_counts = _split_csv_counts([(str(item[0] or ""), int(item[1] or 0)) for item in memory_rows])
    return DiagnosticsMetrics(
        window_seconds=effective_window,
        total_requests=int(row["total_requests"] or 0),
        verified_count=int(row["verified_count"] or 0),
        inferred_count=int(row["inferred_count"] or 0),
        insufficient_count=int(row["insufficient_count"] or 0),
        degraded_count=int(row["degraded_count"] or 0),
        live_stale_count=int(row["live_stale_count"] or 0),
        live_failed_count=int(row["live_failed_count"] or 0),
        runtime_probe_count=int(row["runtime_probe_count"] or 0),
        self_check_issue_count=int(row["self_check_issue_count"] or 0),
        prevented_false_claim_count=int(row["prevented_false_claim_count"] or 0),
        route_counts=route_counts,
        memory_counts=memory_counts,
    )


def render_diagnostics_metrics(metrics: DiagnosticsMetrics) -> str:
    hours = max(1, metrics.window_seconds // 3600)
    lines = [
        f"Quality diagnostics за {hours}ч",
        f"- total={metrics.total_requests}",
        f"- verified={metrics.verified_count} inferred={metrics.inferred_count} insufficient={metrics.insufficient_count}",
        f"- degraded_routes={metrics.degraded_count} self_check_issues={metrics.self_check_issue_count}",
        f"- live_stale={metrics.live_stale_count} live_failed={metrics.live_failed_count}",
        f"- runtime_probe_required={metrics.runtime_probe_count}",
        f"- prevented_false_claims={metrics.prevented_false_claim_count}",
    ]
    if metrics.route_counts:
        lines.append("- top_routes=" + ", ".join(f"{name}:{count}" for name, count in metrics.route_counts))
    else:
        lines.append("- top_routes=none")
    if metrics.memory_counts:
        lines.append("- top_memory=" + ", ".join(f"{name}:{count}" for name, count in metrics.memory_counts))
    else:
        lines.append("- top_memory=none")
    return "\n".join(lines)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import BridgeState
