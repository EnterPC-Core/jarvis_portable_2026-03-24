import time
from typing import Dict, List, Optional, Sequence

from bridge_repository import BridgeRepository, safe_int


RARITY_STYLES = {
    "common": ("Обычное", "⚪", 15),
    "rare": ("Редкое", "🔵", 35),
    "epic": ("Эпическое", "🟣", 70),
    "legendary": ("Легендарное", "🟠", 120),
    "mythic": ("Мифическое", "🌈", 180),
}

METRIC_LABELS = {
    "msg_count": "сообщения",
    "reactions_given": "поставленные реакции",
    "reactions_received": "полученные реакции",
    "activity_score": "очки активности",
    "helpful_messages": "полезные сообщения",
    "long_messages": "длинные сообщения",
    "replied_messages": "ответы в диалогах",
    "best_streak": "лучшая серия дней",
    "good_standing_days": "дни без санкций",
    "behavior_score": "оценка поведения",
    "account_age_days": "дней с момента входа",
}

ACHIEVEMENT_DEFS: Sequence[Dict[str, object]] = (
    {"code": "first_signal", "name": "Первый сигнал", "badge": "🛰️", "rarity": "common", "metric": "msg_count", "target": 5, "tier": 1, "category": "activity", "description": "Закрепиться в чате первыми 5 сообщениями.", "requirements": (("unique_days", 2),)},
    {"code": "starter_pack", "name": "Стартовый импульс", "badge": "🎯", "rarity": "common", "metric": "msg_count", "target": 40, "tier": 1, "category": "activity", "chain_code": "first_signal", "description": "Набрать 40 сообщений и не быть случайным залётом.", "requirements": (("unique_days", 4),)},
    {"code": "voice_of_room", "name": "Голос комнаты", "badge": "🎙️", "rarity": "rare", "metric": "msg_count", "target": 200, "tier": 2, "category": "activity", "chain_code": "starter_pack", "description": "Написать 200 сообщений."},
    {"code": "chat_pulse", "name": "Пульс чата", "badge": "💬", "rarity": "epic", "metric": "msg_count", "target": 500, "tier": 3, "category": "activity", "chain_code": "voice_of_room", "description": "Дойти до 500 сообщений."},
    {"code": "forum_engine", "name": "Двигатель обсуждений", "badge": "🧠", "rarity": "legendary", "metric": "msg_count", "target": 1500, "tier": 4, "category": "activity", "chain_code": "chat_pulse", "description": "Дойти до 1500 сообщений."},
    {"code": "signal_storm", "name": "Шторм сигналов", "badge": "🌩️", "rarity": "mythic", "metric": "msg_count", "target": 4000, "tier": 5, "category": "activity", "chain_code": "forum_engine", "description": "Дойти до 4000 сообщений."},
    {"code": "helper_10", "name": "Полезный участник", "badge": "🛠️", "rarity": "rare", "metric": "helpful_messages", "target": 10, "tier": 1, "category": "contribution", "description": "Набрать 10 полезных сообщений."},
    {"code": "helper_75", "name": "Инженер сообщества", "badge": "🧰", "rarity": "epic", "metric": "helpful_messages", "target": 75, "tier": 3, "category": "contribution", "chain_code": "helper_10", "description": "Набрать 75 полезных сообщений."},
    {"code": "advisor", "name": "Советник комнаты", "badge": "🧭", "rarity": "legendary", "metric": "helpful_messages", "target": 180, "tier": 4, "category": "contribution", "chain_code": "helper_75", "description": "Набрать 180 полезных сообщений."},
    {"code": "deep_diver", "name": "Глубокий разбор", "badge": "📚", "rarity": "rare", "metric": "long_messages", "target": 30, "tier": 2, "category": "quality", "description": "Написать 30 развёрнутых сообщений."},
    {"code": "essayist", "name": "Эссеист", "badge": "📝", "rarity": "epic", "metric": "long_messages", "target": 90, "tier": 3, "category": "quality", "chain_code": "deep_diver", "description": "Написать 90 развёрнутых сообщений."},
    {"code": "community_glue", "name": "Связующее звено", "badge": "🧩", "rarity": "epic", "metric": "replied_messages", "target": 60, "tier": 3, "category": "discussion", "description": "Часто участвовать в диалогах и тредах."},
    {"code": "thread_captain", "name": "Капитан тредов", "badge": "🪢", "rarity": "legendary", "metric": "replied_messages", "target": 180, "tier": 4, "category": "discussion", "chain_code": "community_glue", "description": "Собрать 180 reply-ответов."},
    {"code": "reaction_magnet", "name": "Магнит реакций", "badge": "✨", "rarity": "rare", "metric": "reactions_received", "target": 30, "tier": 2, "category": "social", "description": "Собрать 30 реакций от сообщества.", "requirements": (("msg_count", 40),)},
    {"code": "crowd_favorite", "name": "Любимец толпы", "badge": "🌟", "rarity": "epic", "metric": "reactions_received", "target": 90, "tier": 3, "category": "social", "chain_code": "reaction_magnet", "description": "Собрать 90 реакций.", "requirements": (("msg_count", 120),)},
    {"code": "icon_of_chat", "name": "Икона чата", "badge": "🌠", "rarity": "mythic", "metric": "reactions_received", "target": 180, "tier": 5, "category": "social", "chain_code": "crowd_favorite", "description": "Собрать 180 реакций."},
    {"code": "warm_support", "name": "Тёплая поддержка", "badge": "🤝", "rarity": "common", "metric": "reactions_given", "target": 20, "tier": 1, "category": "social", "description": "Поставить 20 реакций другим.", "requirements": (("msg_count", 20),)},
    {"code": "hype_engine", "name": "Разгоняющий хайп", "badge": "🔥", "rarity": "rare", "metric": "reactions_given", "target": 80, "tier": 2, "category": "social", "chain_code": "warm_support", "description": "Поставить 80 реакций.", "requirements": (("msg_count", 60),)},
    {"code": "social_battery", "name": "Социальная батарея", "badge": "🔋", "rarity": "epic", "metric": "reactions_given", "target": 200, "tier": 3, "category": "social", "chain_code": "hype_engine", "description": "Поставить 200 реакций.", "requirements": (("msg_count", 120),)},
    {"code": "steady_week", "name": "Ритм недели", "badge": "🗓️", "rarity": "rare", "metric": "best_streak", "target": 7, "tier": 2, "category": "consistency", "description": "Продержать серию из 7 дней."},
    {"code": "steady_month", "name": "Железная дисциплина", "badge": "⛓️", "rarity": "legendary", "metric": "best_streak", "target": 30, "tier": 4, "category": "consistency", "chain_code": "steady_week", "description": "Продержать серию из 30 дней."},
    {"code": "ritual_keeper", "name": "Хранитель ритуала", "badge": "🕯️", "rarity": "mythic", "metric": "best_streak", "target": 90, "tier": 5, "category": "consistency", "chain_code": "steady_month", "description": "Продержать серию из 90 дней."},
    {"code": "active_mode", "name": "Активный режим", "badge": "⚡", "rarity": "common", "metric": "activity_score", "target": 250, "tier": 1, "category": "activity", "description": "Набрать 250 очков активности.", "requirements": (("unique_days", 4),)},
    {"code": "live_wire", "name": "Живая искра", "badge": "🔌", "rarity": "rare", "metric": "activity_score", "target": 700, "tier": 2, "category": "activity", "chain_code": "active_mode", "description": "Набрать 700 очков активности.", "requirements": (("unique_days", 10),)},
    {"code": "overclocked", "name": "На оверклоке", "badge": "🚀", "rarity": "legendary", "metric": "activity_score", "target": 1500, "tier": 4, "category": "activity", "chain_code": "live_wire", "description": "Набрать 1500 очков активности."},
    {"code": "clean_path", "name": "Чистая траектория", "badge": "🧼", "rarity": "epic", "metric": "good_standing_days", "target": 30, "tier": 3, "category": "behavior", "hidden": 1, "description": "30 дней без санкций."},
    {"code": "untouchable", "name": "Безупречная история", "badge": "🛡️", "rarity": "mythic", "metric": "good_standing_days", "target": 90, "tier": 5, "category": "behavior", "hidden": 1, "chain_code": "clean_path", "description": "90 дней без наказаний."},
    {"code": "status_architect", "name": "Архитектор статуса", "badge": "👑", "rarity": "legendary", "metric": "level", "target": 10, "tier": 4, "category": "status", "is_status": 1, "description": "Достичь 10 уровня."},
    {"code": "rank_breaker", "name": "Ломатель рангов", "badge": "🗡️", "rarity": "mythic", "metric": "level", "target": 12, "tier": 5, "category": "status", "is_status": 1, "chain_code": "status_architect", "description": "Достичь 12 уровня."},
    {"code": "season_runner", "name": "Гонка сезона", "badge": "🏁", "rarity": "rare", "metric": "season_score", "target": 800, "tier": 2, "category": "season", "is_seasonal": 1, "description": "Набрать 800 очков сезона."},
    {"code": "season_elite", "name": "Элита сезона", "badge": "🏆", "rarity": "legendary", "metric": "season_score", "target": 2500, "tier": 4, "category": "season", "is_seasonal": 1, "chain_code": "season_runner", "description": "Набрать 2500 сезонных очков."},
    {"code": "season_meteor", "name": "Метеор сезона", "badge": "☄️", "rarity": "mythic", "metric": "season_score", "target": 4500, "tier": 5, "category": "season", "is_seasonal": 1, "chain_code": "season_elite", "description": "Набрать 4500 сезонных очков."},
    {"code": "prestige_one", "name": "Первый престиж", "badge": "🪪", "rarity": "legendary", "metric": "prestige", "target": 1, "tier": 4, "category": "prestige", "is_prestige": 1, "description": "Получить первый престиж."},
    {"code": "prestige_two", "name": "Двойной престиж", "badge": "🪐", "rarity": "mythic", "metric": "prestige", "target": 2, "tier": 5, "category": "prestige", "is_prestige": 1, "chain_code": "prestige_one", "description": "Получить второй престиж."},
    {"code": "silent_guard", "name": "Тихий страж", "badge": "🌙", "rarity": "epic", "metric": "behavior_score", "target": 100, "tier": 3, "category": "behavior", "hidden": 1, "description": "Держать идеальное поведение 100/100.", "requirements": (("good_standing_days", 7), ("msg_count", 25))},
    {"code": "first_reply", "name": "Первый отклик", "badge": "📨", "rarity": "common", "metric": "replied_messages", "target": 3, "tier": 1, "category": "discussion", "description": "Не разово, а реально включиться в диалог.", "requirements": (("msg_count", 15),)},
    {"code": "first_longform", "name": "Первая простыня", "badge": "📜", "rarity": "common", "metric": "long_messages", "target": 3, "tier": 1, "category": "quality", "description": "Написать 3 длинных сообщения, а не одну случайную простыню.", "requirements": (("msg_count", 20),)},
    {"code": "media_drop", "name": "Медиа-дроп", "badge": "🖼️", "rarity": "common", "metric": "media_messages", "target": 5, "tier": 1, "category": "media", "description": "Отправить 5 медиа-сообщений."},
    {"code": "media_curator", "name": "Куратор медиа", "badge": "🎞️", "rarity": "rare", "metric": "media_messages", "target": 20, "tier": 2, "category": "media", "chain_code": "media_drop", "description": "Отправить 20 медиа-сообщений."},
    {"code": "night_shift", "name": "Ночная смена", "badge": "🌃", "rarity": "epic", "metric": "unique_days", "target": 25, "tier": 3, "category": "consistency", "hidden": 1, "description": "Появляться в чате минимум 25 разных дней."},
    {"code": "archive_ghost", "name": "Призрак архива", "badge": "👻", "rarity": "mythic", "metric": "unique_days", "target": 90, "tier": 5, "category": "consistency", "hidden": 1, "chain_code": "night_shift", "description": "Оставаться в истории чата 90 разных дней."},
)


