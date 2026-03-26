from dataclasses import dataclass
from typing import Iterable, Tuple


@dataclass(frozen=True)
class AdminCommandSpec:
    command: str
    usage: str
    scope: str
    domain: str
    evidence: str
    description: str


ADMIN_COMMAND_SPECS: Tuple[AdminCommandSpec, ...] = (
    AdminCommandSpec("/status", "/status", "access", "runtime_audit", "sqlite_snapshot", "Локальный снимок состояния runtime и памяти."),
    AdminCommandSpec("/restart", "/restart", "owner_private", "runtime_audit", "supervisor", "Перезапуск bridge через supervisor."),
    AdminCommandSpec("/ownerreport", "/ownerreport", "owner_private", "runtime_audit", "runtime_probe+world_state", "Подробный operational report."),
    AdminCommandSpec("/qualityreport", "/qualityreport", "owner_private", "diagnostics", "request_diagnostics+world_state", "Агрегированная сводка по verified/inferred/insufficient и деградациям."),
    AdminCommandSpec("/selfhealstatus", "/selfhealstatus", "owner_private", "diagnostics", "self_heal_incidents", "Статус self-healing state machine и последние incidents."),
    AdminCommandSpec("/selfhealrun", "/selfhealrun <playbook|incident_id> [dry-run|execute]", "owner_private", "diagnostics", "self_heal_policy+playbooks", "Dry-run или bounded execute для self-healing playbook."),
    AdminCommandSpec("/errors", "/errors [количество]", "owner_private", "diagnostics", "runtime_log", "Последние реальные ошибки из логов."),
    AdminCommandSpec("/events", "/events [restart|access|system|all] [количество]", "owner_private", "diagnostics", "runtime_log", "Последние operational-события."),
    AdminCommandSpec("/routes", "/routes [количество]", "owner_private", "route_audit", "request_diagnostics", "Последние route/self-check telemetry записи."),
    AdminCommandSpec("/gitstatus", "/gitstatus", "owner_private", "runtime_audit", "git_state", "Сводка git-дерева."),
    AdminCommandSpec("/gitlast", "/gitlast [количество]", "owner_private", "runtime_audit", "git_history", "Последние коммиты."),
    AdminCommandSpec("/resources", "/resources", "owner_private", "runtime_audit", "local_probe", "RAM/CPU/runtime ресурсы."),
    AdminCommandSpec("/topproc", "/topproc", "owner_private", "runtime_audit", "local_probe", "Топ процессов."),
    AdminCommandSpec("/disk", "/disk", "owner_private", "runtime_audit", "local_probe", "Сводка по дискам."),
    AdminCommandSpec("/net", "/net", "owner_private", "runtime_audit", "local_probe", "Сводка по сети."),
    AdminCommandSpec("/memorychat", "/memorychat [запрос]", "owner_only", "memory_audit", "chat_memory", "Инспекция chat memory."),
    AdminCommandSpec("/memoryuser", "/memoryuser [@username|user_id]", "owner_only", "memory_audit", "user_memory", "Инспекция user memory."),
    AdminCommandSpec("/memorysummary", "/memorysummary", "owner_only", "memory_audit", "summary_memory", "Инспекция summary memory."),
    AdminCommandSpec("/selfstate", "/selfstate", "owner_only", "memory_audit", "self_model", "Текущее self-model состояние."),
    AdminCommandSpec("/worldstate", "/worldstate", "owner_only", "memory_audit", "world_state", "Инспекция world-state registry."),
    AdminCommandSpec("/drives", "/drives", "owner_only", "memory_audit", "drive_scores", "Текущее состояние drive pressures."),
    AdminCommandSpec("/autobio", "/autobio [запрос]", "owner_only", "memory_audit", "autobiographical_memory", "Инспекция autobiographical memory."),
    AdminCommandSpec("/skills", "/skills [запрос]", "owner_only", "memory_audit", "skill_memory", "Инспекция skill memory."),
    AdminCommandSpec("/reflections", "/reflections [количество]", "owner_only", "memory_audit", "reflection_loop", "Последние reflections."),
    AdminCommandSpec("/chatdigest", "/chatdigest <chat_id> [YYYY-MM-DD]", "owner_private", "memory_audit", "chat_events", "Digest по выбранному чату."),
    AdminCommandSpec("/search", "/search <запрос>", "access", "memory_audit", "chat_events", "Поиск по chat_events."),
    AdminCommandSpec("/who_said", "/who_said <запрос>", "access", "memory_audit", "chat_events", "Поиск авторов по фразе."),
    AdminCommandSpec("/history", "/history [@username|user_id]", "access", "memory_audit", "chat_events", "Timeline участника."),
    AdminCommandSpec("/daily", "/daily [YYYY-MM-DD]", "access", "memory_audit", "chat_events", "Сводка по дню."),
    AdminCommandSpec("/digest", "/digest [YYYY-MM-DD]", "access", "memory_audit", "chat_events", "Digest текущего чата."),
    AdminCommandSpec("/sdls", "/sdls [/sdcard/путь]", "owner_private", "runtime_audit", "filesystem", "Список файлов на sdcard."),
    AdminCommandSpec("/sdsend", "/sdsend /sdcard/путь/к/файлу", "owner_private", "runtime_audit", "filesystem", "Отправка файла из sdcard."),
    AdminCommandSpec("/sdsave", "/sdsave /sdcard/папка/или/файл", "owner_private", "runtime_audit", "filesystem", "Сохранение медиа на sdcard."),
    AdminCommandSpec("/upgrade", "/upgrade <что изменить>", "owner_private", "runtime_audit", "workspace+codex", "Workspace-изменения через Enterprise."),
    AdminCommandSpec("/ownerautofix", "/ownerautofix on|off|status", "owner_only", "diagnostics", "meta_state", "Управление owner autofix."),
    AdminCommandSpec("/appeals", "/appeals", "owner_only", "moderation_audit", "appeals_db", "Очередь апелляций."),
    AdminCommandSpec("/appeal_review", "/appeal_review <id>", "owner_only", "moderation_audit", "appeals_db", "Перевод апелляции в review."),
    AdminCommandSpec("/appeal_approve", "/appeal_approve <id> [решение]", "owner_only", "moderation_audit", "appeals_db", "Одобрение апелляции."),
    AdminCommandSpec("/appeal_reject", "/appeal_reject <id> [решение]", "owner_only", "moderation_audit", "appeals_db", "Отклонение апелляции."),
)


