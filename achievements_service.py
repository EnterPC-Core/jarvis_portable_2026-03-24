import time
from typing import Dict, List, Optional, Sequence, Tuple

from bridge_repository import BridgeRepository, safe_int


RARITY_STYLES = {
    "common": ("Обычное", "⚪", 15),
    "rare": ("Редкое", "🔵", 35),
    "epic": ("Эпическое", "🟣", 70),
    "legendary": ("Легендарное", "🟠", 120),
    "mythic": ("Мифическое", "🌈", 180),
}

ACHIEVEMENT_DEFS: Sequence[Dict[str, object]] = (
    {"code": "first_signal", "name": "Первый сигнал", "badge": "🛰️", "rarity": "common", "metric": "msg_count", "target": 1, "tier": 1, "category": "activity", "description": "Отправить первое сообщение."},
    {"code": "starter_pack", "name": "Стартовый импульс", "badge": "🎯", "rarity": "common", "metric": "msg_count", "target": 25, "tier": 1, "category": "activity", "chain_code": "first_signal", "description": "Написать 25 сообщений."},
    {"code": "voice_of_room", "name": "Голос комнаты", "badge": "🎙️", "rarity": "rare", "metric": "msg_count", "target": 150, "tier": 2, "category": "activity", "chain_code": "starter_pack", "description": "Написать 150 сообщений."},
    {"code": "forum_engine", "name": "Двигатель обсуждений", "badge": "🧠", "rarity": "legendary", "metric": "msg_count", "target": 1500, "tier": 4, "category": "activity", "chain_code": "voice_of_room", "description": "Дойти до 1500 сообщений."},
    {"code": "helper_10", "name": "Полезный участник", "badge": "🛠️", "rarity": "rare", "metric": "helpful_messages", "target": 10, "tier": 1, "category": "contribution", "description": "Набрать 10 полезных сообщений."},
    {"code": "helper_75", "name": "Инженер сообщества", "badge": "🧰", "rarity": "epic", "metric": "helpful_messages", "target": 75, "tier": 3, "category": "contribution", "chain_code": "helper_10", "description": "Набрать 75 полезных сообщений."},
    {"code": "deep_diver", "name": "Глубокий разбор", "badge": "📚", "rarity": "rare", "metric": "long_messages", "target": 30, "tier": 2, "category": "quality", "description": "Написать 30 развёрнутых сообщений."},
    {"code": "community_glue", "name": "Связующее звено", "badge": "🧩", "rarity": "epic", "metric": "replied_messages", "target": 60, "tier": 3, "category": "discussion", "description": "Часто участвовать в диалогах и тредах."},
    {"code": "reaction_magnet", "name": "Магнит реакций", "badge": "✨", "rarity": "rare", "metric": "reactions_received", "target": 20, "tier": 2, "category": "social", "description": "Собрать 20 реакций от сообщества."},
    {"code": "steady_week", "name": "Ритм недели", "badge": "🗓️", "rarity": "rare", "metric": "best_streak", "target": 7, "tier": 2, "category": "consistency", "description": "Продержать серию из 7 дней."},
    {"code": "steady_month", "name": "Железная дисциплина", "badge": "⛓️", "rarity": "legendary", "metric": "best_streak", "target": 30, "tier": 4, "category": "consistency", "chain_code": "steady_week", "description": "Продержать серию из 30 дней."},
    {"code": "clean_path", "name": "Чистая траектория", "badge": "🧼", "rarity": "epic", "metric": "good_standing_days", "target": 30, "tier": 3, "category": "behavior", "hidden": 1, "description": "30 дней без санкций."},
    {"code": "untouchable", "name": "Безупречная история", "badge": "🛡️", "rarity": "mythic", "metric": "good_standing_days", "target": 90, "tier": 5, "category": "behavior", "hidden": 1, "chain_code": "clean_path", "description": "90 дней без наказаний."},
    {"code": "status_architect", "name": "Архитектор статуса", "badge": "👑", "rarity": "legendary", "metric": "level", "target": 10, "tier": 4, "category": "status", "is_status": 1, "description": "Достичь 10 уровня."},
    {"code": "season_runner", "name": "Гонка сезона", "badge": "🏁", "rarity": "rare", "metric": "season_score", "target": 800, "tier": 2, "category": "season", "is_seasonal": 1, "description": "Набрать 800 очков сезона."},
    {"code": "season_elite", "name": "Элита сезона", "badge": "🏆", "rarity": "legendary", "metric": "season_score", "target": 2500, "tier": 4, "category": "season", "is_seasonal": 1, "chain_code": "season_runner", "description": "Набрать 2500 сезонных очков."},
    {"code": "prestige_one", "name": "Первый престиж", "badge": "🪪", "rarity": "legendary", "metric": "prestige", "target": 1, "tier": 4, "category": "prestige", "is_prestige": 1, "description": "Получить первый престиж."},
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

    def evaluate(self, user_id: int, snapshot: Dict[str, int], awarded_at: Optional[int] = None, metadata_extra: Optional[Dict[str, object]] = None) -> List[Tuple[str, str]]:
        unlocked: List[Tuple[str, str]] = []
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
                unlocked.append((str(definition["name"]), str(definition["badge"])))
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
        for definition in ACHIEVEMENT_DEFS:
            code = str(definition["code"])
            row = rows.get(code)
            target = safe_int(definition["target"])
            current = safe_int(row["progress_value"] if row else snapshot.get(str(definition["metric"]), 0))
            hidden = safe_int(definition.get("hidden", 0), 0) == 1
            unlocked = bool(row and row["unlocked_at"])
            if unlocked:
                unlocked_count += 1
                unlocked_lines.append(f"{definition['badge']} {definition['name']}")
                continue
            title = "???" if hidden else str(definition["name"])
            desc = "Скрытое достижение" if hidden else str(definition["description"])
            rarity_name, rarity_badge, _ = RARITY_STYLES[str(definition["rarity"])]
            progress_lines.append(
                f"{definition['badge']} {title}\n"
                f"   {rarity_badge} {rarity_name} • {desc}\n"
                f"   [{progress_bar(min(current, target), target, 8)}] {min(current, target)}/{target}"
            )
        header = [
            f"🏅 ДОСТИЖЕНИЯ • {display_name}",
            "",
            f"Открыто: {unlocked_count}/{len(ACHIEVEMENT_DEFS)}",
            "",
            "ОТКРЫТЫЕ:",
            *(unlocked_lines[:12] or ["Пока пусто."]),
            "",
            "В ПРОГРЕССЕ:",
            *(progress_lines[:8] or ["Все видимые ачивки уже открыты."]),
        ]
        return "\n".join(header)
