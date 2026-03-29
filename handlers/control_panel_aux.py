from typing import TYPE_CHECKING, Tuple


def build_admin_warns_panel(renderer: "ControlPanelRenderer", bridge: "TelegramBridge", payload: str) -> Tuple[str, dict]:
    selected_chat_id = 0
    try:
        selected_chat_id = int((payload or "0").strip())
    except ValueError:
        selected_chat_id = 0
    with bridge.state.db_lock:
        rows = bridge.state.db.execute(
            "SELECT chat_id, warn_limit, warn_mode, warn_expire_seconds FROM warn_settings ORDER BY chat_id DESC LIMIT 12"
        ).fetchall()
    settings_map = {int(row[0]): (int(row[1]), str(row[2]), int(row[3] or 0)) for row in rows}
    chat_candidates = list(settings_map.keys())
    for chat_id in bridge.state.get_managed_group_chat_ids():
        if chat_id not in chat_candidates:
            chat_candidates.append(chat_id)
    chat_candidates = chat_candidates[:8]
    if selected_chat_id == 0 and chat_candidates:
        selected_chat_id = int(chat_candidates[0])
    warn_limit, warn_mode, warn_expire_seconds = bridge.state.get_warn_settings(selected_chat_id) if selected_chat_id else (3, "mute", 0)
    chat_title = bridge.state.get_chat_title(selected_chat_id, f"chat={selected_chat_id}") if selected_chat_id else "чат не выбран"
    warn_lines = [
        "JARVIS • НАСТРОЙКИ ПРЕДУПРЕЖДЕНИЙ",
        "",
        "Здесь уже не просто справка, а быстрые owner-контролы warn-системы по группам.",
        "",
    ]
    if not chat_candidates:
        warn_lines.append("Управляемые группы пока не найдены.")
    else:
        warn_lines.extend([
            f"Текущий чат: {chat_title}",
            f"chat_id={selected_chat_id}",
            f"Лимит warn: {warn_limit}",
            f"Режим: {renderer._format_warn_mode_label(warn_mode)}",
            f"Срок warn: {renderer.format_duration_seconds(warn_expire_seconds) if warn_expire_seconds > 0 else 'off'}",
            "",
            "Быстрые действия ниже сразу меняют настройки для выбранной группы.",
        ])
    keyboard = []
    if chat_candidates:
        row_buttons = []
        for chat_id in chat_candidates[:4]:
            row_buttons.append({"text": renderer.truncate_text(bridge.state.get_chat_title(chat_id, str(chat_id)), 18), "callback_data": f"ui:warncfg:chat:{chat_id}"})
        if row_buttons:
            keyboard.append(row_buttons)
        if len(chat_candidates) > 4:
            row_buttons = []
            for chat_id in chat_candidates[4:8]:
                row_buttons.append({"text": renderer.truncate_text(bridge.state.get_chat_title(chat_id, str(chat_id)), 18), "callback_data": f"ui:warncfg:chat:{chat_id}"})
            keyboard.append(row_buttons)
        keyboard.extend([
            [{"text": "Лимит 3", "callback_data": f"ui:warncfg:limit:{selected_chat_id}:3"}, {"text": "Лимит 4", "callback_data": f"ui:warncfg:limit:{selected_chat_id}:4"}, {"text": "Лимит 5", "callback_data": f"ui:warncfg:limit:{selected_chat_id}:5"}],
            [{"text": "Mute", "callback_data": f"ui:warncfg:mode:{selected_chat_id}:mute"}, {"text": "Kick", "callback_data": f"ui:warncfg:mode:{selected_chat_id}:kick"}, {"text": "Ban", "callback_data": f"ui:warncfg:mode:{selected_chat_id}:ban"}],
            [{"text": "TMute 1ч", "callback_data": f"ui:warncfg:mode:{selected_chat_id}:tmute:3600"}, {"text": "TMute 24ч", "callback_data": f"ui:warncfg:mode:{selected_chat_id}:tmute:86400"}],
            [{"text": "TBan 1д", "callback_data": f"ui:warncfg:mode:{selected_chat_id}:tban:86400"}, {"text": "TBan 7д", "callback_data": f"ui:warncfg:mode:{selected_chat_id}:tban:604800"}],
            [{"text": "TTL off", "callback_data": f"ui:warncfg:ttl:{selected_chat_id}:0"}, {"text": "TTL 7д", "callback_data": f"ui:warncfg:ttl:{selected_chat_id}:604800"}, {"text": "TTL 30д", "callback_data": f"ui:warncfg:ttl:{selected_chat_id}:2592000"}],
        ])
    keyboard.extend([
        [{"text": "Модерация", "callback_data": "ui:adm:moderation"}, {"text": "Очередь апелляций", "callback_data": "ui:adm:queue"}],
        [{"text": "Главная", "callback_data": "ui:home"}],
    ])
    return "\n".join(warn_lines), {"inline_keyboard": keyboard}


