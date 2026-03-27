import os
from pathlib import Path
from typing import Dict, List


def build_help_panel_text(
    section: str,
    *,
    owner_username: str,
    owner_user_id: int,
    public_help_text: str,
    public_achievements_help_text: str,
    public_appeal_help_text: str,
) -> str:
    owner_line = f"Создатель: {owner_username}\nID владельца: {owner_user_id}"
    panels = {
        "public": public_help_text,
        "public_achievements": public_achievements_help_text,
        "public_appeal": public_appeal_help_text,
        "main": (
            "JARVIS • ГЛАВНОЕ МЕНЮ\n\n"
            "Выбирай раздел кнопками ниже.\n"
            "Сообщение обновляется на месте, без мусора в чате.\n\n"
            "Быстрый старт:\n"
            "• /status — состояние бота\n"
            "• /rating — ваш уровень и прогресс\n"
            "• /achievements — ваши достижения\n"
            "• /top — общий топ участников\n"
            "• /stats — статистика чата\n\n"
            "Режимы ответа:\n"
            "• /mode jarvis — обычный режим\n"
            "• /mode code — инженерный режим\n"
            "• /mode strict — короткие ответы\n\n"
            "Сервис:\n"
            "• /help — открыть это меню\n"
            "• /commands — открыть это меню\n"
            "• /ping — проверка отклика\n"
            "• /appeal <текст> — апелляция владельцу\n\n"
            + owner_line
        ),
        "access": (
            "ДОСТУП И РЕЖИМЫ\n\n"
            "Доступ:\n"
            "• бот отвечает только владельцу\n"
            "• вход по паролю отключён\n\n"
            "Как бот отвечает:\n"
            "• в личке — только владельцу\n"
            "• в группе — только на обращения владельца\n\n"
            "Режимы:\n"
            "• /mode jarvis\n"
            "• /mode code\n"
            "• /mode strict\n\n"
            "Автоисправление владельца:\n"
            "• /ownerautofix on\n"
            "• /ownerautofix off\n"
            "• /ownerautofix status"
        ),
        "memory": (
            "ПАМЯТЬ И СТАТИСТИКА\n\n"
            "Память и поиск:\n"
            "• /remember <факт>\n"
            "• /recall [запрос]\n"
            "• /search <запрос>\n"
            "• /who_said <запрос>\n\n"
            "История и профили:\n"
            "• /history [@username|user_id]\n"
            "• /portrait [@username]\n"
            "• /daily [YYYY-MM-DD]\n"
            "• /digest [YYYY-MM-DD]\n"
            "• /chatdigest <chat_id> [YYYY-MM-DD]\n"
            "• /export [chat|today|@username|user_id]\n\n"
            "Активность:\n"
            "• /top\n"
            "• /topweek\n"
            "• /topday\n"
            "• /stats\n"
            "• /reset"
        ),
        "moderation": (
            "МОДЕРАЦИЯ\n\n"
            "Работает в группе и супергруппе.\n"
            "Цель можно указать reply, @username или user_id.\n\n"
            "Основные действия:\n"
            "• /ban <цель> [причина]\n"
            "• /unban <цель>\n"
            "• /mute <цель> [причина]\n"
            "• /unmute <цель>\n"
            "• /kick <цель> [причина]\n"
            "• /tban 1d <цель> [причина]\n"
            "• /tmute 1h <цель> [причина]"
        ),
        "warns": (
            "ПРЕДУПРЕЖДЕНИЯ\n\n"
            "Быстрые команды:\n"
            "• /warn <цель> [причина]\n"
            "• /dwarn <цель> [причина]\n"
            "• /swarn <цель> [причина]\n"
            "• /warns <цель>\n"
            "• /warnreasons <цель>\n"
            "• /rmwarn <цель>\n"
            "• /resetwarn <цель>\n\n"
            "Настройки системы:\n"
            "• /setwarnlimit <число>\n"
            "• /setwarnmode mute|tmute 1h|ban|tban 1d|kick\n"
            "• /warntime 7d|off\n"
            "• /modlog"
        ),
        "welcome": (
            "ПРИВЕТСТВИЕ\n\n"
            "Управление:\n"
            "• /welcome on\n"
            "• /welcome off\n"
            "• /welcome status\n"
            "• /setwelcome <текст>\n"
            "• /resetwelcome\n\n"
            "Переменные шаблона:\n"
            "• {first_name}\n"
            "• {last_name}\n"
            "• {full_name}\n"
            "• {username}\n"
            "• {chat_title}"
        ),
        "creator": (
            "ВЛАДЕЛЕЦ И СЕРВИС\n\n"
            "Служебные команды:\n"
            "• /upgrade <что изменить>\n"
            "• /restart\n"
            "  сообщает статус: self-restart отключён, внешний restart делает supervisor\n"
            "• /status\n"
            "• /ownerreport\n"
            "• /qualityreport\n"
            "• /selfhealstatus\n"
            "• /selfhealrun <playbook|incident_id> [dry-run|execute]\n"
            "• /selfhealapprove <incident_id>\n"
            "• /selfhealdeny <incident_id>\n"
            "• /gitstatus\n"
            "• /gitlast [количество]\n"
            "• /errors [количество]\n"
            "• /routes [количество]\n"
            "• /appeals\n"
            "• /appeal_review <id>\n"
            "• /appeal_approve <id> [решение]\n"
            "• /appeal_reject <id> [решение]\n"
            "• /help\n"
            "• /commands\n\n"
            "Интеграция:\n"
            "• owner id синхронизирован с основной системой Jarvis\n"
            "• рейтинг, достижения и апелляции идут через legacy jarvis.db\n"
            "• если Enterprise Core недоступен, бот пишет: Enterprise Core выключен"
        ),
    }
    default_section = "public" if section.startswith("public") else "main"
    return panels.get(section, panels[default_section])