def progress_bar(current: int, target: int, width: int = 10) -> str:
    if target <= 0:
        return "█" * width
    ratio = max(0.0, min(1.0, current / target))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


class AchievementsService:
    def __init__(self, repository: BridgeRepository) -> None:
        self.repository = repository
        self.seed_catalog()

    def seed_catalog(self) -> None:
        with self.repository.connect() as conn:
            for definition in ACHIEVEMENT_DEFS:
                rarity = str(definition["rarity"])
                _, _, rarity_score = RARITY_STYLES[rarity]
                conn.execute(
                    """INSERT OR REPLACE INTO achievement_catalog
                    (code, name, badge, rarity, category, metric, target_value, tier, hidden, chain_code, reward_xp, reward_score, reward_badge, is_seasonal, is_status, is_prestige, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        definition["code"],
                        definition["name"],
                        definition["badge"],
                        definition["rarity"],
                        definition["category"],
                        definition["metric"],
                        definition["target"],
                        safe_int(definition.get("tier", 1), 1),
                        safe_int(definition.get("hidden", 0), 0),
                        str(definition.get("chain_code", "")),
                        20 + rarity_score,
                        rarity_score * 2,
                        definition["badge"],
                        safe_int(definition.get("is_seasonal", 0), 0),
                        safe_int(definition.get("is_status", 0), 0),
                        safe_int(definition.get("is_prestige", 0), 0),
                        definition["description"],
                    ),
                )
            conn.commit()

    def get_definition(self, code: str) -> Optional[Dict[str, object]]:
        for definition in ACHIEVEMENT_DEFS:
            if str(definition["code"]) == code:
                return dict(definition)
        return None

    def requirements_met(self, definition: Dict[str, object], snapshot: Dict[str, int]) -> bool:
        requirements = tuple(definition.get("requirements", ()))
        for metric, target in requirements:
            if safe_int(snapshot.get(str(metric), 0)) < safe_int(target):
                return False
        return True

    def build_reason_text(self, definition: Dict[str, object], snapshot: Dict[str, int], current_progress: int, target: int) -> str:
        metric = str(definition["metric"])
        metric_label = METRIC_LABELS.get(metric, metric.replace("_", " "))
        base = f"{metric_label}: {current_progress}/{target}"
        requirements = tuple(definition.get("requirements", ()))
        if not requirements:
            return base
        extra = ", ".join(
            f"{METRIC_LABELS.get(str(req_metric), str(req_metric).replace('_', ' '))}: {safe_int(snapshot.get(str(req_metric), 0))}/{safe_int(req_target)}"
            for req_metric, req_target in requirements
        )
        return f"{base}; условия: {extra}"

    def format_unlock_announcement(self, display_name: str, unlocked: Sequence[Dict[str, object]]) -> str:
        if not unlocked:
            return ""
        lines = [f"🏅 {display_name} открывает достижение!" if len(unlocked) == 1 else f"🏅 {display_name} открывает достижения!", ""]
        for item in unlocked[:3]:
            rarity_name, rarity_badge, _ = RARITY_STYLES[str(item["rarity"])]
            lines.append(f"{item['badge']} {item['name']}")
            lines.append(f"   {rarity_badge} {rarity_name} • {item['description']}")
            lines.append(f"   За что: {item['reason_text']}")
        if len(unlocked) > 3:
            lines.extend(["", f"И ещё {len(unlocked) - 3} достиж."])
        return "\n".join(lines)

    def evaluate(self, user_id: int, snapshot: Dict[str, int], awarded_at: Optional[int] = None, metadata_extra: Optional[Dict[str, object]] = None) -> List[Dict[str, object]]:
        unlocked: List[Dict[str, object]] = []
        now_ts = safe_int(awarded_at) or int(time.time())
        extra = dict(metadata_extra or {})
        with self.repository.connect() as conn:
            for definition in ACHIEVEMENT_DEFS:
                code = str(definition["code"])
                metric = str(definition["metric"])
                progress = safe_int(snapshot.get(metric, 0))
                target = safe_int(definition["target"])
                conn.execute(
                    """INSERT OR IGNORE INTO user_achievement_state
                    (user_id, code, progress_value, progress_target, unlocked_at, tier_achieved, last_evaluated_at)
                    VALUES (?, ?, 0, ?, NULL, 0, 0)""",
                    (user_id, code, target),
                )
                chain_code = str(definition.get("chain_code", ""))
                if chain_code:
                    parent = conn.execute(
                        "SELECT unlocked_at FROM user_achievement_state WHERE user_id = ? AND code = ?",
                        (user_id, chain_code),
                    ).fetchone()
                    if not parent or not parent["unlocked_at"]:
                        conn.execute(
                            "UPDATE user_achievement_state SET progress_value = ?, progress_target = ?, last_evaluated_at = ? WHERE user_id = ? AND code = ?",
                            (progress, target, now_ts, user_id, code),
                        )
                        continue
                row = conn.execute(
                    "SELECT unlocked_at, progress_value FROM user_achievement_state WHERE user_id = ? AND code = ?",
                    (user_id, code),
                ).fetchone()
                current_progress = max(progress, safe_int(row["progress_value"] if row else 0))
                conn.execute(
                    "UPDATE user_achievement_state SET progress_value = ?, progress_target = ?, last_evaluated_at = ? WHERE user_id = ? AND code = ?",
                    (current_progress, target, now_ts, user_id, code),
                )
                if row and row["unlocked_at"]:
                    continue
                if not self.requirements_met(definition, snapshot):
                    continue
                if current_progress < target:
                    continue
                conn.execute(
                    "UPDATE user_achievement_state SET unlocked_at = ?, tier_achieved = ? WHERE user_id = ? AND code = ?",
                    (now_ts, safe_int(definition.get("tier", 1), 1), user_id, code),
                )
                reward_xp = 20 + RARITY_STYLES[str(definition["rarity"])][2]
                reward_score = RARITY_STYLES[str(definition["rarity"])][2] * 2
                self.repository.record_score_event(
                    conn,
                    user_id=user_id,
                    chat_id=0,
                    event_type="achievement_unlock",
                    xp_delta=reward_xp,
                    score_delta=reward_score,
                    reason=str(definition["name"]),
                    metadata={"code": code, "rarity": definition["rarity"], **extra},
                    created_at=now_ts,
                )
                unlocked.append(
                    {
                        "code": code,
                        "name": str(definition["name"]),
                        "badge": str(definition["badge"]),
                        "description": str(definition["description"]),
                        "rarity": str(definition["rarity"]),
                        "reason_text": self.build_reason_text(definition, snapshot, current_progress, target),
                    }
                )
            conn.commit()
        return unlocked

    def render(self, user_id: int, snapshot: Dict[str, int], display_name: str) -> str:
        with self.repository.connect() as conn:
            rows = {
                row["code"]: row
                for row in conn.execute(
                    "SELECT code, progress_value, progress_target, unlocked_at FROM user_achievement_state WHERE user_id = ?",
                    (user_id,),
                ).fetchall()
            }
        unlocked_lines: List[str] = []
        progress_lines: List[str] = []
        unlocked_count = 0
        hidden_left = 0
        for definition in ACHIEVEMENT_DEFS:
            code = str(definition["code"])
            row = rows.get(code)
            target = safe_int(definition["target"])
            current = safe_int(row["progress_value"] if row else snapshot.get(str(definition["metric"]), 0))
            hidden = safe_int(definition.get("hidden", 0), 0) == 1
            unlocked = bool(row and row["unlocked_at"])
            if unlocked:
                unlocked_count += 1
                rarity_name, rarity_badge, _ = RARITY_STYLES[str(definition["rarity"])]
                unlocked_lines.append(f"{definition['badge']} {definition['name']} • {rarity_badge} {rarity_name}")
                continue
            title = "???" if hidden else str(definition["name"])
            desc = "Скрытое достижение" if hidden else str(definition["description"])
            rarity_name, rarity_badge, _ = RARITY_STYLES[str(definition["rarity"])]
            if hidden:
                hidden_left += 1
            progress_lines.append(
                f"{definition['badge']} {title}\n"
                f"   {rarity_badge} {rarity_name} • {desc}\n"
                f"   [{progress_bar(min(current, target), target, 8)}] {min(current, target)}/{target}"
            )
        header = [
            f"🏅 ДОСТИЖЕНИЯ • {display_name}",
            "",
            f"Открыто: {unlocked_count}/{len(ACHIEVEMENT_DEFS)}",
            f"Скрытых осталось: {hidden_left}",
            "",
            "СЕЙЧАС В КОЛЛЕКЦИИ:",
            *(unlocked_lines[:12] or ["Пока пусто."]),
            "",
            "НА ПОДХОДЕ:",
            *(progress_lines[:10] or ["Все видимые ачивки уже открыты."]),
        ]
        return "\n".join(header)
