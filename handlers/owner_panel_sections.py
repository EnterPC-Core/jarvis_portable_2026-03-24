import time
from datetime import datetime
from zoneinfo import ZoneInfo

from services.admin_registry import iter_admin_commands
from services.diagnostics_metrics import collect_diagnostics_metrics, render_diagnostics_metrics


def build_owner_commands_panel(renderer: "ControlPanelRenderer", payload: str):
    domain_labels = {
        "runtime_audit": "Среда и рантайм",
        "diagnostics": "Диагностика",
        "route_audit": "Маршрутизация",
        "memory_audit": "Память и контекст",
        "moderation_audit": "Модерация",
        "access": "Общий доступ",
    }
    specs = list(iter_admin_commands())
    if payload:
        if payload == "access":
            selected = [spec for spec in specs if spec.scope == "access"]
            title = domain_labels["access"]
        else:
            selected = [spec for spec in specs if spec.domain == payload]
            title = domain_labels.get(payload, payload)
        lines = [
            f"JARVIS • КОМАНДЫ: {title.upper()}",
            "",
        ]
        if not selected:
            lines.append("Команды для этого раздела не найдены.")
        else:
            for spec in selected:
                lines.append(f"- {spec.usage}")
                lines.append(f"  доступ={spec.scope}; источник={spec.evidence}; зачем={spec.description}")
        lines.extend([
            "",
            "Правила:",
            "- owner_only и owner_private команды нельзя выполнять без прав владельца.",
            "- каждый admin/output должен опираться на свой источник данных.",
        ])
        text = "\n".join(lines)
    else:
        counts = {
            "runtime_audit": len([spec for spec in specs if spec.domain == "runtime_audit"]),
            "diagnostics": len([spec for spec in specs if spec.domain == "diagnostics"]),
            "route_audit": len([spec for spec in specs if spec.domain == "route_audit"]),
            "memory_audit": len([spec for spec in specs if spec.domain == "memory_audit"]),
            "moderation_audit": len([spec for spec in specs if spec.domain == "moderation_audit"]),
            "access": len([spec for spec in specs if spec.scope == "access"]),
        }
        text = (
            "JARVIS • СПРАВОЧНИК OWNER/ADMIN КОМАНД\n\n"
            "Короткая навигация по категориям. Полные списки открываются отдельными кнопками.\n\n"
            f"• Среда и рантайм: {counts['runtime_audit']}\n"
            f"• Диагностика и автовосстановление: {counts['diagnostics']}\n"
            f"• Маршрутизация: {counts['route_audit']}\n"
            f"• Память и контекст: {counts['memory_audit']}\n"
            f"• Модерация: {counts['moderation_audit']}\n"
            f"• Общий доступ: {counts['access']}\n\n"
            "Если нужен совсем полный плоский текст, остаются /help и /commands."
        )
    markup = {
        "inline_keyboard": [
            [
                {"text": "Среда и рантайм", "callback_data": "ui:panel:owner_commands:runtime_audit"},
                {"text": "Диагностика", "callback_data": "ui:panel:owner_commands:diagnostics"},
            ],
            [
                {"text": "Маршрутизация", "callback_data": "ui:panel:owner_commands:route_audit"},
                {"text": "Память", "callback_data": "ui:panel:owner_commands:memory_audit"},
            ],
            [
                {"text": "Модерация", "callback_data": "ui:panel:owner_commands:moderation_audit"},
                {"text": "Общий доступ", "callback_data": "ui:panel:owner_commands:access"},
            ],
            [
                {"text": "К сводке", "callback_data": "ui:panel:owner_commands"},
                {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"},
            ],
            [{"text": "Главная", "callback_data": "ui:home"}],
        ]
    }
    return text, markup


def build_owner_runtime_summary(
    renderer: "ControlPanelRenderer",
    bridge: "TelegramBridge",
    *,
    collect_diagnostics_metrics_func=collect_diagnostics_metrics,
):
    operational_state = bridge.refresh_world_state_registry("owner_runtime_panel", chat_id=renderer.owner_user_id)
    drive_scores = bridge.recompute_drive_scores(operational_state)
    diagnostics_metrics = collect_diagnostics_metrics_func(bridge.state, window_seconds=86400)
    owner_autofix_enabled = bridge.owner_autofix_enabled()
    owner_autofix_status = "включено" if owner_autofix_enabled else "выключено"
    runtime_snapshot = bridge.inspect_runtime_log()
    heartbeat_age_text = "n/a"
    if bridge.heartbeat_path.exists():
        try:
            heartbeat_age_text = f"{max(0, int(time.time() - bridge.heartbeat_path.stat().st_mtime))}s"
        except OSError:
            heartbeat_age_text = "n/a"
    last_backup_raw = bridge.state.get_meta("last_backup_ts", "0")
    try:
        last_backup_value = float(last_backup_raw or "0")
    except ValueError:
        last_backup_value = 0.0
    if last_backup_value > 0:
        backup_line = datetime.fromtimestamp(last_backup_value, tz=ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S %Z")
    else:
        backup_line = "ещё не было"
    text = (
        "JARVIS • СРЕДА И RUNTIME\n\n"
        "Это короткий экран состояния. Ниже можно открыть подробные разделы по кнопкам.\n\n"
        "Что смотреть в первую очередь:\n"
        "• свеж ли heartbeat\n"
        "• чиста ли текущая сессия после запуска\n"
        "• что осталось в хвосте за 24 часа\n\n"
        f"• Время: {datetime.now(ZoneInfo('Europe/Moscow')).strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"• Автофикс владельца: {owner_autofix_status}\n"
        f"• Пинг Telegram API: {bridge.get_telegram_ping_text()}\n"
        f"• Heartbeat: {heartbeat_age_text}\n"
        f"• Последний backup: {backup_line}\n"
        "\n"
        "Текущая сессия:\n"
        f"• Серьёзные ошибки после запуска: {int(runtime_snapshot.get('session_severe_error_count', 0))}\n"
        f"• Предупреждения после запуска: {int(runtime_snapshot.get('session_warning_count', 0))}\n"
        f"• Риск рантайма: {drive_scores.get('runtime_risk_pressure', 0.0):.1f}\n"
        "\n"
        "Хвост за 24 часа:\n"
        f"• Перезапуски: {int(runtime_snapshot.get('restart_count', 0))}\n"
        f"• Серьёзные ошибки: {int(operational_state.get('window_errors_count', 0))}\n"
        f"• Предупреждения: {int(operational_state.get('window_warning_count', 0))}\n"
        f"• Уровень неопределённости: {drive_scores.get('uncertainty_pressure', 0.0):.1f}\n"
        f"• Деградировавшие маршруты: {diagnostics_metrics.degraded_count}\n"
        "\n"
        "Рабочее дерево:\n"
        f"• Грязных файлов в Git: {int(operational_state.get('git_dirty_count', 0))}"
    )
    markup = {
        "inline_keyboard": [
            [
                {"text": "Рантайм", "callback_data": "ui:panel:owner_runtime:runtime"},
                {"text": "Логи", "callback_data": "ui:panel:owner_git:logs"},
            ],
            [
                {"text": "Состояние мира", "callback_data": "ui:panel:owner_runtime:world"},
                {"text": "Давления системы", "callback_data": "ui:panel:owner_runtime:drives"},
            ],
            [
                {"text": "Качество ответов", "callback_data": "ui:panel:owner_runtime:quality"},
                {"text": "Состояние Git", "callback_data": "ui:panel:owner_git:state"},
            ],
            [{"text": "Автовосстановление", "callback_data": "ui:panel:owner_selfheal"}],
            [
                {"text": f"Автофикс: {'ВКЛ' if owner_autofix_enabled else 'ВЫКЛ'}", "callback_data": "ui:ownerautofix:status"},
                {"text": "Переключить", "callback_data": "ui:ownerautofix:toggle"},
            ],
            [{"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
        ]
    }
    return text, markup


def build_owner_runtime_detail(
    renderer: "ControlPanelRenderer",
    bridge: "TelegramBridge",
    payload: str,
    *,
    collect_diagnostics_metrics_func=collect_diagnostics_metrics,
    render_diagnostics_metrics_func=render_diagnostics_metrics,
):
    operational_state = bridge.refresh_world_state_registry("owner_runtime_panel", chat_id=renderer.owner_user_id)
    bridge.recompute_drive_scores(operational_state)
    diagnostics_metrics = collect_diagnostics_metrics_func(bridge.state, window_seconds=86400)
    runtime_snapshot = bridge.inspect_runtime_log()
    if payload == "runtime":
        text = (
            "JARVIS • РАНТАЙМ\n\n"
            "Здесь собраны живость процесса, ресурсы и последний технический срез по bridge.\n\n"
            f"{bridge.render_resource_summary()}\n\n"
            f"{bridge.render_bridge_runtime_watch()}"
        )
    elif payload == "world":
        snapshots = bridge.state.get_recent_world_state_snapshots(limit=5)
        lines = [
            "JARVIS • СОСТОЯНИЕ МИРА",
            "",
            "Это актуальные служебные записи о состоянии рантайма, проекта, live-источников и диагностики.",
            "",
            bridge.state.get_world_state_context(limit=10) or "Состояние мира пока пусто.",
        ]
        if snapshots:
            lines.extend(["", "Последние snapshots:"])
            for row in snapshots:
                stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
                lines.append(f"- [{stamp}] {row['source'] or '-'}: {renderer.truncate_text(row['summary'] or '', 180)}")
        text = "\n".join(lines)
    elif payload == "drives":
        text = (
            "JARVIS • ДАВЛЕНИЯ СИСТЕМЫ\n\n"
            "Это внутренние pressure-сигналы приоритизации: где система видит накопленный риск или долг.\n\n"
            + (bridge.state.get_drive_context() or "Давления системы пока не рассчитаны.")
        )
    elif payload == "quality":
        recent_routes = bridge.state.get_recent_request_diagnostics(limit=6)
        lines = [
            "JARVIS • КАЧЕСТВО ОТВЕТОВ",
            "",
            "Здесь видно, насколько ответы были verified / inferred / insufficient и где роутинг деградировал.",
            "",
            render_diagnostics_metrics_func(diagnostics_metrics),
        ]
        if recent_routes:
            lines.extend(["", "Последние route decisions:", bridge.render_route_diagnostics_rows(recent_routes)])
        text = "\n".join(lines)
    else:
        return build_owner_runtime_summary(
            renderer,
            bridge,
            collect_diagnostics_metrics_func=collect_diagnostics_metrics_func,
        )
    markup = {
        "inline_keyboard": [
            [
                {"text": "Рантайм", "callback_data": "ui:panel:owner_runtime:runtime"},
                {"text": "Логи", "callback_data": "ui:panel:owner_git:logs"},
            ],
            [
                {"text": "Состояние мира", "callback_data": "ui:panel:owner_runtime:world"},
                {"text": "Давления системы", "callback_data": "ui:panel:owner_runtime:drives"},
            ],
            [
                {"text": "Качество ответов", "callback_data": "ui:panel:owner_runtime:quality"},
                {"text": "Состояние Git", "callback_data": "ui:panel:owner_git:state"},
            ],
            [{"text": "Автовосстановление", "callback_data": "ui:panel:owner_selfheal"}],
            [{"text": "К сводке", "callback_data": "ui:panel:owner_runtime"}, {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}],
        ]
    }
    return text, markup


def build_owner_git_panel(renderer: "ControlPanelRenderer", bridge: "TelegramBridge", payload: str):
    if payload == "state":
        text = (
            "JARVIS • СОСТОЯНИЕ GIT\n\n"
            "Здесь видно, чисто ли дерево, какие файлы изменены и какие были последние коммиты.\n\n"
            f"{renderer.render_git_status_summary(bridge.script_path.parent)}\n\n"
            f"{renderer.render_git_last_commits(bridge.script_path.parent, limit=5)}"
        )
    elif payload == "logs":
        runtime_snapshot = bridge.inspect_runtime_log()
        recent_errors = [renderer.truncate_text(str(item), 220) for item in runtime_snapshot.get("recent_session_error_lines", [])[-8:]]
        if not recent_errors:
            recent_errors = [renderer.truncate_text(str(item), 220) for item in runtime_snapshot.get("recent_error_lines", [])[-8:]]
        bridge_tail = bridge.read_recent_operational_highlights(limit=8, category="all")
        lines = [
            "JARVIS • ЛОГИ",
            "",
            "Этот экран нужен, если бот тупит, молчит или вёл себя странно. Сначала смотри последние ошибки.",
            "",
            "Последние ошибки:",
        ]
        if recent_errors:
            lines.extend(f"- {item}" for item in recent_errors)
        else:
            lines.append("- Явных ошибок в хвосте лога не найдено.")
        recent_warnings = [renderer.truncate_text(str(item), 220) for item in runtime_snapshot.get("recent_session_warning_lines", [])[-5:]]
        if not recent_warnings:
            recent_warnings = [renderer.truncate_text(str(item), 220) for item in runtime_snapshot.get("recent_warning_lines", [])[-5:]]
        if recent_warnings:
            lines.extend(["", "Последние восстанавливаемые предупреждения:"])
            lines.extend(f"- {item}" for item in recent_warnings)
        if bridge_tail:
            lines.extend(["", "Операционный хвост логов:"])
            lines.extend(f"- {item}" for item in bridge_tail[-6:])
        text = "\n".join(lines)
    else:
        operational_state = bridge.refresh_world_state_registry("owner_git_panel", chat_id=renderer.owner_user_id)
        runtime_snapshot = bridge.inspect_runtime_log()
        text = (
            "JARVIS • GIT И ЛОГИ\n\n"
            "Короткая сводка. Ниже можно открыть состояние Git и сами логи отдельно.\n\n"
            "Текущая сессия:\n"
            f"• Серьёзные ошибки: {int(runtime_snapshot.get('session_severe_error_count', 0))}\n"
            f"• Предупреждения: {int(runtime_snapshot.get('session_warning_count', 0))}\n"
            "\n"
            "Хвост за 24 часа:\n"
            f"• Серьёзные ошибки: {int(operational_state.get('window_errors_count', 0))}\n"
            f"• Предупреждения: {int(operational_state.get('window_warning_count', 0))}\n"
            f"• Codex degraded: {int(runtime_snapshot.get('codex_degraded_count', 0))}\n"
            f"• Жёсткие ошибки Codex: {int(runtime_snapshot.get('codex_error_count', 0))}\n"
            "\n"
            "Git:\n"
            f"• Грязных файлов в Git: {int(operational_state.get('git_dirty_count', 0))}\n"
            "\n"
            "Полезные команды: /gitstatus, /gitlast, /errors, /events, /routes, /upgrade"
        )
    markup = {
        "inline_keyboard": [
            [
                {"text": "Состояние Git", "callback_data": "ui:panel:owner_git:state"},
                {"text": "Логи", "callback_data": "ui:panel:owner_git:logs"},
            ],
            [
                {"text": "Сводка рантайма", "callback_data": "ui:panel:owner_runtime"},
                {"text": "Автовосстановление", "callback_data": "ui:panel:owner_selfheal"},
            ],
            [{"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
        ]
    }
    return text, markup


def build_owner_jarvis_panel(renderer: "ControlPanelRenderer", bridge: "TelegramBridge", payload: str):
    owner_mode = bridge.state.get_mode(renderer.owner_user_id)
    managed_chats = bridge.state.get_managed_group_chat_ids()
    selected = (payload or "overview").strip().lower()
    title = "JARVIS • JARVIS CONTROL"

    if selected == "modes":
        text = (
            f"{title} • РЕЖИМЫ\n\n"
            "Здесь собраны режимы и поведенческие профили Jarvis.\n\n"
            f"• Текущий режим owner-чата: {owner_mode}\n"
            "• Базовый owner-приоритет: включён\n"
            "• Reply-first поведение: включено\n"
            "• Active subject для фото/контекста: включён\n"
            "• Soft moderation: включена как отдельный контур\n\n"
            "Практический смысл:\n"
            "• owner-чат получает максимальный приоритет по вниманию и качеству\n"
            "• reply на фото/сообщение должен считаться главным объектом разговора\n"
            "• короткие продолжения вроде «и что там?» должны наследовать текущий фокус\n"
            "• moderation-режим работает отдельно и не должен ломать обычный диалог\n\n"
            "Если дальше понадобится, сюда можно добавить живое переключение runtime profile и owner-поведения."
        )
    elif selected == "access":
        text = (
            f"{title} • ДОСТУП\n\n"
            "Это текущая модель доступа к Jarvis.\n\n"
            "• Свободный диалог: только создатель\n"
            "• Обычная панель участников: только профиль, рейтинги, достижения, апелляции\n"
            "• Owner-панель: runtime, память, модерация, self-heal, команды, deep-analysis\n"
            f"• Управляемых групп в контуре: {len(managed_chats)}\n"
            "• Публичный UI не должен показывать внутренние инструкции и owner-управление\n\n"
            "Правила:\n"
            "• если давать доступ другим, это нужно делать отдельной access-логикой\n"
            "• owner-настройки не должны утекать в публичную панель\n"
            "• public UI должен оставаться простым и безопасным для обычных участников"
        )
    elif selected == "instructions":
        text = (
            f"{title} • ИНСТРУКЦИИ\n\n"
            "Это рабочие инструкции по тому, как с Jarvis лучше общаться в Telegram.\n\n"
            "Диалог:\n"
            "• вопрос про фото, документ или конкретное сообщение лучше задавать reply на него\n"
            "• короткое продолжение лучше писать сразу после нужного контекста\n"
            "• если важна точность, лучше явно указывать, о каком фото или человеке речь\n\n"
            "Сильные сценарии:\n"
            "• «что на фото?» reply на фото\n"
            "• «а тут что?» reply на другое фото\n"
            "• «и что там?» сразу после предыдущего разбора\n"
            "• «кто это?» reply на сообщение или фото конкретного человека\n\n"
            "Owner-команды:\n"
            "• обзор по группе: /whatshappening, /summary24h, /chatdeep, /conflicts\n"
            "• по человеку: /whois, /portrait, /profilecheck, /history\n"
            "• по техсостоянию: /ownerreport, /qualityreport, /errors, /routes"
        )
    elif selected == "memory":
        text = (
            f"{title} • ПАМЯТЬ\n\n"
            "Память Jarvis сейчас состоит из нескольких слоёв.\n\n"
            "• Chat memory: факты и контекст по текущему чату\n"
            "• User memory: профиль, сигналы и поведение по участнику\n"
            "• Visual memory: анализ фото и сигналов по media message_id\n"
            "• Active subject: текущий объект разговора для reply и коротких продолжений\n"
            "• Summary/history layers: digest, recent events, traces по чату\n\n"
            "Что это даёт:\n"
            "• reply на фото должен поднимать нужное описание из памяти, а не фантазировать\n"
            "• переход между двумя фото должен опираться на новый reply, а не на старый контекст\n"
            "• вопросы про людей и споры можно разбирать по накопленной истории\n\n"
            "Основные owner-инструменты:\n"
            "• /recall, /memorychat, /memoryuser, /memorysummary\n"
            "• /whois, /profilecheck, /history, /portrait\n"
            "• /whatshappening, /chatdeep, /summary24h, /conflicts"
        )
    elif selected == "moderation":
        text = (
            f"{title} • МОДЕРАЦИЯ\n\n"
            "Здесь про то, как Jarvis должен вести себя в спорных ситуациях.\n\n"
            "Текущий контур:\n"
            "• мягкая деэскалация без санкции включена\n"
            "• бот может остудить спор, отделить факты от эмоций и отметить риск дезинформации\n"
            "• warn / mute / ban остаются owner/admin-контуром\n"
            "• публичная панель не должна превращаться в центр модерации\n\n"
            "Что важно держать:\n"
            "• сперва охлаждать и структурировать спор\n"
            "• не фантазировать о фактах без подтверждения\n"
            "• не спамить одинаковыми охлаждающими сообщениями\n"
            "• тяжёлые случаи должны оставаться под owner-контролем"
        )
    else:
        text = (
            f"{title}\n\n"
            "Это owner-only центр управления самим Jarvis в Telegram.\n\n"
            "Текущий контур:\n"
            f"• Режим owner-чата: {owner_mode}\n"
            "• Свободный диалог: только создатель\n"
            f"• Управляемых групп: {len(managed_chats)}\n"
            "• Публичный контур: профиль, рейтинги, достижения, апелляции\n"
            "• Owner-only контур: память, модерация, runtime, self-heal, deep-analysis\n\n"
            "Открой нужный подпункт кнопками ниже:\n"
            "• Режимы\n"
            "• Доступ\n"
            "• Инструкции\n"
            "• Память\n"
            "• Модерация"
        )

    markup = {
        "inline_keyboard": [
            [
                {"text": "Обзор", "callback_data": "ui:panel:owner_jarvis:overview"},
                {"text": "Режимы", "callback_data": "ui:panel:owner_jarvis:modes"},
            ],
            [
                {"text": "Доступ", "callback_data": "ui:panel:owner_jarvis:access"},
                {"text": "Инструкции", "callback_data": "ui:panel:owner_jarvis:instructions"},
            ],
            [
                {"text": "Память", "callback_data": "ui:panel:owner_jarvis:memory"},
                {"text": "Модерация", "callback_data": "ui:panel:owner_jarvis:moderation"},
            ],
            [
                {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"},
                {"text": "Главная", "callback_data": "ui:home"},
            ],
        ]
    }
    return text, markup


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from handlers.control_panel_renderer import ControlPanelRenderer
    from tg_codex_bridge import TelegramBridge