def build_help_panel_markup(section: str) -> dict:
    if section == "public":
        return {
            "inline_keyboard": [
                [{"text": "Рейтинг", "callback_data": "ui:profile"}],
                [{"text": "Ачивки", "callback_data": "help:public_achievements"}],
                [{"text": "Апелляция", "callback_data": "help:public_appeal"}],
                [{"text": "Главная", "callback_data": "ui:home"}],
            ]
        }
    if section in {"public_achievements", "public_appeal"}:
        return {
            "inline_keyboard": [
                [{"text": "Рейтинг", "callback_data": "ui:profile"}],
                [{"text": "Общая инструкция", "callback_data": "help:public"}],
                [{"text": "Главная", "callback_data": "ui:home"}],
            ]
        }
    labels: Dict[str, str] = {
        "main": "Главная",
        "access": "Доступ",
        "memory": "Память",
        "moderation": "Модерация",
        "warns": "Варны",
        "welcome": "Приветствие",
        "creator": "Сервис",
    }
    rows = [
        [
            {"text": labels["main"], "callback_data": "help:main"},
            {"text": labels["access"], "callback_data": "help:access"},
            {"text": labels["memory"], "callback_data": "help:memory"},
        ],
        [
            {"text": labels["moderation"], "callback_data": "help:moderation"},
            {"text": labels["warns"], "callback_data": "help:warns"},
            {"text": labels["welcome"], "callback_data": "help:welcome"},
        ],
        [
            {"text": labels["creator"], "callback_data": "help:creator"},
        ],
    ]
    return {"inline_keyboard": rows}


def build_voice_transcription_help(
    *,
    tmp_dir: Path,
    stt_backend: str,
    audio_transcribe_model: str,
    openai_api_key_present: bool,
) -> str:
    issues: List[str] = []

    if stt_backend not in {"openai", "ai"}:
        issues.append(f"неподдерживаемый STT backend: {stt_backend}")
    if not audio_transcribe_model:
        issues.append("не задан AUDIO_TRANSCRIBE_MODEL")
    if not openai_api_key_present:
        issues.append("не задан OPENAI_API_KEY для AI-распознавания голосовых сообщений")

    if tmp_dir is not None:
        if not tmp_dir.exists():
            issues.append(f"TMP_DIR недоступен: {tmp_dir}")
        elif not tmp_dir.is_dir():
            issues.append(f"TMP_DIR не является директорией: {tmp_dir}")
        elif not os.access(tmp_dir, os.W_OK):
            issues.append(f"нет прав на запись в TMP_DIR: {tmp_dir}")

    if not issues:
        return (
            "Не удалось распознать голосовое. Дополнительные Android/Telegram-права для этого не нужны. "
            "Проблема, вероятно, в формате аудио, сети или в speech-to-text backend. "
            "Проверь runtime-лог bridge."
        )

    details = "\n".join(f"- {item}" for item in issues)
    return (
        "Не удалось распознать голосовое. Дополнительные Android/Telegram-права для этого не нужны.\n"
        f"{details}"
    )
