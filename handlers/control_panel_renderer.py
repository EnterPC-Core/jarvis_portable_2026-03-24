import time
from datetime import datetime
from typing import Callable, Optional, Tuple

from handlers.owner_panel_sections import (
    build_owner_commands_panel,
    build_owner_git_panel,
    build_owner_jarvis_panel,
    build_owner_runtime_detail,
    build_owner_runtime_summary,
)
from handlers.control_panel_aux import (
    build_admin_warns_panel,
    build_owner_people_live_panel,
    build_top_navigation,
    list_participant_profile_chats,
)
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
        return build_owner_commands_panel(self, payload)

    def _build_owner_runtime_summary(self, bridge: "TelegramBridge") -> Tuple[str, dict]:
        return build_owner_runtime_summary(
            self,
            bridge,
            collect_diagnostics_metrics_func=collect_diagnostics_metrics,
        )

    def _build_owner_runtime_detail(self, bridge: "TelegramBridge", payload: str) -> Tuple[str, dict]:
        return build_owner_runtime_detail(
            self,
            bridge,
            payload,
            collect_diagnostics_metrics_func=collect_diagnostics_metrics,
            render_diagnostics_metrics_func=render_diagnostics_metrics,
        )

    def _format_warn_mode_label(self, stored_mode: str) -> str:
        mode = (stored_mode or "mute").strip().lower()
        if ":" not in mode:
            return mode
        name, raw_seconds = mode.split(":", 1)
        try:
            seconds = int(raw_seconds)
        except ValueError:
            return mode
        return f"{name} {self.format_duration_seconds(seconds)}"

    def _build_admin_warns_panel(self, bridge: "TelegramBridge", payload: str) -> Tuple[str, dict]:
        return build_admin_warns_panel(self, bridge, payload)

    def _build_owner_git_panel(self, bridge: "TelegramBridge", payload: str) -> Tuple[str, dict]:
        return build_owner_git_panel(self, bridge, payload)

    def _build_owner_jarvis_panel(self, bridge: "TelegramBridge", payload: str) -> Tuple[str, dict]:
        return build_owner_jarvis_panel(self, bridge, payload)

    def _list_participant_profile_chats(self, bridge: "TelegramBridge", limit: int = 12) -> list[tuple[int, str]]:
        return list_participant_profile_chats(self, bridge, limit=limit)

    def _build_owner_people_live_panel(self, bridge: "TelegramBridge", mode: str, payload: str) -> Tuple[str, dict]:
        return build_owner_people_live_panel(self, bridge, mode, payload)

    def _parse_top_page(self, payload: str) -> int:
        try:
            return max(1, int((payload or "1").strip()))
        except ValueError:
            return 1

    def _build_top_navigation(self, top_key: str, page: int, *, home_label: str = "Главная") -> list[list[dict]]:
        return build_top_navigation(top_key, page, home_label=home_label)

    def build_public_control_panel(self, bridge: "TelegramBridge", user_id: int, section: str, payload: str = "") -> Tuple[str, dict]:
        if section == "profile":
            text = (
                "JARVIS • МОЙ ПРОФИЛЬ\n\n"
                "Персональная карточка участника: уровень, рейтинг, вклад, реакции и текущая динамика.\n\n"
                f"{bridge.legacy.render_dashboard_summary(user_id)}"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Все топы", "callback_data": "ui:top"}, {"text": "Достижения", "callback_data": "ui:achievements"}],
                    [{"text": "Реакции", "callback_data": "ui:top:reactions:1"}, {"text": "За неделю", "callback_data": "ui:top:week:1"}],
                    [{"text": "Сообщения", "callback_data": "ui:top:messages:1"}, {"text": "Полезность", "callback_data": "ui:top:helpful:1"}],
                    [{"text": "Апелляции", "callback_data": "ui:appeals"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "achievements":
            text = (
                "JARVIS • ДОСТИЖЕНИЯ\n\n"
                "Коллекция участника: открытые ачивки, скрытые слоты и ближайший прогресс.\n\n"
                f"{bridge.legacy.render_achievements(user_id)}"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Профиль", "callback_data": "ui:profile"}, {"text": "Все топы", "callback_data": "ui:top"}],
                    [{"text": "Рейтинг ачивок", "callback_data": "ui:top:achievements:1"}, {"text": "Реакции", "callback_data": "ui:top:reactions:1"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section in {
            "top_all",
            "top_history",
            "top_week",
            "top_day",
            "top_social",
            "top_season",
            "top_reactions_received",
            "top_reactions_given",
            "top_activity",
            "top_behavior",
            "top_achievements",
            "top_messages",
            "top_helpful",
            "top_streak",
        }:
            page = self._parse_top_page(payload)
            mapping = {
                "top_all": ("all", bridge.legacy.render_top_all_time(page)),
                "top_history": ("history", bridge.legacy.render_top_historical(page)),
                "top_week": ("week", bridge.legacy.render_top_week(page)),
                "top_day": ("day", bridge.legacy.render_top_day(page)),
                "top_social": ("social", bridge.legacy.render_top_social(page)),
                "top_season": ("season", bridge.legacy.render_top_season(page)),
                "top_reactions_received": ("reactions", bridge.legacy.render_top_reactions_received(page)),
                "top_reactions_given": ("given", bridge.legacy.render_top_reactions_given(page)),
                "top_activity": ("activity", bridge.legacy.render_top_activity(page)),
                "top_behavior": ("behavior", bridge.legacy.render_top_behavior(page)),
                "top_achievements": ("achievements", bridge.legacy.render_top_achievements(page)),
                "top_messages": ("messages", bridge.legacy.render_top_messages(page)),
                "top_helpful": ("helpful", bridge.legacy.render_top_helpful(page)),
                "top_streak": ("streak", bridge.legacy.render_top_streak(page)),
            }
            top_key, text = mapping[section]
            markup = {"inline_keyboard": self._build_top_navigation(top_key, page)}
            return text, markup
        if section == "top_menu":
            text = (
                "JARVIS • РЕЙТИНГИ\n\n"
                "Здесь собраны все доступные срезы рейтинга.\n\n"
                "Что можно смотреть:\n"
                "• новый рейтинг\n"
                "• исторический рейтинг\n"
                "• день / неделя / сезон\n"
                "• вклад в сообщество\n"
                "• реакции полученные и отправленные\n"
                "• активность\n"
                "• поведение\n"
                "• сообщения\n"
                "• полезность\n"
                "• стрики\n"
                "• достижения"
            )
            markup = {
                "inline_keyboard": [
                    [
                        {"text": "Новый", "callback_data": "ui:top:all:1"},
                        {"text": "История", "callback_data": "ui:top:history:1"},
                    ],
                    [
                        {"text": "Неделя", "callback_data": "ui:top:week:1"},
                        {"text": "День", "callback_data": "ui:top:day:1"},
                    ],
                    [
                        {"text": "Вклад", "callback_data": "ui:top:social:1"},
                        {"text": "Сезон", "callback_data": "ui:top:season:1"},
                    ],
                    [
                        {"text": "Реакции+", "callback_data": "ui:top:reactions:1"},
                        {"text": "Реакции→", "callback_data": "ui:top:given:1"},
                    ],
                    [
                        {"text": "Активность", "callback_data": "ui:top:activity:1"},
                        {"text": "Поведение", "callback_data": "ui:top:behavior:1"},
                    ],
                    [
                        {"text": "Сообщения", "callback_data": "ui:top:messages:1"},
                        {"text": "Полезность", "callback_data": "ui:top:helpful:1"},
                    ],
                    [
                        {"text": "Стрик", "callback_data": "ui:top:streak:1"},
                        {"text": "Ачивки", "callback_data": "ui:top:achievements:1"},
                    ],
                    [{"text": "Профиль", "callback_data": "ui:profile"}, {"text": "Апелляции", "callback_data": "ui:appeals"}],
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
                "Проверка строится по активным санкциям, предупреждениям и истории решений.",
                "",
                "Текущее состояние:",
                f"• Активные баны: {len(snapshot.get('active_bans', []))}",
                f"• Активные муты: {len(snapshot.get('active_mutes', []))}",
                f"• Активные предупреждения: {snapshot.get('active_warnings', 0)}",
                f"• Подтвержденные нарушения: {snapshot.get('confirmed_violations', 0)}",
                f"• Прошлые апелляции: {snapshot.get('past_appeals', 0)}",
                "",
                "Если оснований для ограничения уже нет, апелляция может быть одобрена автоматически.",
            ]
            if rows:
                lines.extend(["", "Последние апелляции:"])
                for row in rows:
                    lines.append(f"• #{int(row['id'])} {row['status']} — {self.truncate_text(row['reason'] or '', 70)}")
            markup = {
                "inline_keyboard": [
                    [{"text": "Подать апелляцию", "callback_data": "ui:appeal:new"}],
                    [{"text": "История", "callback_data": "ui:appeal:history"}, {"text": "Мой профиль", "callback_data": "ui:profile"}],
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
                    [{"text": "Назад", "callback_data": "ui:appeals"}, {"text": "Мой профиль", "callback_data": "ui:profile"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return "\n".join(lines).strip(), markup
        return self.public_home_text, {
            "inline_keyboard": [
                [{"text": "Мой профиль", "callback_data": "ui:profile"}, {"text": "Все топы", "callback_data": "ui:top"}],
                [{"text": "Достижения", "callback_data": "ui:achievements"}, {"text": "Рейтинг ачивок", "callback_data": "ui:top:achievements:1"}],
                [{"text": "Реакции+", "callback_data": "ui:top:reactions:1"}, {"text": "За неделю", "callback_data": "ui:top:week:1"}],
                [{"text": "Сообщения", "callback_data": "ui:top:messages:1"}, {"text": "Полезность", "callback_data": "ui:top:helpful:1"}],
                [{"text": "Апелляции", "callback_data": "ui:appeals"}],
            ]
        }

    def build_control_panel(self, bridge: "TelegramBridge", user_id: int, section: str, payload: str = "") -> Tuple[str, dict]:
        section = section if section in self.control_panel_sections else "home"
        has_full_access = self.has_chat_access(bridge.state.authorized_user_ids, user_id)
        if not has_full_access:
            return self.build_public_control_panel(bridge, user_id, section, payload)
        if section == "admin_warns" and user_id == self.owner_user_id:
            return self._build_admin_warns_panel(bridge, payload)
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
                "Это короткая owner-only панель без публичного и декоративного слоя.\n"
                "Здесь оставлены только рабочие контуры: runtime, git/logs, память, файлы, команды, модерация и автовосстановление.\n\n"
                "Как пользоваться:\n"
                "• разделы ниже открывают экраны с пояснениями и быстрыми сводками\n"
                "• команды с параметрами запускай текстом из owner-чата\n"
                "• если забыл синтаксис, сначала открывай «Все команды»\n"
                "• панель больше не пытается быть публичным help/меню для остальных\n\n"
                "Разделы:\n"
                "• Среда и рантайм: здоровье процесса, ресурсы, owner-report\n"
                "• Jarvis Control: режим, доступ, инструкции, память и Telegram-сценарии\n"
                "• Git и логи: состояние дерева, хвост ошибок, последние коммиты\n"
                "• Карта системы: один экран со всеми owner-разделами, автоматикой и ограничениями\n"
                "• Что умеет Jarvis: карта возможностей, режимов и owner-сценариев\n"
                "• Авто-режимы и алерты: что бот делает сам, какие сигналы шлёт и с каким cooldown\n"
                "• Память и чаты: history, recall, digest, deep-profile, whois, conflicts\n"
                "• Обзор чатов: что происходит по группам, быстрые daily/24h срезы\n"
                "• Люди и связи: whois, watchlist, reliable, ownergraph, cross-chat пересечения\n"
                "• Owner Identity: основной аккаунт, alias-аккаунты и их статусы по чатам\n"
                "• Файлы и медиа: sdcard, сохранение и пересылка вложений\n"
                "• Все команды: полный owner/admin реестр с доступом и источниками данных\n"
                "• Модерация: санкции, warnings, welcome, owner-report\n"
                "• Автовосстановление: инциденты, статус, bounded repair playbooks"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Среда и рантайм", "callback_data": "ui:panel:owner_runtime"}, {"text": "Jarvis Control", "callback_data": "ui:panel:owner_jarvis"}],
                    [{"text": "Git и логи", "callback_data": "ui:panel:owner_git"}, {"text": "Карта системы", "callback_data": "ui:panel:owner_system_map"}],
                    [{"text": "Что умеет Jarvis", "callback_data": "ui:panel:owner_capabilities"}, {"text": "Авто-режимы и алерты", "callback_data": "ui:panel:owner_automation"}],
                    [{"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}, {"text": "Обзор чатов", "callback_data": "ui:panel:owner_overview"}],
                    [{"text": "Люди и связи", "callback_data": "ui:panel:owner_people"}, {"text": "Owner Identity", "callback_data": "ui:panel:owner_identity"}],
                    [{"text": "Файлы и медиа", "callback_data": "ui:panel:owner_files"}, {"text": "Модерация", "callback_data": "ui:panel:owner_moderation"}],
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands"}, {"text": "Автовосстановление", "callback_data": "ui:panel:owner_selfheal"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_jarvis" and user_id == self.owner_user_id:
            return self._build_owner_jarvis_panel(bridge, payload)
        if section == "owner_identity" and user_id == self.owner_user_id:
            text = (
                "JARVIS • OWNER IDENTITY\n\n"
                "Здесь собраны основной owner-аккаунт и alias-аккаунты владельца.\n"
                "Для каждого аккаунта видно, в каких чатах он состоит и какой у него статус.\n\n"
                + bridge.owner_handlers.render_owner_identity_text(bridge)
                + "\n\nПояснение:\n"
                "• если статус `создатель` или `админ`, бот не применяет auto-moderation к этому аккаунту\n"
                "• если статус `участник`, ограничение по статусу не мешает модерации\n"
                "• названия чатов берутся из runtime cache, а не из случайного внешнего слепка"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Люди и связи", "callback_data": "ui:panel:owner_people"}, {"text": "Среда и рантайм", "callback_data": "ui:panel:owner_runtime"}],
                    [{"text": "Карта системы", "callback_data": "ui:panel:owner_system_map"}, {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_system_map" and user_id == self.owner_user_id:
            text = (
                "JARVIS • КАРТА СИСТЕМЫ\n\n"
                "Это общий owner-экран: что есть в системе, где это искать и что работает автоматически.\n\n"
                "Разделы панели:\n"
                "• Среда и рантайм — здоровье bridge, heartbeat, ресурсы, owner-report\n"
                "• Git и логи — состояние дерева, ошибки, route/runtime хвосты\n"
                "• Что умеет Jarvis — user-facing и owner-facing возможности\n"
                "• Авто-режимы и алерты — scheduled процессы, digests, alert-сигналы\n"
                "• Память и чаты — facts, memory layers, digest, history, export\n"
                "• Обзор чатов — быстрый срез по группам и deep-profile по конкретному чату\n"
                "• Люди и связи — whois, portrait, ownergraph, cross-chat relation context\n"
                "• Owner Identity — owner и alias-аккаунты, статусы по чатам и ограничения модерации\n"
                "• Файлы и медиа — sdcard, вложения, документы, фото\n"
                "• Модерация — санкции, warn-system, welcome, appeals\n"
                "• Автовосстановление — incidents, playbooks, approve/deny, owner autofix\n"
                "• Все команды — структурированный реестр команд с доступом и источниками данных\n\n"
                "Автоматика уже работает сама:\n"
                "• health-aware supervisor\n"
                "• owner daily/weekly digests\n"
                "• memory refresh\n"
                "• owner alerts по конфликту, активности, unanswered, newcomer\n"
                "• self-heal diagnostics\n\n"
                "Главные owner-команды по ролям:\n"
                "• группы: /whatshappening, /chatdeep, /summary24h, /conflicts\n"
                "• люди: /whois, /profilecheck, /watchlist, /reliable, /suspects, /portrait, /history, /ownergraph, /achaudit\n"
                "• техсостояние: /ownerreport, /qualityreport, /gitstatus, /errors, /routes\n"
                "• repair: /selfhealstatus, /selfhealrun, /selfhealapprove, /selfhealdeny\n\n"
                "Ключевые ограничения:\n"
                "• owner alerts идут с cooldown и не должны засыпать личку дублями\n"
                "• restart supervisor не должен валить enterprise_server\n"
                "• ответы Jarvis должны опираться на память, историю и локальный контекст, а не на выдумку"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Что умеет Jarvis", "callback_data": "ui:panel:owner_capabilities"}, {"text": "Авто-режимы и алерты", "callback_data": "ui:panel:owner_automation"}],
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands"}, {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}],
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
        if section == "owner_capabilities" and user_id == self.owner_user_id:
            text = (
                "JARVIS • ЧТО УМЕЕТ JARVIS\n\n"
                "Это карта возможностей системы без внутреннего маркетинга и без скрытых режимов.\n\n"
                "Основные контуры:\n"
                "• Локальный chat reasoning по истории, reply-thread и памяти\n"
                "• Память по чатам, участникам, relation-layer и owner cross-chat context\n"
                "• Group analysis: /chatdeep, /whatshappening, /summary24h, /conflicts\n"
                "• Профили людей: /whois, /profilecheck, /watchlist, /reliable, /suspects, /history, /portrait, /memoryuser, /ownergraph\n"
                "• Runtime/ops: /ownerreport, /qualityreport, /gitstatus, /errors, /routes\n"
                "• Файлы и медиа: /sdls, /sdsend, /sdsave, анализ документов и фото\n"
                "• Runtime hardening: supervisor, health-check, self-heal, owner alerts\n\n"
                "Что умеет автоматически:\n"
                "• daily/weekly owner digests\n"
                "• memory refresh по чатам\n"
                "• owner alerts по конфликту, всплеску активности, вопросам без ответа и новым заметным участникам\n"
                "• self-heal diagnostics и bounded repair playbooks\n\n"
                "Как лучше пользоваться:\n"
                "• для одной группы: /chatdeep или /summary24h\n"
                "• для всех групп сразу: /whatshappening\n"
                "• для человека: /whois или /portrait\n"
                "• для общей картины по Дмитрию: /ownergraph\n"
                "• для техсостояния: owner runtime / git / selfheal панели"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Авто-режимы и алерты", "callback_data": "ui:panel:owner_automation"}, {"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}],
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands"}, {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_automation" and user_id == self.owner_user_id:
            text = (
                "JARVIS • АВТО-РЕЖИМЫ И АЛЕРТЫ\n\n"
                "Здесь описано, что бот делает сам без ручной команды владельца.\n\n"
                "Автоматические процессы:\n"
                "• heartbeat и runtime health-check\n"
                "• health-aware supervisor loop\n"
                "• scheduled backup\n"
                "• memory refresh по активным чатам\n"
                "• daily owner digest\n"
                "• weekly owner report\n"
                "• self-heal diagnostics и bounded repair loop\n\n"
                "Owner alerts сейчас шлются по сигналам:\n"
                "• конфликт/шум\n"
                "• всплеск активности\n"
                "• вопросы без ответа\n"
                "• новый заметный участник\n\n"
                "Как устроены ограничения:\n"
                "• по каждому чату и типу сигнала есть cooldown\n"
                "• алерты не должны лупить бесконечно по одному и тому же событию\n"
                "• если сигналов нет, owner-личка не засоряется\n\n"
                "Что смотреть руками:\n"
                "• owner runtime panel — для процесса и среды\n"
                "• owner selfheal panel — для инцидентов и repair\n"
                "• owner overview / owner people — для содержательного контекста"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Что умеет Jarvis", "callback_data": "ui:panel:owner_capabilities"}, {"text": "Автовосстановление", "callback_data": "ui:panel:owner_selfheal"}],
                    [{"text": "Среда и рантайм", "callback_data": "ui:panel:owner_runtime"}, {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_memory" and user_id == self.owner_user_id:
            text = (
                "JARVIS • ПАМЯТЬ И ЧАТЫ\n\n"
                "Owner-only контур памяти и поиска по истории.\n"
                "Здесь только инженерные инструменты: поднять контекст, проверить память, собрать digest, найти источник фразы.\n\n"
                "Память и поиск:\n"
                "• /remember <факт> — записать факт в память чата\n"
                "• /recall [запрос] — поднять релевантные факты и события\n"
                "• /search <запрос> — поиск по chat_events\n"
                "• /memorychat [запрос] — показать текущий chat memory слой\n"
                "• /memoryuser @username|user_id — показать user memory по участнику\n"
                "• /memorysummary — показать summary memory snapshots\n"
                "• /whois @username|user_id — профиль участника с памятью, поведением и следами по чатам\n"
                "• /profilecheck @username|user_id — усиленная проверка профиля с visual/repeat сигналами\n"
                "• /watchlist [chat_id] — рисковые и проблемные участники по группе\n"
                "• /reliable [chat_id] — самые надёжные и полезные участники по группе\n"
                "• /suspects [chat_id] — suspect/scam/bait сигналы по людям с учётом тихого анализа фото\n\n"
                "История и digest:\n"
                "• /who_said <запрос> — кто чаще писал фразу/слово\n"
                "• /history @username — timeline участника\n"
                "• /daily [YYYY-MM-DD] — активность за день в текущем чате\n"
                "• /digest [YYYY-MM-DD] — digest по текущему чату\n"
                "• /chatdigest <chat_id> [YYYY-MM-DD] — digest по конкретной группе из owner-лички\n"
                "• /chatdeep [chat_id] — глубокий профиль группы и её памяти\n"
                "• /whatshappening [chat_id] — обзор по активным чатам или конкретной группе\n"
                "• /summary24h [chat_id] — краткий digest за 24 часа\n"
                "• /conflicts [chat_id] — конфликтные сигналы и напряжённые reply-пары\n"
                "• /portrait [@username] — AI-портрет участника по текущему чату\n"
                "• /achaudit [количество] — последние выдачи ачивок по людям и чатам\n\n"
                "Экспорт и сервис:\n"
                "• /export chat|today|@username|user_id — выгрузка событий\n"
                "• /reset — очистка контекста текущего чата\n\n"
                "Подсказки:\n"
                "• /history, /portrait и /whois можно вызывать через reply на сообщение\n"
                "• /whatshappening без chat_id показывает сводку по активным чатам владельца\n"
                "• /chatdeep, /summary24h и /conflicts в группе можно вызывать без chat_id\n"
                "• это owner-инструменты, публичный memory/help слой для остальных отключён"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands:memory_audit"}, {"text": "Файлы и медиа", "callback_data": "ui:panel:owner_files"}],
                    [{"text": "Среда и рантайм", "callback_data": "ui:panel:owner_runtime"}, {"text": "Модерация", "callback_data": "ui:panel:owner_moderation"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_overview" and user_id == self.owner_user_id:
            text = (
                "JARVIS • ОБЗОР ЧАТОВ\n\n"
                "Раздел для быстрого понимания, что происходит по группам без ручного ковыряния истории.\n\n"
                "Главные команды:\n"
                "• /whatshappening — сводка по активным чатам за последние 24 часа\n"
                "• /whatshappening <chat_id> — deep-view по конкретной группе\n"
                "• /chatdeep [chat_id] — глубокий профиль группы и памяти\n"
                "• /summary24h [chat_id] — краткий digest за сутки\n"
                "• /chatdigest <chat_id> [YYYY-MM-DD] — digest по конкретному дню\n"
                "• /conflicts [chat_id] — признаки срача, грубости и напряжённых reply-пар\n\n"
                "Новые срезы по людям внутри deep-analysis:\n"
                "• /chatdeep теперь включает watchlist и reliable блоки прямо в профиле чата\n"
                "• /watchlist [chat_id] — быстрый список проблемных участников\n"
                "• /reliable [chat_id] — быстрый список надёжных участников\n"
                "• /suspects [chat_id] — визуально/поведенчески подозрительные аккаунты\n\n"
                "Когда что использовать:\n"
                "• если нужен общий срез по всем чатам: /whatshappening\n"
                "• если нужно понять одну группу глубже: /chatdeep\n"
                "• если нужно быстрое краткое summary: /summary24h\n"
                "• если подозреваешь конфликт или шум: /conflicts"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}, {"text": "Люди и связи", "callback_data": "ui:panel:owner_people"}],
                    [{"text": "Watchlist", "callback_data": "ui:panel:owner_watchlist"}, {"text": "Suspects", "callback_data": "ui:panel:owner_suspects"}],
                    [{"text": "Надёжные", "callback_data": "ui:panel:owner_reliable"}],
                    [{"text": "Что умеет Jarvis", "callback_data": "ui:panel:owner_capabilities"}, {"text": "Карта системы", "callback_data": "ui:panel:owner_system_map"}],
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands:memory_audit"}, {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_people" and user_id == self.owner_user_id:
            text = (
                "JARVIS • ЛЮДИ И СВЯЗИ\n\n"
                "Этот экран про участников, пересечения и social context вокруг Дмитрия.\n\n"
                "Главные команды:\n"
                "• /whois @username|user_id — профиль участника с памятью, поведением и следами по чатам\n"
                "• /profilecheck @username|user_id — расширенная проверка профиля и visual memory\n"
                "• /watchlist [chat_id] — проблемные/рисковые участники по группе\n"
                "• /reliable [chat_id] — надёжные и полезные участники по группе\n"
                "• /suspects [chat_id] — suspect/scam/bait и bot-like сигналы по группе\n"
                "• /ownergraph — cross-chat social graph владельца\n"
                "• /achaudit [количество] — аудит последних ачивок\n"
                "• /memoryuser @username|user_id — сырой user memory слой\n"
                "• /history @username — timeline участника в текущем чате\n"
                "• /portrait [@username] — AI-портрет участника\n\n"
                "Подсказки:\n"
                "• /whois, /history и /portrait можно вызывать reply на сообщение\n"
                "• /watchlist полезен, когда нужно быстро понять, кто шумит, конфликтует или флудит\n"
                "• /reliable полезен, когда нужно понять, на кого можно опереться в группе\n"
                "• /suspects полезен, когда нужно поймать bait/scam/bot-like аккаунты и визуальные сигналы по фото\n"
                "• /ownergraph полезен, когда нужно понять, кто чаще всего пересекается с Дмитрием по разным чатам\n"
                "• /memoryuser полезен для проверки, что именно лежит в памяти, без AI-обработки"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Обзор чатов", "callback_data": "ui:panel:owner_overview"}, {"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}],
                    [{"text": "Watchlist", "callback_data": "ui:panel:owner_watchlist"}, {"text": "Suspects", "callback_data": "ui:panel:owner_suspects"}],
                    [{"text": "Надёжные", "callback_data": "ui:panel:owner_reliable"}],
                    [{"text": "Что умеет Jarvis", "callback_data": "ui:panel:owner_capabilities"}, {"text": "Карта системы", "callback_data": "ui:panel:owner_system_map"}],
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands:memory_audit"}, {"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_watchlist" and user_id == self.owner_user_id:
            return self._build_owner_people_live_panel(bridge, "watchlist", payload)
        if section == "owner_suspects" and user_id == self.owner_user_id:
            return self._build_owner_people_live_panel(bridge, "suspects", payload)
        if section == "owner_reliable" and user_id == self.owner_user_id:
            return self._build_owner_people_live_panel(bridge, "reliable", payload)
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
                    [{"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}, {"text": "Все команды", "callback_data": "ui:panel:owner_commands:runtime_audit"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_live" and user_id == self.owner_user_id:
            return self._build_owner_runtime_summary(bridge)
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
                "JARVIS • МОДЕРАЦИЯ\n\n"
                "Owner-only контур модерации. Бот не ведёт публичный диалог и не обслуживает пользовательский help/UI.\n"
                "Здесь только реальные санкции, предупреждения, welcome и owner-report по спорным кейсам.\n\n"
                "Auto-moderation сейчас:\n"
                "• auto-ban отключён\n"
                "• бот сам даёт только warn или временный mute\n"
                "• тяжёлые кейсы отправляются владельцу отдельным owner-report в ЛС\n"
                "• owner-report должен содержать факт, контекст и предлагаемое решение\n"
                "• бот не спорит с явными нарушениями, а переходит к санкции\n\n"
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
                "Welcome:\n"
                "• /welcome on|off|status\n"
                "• /setwelcome <текст>\n"
                "• /resetwelcome"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Кабинет модерации", "callback_data": "ui:adm:moderation"}, {"text": "Настройки warn", "callback_data": "ui:adm:warns"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_commands" and user_id == self.owner_user_id:
            return self._build_owner_commands_panel(payload)
        if section == "profile":
            if user_id == self.owner_user_id:
                return self.build_control_panel(bridge, user_id, "owner_root")
            return self.build_public_control_panel(bridge, user_id, section, payload)
        if section == "achievements":
            text = (
                "JARVIS • ДОСТИЖЕНИЯ\n\n"
                "Коллекция участника: открытые ачивки, скрытые слоты и ближайший прогресс.\n\n"
                + bridge.legacy.render_achievements(user_id)
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Профиль", "callback_data": "ui:profile"}, {"text": "Топы", "callback_data": "ui:top"}],
                    [{"text": "Рейтинг", "callback_data": "ui:top:achievements:1"}, {"text": "Реакции", "callback_data": "ui:top:reactions:1"}],
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
                "Проверка строится по активным санкциям, предупреждениям и истории решений.",
                "",
                "Текущее состояние:",
                f"• Активные баны: {len(snapshot.get('active_bans', []))}",
                f"• Активные муты: {len(snapshot.get('active_mutes', []))}",
                f"• Активные предупреждения: {snapshot.get('active_warnings', 0)}",
                f"• Подтвержденные нарушения: {snapshot.get('confirmed_violations', 0)}",
                f"• Legacy warnings: {snapshot.get('legacy_user_warnings', 0)}",
                f"• Прошлые апелляции: {snapshot.get('past_appeals', 0)}",
                "",
                "Если активных оснований нет или срок санкции уже истёк, ограничение может быть снято автоматически.",
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
        if user_id == self.owner_user_id:
            return self.build_control_panel(bridge, user_id, "owner_root")
        return self.build_public_control_panel(bridge, user_id, section, payload)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
