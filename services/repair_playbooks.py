from typing import Dict, Iterable, List, Tuple

from services.repair_contracts import FailureSignal, RepairPlaybook, VerificationStep


REPAIR_PLAYBOOKS: Tuple[RepairPlaybook, ...] = (
    RepairPlaybook(
        playbook_id="restart_bridge_runtime",
        title="Restart bridge runtime via supervisor",
        allowed_actions=("restart_bridge_process", "inspect_supervisor_log"),
        required_prechecks=("single_supervisor_present", "owner_permission", "runtime_process_exists"),
        verification_steps=(
            VerificationStep("bridge_process_alive", "Убедиться, что после рестарта жив ровно один python3 tg_codex_bridge.py"),
            VerificationStep("startup_marker", "Убедиться, что в логах есть свежий marker 'bot started'"),
            VerificationStep("heartbeat_fresh", "Убедиться, что heartbeat обновляется"),
        ),
        rollback_steps=("Не применять destructive rollback; при неуспехе оставить incident open и эскалировать owner.",),
        claim_policy="Можно говорить о рестарте только после process+startup verification.",
        handles_signals=("restart_loop", "heartbeat_stale", "runtime_process_missing"),
    ),
    RepairPlaybook(
        playbook_id="repair_sqlite_schema",
        title="Repair SQLite schema mismatch",
        allowed_actions=("inspect_schema", "apply_migration_patch", "run_py_compile", "run_smoke_checks"),
        required_prechecks=("owner_permission", "db_backup_or_snapshot", "schema_error_confirmed"),
        verification_steps=(
            VerificationStep("schema_probe", "Подтвердить, что проблемная таблица/колонка существует"),
            VerificationStep("smoke_checks", "Прогнать smoke-check"),
            VerificationStep("behavioral_checks", "Прогнать behavioral-check"),
        ),
        rollback_steps=("Откатить последний patch по схеме или восстановить backup snapshot.",),
        claim_policy="Нельзя говорить, что schema fixed, если smoke/behavioral не прошли.",
        handles_signals=("sqlite_schema_mismatch",),
    ),
    RepairPlaybook(
        playbook_id="stabilize_live_providers",
        title="Stabilize degraded live providers",
        allowed_actions=("inspect_provider_failures", "switch_to_fallback_chain", "re-run_live_query_smoke"),
        required_prechecks=("provider_error_confirmed", "network_available"),
        verification_steps=(
            VerificationStep("provider_status", "Проверить, что fallback provider отвечает"),
            VerificationStep("freshness_present", "Проверить, что ответ содержит source/freshness"),
        ),
        rollback_steps=("Оставить route в insufficient mode, если fallback не подтверждён.",),
        claim_policy="При непрошедшем provider verification ответ должен быть insufficient, а не repaired.",
        handles_signals=("live_provider_degraded",),
    ),
    RepairPlaybook(
        playbook_id="audit_route_regression",
        title="Audit route regression before repair",
        allowed_actions=("inspect_route_diagnostics", "run_routing_smoke", "patch_router"),
        required_prechecks=("route_signal_confirmed", "owner_permission"),
        verification_steps=(
            VerificationStep("routing_smoke", "Проверить routing smoke-check"),
            VerificationStep("route_trace", "Убедиться, что целевой prompt идёт по нужному route"),
        ),
        rollback_steps=("Откатить router patch и вернуть previous policy.",),
        claim_policy="Нельзя говорить, что route repaired, если route trace после фикса не подтверждён.",
        handles_signals=("route_regression",),
    ),
)


def select_playbooks_for_signals(signals: Iterable[FailureSignal]) -> List[RepairPlaybook]:
    selected: List[RepairPlaybook] = []
    seen = set()
    signal_codes = {signal.signal_code for signal in signals}
    for playbook in REPAIR_PLAYBOOKS:
        if not signal_codes.intersection(playbook.handles_signals):
            continue
        if playbook.playbook_id in seen:
            continue
        selected.append(playbook)
        seen.add(playbook.playbook_id)
    return selected


def render_playbook_summary(playbooks: Iterable[RepairPlaybook]) -> str:
    items = list(playbooks)
    if not items:
        return "Repair playbooks: нет подтверждённых кандидатов."
    lines = ["Repair playbooks"]
    for item in items:
        lines.append(f"- {item.playbook_id}: {item.title}")
        lines.append(f"  allowed_actions={', '.join(item.allowed_actions)}")
        lines.append(f"  prechecks={', '.join(item.required_prechecks)}")
        lines.append(f"  claim_policy={item.claim_policy}")
    return "\n".join(lines)

