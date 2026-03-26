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
    AdminCommandSpec("/ownerreport", "/ownerreport", "owner_private", "runtime_audit", "runtime_probe+world_state", "Подробный отчёт по состоянию среды, памяти, world-state и route diagnostics."),
    AdminCommandSpec("/qualityreport", "/qualityreport", "owner_private", "diagnostics", "request_diagnostics+world_state", "Агрегированная сводка по verified/inferred/insufficient и деградациям."),
    AdminCommandSpec("/selfhealstatus", "/selfhealstatus", "owner_private", "diagnostics", "self_heal_incidents", "Статус автоматики восстановления, последние инциденты и их состояния."),
    AdminCommandSpec("/selfhealrun", "/selfhealrun <playbook|incident_id> [dry-run|execute]", "owner_private", "diagnostics", "self_heal_policy+playbooks", "Dry-run или ограниченный запуск playbook по правилам безопасности."),
    AdminCommandSpec("/selfhealapprove", "/selfhealapprove <incident_id>", "owner_private", "diagnostics", "self_heal_incidents+policy", "Одобрение отложенного инцидента, который ждёт решения владельца."),
    AdminCommandSpec("/selfhealdeny", "/selfhealdeny <incident_id>", "owner_private", "diagnostics", "self_heal_incidents+policy", "Отклонение авто-ремонта и перевод кейса в ручное сопровождение."),
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
        ("runtime_audit", "Среда и runtime"),
        ("diagnostics", "Диагностика и автовосстановление"),
        ("route_audit", "Маршрутизация"),
        ("memory_audit", "Память и контекст"),
        ("moderation_audit", "Модерация"),
    )
    lines = [
        "JARVIS • РЕЕСТР OWNER/ADMIN КОМАНД",
        "",
        "Ниже команды, сгруппированные по рабочим доменам.",
        "Это не просто help-текст, а реестр owner/admin surface с привязкой к источникам данных.",
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
            lines.append(f"  доступ={spec.scope}; источник={spec.evidence}; зачем={spec.description}")
        lines.append("")
    access_specs = [spec for spec in ADMIN_COMMAND_SPECS if spec.scope == "access"]
    if access_specs:
        lines.append("Команды общего доступа:")
        for spec in access_specs:
            lines.append(f"- {spec.usage}")
            lines.append(f"  домен={spec.domain}; источник={spec.evidence}; зачем={spec.description}")
        lines.append("")
    lines.append("Правила работы:")
    lines.append("- owner_only и owner_private команды нельзя выполнять без прав владельца.")
    lines.append("- каждый admin/output должен опираться на свой источник данных, а не на свободный chat reply.")
    return "\n".join(lines)
