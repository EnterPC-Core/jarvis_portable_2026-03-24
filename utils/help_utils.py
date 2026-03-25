import os
import shutil
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
            "Личный доступ:\n"
            "• /password <пароль> — открыть доступ в личке\n"
            "• владелец проходит без пароля\n\n"
            "Как бот отвечает:\n"
            "• в личке — после авторизации\n"
            "• в группе — по команде, reply или явному обращению\n\n"
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
            "• /status\n"
            "• /ownerreport\n"
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
    ffmpeg_binary: str,
    tmp_dir: Path,
    whisper_model: str,
    whisper_cpp_bin_path: str,
    whisper_cpp_models_dir: str,
) -> str:
    issues: List[str] = []

    ffmpeg_path = shutil.which(ffmpeg_binary)
    bundled_ffmpeg_path = ""
    if ffmpeg_path is None:
        try:
            import imageio_ffmpeg  # type: ignore

            bundled_ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            bundled_ffmpeg_path = ""
    if ffmpeg_path is None:
        if bundled_ffmpeg_path:
            ffmpeg_path = bundled_ffmpeg_path
        else:
            issues.append(f"ffmpeg не найден в PATH: {ffmpeg_binary}")

    whisper_cli_path = shutil.which("whisper")
    python_whisper_available = False
    try:
        import whisper  # type: ignore  # noqa: F401
    except ImportError:
        python_whisper_available = False
    else:
        python_whisper_available = True

    faster_whisper_available = False
    try:
        import faster_whisper  # type: ignore  # noqa: F401
    except ImportError:
        faster_whisper_available = False
    else:
        faster_whisper_available = True

    whisper_cpp_bin = Path(whisper_cpp_bin_path)
    whisper_cpp_model = Path(whisper_cpp_models_dir) / f"ggml-{whisper_model}.bin"
    whisper_cpp_ready = whisper_cpp_bin.exists() and whisper_cpp_model.exists()

    if whisper_cli_path is None and not python_whisper_available and not faster_whisper_available and not whisper_cpp_ready:
        issues.append(
            "не найден ни один backend whisper: CLI `whisper`, Python-модуль `whisper`, Python-модуль "
            f"`faster_whisper` или `{whisper_cpp_bin}` с моделью `{whisper_cpp_model.name}`"
        )
    elif whisper_cpp_bin.exists() and not whisper_cpp_model.exists():
        issues.append(f"для whisper.cpp отсутствует модель `{whisper_cpp_model.name}`")

    if tmp_dir is not None:
        if not tmp_dir.exists():
            issues.append(f"TMP_DIR недоступен: {tmp_dir}")
        elif not os.access(tmp_dir, os.W_OK):
            issues.append(f"нет прав на запись в TMP_DIR: {tmp_dir}")

    if not issues:
        return (
            "Не удалось распознать голосовое. Дополнительные Android/Telegram-права для этого не нужны. "
            "Проблема, вероятно, в формате аудио или в локальном окружении whisper. "
            "Проверь лог `tg_codex_bridge.py`."
        )

    details = "\n".join(f"- {item}" for item in issues)
    return (
        "Не удалось распознать голосовое. Дополнительные Android/Telegram-права для этого не нужны.\n"
        f"{details}"
    )
