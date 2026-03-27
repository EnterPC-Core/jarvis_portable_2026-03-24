import time
from datetime import datetime
from typing import Callable, Optional, Tuple
from zoneinfo import ZoneInfo

from services.admin_registry import iter_admin_commands
from services.diagnostics_metrics import collect_diagnostics_metrics, render_diagnostics_metrics


class ControlPanelRenderer:
    def __init__(
        self,
        *,
        owner_user_id: int,
        owner_username: str,
        public_home_text: str,
        commands_list_text: str,
        control_panel_sections: set[str],
        has_chat_access_func: Callable[[set[int], Optional[int]], bool],
        format_duration_seconds_func: Callable[[int], str],
        truncate_text_func: Callable[[str, int], str],
        render_git_status_summary_func: Callable[..., str],
        render_git_last_commits_func: Callable[..., str],
        render_admin_command_catalog_func: Callable[..., str],
    ) -> None:
        self.owner_user_id = owner_user_id
        self.owner_username = owner_username
        self.public_home_text = public_home_text
        self.commands_list_text = commands_list_text
        self.control_panel_sections = control_panel_sections
        self.has_chat_access = has_chat_access_func
        self.format_duration_seconds = format_duration_seconds_func
        self.truncate_text = truncate_text_func
        self.render_git_status_summary = render_git_status_summary_func
        self.render_git_last_commits = render_git_last_commits_func
        self.render_admin_command_catalog = render_admin_command_catalog_func

    def _build_owner_commands_text(self) -> str:
        catalog_text = self.render_admin_command_catalog(
            owner_user_id=self.owner_user_id,
            owner_username=self.owner_username,
        )
        legacy_preview = self.truncate_text(self.commands_list_text.strip(), 1800)
        return (
            f"{catalog_text}\n\n"
            "Legacy-команды, краткий просмотр:\n\n"
            f"{legacy_preview}\n\n"
            "Если нужен полный список без сокращений, используй /help, /commands или открой COMMANDS.md."
        )

    def _build_owner_commands_panel(self, payload: str) -> Tuple[str, dict]:
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

    def _build_owner_runtime_summary(self, bridge: "TelegramBridge") -> Tuple[str, dict]:
        operational_state = bridge.refresh_world_state_registry("owner_runtime_panel", chat_id=self.owner_user_id)
        drive_scores = bridge.recompute_drive_scores(operational_state)
        diagnostics_metrics = collect_diagnostics_metrics(bridge.state, window_seconds=86400)
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
            "• есть ли ошибки за последние 24 часа\n"
            "• не накопился ли риск по рантайму и качеству ответов\n\n"
            f"• Время: {datetime.now(ZoneInfo('Europe/Moscow')).strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"• Автофикс владельца: {owner_autofix_status}\n"
            f"• Пинг Telegram API: {bridge.get_telegram_ping_text()}\n"
            f"• Heartbeat: {heartbeat_age_text}\n"
            f"• Последний backup: {backup_line}\n"
            f"• Перезапуски за 24ч: {int(runtime_snapshot.get('restart_count', 0))}\n"
            f"• Серьёзные ошибки после запуска: {int(runtime_snapshot.get('session_severe_error_count', 0))}\n"
            f"• Предупреждения после запуска: {int(runtime_snapshot.get('session_warning_count', 0))}\n"
            f"• Риск рантайма: {drive_scores.get('runtime_risk_pressure', 0.0):.1f}\n"
            f"• Уровень неопределённости: {drive_scores.get('uncertainty_pressure', 0.0):.1f}\n"
            f"• Деградировавшие маршруты: {diagnostics_metrics.degraded_count}\n"
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

    def _build_owner_runtime_detail(self, bridge: "TelegramBridge", payload: str) -> Tuple[str, dict]:
        operational_state = bridge.refresh_world_state_registry("owner_runtime_panel", chat_id=self.owner_user_id)
        bridge.recompute_drive_scores(operational_state)
        diagnostics_metrics = collect_diagnostics_metrics(bridge.state, window_seconds=86400)
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
                    lines.append(f"- [{stamp}] {row['source'] or '-'}: {self.truncate_text(row['summary'] or '', 180)}")
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
                render_diagnostics_metrics(diagnostics_metrics),
            ]
            if recent_routes:
                lines.extend(["", "Последние route decisions:", bridge.render_route_diagnostics_rows(recent_routes)])
            text = "\n".join(lines)
        else:
            return self._build_owner_runtime_summary(bridge)
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

    def _build_owner_git_panel(self, bridge: "TelegramBridge", payload: str) -> Tuple[str, dict]:
        if payload == "state":
            text = (
                "JARVIS • СОСТОЯНИЕ GIT\n\n"
                "Здесь видно, чисто ли дерево, какие файлы изменены и какие были последние коммиты.\n\n"
                f"{self.render_git_status_summary(bridge.script_path.parent)}\n\n"
                f"{self.render_git_last_commits(bridge.script_path.parent, limit=5)}"
            )
        elif payload == "logs":
            runtime_snapshot = bridge.inspect_runtime_log()
            recent_errors = [self.truncate_text(str(item), 220) for item in runtime_snapshot.get("recent_session_error_lines", [])[-8:]]
            if not recent_errors:
                recent_errors = [self.truncate_text(str(item), 220) for item in runtime_snapshot.get("recent_error_lines", [])[-8:]]
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
            recent_warnings = [self.truncate_text(str(item), 220) for item in runtime_snapshot.get("recent_session_warning_lines", [])[-5:]]
            if not recent_warnings:
                recent_warnings = [self.truncate_text(str(item), 220) for item in runtime_snapshot.get("recent_warning_lines", [])[-5:]]
            if recent_warnings:
                lines.extend(["", "Последние восстанавливаемые предупреждения:"])
                lines.extend(f"- {item}" for item in recent_warnings)
            if bridge_tail:
                lines.extend(["", "Операционный хвост логов:"])
                lines.extend(f"- {item}" for item in bridge_tail[-6:])
            text = "\n".join(lines)
        else:
            operational_state = bridge.refresh_world_state_registry("owner_git_panel", chat_id=self.owner_user_id)
            runtime_snapshot = bridge.inspect_runtime_log()
            text = (
                "JARVIS • GIT И ЛОГИ\n\n"
                "Короткая сводка. Ниже можно открыть состояние Git и сами логи отдельно.\n\n"
                f"• Грязных файлов в Git: {int(operational_state.get('git_dirty_count', 0))}\n"
                f"• Серьёзные ошибки после запуска: {int(runtime_snapshot.get('session_severe_error_count', 0))}\n"
                f"• Предупреждения после запуска: {int(runtime_snapshot.get('session_warning_count', 0))}\n"
                f"• Codex degraded: {int(runtime_snapshot.get('codex_degraded_count', 0))}\n"
                f"• Жёсткие ошибки Codex: {int(runtime_snapshot.get('codex_error_count', 0))}\n\n"
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

    def build_public_control_panel(self, bridge: "TelegramBridge", user_id: int, section: str, payload: str = "") -> Tuple[str, dict]:
        if section == "profile":
            return (
                bridge.legacy.render_rating(user_id),
                {
                    "inline_keyboard": [
                        [{"text": "Обновить рейтинг", "callback_data": "ui:profile"}],
                        [{"text": "Топы", "callback_data": "ui:top"}],
                        [{"text": "Ачивки: как работает", "callback_data": "help:public_achievements"}],
                        [{"text": "Апелляция: как подать", "callback_data": "help:public_appeal"}],
                        [{"text": "Главная", "callback_data": "ui:home"}],
                    ]
                },
            )
        if section in {"top_all", "top_history", "top_week", "top_day", "top_social", "top_season"}:
            mapping = {
                "top_all": bridge.legacy.render_top_all_time(),
                "top_history": bridge.legacy.render_top_historical(),
                "top_week": bridge.legacy.render_top_week(),
                "top_day": bridge.legacy.render_top_day(),
                "top_social": bridge.legacy.render_top_social(),
                "top_season": bridge.legacy.render_top_season(),
            }
            return mapping[section], {
                "inline_keyboard": [
                    [
                        {"text": "Новый", "callback_data": "ui:top:all"},
                        {"text": "История", "callback_data": "ui:top:history"},
                    ],
                    [
                        {"text": "Неделя", "callback_data": "ui:top:week"},
                        {"text": "День", "callback_data": "ui:top:day"},
                    ],
                    [
                        {"text": "Вклад", "callback_data": "ui:top:social"},
                        {"text": "Сезон", "callback_data": "ui:top:season"},
                    ],
                    [{"text": "Рейтинг", "callback_data": "ui:profile"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
        if section == "top_menu":
            return (
                "JARVIS • РЕЙТИНГИ\n\nВыберите нужный срез рейтинга.",
                {
                    "inline_keyboard": [
                        [
                            {"text": "Новый", "callback_data": "ui:top:all"},
                            {"text": "История", "callback_data": "ui:top:history"},
                        ],
                        [
                            {"text": "Неделя", "callback_data": "ui:top:week"},
                            {"text": "День", "callback_data": "ui:top:day"},
                        ],
                        [
                            {"text": "Вклад", "callback_data": "ui:top:social"},
                            {"text": "Сезон", "callback_data": "ui:top:season"},
                        ],
                        [{"text": "Рейтинг", "callback_data": "ui:profile"}, {"text": "Главная", "callback_data": "ui:home"}],
                    ]
                },
            )
        return self.public_home_text, {
            "inline_keyboard": [
                [{"text": "Рейтинг", "callback_data": "ui:profile"}],
                [{"text": "Ачивки: инструкция", "callback_data": "help:public_achievements"}],
                [{"text": "Апелляция: инструкция", "callback_data": "help:public_appeal"}],
            ]
        }

    def build_control_panel(self, bridge: "TelegramBridge", user_id: int, section: str, payload: str = "") -> Tuple[str, dict]:
        section = section if section in self.control_panel_sections else "home"
        has_full_access = self.has_chat_access(bridge.state.authorized_user_ids, user_id)
        if not has_full_access:
            return self.build_public_control_panel(bridge, user_id, section, payload)
        if section == "admin_warns" and user_id == self.owner_user_id:
            warn_lines = ["JARVIS • НАСТРОЙКИ ПРЕДУПРЕЖДЕНИЙ", ""]
            with bridge.state.db_lock:
                rows = bridge.state.db.execute(
                    "SELECT chat_id, warn_limit, warn_mode, warn_expire_seconds FROM warn_settings ORDER BY chat_id DESC LIMIT 8"
                ).fetchall()
            if not rows:
                warn_lines.append("Явных настроек warn по чатам пока нет.")
            else:
                for row in rows:
                    warn_lines.append(
                        f"chat={int(row[0])} • limit={int(row[1])} • mode={row[2]} • ttl={self.format_duration_seconds(int(row[3])) if int(row[3]) > 0 else 'off'}"
                    )
            markup = {
                "inline_keyboard": [
                    [{"text": "Модерация", "callback_data": "ui:adm:moderation"}, {"text": "Очередь апелляций", "callback_data": "ui:adm:queue"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return "\n".join(warn_lines), markup
        if section == "admin_moderation" and user_id == self.owner_user_id:
            with bridge.state.db_lock:
                total_actions = bridge.state.db.execute("SELECT COUNT(*) FROM moderation_actions").fetchone()[0]
                active_actions = bridge.state.db.execute("SELECT COUNT(*) FROM moderation_actions WHERE active = 1").fetchone()[0]
                total_warnings = bridge.state.db.execute("SELECT COUNT(*) FROM warnings").fetchone()[0]
                last_rows = bridge.state.db.execute(
                    """SELECT created_at, chat_id, user_id, action, reason, active
                    FROM moderation_actions ORDER BY id DESC LIMIT 8"""
                ).fetchall()
            lines = [
                "JARVIS • МОДЕРАЦИЯ",
                "",
                f"Всего санкций: {int(total_actions)}",
                f"Активных санкций: {int(active_actions)}",
                f"Активных/исторических warn rows: {int(total_warnings)}",
                "",
                "Текущий контур:",
                "• auto-ban отключён",
                "• бот сам даёт только warn или временный mute",
                "• тяжёлые случаи уходят владельцу owner-report в ЛС",
                "• natural-language override владельца: «сними», «сними мут», «сними бан»",
                "• если активных санкций несколько, снимать нужно reply-командой на нужного участника",
                "",
                "Последние действия:",
            ]
            if not last_rows:
                lines.append("Пока пусто.")
            else:
                for row in last_rows:
                    stamp = datetime.fromtimestamp(int(row[0])).strftime("%m-%d %H:%M")
                    lines.append(
                        f"• {stamp} chat={int(row[1])} user={int(row[2])} {row[3]} {'active' if int(row[5]) else 'done'}"
                    )
                    if row[4]:
                        lines.append(f"  {self.truncate_text(row[4], 90)}")
            markup = {
                "inline_keyboard": [
                    [{"text": "Настройки предупреждений", "callback_data": "ui:adm:warns"}, {"text": "Очередь апелляций", "callback_data": "ui:adm:queue"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return "\n".join(lines), markup
        if section == "owner_root" and user_id == self.owner_user_id:
            text = (
                "JARVIS • ПАНЕЛЬ ВЛАДЕЛЬЦА\n\n"
                "Это центральная админ-панель проекта.\n"
                "Здесь собраны все owner-команды, runtime-сводки, git/logs сценарии, работа с памятью чатов, файлами и live-data.\n\n"
                "Как пользоваться:\n"
                "• разделы ниже открывают экраны с пояснениями и быстрыми сводками\n"
                "• команды без параметров можно запускать прямо как отдельные команды из чата\n"
                "• команды с параметрами здесь описаны с примерами и usage-шаблонами\n"
                "• если нужен полный справочник без сокращений, открывай раздел «Все команды»\n\n"
                "Разделы:\n"
                "• Среда и рантайм: здоровье процесса, ресурсы, перезапуск, owner report\n"
                "• Git и логи: ветка, коммиты, ошибки, upgrade\n"
                "• Память и чаты: history, digest, recall, portraits, export\n"
                "• Файлы и медиа: sdcard-команды, файлы, документы, media-context\n"
                "• Live-данные: погода, курсы, новости, current-facts\n"
                "• Автовосстановление: инциденты, статус, безопасные repair playbooks\n"
                "• Модерация: санкции, предупреждения, welcome, appeals\n"
                "• Все команды: полный текстовый реестр проекта"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Среда и рантайм", "callback_data": "ui:panel:owner_runtime"}, {"text": "Git и логи", "callback_data": "ui:panel:owner_git"}],
                    [{"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}, {"text": "Файлы и медиа", "callback_data": "ui:panel:owner_files"}],
                    [{"text": "Live-данные", "callback_data": "ui:panel:owner_live"}, {"text": "Автовосстановление", "callback_data": "ui:panel:owner_selfheal"}],
                    [{"text": "Модерация", "callback_data": "ui:panel:owner_moderation"}],
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_runtime" and user_id == self.owner_user_id:
            if payload:
                return self._build_owner_runtime_detail(bridge, payload)
            return self._build_owner_runtime_summary(bridge)
        if section == "owner_git" and user_id == self.owner_user_id:
            return self._build_owner_git_panel(bridge, payload)
        if section == "owner_memory" and user_id == self.owner_user_id:
            text = (
                "JARVIS • ПАМЯТЬ И ЧАТЫ\n\n"
                "Раздел для памяти, поиска по событиям и анализа конкретных чатов/участников.\n"
                "Подходит, когда нужно поднять историю, найти автора фразы, собрать digest или посмотреть профиль участника.\n\n"
                "Команды раздела:\n"
                "• /remember <факт> — записать факт в память чата\n"
                "• /recall [запрос] — поднять релевантные факты и события\n"
                "• /search <запрос> — поиск по chat_events\n"
                "• /memorychat [запрос] — показать текущий chat memory слой\n"
                "• /memoryuser @username|user_id — показать user memory по участнику\n"
                "• /memorysummary — показать summary memory snapshots\n"
                "• /who_said <запрос> — кто чаще писал фразу/слово\n"
                "• /history @username — timeline участника\n"
                "• /daily [YYYY-MM-DD] — активность за день в текущем чате\n"
                "• /digest [YYYY-MM-DD] — digest по текущему чату\n"
                "• /chatdigest <chat_id> [YYYY-MM-DD] — digest по конкретной группе из owner-лички\n"
                "• /export chat|today|@username|user_id — выгрузка событий\n"
                "• /portrait [@username] — профиль участника\n"
                "• /reset — очистка контекста текущего чата\n\n"
                "Подсказки:\n"
                "• /history и /portrait можно вызывать через reply на сообщение\n"
                "• /chatdigest полезен для групп, куда ты не хочешь писать команды прямо в чат"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Файлы и медиа", "callback_data": "ui:panel:owner_files"}, {"text": "Live-данные", "callback_data": "ui:panel:owner_live"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_files" and user_id == self.owner_user_id:
            text = (
                "JARVIS • ФАЙЛЫ И МЕДИА\n\n"
                "Раздел для файловых сценариев и media-aware поведения.\n"
                "Если нужно лазить по /sdcard, переслать файл, сохранить вложение или понять, как bot разбирает документы и фото, это здесь.\n\n"
                "Команды раздела:\n"
                "• /sdls [/sdcard/путь] — список файлов и папок\n"
                "• /sdsend /sdcard/путь/к/файлу — отправить файл в Telegram\n"
                "• /sdsave /sdcard/папка/или/файл — сохранить документ/медиа из reply\n\n"
                "Что умеет бот автоматически:\n"
                "• анализировать фото\n"
                "• анализировать документы\n"
                "• вытаскивать excerpt из текстовых файлов\n"
                "• добавлять reply-context вокруг медиа\n\n"
                "Как использовать /sdsave:\n"
                "• reply на сообщение с документом или медиа\n"
                "• затем отправить /sdsave /sdcard/Download/..."
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}, {"text": "Live-данные", "callback_data": "ui:panel:owner_live"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_live" and user_id == self.owner_user_id:
            text = (
                "JARVIS • LIVE-ДАННЫЕ\n\n"
                "Раздел для всех live-data маршрутов.\n"
                "Сюда относятся запросы, где важна свежесть данных: погода, курсы, рынок, новости, current facts.\n\n"
                "Live-маршруты:\n"
                "• погода\n"
                "• курсы валют\n"
                "• крипта\n"
                "• акции\n"
                "• новости\n"
                "• current-facts по должностям и ролям\n\n"
                "Как это работает:\n"
                "• такие запросы идут не в обычный prompt, а в отдельные live-источники\n"
                "• если источник не ответил, бот должен писать это честно\n"
                "• current-fact запросы пытаются собрать короткий вывод по найденным источникам\n\n"
                "Примеры:\n"
                "• Погода в Брянске\n"
                "• курс доллара\n"
                "• цена btc\n"
                "• последние новости по Apple\n"
                "• кто сейчас президент Франции\n"
                "• CEO OpenAI"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Файлы и медиа", "callback_data": "ui:panel:owner_files"}, {"text": "Модерация", "callback_data": "ui:panel:owner_moderation"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_selfheal" and user_id == self.owner_user_id:
            owner_autofix_enabled = bridge.owner_autofix_enabled()
            owner_autofix_status = "включено" if owner_autofix_enabled else "выключено"
            incidents = bridge.state.get_recent_self_heal_incidents(limit=10)
            if payload.isdigit():
                incident = bridge.state.get_self_heal_incident(int(payload))
            else:
                incident = None
            if incident is not None:
                text = (
                    "JARVIS • АВТОВОССТАНОВЛЕНИЕ\n\n"
                    f"Инцидент #{int(incident['id'])}\n"
                    f"problem={incident['problem_type']}\n"
                    f"signal={incident['signal_code']}\n"
                    f"state={incident['state']}\n"
                    f"severity={incident['severity']}\n"
                    f"risk={incident['risk_level']}\n"
                    f"autonomy={incident['autonomy_level']}\n"
                    f"playbook={incident['suggested_playbook'] or '-'}\n"
                    f"verification={incident['verification_status'] or '-'}\n\n"
                    f"что случилось:\n{incident['summary'] or '-'}\n\n"
                    f"подтверждение:\n{self.truncate_text(incident['evidence'] or '-', 500)}"
                )
                keyboard = []
                if str(incident["state"] or "") in {"awaiting_approval", "repair_planned"}:
                    keyboard.append(
                        [
                            {"text": "Одобрить", "callback_data": f"ui:selfheal:approve:{int(incident['id'])}"},
                            {"text": "Отклонить", "callback_data": f"ui:selfheal:deny:{int(incident['id'])}"},
                        ]
                    )
                keyboard.append([{"text": "К списку", "callback_data": "ui:panel:owner_selfheal"}])
                keyboard.append([{"text": "Очередь согласования", "callback_data": "ui:panel:owner_selfheal_queue"}])
                keyboard.append([{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}])
                return text, {"inline_keyboard": keyboard}
            lines = [
                "JARVIS • АВТОВОССТАНОВЛЕНИЕ",
                "",
                "Здесь собраны автоматические инциденты, безопасные repair-playbook'и и ручные owner-решения.",
                f"Owner autofix сейчас: {owner_autofix_status}.",
                "Когда использовать:",
                "• если бот сам что-то чинит",
                "• если нужен dry-run или ручной approve/deny",
                "• если нужно понять, что именно сломалось и что уже проверено",
                "",
                "Команды:",
                "• /selfhealstatus",
                "• /selfhealrun <playbook|incident_id> [dry-run|execute]",
                "• /selfhealapprove <incident_id>",
                "• /selfhealdeny <incident_id>",
                "",
                "Последние инциденты:",
            ]
            keyboard = []
            if not incidents:
                lines.append("Пока пусто.")
            else:
                for row in incidents[:6]:
                    lines.append(
                        f"• #{int(row['id'])} {row['problem_type']} [{row['state']}] playbook={row['suggested_playbook'] or '-'}"
                    )
                    keyboard.append(
                        [{"text": f"Инцидент #{int(row['id'])}", "callback_data": f"ui:selfheal:view:{int(row['id'])}"}]
                    )
            keyboard.append(
                [
                    {"text": f"Owner autofix: {'ON' if owner_autofix_enabled else 'OFF'}", "callback_data": "ui:ownerautofix:status"},
                    {"text": "Переключить", "callback_data": "ui:ownerautofix:toggle"},
                ]
            )
            keyboard.append([{"text": "Очередь согласования", "callback_data": "ui:panel:owner_selfheal_queue"}])
            keyboard.append([{"text": "Среда и runtime", "callback_data": "ui:panel:owner_runtime"}, {"text": "Все команды", "callback_data": "ui:panel:owner_commands"}])
            keyboard.append([{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}])
            return "\n".join(lines), {"inline_keyboard": keyboard}
        if section == "owner_selfheal_queue" and user_id == self.owner_user_id:
            incidents = [
                row for row in bridge.state.get_recent_self_heal_incidents(limit=20)
                if str(row["state"] or "") in {"awaiting_approval", "repair_planned"}
            ]
            lines = [
                "JARVIS • ОЧЕРЕДЬ СОГЛАСОВАНИЯ АВТОВОССТАНОВЛЕНИЯ",
                "",
                "Здесь только те инциденты, которые ждут решения владельца.",
                "Если одобряешь, бот выполнит только разрешённый bounded playbook и потом сам себя проверит.",
                "",
                "Инциденты в очереди:",
            ]
            keyboard = []
            if not incidents:
                lines.append("Очередь пуста.")
            else:
                for row in incidents[:8]:
                    lines.append(
                        f"• #{int(row['id'])} {row['problem_type']} [{row['state']}] playbook={row['suggested_playbook'] or '-'}"
                    )
                    keyboard.append(
                        [
                            {"text": f"Открыть #{int(row['id'])}", "callback_data": f"ui:selfheal:view:{int(row['id'])}"},
                            {"text": "Одобрить", "callback_data": f"ui:selfheal:approve:{int(row['id'])}"},
                            {"text": "Отклонить", "callback_data": f"ui:selfheal:deny:{int(row['id'])}"},
                        ]
                    )
            keyboard.append([{"text": "Автовосстановление", "callback_data": "ui:panel:owner_selfheal"}, {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}])
            keyboard.append([{"text": "Главная", "callback_data": "ui:home"}])
            return "\n".join(lines), {"inline_keyboard": keyboard}
        if section == "owner_moderation" and user_id == self.owner_user_id:
            text = (
                "JARVIS • МОДЕРАЦИЯ И АПЕЛЛЯЦИИ\n\n"
                "Раздел для администрирования групп: санкции, auto-moderation, warns, welcome и appeals.\n"
                "Здесь собраны команды и правила, которые сейчас реально действуют в runtime.\n\n"
                "Auto-moderation сейчас:\n"
                "• auto-ban отключён\n"
                "• бот сам даёт только warn или временный mute\n"
                "• тяжёлые кейсы отправляются владельцу отдельным owner-report в ЛС\n"
                "• бот не должен спорить с серией адресных оскорблений, а должен переходить к санкции\n"
                "• /rules отдаёт правила группы\n\n"
                "Санкции:\n"
                "• /ban /unban /mute /unmute /kick /tban /tmute\n"
                "• цель можно задавать reply, @username или user_id\n"
                "• natural-language override владельца: «сними», «сними мут», «сними бан», «размуть», «разбань»\n"
                "• если активных санкций несколько, снимать лучше reply-командой на нужного участника\n\n"
                "Warn system:\n"
                "• /warn /dwarn /swarn /warns /warnreasons /rmwarn /resetwarn\n"
                "• /setwarnlimit\n"
                "• /setwarnmode\n"
                "• /warntime\n"
                "• /modlog\n\n"
                "Reply UX:\n"
                "• групповые ответы бота теперь по возможности идут reply на исходное сообщение\n"
                "• это же касается обычных текстовых ответов, фото, документов и голосовых\n\n"
                "Welcome:\n"
                "• /welcome on|off|status\n"
                "• /setwelcome <текст>\n"
                "• /resetwelcome\n\n"
                "Appeals:\n"
                "• /appeals\n"
                "• /appeal_review <id>\n"
                "• /appeal_approve <id> [решение]\n"
                "• /appeal_reject <id> [решение]\n\n"
                "Если нужен UI-режим по appeals и moderation, используй кнопки ниже."
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Кабинет модерации", "callback_data": "ui:adm:moderation"}, {"text": "Очередь апелляций", "callback_data": "ui:adm:queue"}],
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_commands" and user_id == self.owner_user_id:
            return self._build_owner_commands_panel(payload)
        if section == "profile":
            text = bridge.legacy.render_rating(user_id)
            keyboard = [[{"text": "Обновить", "callback_data": "ui:profile"}]]
            if has_full_access:
                keyboard.append([{"text": "Ачивки", "callback_data": "ui:achievements"}, {"text": "Топы", "callback_data": "ui:top"}])
            keyboard.append([{"text": "Апелляции", "callback_data": "ui:appeals"}, {"text": "Главная", "callback_data": "ui:home"}])
            markup = {"inline_keyboard": keyboard}
            return text, markup
        if section == "achievements":
            text = "JARVIS • ДОСТИЖЕНИЯ\n\n" + bridge.legacy.render_achievements(user_id)
            markup = {
                "inline_keyboard": [
                    [{"text": "Профиль", "callback_data": "ui:profile"}, {"text": "Топы", "callback_data": "ui:top"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section in {"top_all", "top_history", "top_week", "top_day", "top_social", "top_season"}:
            mapping = {
                "top_all": bridge.legacy.render_top_all_time(),
                "top_history": bridge.legacy.render_top_historical(),
                "top_week": bridge.legacy.render_top_week(),
                "top_day": bridge.legacy.render_top_day(),
                "top_social": bridge.legacy.render_top_social(),
                "top_season": bridge.legacy.render_top_season(),
            }
            text = mapping[section]
            markup = {
                "inline_keyboard": [
                    [
                        {"text": "Новый", "callback_data": "ui:top:all"},
                        {"text": "История", "callback_data": "ui:top:history"},
                    ],
                    [
                        {"text": "Неделя", "callback_data": "ui:top:week"},
                        {"text": "День", "callback_data": "ui:top:day"},
                    ],
                    [
                        {"text": "Вклад", "callback_data": "ui:top:social"},
                        {"text": "Сезон", "callback_data": "ui:top:season"},
                    ],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "top_menu":
            text = (
                "JARVIS • РЕЙТИНГИ\n\n"
                "Выберите срез рейтинга. Все экраны обновляются в одном сообщении.\n\n"
                "Доступно:\n"
                "• новый рейтинг без legacy-архива\n"
                "• исторический архивный рейтинг\n"
                "• недельная динамика\n"
                "• дневная динамика\n"
                "• вклад в сообщество\n"
                "• сезонный рейтинг"
            )
            markup = {
                "inline_keyboard": [
                    [
                        {"text": "Новый", "callback_data": "ui:top:all"},
                        {"text": "История", "callback_data": "ui:top:history"},
                    ],
                    [
                        {"text": "Неделя", "callback_data": "ui:top:week"},
                        {"text": "День", "callback_data": "ui:top:day"},
                    ],
                    [
                        {"text": "Вклад", "callback_data": "ui:top:social"},
                        {"text": "Сезон", "callback_data": "ui:top:season"},
                    ],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "appeals":
            snapshot = bridge.appeals.get_case_snapshot(user_id)
            rows = bridge.appeals.get_user_appeals(user_id, limit=4)
            lines = [
                "JARVIS • АПЕЛЛЯЦИИ",
                "",
                "Текущая проверка оснований:",
                f"• Активные баны: {len(snapshot.get('active_bans', []))}",
                f"• Активные муты: {len(snapshot.get('active_mutes', []))}",
                f"• Активные предупреждения: {snapshot.get('active_warnings', 0)}",
                f"• Подтвержденные нарушения: {snapshot.get('confirmed_violations', 0)}",
                f"• Legacy warnings: {snapshot.get('legacy_user_warnings', 0)}",
                f"• Прошлые апелляции: {snapshot.get('past_appeals', 0)}",
                "",
                "Если активных оснований нет или срок санкции истек, система снимет ограничение автоматически.",
            ]
            if rows:
                lines.extend(["", "Последние апелляции:"])
                for row in rows:
                    lines.append(f"• #{int(row['id'])} {row['status']} — {self.truncate_text(row['reason'] or '', 70)}")
            markup = {
                "inline_keyboard": [
                    [{"text": "Подать апелляцию", "callback_data": "ui:appeal:new"}],
                    [{"text": "История", "callback_data": "ui:appeal:history"}, {"text": "Профиль", "callback_data": "ui:profile"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return "\n".join(lines), markup
        if section == "appeal_history":
            rows = bridge.appeals.get_user_appeals(user_id, limit=12)
            lines = [
                "JARVIS • ИСТОРИЯ АПЕЛЛЯЦИЙ",
                "",
            ]
            if not rows:
                lines.append("Апелляций пока нет.")
            else:
                for row in rows:
                    stamp = datetime.fromtimestamp(int(row["created_at"])).strftime("%Y-%m-%d %H:%M")
                    lines.append(f"#{int(row['id'])} • {row['status']} • {stamp}")
                    if row["decision_type"]:
                        lines.append(f"Решение: {row['decision_type']}")
                    if row["review_comment"]:
                        lines.append(f"Комментарий: {self.truncate_text(row['review_comment'], 120)}")
                    lines.append(self.truncate_text(row["reason"] or "", 120))
                    lines.append("")
            markup = {
                "inline_keyboard": [
                    [{"text": "Подать апелляцию", "callback_data": "ui:appeal:new"}],
                    [{"text": "Назад", "callback_data": "ui:appeals"}, {"text": "Профиль", "callback_data": "ui:profile"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return "\n".join(lines).strip(), markup
        if section == "admin_appeals":
            rows = bridge.appeals.list_open_appeals(limit=8)
            lines = ["JARVIS • ОЧЕРЕДЬ АПЕЛЛЯЦИЙ", ""]
            if not rows:
                lines.append("Открытых апелляций нет.")
            else:
                for row in rows:
                    stamp = datetime.fromtimestamp(int(row["created_at"])).strftime("%Y-%m-%d %H:%M")
                    lines.append(f"#{int(row['id'])} • user={int(row['user_id'])} • {row['status']} • {stamp}")
                    lines.append(self.truncate_text(row["reason"] or "", 100))
                    lines.append("")
            keyboard = []
            for row in rows[:5]:
                keyboard.append([{"text": f"Открыть #{int(row['id'])}", "callback_data": f"ui:adm:view:{int(row['id'])}"}])
            keyboard.append([{"text": "Обновить", "callback_data": "ui:adm:queue"}, {"text": "Главная", "callback_data": "ui:home"}])
            return "\n".join(lines).strip(), {"inline_keyboard": keyboard}
        if section == "admin_appeal_detail":
            appeal_id = int(payload or "0")
            row = bridge.appeals.get_appeal(appeal_id)
            if not row:
                return "Апелляция не найдена.", {"inline_keyboard": [[{"text": "Назад", "callback_data": "ui:adm:queue"}]]}
            events = bridge.appeals.get_appeal_events(appeal_id)
            lines = [
                f"JARVIS • АПЕЛЛЯЦИЯ #{appeal_id}",
                "",
                f"user_id: {int(row['user_id'])}",
                f"status: {row['status']}",
                f"source_action: {row['source_action'] or 'unknown'}",
                f"decision_type: {row['decision_type']}",
                f"auto_result: {row['auto_result'] or '-'}",
                f"reason: {row['reason']}",
            ]
            if row["resolution"]:
                lines.append(f"resolution: {row['resolution']}")
            if row["review_comment"]:
                lines.append(f"comment: {row['review_comment']}")
            if events:
                lines.extend(["", "timeline:"])
                for event in events[-5:]:
                    stamp = datetime.fromtimestamp(int(event["created_at"])).strftime("%m-%d %H:%M")
                    lines.append(f"• {stamp} {event['event_type']} {event['status_from']} -> {event['status_to']}")
            markup = {
                "inline_keyboard": [
                    [{"text": "В review", "callback_data": f"ui:adm:review:{appeal_id}"}],
                    [{"text": "Одобрить", "callback_data": f"ui:adm:approve:{appeal_id}"}, {"text": "Отклонить", "callback_data": f"ui:adm:reject:{appeal_id}"}],
                    [{"text": "Одобрить + коммент", "callback_data": f"ui:adm:approvec:{appeal_id}"}],
                    [{"text": "Отклонить + коммент", "callback_data": f"ui:adm:rejectc:{appeal_id}"}],
                    [{"text": "Закрыть + коммент", "callback_data": f"ui:adm:closec:{appeal_id}"}],
                    [{"text": "Назад к очереди", "callback_data": "ui:adm:queue"}],
                ]
            }
            return "\n".join(lines), markup
        text = (
            "JARVIS • ЕДИНОЕ ОКНО\n\n"
            "Все основные сценарии вынесены в кнопки и обновляются в одном сообщении.\n\n"
            + bridge.legacy.render_dashboard_summary(user_id)
        )
        keyboard = [
            [{"text": "Профиль", "callback_data": "ui:profile"}, {"text": "Ачивки", "callback_data": "ui:achievements"}],
            [{"text": "Топы", "callback_data": "ui:top"}, {"text": "Апелляции", "callback_data": "ui:appeals"}],
            [{"text": "Справка", "callback_data": "help:main"}],
        ]
        if user_id == self.owner_user_id:
            keyboard.insert(2, [{"text": "Модерация апелляций", "callback_data": "ui:adm:queue"}])
            keyboard.insert(3, [{"text": "Кабинет модерации", "callback_data": "ui:adm:moderation"}])
            keyboard.insert(4, [{"text": "Owner Panel", "callback_data": "ui:panel:owner_root"}])
        return text, {"inline_keyboard": keyboard}


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
