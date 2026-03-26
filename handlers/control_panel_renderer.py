from datetime import datetime
from typing import Callable, Optional, Tuple


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
            warn_lines = ["JARVIS • WARN SYSTEM", ""]
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
                    [{"text": "Warn settings", "callback_data": "ui:adm:warns"}, {"text": "Очередь апелляций", "callback_data": "ui:adm:queue"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return "\n".join(lines), markup
        if section == "owner_root" and user_id == self.owner_user_id:
            text = (
                "JARVIS • OWNER PANEL\n\n"
                "Это центральная админ-панель проекта.\n"
                "Здесь собраны все owner-команды, runtime-сводки, git/logs сценарии, работа с памятью чатов, файлами и live-data.\n\n"
                "Как пользоваться:\n"
                "• разделы ниже открывают экраны с пояснениями и быстрыми сводками\n"
                "• команды без параметров можно запускать прямо как отдельные команды из чата\n"
                "• команды с параметрами здесь описаны с примерами и usage-шаблонами\n"
                "• если нужен полный справочник без сокращений, открывай раздел «Все команды»\n\n"
                "Разделы:\n"
                "• Runtime: здоровье процесса, ресурсы, рестарт, owner report\n"
                "• Git и логи: branch, commits, ошибки, upgrade\n"
                "• Память и чаты: history, digest, recall, portraits, export\n"
                "• Файлы и медиа: sdcard-команды, файлы, документы, media-context\n"
                "• Live-data: погода, курсы, новости, current-facts\n"
                "• Self-heal: incidents, approval gate, bounded repair playbooks\n"
                "• Модерация: sanctions, warns, welcome, appeals\n"
                "• Все команды: полный текстовый реестр проекта"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Runtime", "callback_data": "ui:panel:owner_runtime"}, {"text": "Git и логи", "callback_data": "ui:panel:owner_git"}],
                    [{"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}, {"text": "Файлы и медиа", "callback_data": "ui:panel:owner_files"}],
                    [{"text": "Live-data", "callback_data": "ui:panel:owner_live"}, {"text": "Self-heal", "callback_data": "ui:panel:owner_selfheal"}],
                    [{"text": "Модерация", "callback_data": "ui:panel:owner_moderation"}],
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_runtime" and user_id == self.owner_user_id:
            text = (
                "JARVIS • OWNER RUNTIME\n\n"
                "Раздел для проверки живости бота и текущего runtime.\n"
                "Сюда имеет смысл идти, если бот тупит, не отвечает, медленно работает или нужно понять общее состояние среды.\n\n"
                f"{bridge.render_owner_report_text(user_id)}\n\n"
                "Команды раздела:\n"
                "• /status — общая служебная сводка по текущему чату и runtime\n"
                "• /ownerreport — расширенный owner-отчёт\n"
                "• /resources — память, CPU, swap\n"
                "• /topproc — самые тяжёлые процессы\n"
                "• /disk — заполнение дисков\n"
                "• /net — сетевые интерфейсы и трафик\n"
                "• /restart — перезапуск bridge через supervisor\n"
                "• /ownerautofix on|off|status — автоисправление текста владельца"
                "\n• /selfhealstatus — последние self-heal incidents и state machine"
                "\n• /selfhealrun <playbook|incident_id> [dry-run|execute] — bounded self-heal запуск"
                "\n• /selfhealapprove <incident_id> — owner approval queued incident"
                "\n• /selfhealdeny <incident_id> — deny/manual follow-up"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Git и логи", "callback_data": "ui:panel:owner_git"}, {"text": "Self-heal", "callback_data": "ui:panel:owner_selfheal"}],
                    [{"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}],
                    [{"text": "Все команды", "callback_data": "ui:panel:owner_commands"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_git" and user_id == self.owner_user_id:
            text = (
                "JARVIS • OWNER GIT / LOGS\n\n"
                "Раздел для проектных изменений, истории коммитов и ошибок runtime.\n"
                "Если нужно понять, что поменялось, в каком состоянии git и что сломалось в хвосте логов, смотреть сюда.\n\n"
                f"{self.render_git_status_summary(bridge.script_path.parent)}\n\n"
                f"{self.render_git_last_commits(bridge.script_path.parent, limit=5)}\n\n"
                "Команды раздела:\n"
                "• /gitstatus — worktree, branch, upstream\n"
                "• /gitlast 5 — последние коммиты, число можно менять\n"
                "• /errors 10 — только реальные ошибки и поломки\n"
                "• /events 10 — все служебные события\n"
                "• /events restart 10 — только рестарты\n"
                "• /events access 10 — только блокировки доступа\n"
                "• /events system 10 — только системные operational-события\n"
                "• /routes 10 — последние route decisions и self-check telemetry\n"
                "• /upgrade <что изменить> — постановка задачи на изменение кода\n\n"
                "Примеры:\n"
                "• /gitlast 12\n"
                "• /errors 20\n"
                "• /events 20\n"
                "• /events restart 20\n"
                "• /events access 20\n"
                "• /routes 10\n"
                "• /upgrade добавь новый route для ..."
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Runtime", "callback_data": "ui:panel:owner_runtime"}, {"text": "Ошибки / логи", "callback_data": "ui:panel:owner_commands"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_memory" and user_id == self.owner_user_id:
            text = (
                "JARVIS • OWNER MEMORY / CHAT\n\n"
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
                    [{"text": "Файлы и медиа", "callback_data": "ui:panel:owner_files"}, {"text": "Live-data", "callback_data": "ui:panel:owner_live"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_files" and user_id == self.owner_user_id:
            text = (
                "JARVIS • OWNER FILES / MEDIA\n\n"
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
                    [{"text": "Память и чаты", "callback_data": "ui:panel:owner_memory"}, {"text": "Live-data", "callback_data": "ui:panel:owner_live"}],
                    [{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
        if section == "owner_live" and user_id == self.owner_user_id:
            text = (
                "JARVIS • OWNER LIVE DATA\n\n"
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
            incidents = bridge.state.get_recent_self_heal_incidents(limit=10)
            if payload.isdigit():
                incident = bridge.state.get_self_heal_incident(int(payload))
            else:
                incident = None
            if incident is not None:
                text = (
                    "JARVIS • OWNER SELF-HEAL\n\n"
                    f"Incident #{int(incident['id'])}\n"
                    f"problem={incident['problem_type']}\n"
                    f"signal={incident['signal_code']}\n"
                    f"state={incident['state']}\n"
                    f"severity={incident['severity']}\n"
                    f"risk={incident['risk_level']}\n"
                    f"autonomy={incident['autonomy_level']}\n"
                    f"playbook={incident['suggested_playbook'] or '-'}\n"
                    f"verification={incident['verification_status'] or '-'}\n\n"
                    f"summary:\n{incident['summary'] or '-'}\n\n"
                    f"evidence:\n{self.truncate_text(incident['evidence'] or '-', 500)}"
                )
                keyboard = []
                if str(incident["state"] or "") in {"awaiting_approval", "repair_planned"}:
                    keyboard.append(
                        [
                            {"text": "Approve", "callback_data": f"ui:selfheal:approve:{int(incident['id'])}"},
                            {"text": "Deny", "callback_data": f"ui:selfheal:deny:{int(incident['id'])}"},
                        ]
                    )
                keyboard.append([{"text": "К списку", "callback_data": "ui:panel:owner_selfheal"}])
                keyboard.append([{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}])
                return text, {"inline_keyboard": keyboard}
            lines = [
                "JARVIS • OWNER SELF-HEAL",
                "",
                "Команды:",
                "• /selfhealstatus",
                "• /selfhealrun <playbook|incident_id> [dry-run|execute]",
                "• /selfhealapprove <incident_id>",
                "• /selfhealdeny <incident_id>",
                "",
                "Последние incidents:",
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
                        [{"text": f"Incident #{int(row['id'])}", "callback_data": f"ui:selfheal:view:{int(row['id'])}"}]
                    )
            keyboard.append([{"text": "Runtime", "callback_data": "ui:panel:owner_runtime"}, {"text": "Все команды", "callback_data": "ui:panel:owner_commands"}])
            keyboard.append([{"text": "Назад", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}])
            return "\n".join(lines), {"inline_keyboard": keyboard}
        if section == "owner_moderation" and user_id == self.owner_user_id:
            text = (
                "JARVIS • OWNER MODERATION\n\n"
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
            text = (
                self.render_admin_command_catalog(
                    owner_user_id=self.owner_user_id,
                    owner_username=self.owner_username,
                )
                + "\n\nПолный legacy-список команд:\n\n"
                + self.commands_list_text
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "Owner panel", "callback_data": "ui:panel:owner_root"}],
                    [{"text": "Главная", "callback_data": "ui:home"}],
                ]
            }
            return text, markup
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
