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
    AdminCommandSpec("/restart", "/restart", "owner_private", "runtime_audit", "supervisor", "Показывает, что self-restart отключён; реальный перезапуск выполняется только внешним supervisor."),
    AdminCommandSpec("/ownerreport", "/ownerreport", "owner_private", "runtime_audit", "runtime_probe+world_state", "Подробный отчёт по состоянию среды, памяти, world-state и route diagnostics."),
    AdminCommandSpec("/resources", "/resources", "owner_private", "runtime_audit", "local_probe", "RAM/CPU/runtime ресурсы."),
    AdminCommandSpec("/topproc", "/topproc", "owner_private", "runtime_audit", "local_probe", "Топ процессов."),
    AdminCommandSpec("/disk", "/disk", "owner_private", "runtime_audit", "local_probe", "Сводка по дискам."),
    AdminCommandSpec("/net", "/net", "owner_private", "runtime_audit", "local_probe", "Сводка по сети."),
    AdminCommandSpec("/gitstatus", "/gitstatus", "owner_private", "runtime_audit", "git_state", "Сводка git-дерева."),
    AdminCommandSpec("/gitlast", "/gitlast [количество]", "owner_private", "runtime_audit", "git_history", "Последние коммиты."),
    AdminCommandSpec("/upgrade", "/upgrade <что изменить>", "owner_private", "runtime_audit", "workspace+codex", "Workspace-изменения через Enterprise."),
    AdminCommandSpec("/sdls", "/sdls [/sdcard/путь]", "owner_private", "runtime_audit", "filesystem", "Список файлов на sdcard."),
    AdminCommandSpec("/sdsend", "/sdsend /sdcard/путь/к/файлу", "owner_private", "runtime_audit", "filesystem", "Отправка файла из sdcard."),
    AdminCommandSpec("/sdsave", "/sdsave /sdcard/папка/или/файл", "owner_private", "runtime_audit", "filesystem", "Сохранение медиа на sdcard."),
    AdminCommandSpec("/qualityreport", "/qualityreport", "owner_private", "diagnostics", "request_diagnostics+world_state", "Агрегированная сводка по verified/inferred/insufficient и деградациям."),
    AdminCommandSpec("/selfhealstatus", "/selfhealstatus", "owner_private", "diagnostics", "self_heal_incidents", "Статус автоматики восстановления, последние инциденты и их состояния."),
    AdminCommandSpec("/selfhealrun", "/selfhealrun <playbook|incident_id> [dry-run|execute]", "owner_private", "diagnostics", "self_heal_policy+playbooks", "Dry-run или ограниченный запуск playbook по правилам безопасности."),
    AdminCommandSpec("/selfhealapprove", "/selfhealapprove <incident_id>", "owner_private", "diagnostics", "self_heal_incidents+policy", "Одобрение отложенного инцидента, который ждёт решения владельца."),
    AdminCommandSpec("/selfhealdeny", "/selfhealdeny <incident_id>", "owner_private", "diagnostics", "self_heal_incidents+policy", "Отклонение авто-ремонта и перевод кейса в ручное сопровождение."),
    AdminCommandSpec("/ownerautofix", "/ownerautofix on|off|status", "owner_only", "diagnostics", "meta_state", "Управление owner autofix."),
    AdminCommandSpec("/errors", "/errors [количество]", "owner_private", "diagnostics", "runtime_log", "Последние реальные ошибки из логов."),
    AdminCommandSpec("/events", "/events [restart|access|system|all] [количество]", "owner_private", "diagnostics", "runtime_log", "Последние operational-события."),
    AdminCommandSpec("/routes", "/routes [количество]", "owner_private", "route_audit", "request_diagnostics", "Последние route/self-check telemetry записи."),
    AdminCommandSpec("/remember", "/remember <факт>", "owner_only", "memory_audit", "memory_facts", "Записать факт в память текущего чата."),
    AdminCommandSpec("/recall", "/recall [запрос]", "owner_only", "memory_audit", "memory_facts+chat_events", "Поднять релевантные факты и события."),
    AdminCommandSpec("/memorychat", "/memorychat [запрос]", "owner_only", "memory_audit", "chat_memory", "Инспекция chat memory."),
    AdminCommandSpec("/memoryuser", "/memoryuser [@username|user_id]", "owner_only", "memory_audit", "user_memory", "Инспекция user memory."),
    AdminCommandSpec("/memorysummary", "/memorysummary", "owner_only", "memory_audit", "summary_memory", "Инспекция summary memory."),
    AdminCommandSpec("/chatdeep", "/chatdeep [chat_id]", "owner_only", "memory_audit", "chat_memory+summary_snapshots", "Глубокий профиль группы с памятью, summary и recent highlights."),
    AdminCommandSpec("/whois", "/whois [@username|user_id]", "owner_only", "memory_audit", "user_memory+relation_memory+chat_events", "Портрет участника с памятью и следами по чатам."),
    AdminCommandSpec("/profilecheck", "/profilecheck [@username|user_id]", "owner_only", "memory_audit", "participant_profiles+participant_visual_signals", "Расширенная проверка профиля: поведение, visual memory и повторы медиа."),
    AdminCommandSpec("/watchlist", "/watchlist [chat_id]", "owner_only", "memory_audit", "participant_chat_profiles+participant_observations", "Проблемные и рисковые участники по группе."),
    AdminCommandSpec("/reliable", "/reliable [chat_id]", "owner_only", "memory_audit", "participant_chat_profiles", "Надёжные и полезные участники по группе."),
    AdminCommandSpec("/suspects", "/suspects [chat_id]", "owner_only", "memory_audit", "participant_chat_profiles+participant_visual_signals", "Подозрительные bot/scam/bait аккаунты и визуальные сигналы по группе."),
    AdminCommandSpec("/achaudit", "/achaudit [количество]", "owner_only", "memory_audit", "score_events+achievement_catalog", "Последние выдачи ачивок: кто, где, когда и что именно открыл."),
    AdminCommandSpec("/whatshappening", "/whatshappening [chat_id]", "owner_only", "memory_audit", "chat_events+summary_snapshots", "Обзор по активным чатам за 24 часа или deep-view по одной группе."),
    AdminCommandSpec("/summary24h", "/summary24h [chat_id]", "owner_only", "memory_audit", "chat_events", "Быстрый digest группы за последние 24 часа."),
    AdminCommandSpec("/conflicts", "/conflicts [chat_id]", "owner_only", "memory_audit", "chat_events+reply_links", "Конфликтные сигналы, грубые реплики и напряжённые reply-пары."),
    AdminCommandSpec("/ownergraph", "/ownergraph", "owner_only", "memory_audit", "owner_cross_chat_memory", "Cross-chat social graph владельца: активные чаты и пересечения по людям."),
    AdminCommandSpec("/selfstate", "/selfstate", "owner_only", "memory_audit", "self_model", "Текущее self-model состояние."),
    AdminCommandSpec("/worldstate", "/worldstate", "owner_only", "memory_audit", "world_state", "Инспекция world-state registry."),
    AdminCommandSpec("/drives", "/drives", "owner_only", "memory_audit", "drive_scores", "Текущее состояние drive pressures."),
    AdminCommandSpec("/autobio", "/autobio [запрос]", "owner_only", "memory_audit", "autobiographical_memory", "Инспекция autobiographical memory."),
    AdminCommandSpec("/skills", "/skills [запрос]", "owner_only", "memory_audit", "skill_memory", "Инспекция skill memory."),
    AdminCommandSpec("/reflections", "/reflections [количество]", "owner_only", "memory_audit", "reflection_loop", "Последние reflections."),
    AdminCommandSpec("/chatdigest", "/chatdigest <chat_id> [YYYY-MM-DD]", "owner_private", "memory_audit", "chat_events", "Digest по выбранному чату."),
    AdminCommandSpec("/portrait", "/portrait [@username]", "owner_only", "memory_audit", "chat_events+codex", "AI-портрет участника по сообщениям текущего чата."),
    AdminCommandSpec("/export", "/export [chat|today|@username|user_id]", "owner_only", "memory_audit", "chat_events", "Выгрузка событий по чату, дню или участнику."),
    AdminCommandSpec("/search", "/search <запрос>", "access", "memory_audit", "chat_events", "Поиск по chat_events."),
    AdminCommandSpec("/who_said", "/who_said <запрос>", "access", "memory_audit", "chat_events", "Поиск авторов по фразе."),
    AdminCommandSpec("/history", "/history [@username|user_id]", "access", "memory_audit", "chat_events", "Timeline участника."),
    AdminCommandSpec("/daily", "/daily [YYYY-MM-DD]", "access", "memory_audit", "chat_events", "Сводка по дню."),
    AdminCommandSpec("/digest", "/digest [YYYY-MM-DD]", "access", "memory_audit", "chat_events", "Digest текущего чата."),
    AdminCommandSpec("/appeals", "/appeals", "owner_only", "moderation_audit", "appeals_db", "Очередь апелляций."),
    AdminCommandSpec("/appeal_review", "/appeal_review <id>", "owner_only", "moderation_audit", "appeals_db", "Перевод апелляции в review."),
    AdminCommandSpec("/appeal_approve", "/appeal_approve <id> [решение]", "owner_only", "moderation_audit", "appeals_db", "Одобрение апелляции."),
    AdminCommandSpec("/appeal_reject", "/appeal_reject <id> [решение]", "owner_only", "moderation_audit", "appeals_db", "Отклонение апелляции."),
    AdminCommandSpec("/ban", "/ban <reply|@username|user_id> [причина]", "owner_only", "moderation_audit", "moderation_actions", "Постоянный бан участника."),
    AdminCommandSpec("/mute", "/mute <reply|@username|user_id> [причина]", "owner_only", "moderation_audit", "moderation_actions", "Выдать mute участнику."),
    AdminCommandSpec("/kick", "/kick <reply|@username|user_id> [причина]", "owner_only", "moderation_audit", "moderation_actions", "Кикнуть участника."),
    AdminCommandSpec("/tban", "/tban <reply|@username|user_id> <время> [причина]", "owner_only", "moderation_audit", "moderation_actions", "Временный бан."),
    AdminCommandSpec("/tmute", "/tmute <reply|@username|user_id> <время> [причина]", "owner_only", "moderation_audit", "moderation_actions", "Временный mute."),
    AdminCommandSpec("/unban", "/unban <reply|@username|user_id>", "owner_only", "moderation_audit", "moderation_actions", "Снять бан."),
    AdminCommandSpec("/unmute", "/unmute <reply|@username|user_id>", "owner_only", "moderation_audit", "moderation_actions", "Снять mute."),
    AdminCommandSpec("/warn", "/warn <reply|@username|user_id> [причина]", "owner_only", "moderation_audit", "warnings", "Выдать предупреждение."),
    AdminCommandSpec("/dwarn", "/dwarn <reply|@username|user_id> [причина]", "owner_only", "moderation_audit", "warnings", "Снять одно предупреждение."),
    AdminCommandSpec("/swarn", "/swarn <reply|@username|user_id> [причина]", "owner_only", "moderation_audit", "warnings", "Выдать сильное предупреждение."),
    AdminCommandSpec("/warns", "/warns <reply|@username|user_id>", "owner_only", "moderation_audit", "warnings", "Показать предупреждения участника."),
    AdminCommandSpec("/warnreasons", "/warnreasons", "owner_only", "moderation_audit", "warnings", "Показать причины предупреждений."),
    AdminCommandSpec("/rmwarn", "/rmwarn <reply|@username|user_id>", "owner_only", "moderation_audit", "warnings", "Удалить предупреждение."),
    AdminCommandSpec("/resetwarn", "/resetwarn <reply|@username|user_id>", "owner_only", "moderation_audit", "warnings", "Сбросить предупреждения участника."),
    AdminCommandSpec("/setwarnlimit", "/setwarnlimit <число>", "owner_only", "moderation_audit", "warn_settings", "Изменить лимит warnings."),
    AdminCommandSpec("/setwarnmode", "/setwarnmode <mute|ban>", "owner_only", "moderation_audit", "warn_settings", "Изменить реакцию на лимит warnings."),
    AdminCommandSpec("/warntime", "/warntime <время>", "owner_only", "moderation_audit", "warn_settings", "Изменить TTL предупреждений."),
    AdminCommandSpec("/modlog", "/modlog", "owner_only", "moderation_audit", "moderation_actions+warnings", "Журнал санкций и warning-решений."),
    AdminCommandSpec("/welcome", "/welcome on|off|status", "owner_only", "moderation_audit", "welcome_settings", "Управление welcome-режимом."),
    AdminCommandSpec("/setwelcome", "/setwelcome <текст>", "owner_only", "moderation_audit", "welcome_settings", "Установить текст welcome."),
    AdminCommandSpec("/resetwelcome", "/resetwelcome", "owner_only", "moderation_audit", "welcome_settings", "Сбросить welcome-текст."),
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