def list_participant_profile_chats(_renderer: "ControlPanelRenderer", bridge: "TelegramBridge", limit: int = 12) -> list[tuple[int, str]]:
    with bridge.state.db_lock:
        rows = bridge.state.db.execute(
            """
            SELECT p.chat_id, COALESCE(NULLIF(c.chat_title, ''), CAST(p.chat_id AS TEXT)) AS chat_title,
                   MAX(p.updated_at) AS updated_at
            FROM participant_chat_profiles p
            LEFT JOIN chat_runtime_cache c ON c.chat_id = p.chat_id
            GROUP BY p.chat_id
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [(int(row["chat_id"] or 0), str(row["chat_title"] or "")) for row in rows]


def build_owner_people_live_panel(renderer: "ControlPanelRenderer", bridge: "TelegramBridge", mode: str, payload: str) -> Tuple[str, dict]:
    if mode == "watchlist":
        render_func = bridge.owner_handlers.render_watchlist_text
        title = "WATCHLIST"
    elif mode == "suspects":
        render_func = bridge.owner_handlers.render_suspects_text
        title = "SUSPECTS"
    else:
        render_func = bridge.owner_handlers.render_reliable_text
        title = "НАДЁЖНЫЕ УЧАСТНИКИ"
    if payload:
        try:
            target_chat_id = int(payload)
        except ValueError:
            target_chat_id = 0
    else:
        target_chat_id = 0
    if target_chat_id:
        text = f"JARVIS • {title}\n\n{render_func(bridge, target_chat_id)}"
    else:
        text = f"JARVIS • {title}\n\nЭто live-screen по participant profiles.\nВыбери чат кнопками ниже."
    chat_buttons = [
        {"text": renderer.truncate_text(chat_title, 22), "callback_data": f"ui:panel:owner_{mode}:{chat_id}"}
        for chat_id, chat_title in list_participant_profile_chats(renderer, bridge, limit=8)
    ]
    keyboard = [chat_buttons[index:index + 2] for index in range(0, len(chat_buttons), 2)]
    keyboard.extend([
        [{"text": "Люди и связи", "callback_data": "ui:panel:owner_people"}, {"text": "Обзор чатов", "callback_data": "ui:panel:owner_overview"}],
        [{"text": "Панель владельца", "callback_data": "ui:panel:owner_root"}, {"text": "Главная", "callback_data": "ui:home"}],
    ])
    return text, {"inline_keyboard": keyboard}


def build_top_navigation(top_key: str, page: int, *, home_label: str = "Главная") -> list[list[dict]]:
    prev_page = max(1, page - 1)
    next_page = page + 1
    return [
        [{"text": "Новый", "callback_data": "ui:top:all:1"}, {"text": "История", "callback_data": "ui:top:history:1"}],
        [{"text": "Неделя", "callback_data": "ui:top:week:1"}, {"text": "День", "callback_data": "ui:top:day:1"}],
        [{"text": "Вклад", "callback_data": "ui:top:social:1"}, {"text": "Сезон", "callback_data": "ui:top:season:1"}],
        [{"text": "Реакции+", "callback_data": "ui:top:reactions:1"}, {"text": "Реакции→", "callback_data": "ui:top:given:1"}],
        [{"text": "Активность", "callback_data": "ui:top:activity:1"}, {"text": "Поведение", "callback_data": "ui:top:behavior:1"}],
        [{"text": "Сообщения", "callback_data": "ui:top:messages:1"}, {"text": "Полезность", "callback_data": "ui:top:helpful:1"}],
        [{"text": "Стрик", "callback_data": "ui:top:streak:1"}, {"text": "Ачивки", "callback_data": "ui:top:achievements:1"}],
        [{"text": "◀️ Назад", "callback_data": f"ui:top:{top_key}:{prev_page}"}, {"text": f"Стр. {page}", "callback_data": f"ui:top:{top_key}:{page}"}, {"text": "Вперёд ▶️", "callback_data": f"ui:top:{top_key}:{next_page}"}],
        [{"text": home_label, "callback_data": "ui:home"}, {"text": "Профиль", "callback_data": "ui:profile"}],
    ]


if TYPE_CHECKING:
    from handlers.control_panel_renderer import ControlPanelRenderer
    from tg_codex_bridge import TelegramBridge
