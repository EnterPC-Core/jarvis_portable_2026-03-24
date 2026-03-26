from typing import Iterable, List, Tuple

from services.repair_contracts import (
    AUTONOMY_AUTO_WITH_VERIFICATION,
    AUTONOMY_REQUIRE_OWNER_APPROVAL,
    AUTONOMY_SAFE_AUTO,
    FailureClassification,
    FailureSignal,
    RepairAction,
    RepairPlaybook,
    VerificationStep,
)


REPAIR_PLAYBOOKS: Tuple[RepairPlaybook, ...] = (
    RepairPlaybook(
        playbook_id="restart_runtime",
        title="Restart bridge runtime via supervisor",
        allowed_actions=("restart_bridge_process", "inspect_supervisor_log"),
        required_prechecks=("single_supervisor_present", "owner_permission", "runtime_process_exists"),
        verification_steps=(
            VerificationStep("bridge_process_alive", "Убедиться, что после рестарта жив ровно один python3 tg_codex_bridge.py", verifier_kind="process_alive"),
            VerificationStep("startup_marker", "Убедиться, что в логах есть свежий marker 'bot started'", verifier_kind="startup_marker"),
            VerificationStep("heartbeat_fresh", "Убедиться, что heartbeat обновляется", verifier_kind="heartbeat_fresh"),
        ),
        rollback_steps=("Не применять destructive rollback; при неуспехе оставить incident open и эскалировать owner.",),
        claim_policy="Можно говорить о рестарте только после process+startup verification.",
        handles_signals=("restart_loop", "heartbeat_stale", "runtime_process_missing", "severe_runtime_errors"),
        target_problem_type="runtime_down",
        preconditions=("owner_gate", "single_instance_control"),
        actions=(
            RepairAction("request_restart", "Перезапустить bridge через штатный restart path", action_kind="internal", timeout_seconds=15),
        ),
        expected_effect="Runtime должен подняться заново под supervisor.",
        timeout_seconds=30,
        retry_policy="single_retry_after_verification_failure",
        risk_level="high",
        autonomy_level=AUTONOMY_REQUIRE_OWNER_APPROVAL,
    ),
    RepairPlaybook(
        playbook_id="repair_sqlite_schema",
        title="Repair SQLite schema mismatch",
        allowed_actions=("inspect_schema", "apply_migration_patch", "run_py_compile", "run_smoke_checks"),
        required_prechecks=("owner_permission", "db_backup_or_snapshot", "schema_error_confirmed"),
        verification_steps=(
            VerificationStep("schema_probe", "Подтвердить, что проблемная таблица/колонка существует", verifier_kind="sqlite_probe"),
            VerificationStep("smoke_checks", "Прогнать smoke-check", verifier_kind="smoke_check"),
            VerificationStep("behavioral_checks", "Прогнать behavioral-check", verifier_kind="behavioral_check"),
        ),
        rollback_steps=("Откатить последний patch по схеме или восстановить backup snapshot.",),
        claim_policy="Нельзя говорить, что schema fixed, если smoke/behavioral не прошли.",
        handles_signals=("sqlite_schema_mismatch",),
        target_problem_type="sqlite_error",
        preconditions=("backup_available", "schema_error_confirmed"),
        actions=(
            RepairAction("inspect_sqlite_state", "Проверить локальную схему и lock-состояние SQLite", action_kind="internal"),
            RepairAction("run_smoke_check", "Прогнать smoke-check", action_kind="command", command=("python3", "tools/smoke_check.py"), timeout_seconds=120),
            RepairAction("run_behavioral_check", "Прогнать behavioral-check", action_kind="command", command=("python3", "tools/behavioral_check.py"), timeout_seconds=120),
        ),
        expected_effect="Schema mismatch должен либо подтвердиться, либо быть устранён с последующей верификацией.",
        timeout_seconds=240,
        retry_policy="no_retry_without_owner",
        risk_level="high",
        autonomy_level=AUTONOMY_REQUIRE_OWNER_APPROVAL,
    ),
    RepairPlaybook(
        playbook_id="recover_failed_live_provider_config",
        title="Stabilize degraded live providers",
        allowed_actions=("inspect_provider_failures", "switch_to_fallback_chain", "re-run_live_query_smoke"),
        required_prechecks=("provider_error_confirmed", "network_available"),
        verification_steps=(
            VerificationStep("provider_status", "Проверить, что fallback provider отвечает", verifier_kind="world_state_fresh"),
            VerificationStep("freshness_present", "Проверить, что ответ содержит source/freshness", verifier_kind="world_state_fresh"),
        ),
        rollback_steps=("Оставить route в insufficient mode, если fallback не подтверждён.",),
        claim_policy="При непрошедшем provider verification ответ должен быть insufficient, а не repaired.",
        handles_signals=("live_provider_degraded",),
        target_problem_type="live_provider_failed",
        preconditions=("provider_error_confirmed",),
        actions=(
            RepairAction("refresh_runtime_state", "Пересобрать live/world-state health", action_kind="internal"),
            RepairAction("run_smoke_check", "Прогнать smoke-check", action_kind="command", command=("python3", "tools/smoke_check.py"), timeout_seconds=120),
        ),
        expected_effect="Live provider degradation должна быть либо подтверждена, либо перейти в healthy/insufficient contract.",
        timeout_seconds=180,
        retry_policy="single_retry",
        risk_level="medium",
        autonomy_level=AUTONOMY_SAFE_AUTO,
    ),
    RepairPlaybook(
        playbook_id="audit_route_regression",
        title="Audit route regression before repair",
        allowed_actions=("inspect_route_diagnostics", "run_routing_smoke", "patch_router"),
        required_prechecks=("route_signal_confirmed", "owner_permission"),
        verification_steps=(
            VerificationStep("routing_smoke", "Проверить routing smoke-check", verifier_kind="smoke_check"),
            VerificationStep("route_trace", "Убедиться, что целевой prompt идёт по нужному route", verifier_kind="route_health"),
        ),
        rollback_steps=("Откатить router patch и вернуть previous policy.",),
        claim_policy="Нельзя говорить, что route repaired, если route trace после фикса не подтверждён.",
        handles_signals=("route_regression",),
        target_problem_type="route_drift",
        preconditions=("route_signal_confirmed",),
        actions=(
            RepairAction("run_smoke_check", "Прогнать smoke-check", action_kind="command", command=("python3", "tools/smoke_check.py"), timeout_seconds=120),
            RepairAction("run_behavioral_check", "Прогнать behavioral-check", action_kind="command", command=("python3", "tools/behavioral_check.py"), timeout_seconds=120),
        ),
        expected_effect="Route drift должен либо исчезнуть, либо остаться в explicit degraded/manual_followup состоянии.",
        timeout_seconds=240,
        retry_policy="single_retry",
        risk_level="medium",
        autonomy_level=AUTONOMY_AUTO_WITH_VERIFICATION,
    ),
    RepairPlaybook(
        playbook_id="refresh_runtime_state",
        title="Refresh runtime and world-state health",
        allowed_actions=("refresh_world_state", "refresh_heartbeat", "collect_health_snapshot"),
        required_prechecks=("runtime_process_alive",),
        verification_steps=(
            VerificationStep("world_state_fresh", "Проверить, что world-state обновился и stale markers ушли", verifier_kind="world_state_fresh"),
            VerificationStep("heartbeat_fresh", "Проверить, что heartbeat существует и свежий", verifier_kind="heartbeat_fresh"),
        ),
        rollback_steps=("Rollback не нужен: действие только обновляет runtime-state.",),
        claim_policy="Можно говорить только о refresh/revalidation, а не об исправлении кода.",
        handles_signals=("heartbeat_stale", "severe_runtime_errors"),
        target_problem_type="runtime_degraded",
        preconditions=("runtime_process_alive",),
        actions=(
            RepairAction("refresh_runtime_state", "Обновить world-state и drive pressures", action_kind="internal"),
            RepairAction("reinitialize_heartbeat", "Принудительно обновить heartbeat artifact", action_kind="internal"),
        ),
        expected_effect="Runtime health snapshot и heartbeat должны стать актуальными.",
        timeout_seconds=30,
        retry_policy="single_retry",
        risk_level="low",
        autonomy_level=AUTONOMY_SAFE_AUTO,
    ),
    RepairPlaybook(
        playbook_id="recheck_health",
        title="Re-run bounded health verification",
        allowed_actions=("run_smoke_checks", "run_behavioral_checks", "refresh_world_state"),
        required_prechecks=("project_runtime_access",),
        verification_steps=(
            VerificationStep("smoke_checks", "Прогнать smoke-check", verifier_kind="smoke_check"),
            VerificationStep("behavioral_checks", "Прогнать behavioral-check", verifier_kind="behavioral_check"),
        ),
        rollback_steps=("Rollback не нужен: это проверка и refresh без destructive changes.",),
        claim_policy="Можно говорить только о прохождении health checks, а не о repaired без before/after verification.",
        handles_signals=("route_regression", "live_provider_degraded", "severe_runtime_errors"),
        target_problem_type="failing_health_checks",
        preconditions=("project_runtime_access",),
        actions=(
            RepairAction("run_smoke_check", "Прогнать smoke-check", action_kind="command", command=("python3", "tools/smoke_check.py"), timeout_seconds=120),
            RepairAction("run_behavioral_check", "Прогнать behavioral-check", action_kind="command", command=("python3", "tools/behavioral_check.py"), timeout_seconds=120),
            RepairAction("refresh_runtime_state", "Пересобрать world-state после проверок", action_kind="internal"),
        ),
        expected_effect="Health checks должны дать честный before/after verdict по системе.",
        timeout_seconds=240,
        retry_policy="no_retry",
        risk_level="low",
        autonomy_level=AUTONOMY_AUTO_WITH_VERIFICATION,
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


def select_playbooks_for_classifications(classifications: Iterable[FailureClassification]) -> List[RepairPlaybook]:
    selected: List[RepairPlaybook] = []
    seen = set()
    targets = {(item.problem_type, item.suggested_playbook) for item in classifications}
    for playbook in REPAIR_PLAYBOOKS:
        for problem_type, suggested_playbook in targets:
            if playbook.target_problem_type == problem_type or (suggested_playbook and playbook.playbook_id == suggested_playbook):
                if playbook.playbook_id not in seen:
                    selected.append(playbook)
                    seen.add(playbook.playbook_id)
                break
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
        lines.append(f"  autonomy={item.autonomy_level}; risk={item.risk_level}")
        lines.append(f"  claim_policy={item.claim_policy}")
    return "\n".join(lines)