def iter_admin_commands() -> Tuple[AdminCommandSpec, ...]:
    return ADMIN_COMMAND_SPECS


def render_admin_command_catalog(*, owner_user_id: int, owner_username: str) -> str:
    sections = (
        ("runtime_audit", "Runtime audit"),
        ("diagnostics", "Diagnostics"),
        ("route_audit", "Route audit"),
        ("memory_audit", "Memory audit"),
        ("moderation_audit", "Moderation audit"),
    )
    lines = [
        "JARVIS • OWNER/ADMIN COMMAND REGISTRY",
        "",
        "Ниже команды, сгруппированные по operational-доменам.",
        "Это registry для owner/admin surface, а не просто плоский help-текст.",
        f"Owner: {owner_username} ({owner_user_id})",
        "",
    ]
    for domain_key, domain_label in sections:
        domain_specs = [spec for spec in ADMIN_COMMAND_SPECS if spec.domain == domain_key]
        if not domain_specs:
            continue
        lines.append(f"{domain_label}:")
        for spec in domain_specs:
            lines.append(f"- {spec.usage}")
            lines.append(f"  scope={spec.scope}; evidence={spec.evidence}; note={spec.description}")
        lines.append("")
    access_specs = [spec for spec in ADMIN_COMMAND_SPECS if spec.scope == "access"]
    if access_specs:
        lines.append("Shared access commands:")
        for spec in access_specs:
            lines.append(f"- {spec.usage}")
            lines.append(f"  domain={spec.domain}; evidence={spec.evidence}; note={spec.description}")
        lines.append("")
    lines.append("Правило:")
    lines.append("- owner_only и owner_private команды не должны выполняться без owner permission.")
    lines.append("- каждый admin/output должен опираться на свой evidence-domain, а не на свободный chat reply.")
    return "\n".join(lines)
