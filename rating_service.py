import time
import unicodedata
from typing import Dict, List, Sequence, Tuple

from bridge_repository import BridgeRepository, safe_int


LEVEL_THRESHOLDS = [0, 15, 45, 100, 180, 300, 480, 720, 1050, 1500, 2100, 2900, 3900, 5200, 6800, 8800]
LEVEL_NAMES = ["Новичок", "Искра", "Участник", "Активный", "Опытный", "Ветеран", "Мастер", "Эксперт", "Легенда", "Гуру", "Архитектор", "Титан", "Миф", "Астрал", "Эон", "Божество"]
LEVEL_MEDALS = {0: "🌱", 1: "✨", 2: "📈", 3: "⚡", 4: "🔥", 5: "🛡️", 6: "🎓", 7: "🏆", 8: "👑", 9: "💎", 10: "🌌", 11: "🚀", 12: "🜂", 13: "🪐", 14: "🌠", 15: "🌟"}
RANK_TIERS = [
    (0, "Наблюдатель", "🌫️"),
    (250, "Инициатор", "🔹"),
    (700, "Контрибьютор", "🧩"),
    (1500, "Навигатор", "🧭"),
    (2800, "Катализатор", "⚙️"),
    (4500, "Стратег", "🗡️"),
    (6800, "Чемпион", "🏅"),
    (9500, "Властелин", "👑"),
    (13000, "Архонт", "🜁"),
    (17000, "Космос", "🌌"),
]


def calculate_level(total_xp: int) -> int:
    for idx in range(len(LEVEL_THRESHOLDS) - 1, -1, -1):
        if total_xp >= LEVEL_THRESHOLDS[idx]:
            return idx
    return 0


def get_level_name(level: int) -> str:
    if level < len(LEVEL_NAMES):
        return LEVEL_NAMES[level]
    return f"{LEVEL_NAMES[-1]}+{level - len(LEVEL_NAMES) + 1}"


def get_level_medal(level: int) -> str:
    return LEVEL_MEDALS.get(level, LEVEL_MEDALS[max(LEVEL_MEDALS)])


def get_rank_tier(total_score: int, prestige: int) -> Tuple[str, str]:
    adjusted = total_score + prestige * 1500
    label, badge = RANK_TIERS[0][1], RANK_TIERS[0][2]
    for threshold, next_label, next_badge in RANK_TIERS:
        if adjusted >= threshold:
            label, badge = next_label, next_badge
    return label, badge


def progress_bar(current: int, target: int, width: int = 12) -> str:
    if target <= 0:
        return "█" * width
    ratio = max(0.0, min(1.0, current / target))
    filled = int(round(ratio * width))
    return "█" * filled + "░" * (width - filled)


def compact_number(value: int) -> str:
    return f"{safe_int(value):,}".replace(",", " ")


def clean_display_name(value: object, fallback: str = "Участник", limit: int = 24) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return fallback
    normalized = unicodedata.normalize("NFKD", text)
    combining_count = sum(1 for ch in normalized if unicodedata.combining(ch))
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    if combining_count >= 5 and stripped:
        visible = "".join(
            ch for ch in stripped
            if unicodedata.category(ch)[0] in {"L", "N"} or ch in {" ", ".", "_", "-"}
        ).strip()
        text = visible or stripped
    text = " ".join(text.split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(6, limit - 1)].rstrip() + "…"


def top_limit() -> int:
    return 10000


def block(title: str, lines: Sequence[str]) -> str:
    return "\n".join([title] + [line for line in lines if line])


def place_label(position: int, total: int) -> str:
    return f"#{position} из {total}"


def ordinal_marker(index: int) -> str:
    if index == 0:
        return "🥇"
    if index == 1:
        return "🥈"
    if index == 2:
        return "🥉"
    return f"{index + 1:02d}."


def compact_metric(label: str, value: int) -> str:
    return f"{label}: {compact_number(value)}"


MAX_TELEGRAM_TEXT = 3900
TOP_PAGE_SIZE = 10


class RatingService:
    def __init__(self, repository: BridgeRepository) -> None:
        self.repository = repository

    def _non_legacy_filter_sql(self, alias: str = "") -> str:
        prefix = f"{alias}." if alias else ""
        return (
            f"{prefix}event_type != 'legacy_import' "
            f"AND instr(COALESCE({prefix}metadata_json, '{{}}'), 'legacy_bootstrap') = 0"
        )

    def _sum_score_events(self, conn, user_id: int, since_ts: int = 0, exclude_event_types: Sequence[str] = ()) -> int:
        query = "SELECT COALESCE(SUM(score_delta), 0) FROM score_events WHERE user_id = ?"
        params: List[object] = [user_id]
        if since_ts > 0:
            query += " AND created_at >= ?"
            params.append(since_ts)
        if exclude_event_types:
            placeholders = ",".join("?" for _ in exclude_event_types)
            query += f" AND event_type NOT IN ({placeholders})"
            params.extend(exclude_event_types)
        row = conn.execute(query, tuple(params)).fetchone()
        return safe_int(row[0] if row else 0)

    def _sum_current_score_events(self, conn, user_id: int, since_ts: int = 0) -> int:
        query = f"SELECT COALESCE(SUM(score_delta), 0) FROM score_events WHERE user_id = ? AND {self._non_legacy_filter_sql()}"
        params: List[object] = [user_id]
        if since_ts > 0:
            query += " AND created_at >= ?"
            params.append(since_ts)
        row = conn.execute(query, tuple(params)).fetchone()
        return safe_int(row[0] if row else 0)

    def recalculate_profile(self, user_id: int) -> Dict[str, int]:
        now_ts = int(time.time())
        with self.repository.connect() as conn:
            row = conn.execute("SELECT * FROM progression_profiles WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return {}
            weekly_since = now_ts - 7 * 86400
            monthly_since = now_ts - 30 * 86400
            season_id = self.repository.current_season_id(now_ts)
            total_xp = self.repository.aggregate_recent_xp(conn, user_id, 0)
            weekly_score = self._sum_score_events(conn, user_id, weekly_since, exclude_event_types=("legacy_import",))
            monthly_score = self._sum_score_events(conn, user_id, monthly_since, exclude_event_types=("legacy_import",))
            season_score = self._sum_score_events(conn, user_id, self._season_start_ts(now_ts), exclude_event_types=("legacy_import",))
            achievement_score = conn.execute(
                "SELECT COALESCE(SUM(score_delta), 0) FROM score_events WHERE user_id = ? AND event_type = 'achievement_unlock'",
                (user_id,),
            ).fetchone()[0]
            total_score = self._sum_score_events(conn, user_id, 0)
            level = calculate_level(safe_int(total_xp))
            prestige = max(0, safe_int(total_xp) // 12000)
            rank_name, rank_badge = get_rank_tier(safe_int(total_score), prestige)
            dynamic_score = safe_int(weekly_score) + safe_int(row["behavior_score"]) * 4 + safe_int(row["contribution_score"]) // 2
            status_label = get_level_name(level)
            conn.execute(
                """UPDATE progression_profiles
                SET total_xp = ?, level = ?, prestige = ?, rank_name = ?, rank_badge = ?, status_label = ?,
                    total_score = ?, weekly_score = ?, monthly_score = ?, season_id = ?, season_score = ?,
                    dynamic_score = ?, achievement_score = ?, updated_at = ?
                WHERE user_id = ?""",
                (
                    safe_int(total_xp),
                    level,
                    prestige,
                    rank_name,
                    rank_badge,
                    status_label,
                    safe_int(total_score),
                    safe_int(weekly_score),
                    safe_int(monthly_score),
                    season_id,
                    safe_int(season_score),
                    dynamic_score,
                    safe_int(achievement_score),
                    now_ts,
                    user_id,
                ),
            )
            conn.commit()
            refreshed = conn.execute("SELECT * FROM progression_profiles WHERE user_id = ?", (user_id,)).fetchone()
        return {key: safe_int(refreshed[key]) if isinstance(refreshed[key], (int, float)) else refreshed[key] for key in refreshed.keys()} if refreshed else {}

    def _season_start_ts(self, ts: int) -> int:
        g = time.gmtime(ts)
        month = ((g.tm_mon - 1) // 3) * 3 + 1
        return int(time.mktime((g.tm_year, month, 1, 0, 0, 0, 0, 0, 0)))

    def render_rating(self, user_id: int) -> str:
        snapshot = self.recalculate_profile(user_id)
        if not snapshot:
            return "❌ Профиль ещё не сформирован. Нужна активность в чате."
        with self.repository.connect() as conn:
            rank_rows = conn.execute(
                "SELECT user_id, total_score, contribution_score, weekly_score, season_score FROM progression_profiles ORDER BY total_score DESC"
            ).fetchall()
            current_rows = conn.execute(
                f"""SELECT p.user_id, COALESCE(SUM(se.score_delta), 0) AS current_score
                FROM progression_profiles p
                LEFT JOIN score_events se ON se.user_id = p.user_id AND {self._non_legacy_filter_sql('se')}
                GROUP BY p.user_id
                ORDER BY current_score DESC, p.total_score DESC"""
            ).fetchall()
            current_total = self._sum_current_score_events(conn, user_id)
        level = safe_int(snapshot["level"])
        current_threshold = LEVEL_THRESHOLDS[min(level, len(LEVEL_THRESHOLDS) - 1)]
        next_level = min(level + 1, len(LEVEL_THRESHOLDS) - 1)
        next_threshold = LEVEL_THRESHOLDS[next_level]
        progress = 100 if next_threshold <= current_threshold else int(max(0.0, min(1.0, (snapshot["total_xp"] - current_threshold) / (next_threshold - current_threshold))) * 100)
        need_xp = max(0, next_threshold - snapshot["total_xp"])
        total_pos = self._rank_position(rank_rows, user_id, "total_score")
        current_pos = self._rank_position(current_rows, user_id, "current_score")
        contrib_pos = self._rank_position(rank_rows, user_id, "contribution_score")
        week_pos = self._rank_position(rank_rows, user_id, "weekly_score")
        season_pos = self._rank_position(rank_rows, user_id, "season_score")
        display_name = clean_display_name(snapshot.get("first_name") or snapshot.get("username") or str(user_id), fallback=str(user_id), limit=30)
        sections = [
            block("Профиль", [
                f"{get_level_medal(level)} {display_name}",
                f"{snapshot['rank_badge']} {snapshot['rank_name']} • {get_level_name(level)} • уровень {level}",
            ]),
            block("Позиции", [
                f"Новый рейтинг: {place_label(current_pos[0], current_pos[1])}",
                f"Исторический рейтинг: {place_label(total_pos[0], total_pos[1])}",
                f"По вкладу: #{contrib_pos[0]} • за неделю: #{week_pos[0]} • за сезон: #{season_pos[0]}",
            ]),
            block("Очки", [
                f"Новый рейтинг: {compact_number(current_total)}",
                f"Исторический рейтинг: {compact_number(snapshot['total_score'])}",
                f"Опыт (XP): {compact_number(snapshot['total_xp'])}",
                f"Престиж: {snapshot['prestige']}",
                f"Динамический рейтинг: {compact_number(snapshot['dynamic_score'])}",
            ]),
            block("Прогресс", [
                f"[{progress_bar(progress, 100)}] {progress}%",
                f"До следующего уровня: {compact_number(need_xp)} XP",
            ]),
            block("Разделы", [
                f"Очки активности: {compact_number(snapshot['activity_score'])}",
                f"Очки вклада: {compact_number(snapshot['contribution_score'])}",
                f"Очки ачивок: {compact_number(snapshot['achievement_score'])}",
                f"Поведение: {snapshot['behavior_score']}/100",
                f"Штрафы: {compact_number(snapshot['moderation_penalty'])}",
            ]),
            block("Периоды", [
                f"За неделю: {compact_number(snapshot['weekly_score'])}",
                f"За месяц: {compact_number(snapshot['monthly_score'])}",
                f"За сезон: {compact_number(snapshot['season_score'])}",
            ]),
            block("Активность в чате", [
                f"Сообщения: {compact_number(snapshot['msg_count'])}",
                f"Реакции получено: {compact_number(snapshot['reactions_received'])}",
                f"Реакции отправлено: {compact_number(snapshot['reactions_given'])}",
            ]),
        ]
        return "JARVIS • РЕЙТИНГ\n\n" + "\n\n".join(sections)

    def _rank_position(self, rows: Sequence[object], user_id: int, key: str) -> Tuple[int, int]:
        ordered = sorted(rows, key=lambda row: safe_int(row[key]), reverse=True)
        for index, row in enumerate(ordered, 1):
            if safe_int(row["user_id"]) == user_id:
                return index, len(ordered)
        return len(ordered), len(ordered)

    def _paginate_rows(self, rows: Sequence[object], page: int) -> Tuple[List[object], int, int]:
        total_rows = len(rows)
        total_pages = max(1, (total_rows + TOP_PAGE_SIZE - 1) // TOP_PAGE_SIZE)
        current_page = max(1, min(page, total_pages))
        start = (current_page - 1) * TOP_PAGE_SIZE
        return list(rows[start:start + TOP_PAGE_SIZE]), current_page, total_pages

    def _render_paginated_rows(
        self,
        rows: Sequence[object],
        *,
        title: str,
        page: int,
        line_builder,
        empty_text: str,
    ) -> str:
        if not rows:
            return empty_text
        page_rows, current_page, total_pages = self._paginate_rows(rows, page)
        start_index = (current_page - 1) * TOP_PAGE_SIZE
        lines: List[str] = [f"{title} • {current_page}/{total_pages}", ""]
        for offset, row in enumerate(page_rows, start=start_index):
            lines.extend(line_builder(offset, row))
        lines.extend([
            "",
            f"Показано {start_index + 1}-{start_index + len(page_rows)} из {len(rows)}.",
            "Листай кнопками ниже.",
        ])
        return self._fit_telegram_text(lines)

    def _render_top(
        self,
        title: str,
        key: str,
        value_label: str,
        secondary_key: str = "total_score",
        secondary_label: str = "Рейтинг",
        page: int = 1,
    ) -> str:
        selected_columns = [
            "user_id",
            "first_name",
            "username",
            "level",
            "prestige",
            "rank_name",
            "rank_badge",
            "total_score",
            "season_score",
            key,
        ]
        if secondary_key and secondary_key not in selected_columns:
            selected_columns.append(secondary_key)
        with self.repository.connect() as conn:
            rows = conn.execute(
                f"""SELECT {", ".join(selected_columns)}
                FROM progression_profiles
                WHERE {key} > 0
                ORDER BY {key} DESC, total_score DESC
                LIMIT {top_limit()}"""
            ).fetchall()
        def build_line(idx: int, row: object) -> List[str]:
            label = clean_display_name(row["first_name"] or row["username"] or str(row["user_id"]), limit=22)
            rank_marker = ordinal_marker(idx)
            lines = [f"{rank_marker} {label} {get_level_medal(safe_int(row['level']))}"]
            primary_value = safe_int(row[key])
            meta_parts = [compact_metric(value_label, primary_value)]
            if secondary_key and secondary_key != key:
                secondary_value = safe_int(row[secondary_key])
                if secondary_value != primary_value:
                    meta_parts.append(compact_metric(secondary_label, secondary_value))
            season_value = safe_int(row["season_score"])
            if key != "season_score" and secondary_key != "season_score" and season_value not in {primary_value, 0}:
                meta_parts.append(compact_metric("Сезон", season_value))
            lines.append("   " + " • ".join(meta_parts))
            return lines
        return self._render_paginated_rows(
            rows,
            title=title,
            page=page,
            line_builder=build_line,
            empty_text="📊 Топ пока пуст.",
        )

    def _fit_telegram_text(self, lines: Sequence[str], max_len: int = MAX_TELEGRAM_TEXT) -> str:
        if not lines:
            return ""
        result: List[str] = []
        current_len = 0
        trimmed = False
        for line in lines:
            candidate = line if not result else "\n" + line
            if current_len + len(candidate) > max_len:
                trimmed = True
                break
            result.append(line)
            current_len += len(candidate)
        if trimmed:
            suffix = ""
            if result:
                suffix = "\n\nПоказана верхняя часть списка. Полный рейтинг лучше выводить страницами."
                while result and current_len + len(suffix) > max_len:
                    removed = result.pop()
                    current_len -= len(removed) + (1 if result else 0)
            return "\n".join(result) + suffix
        return "\n".join(result)

    def render_top_current(self, page: int = 1) -> str:
        with self.repository.connect() as conn:
            rows = conn.execute(
                f"""SELECT p.user_id, p.first_name, p.username, p.level, p.total_score,
                           COALESCE(SUM(se.score_delta), 0) AS current_score
                FROM progression_profiles p
                LEFT JOIN score_events se ON se.user_id = p.user_id AND {self._non_legacy_filter_sql('se')}
                GROUP BY p.user_id
                HAVING current_score > 0
                ORDER BY current_score DESC, p.total_score DESC"""
            ).fetchall()
        def build_line(idx: int, row: object) -> List[str]:
            label = clean_display_name(row["first_name"] or row["username"] or str(row["user_id"]), limit=22)
            rank_marker = ordinal_marker(idx)
            lines = [f"{rank_marker} {label} {get_level_medal(safe_int(row['level']))}"]
            current_score = safe_int(row["current_score"])
            total_score = safe_int(row["total_score"])
            meta_parts = [compact_metric("Новый рейтинг", current_score)]
            if total_score != current_score:
                meta_parts.append(compact_metric("Исторический рейтинг", total_score))
            lines.append("   " + " • ".join(meta_parts))
            return lines
        return self._render_paginated_rows(
            rows,
            title="🚀 ТОП • НОВЫЙ РЕЙТИНГ",
            page=page,
            line_builder=build_line,
            empty_text="📊 Новый топ пока пуст.",
        )

    def render_top_historical(self, page: int = 1) -> str:
        return self._render_top("🏛️ ТОП • ИСТОРИЧЕСКИЙ РЕЙТИНГ", "total_score", "Исторический рейтинг", secondary_key="", secondary_label="", page=page)

    def render_top_all_time(self, page: int = 1) -> str:
        return self.render_top_current(page=page)

    def render_top_week(self, page: int = 1) -> str:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """SELECT user_id, first_name, username, level, prestige, rank_name, rank_badge, total_score, season_score, weekly_score
                FROM progression_profiles
                WHERE weekly_score > 0
                ORDER BY weekly_score DESC, total_score DESC"""
            ).fetchall()
        def build_line(idx: int, row: object) -> List[str]:
            label = clean_display_name(row["first_name"] or row["username"] or str(row["user_id"]), limit=22)
            rank_marker = ordinal_marker(idx)
            lines = [f"{rank_marker} {label} {get_level_medal(safe_int(row['level']))}"]
            primary_value = safe_int(row["weekly_score"])
            total_score = safe_int(row["total_score"])
            meta_parts = [compact_metric("Очки за неделю", primary_value)]
            if total_score != primary_value:
                meta_parts.append(compact_metric("Исторический рейтинг", total_score))
            lines.append("   " + " • ".join(meta_parts))
            return lines
        return self._render_paginated_rows(
            rows,
            title="⭐ ТОП • НЕДЕЛЯ",
            page=page,
            line_builder=build_line,
            empty_text="📊 За неделю пока нет новой активности.",
        )

    def render_top_day(self, page: int = 1) -> str:
        with self.repository.connect() as conn:
            since_ts = int(time.time()) - 86400
            rows = conn.execute(
                """SELECT p.user_id, p.first_name, p.username, p.level, p.total_score,
                          COALESCE(SUM(se.score_delta), 0) AS day_score
                FROM progression_profiles p
                LEFT JOIN score_events se ON se.user_id = p.user_id AND se.created_at >= ? AND se.event_type != 'legacy_import' AND instr(COALESCE(se.metadata_json, '{}'), 'legacy_bootstrap') = 0
                GROUP BY p.user_id
                HAVING day_score > 0
                ORDER BY day_score DESC, p.total_score DESC""",
                (since_ts,),
            ).fetchall()
        def build_line(idx: int, row: object) -> List[str]:
            label = clean_display_name(row["first_name"] or row["username"] or row["user_id"], limit=22)
            rank_marker = ordinal_marker(idx)
            lines = [f"{rank_marker} {label} {get_level_medal(safe_int(row['level']))}"]
            day_score = safe_int(row["day_score"])
            total_score = safe_int(row["total_score"])
            meta_parts = [compact_metric("Очки за день", day_score)]
            if total_score != day_score:
                meta_parts.append(compact_metric("Исторический рейтинг", total_score))
            lines.append("   " + " • ".join(meta_parts))
            return lines
        return self._render_paginated_rows(
            rows,
            title="🔥 ТОП • СЕГОДНЯ",
            page=page,
            line_builder=build_line,
            empty_text="📊 Топ пока пуст.",
        )

    def render_top_social(self, page: int = 1) -> str:
        return self._render_top("🤝 ТОП • ВКЛАД", "contribution_score", "Очки вклада", secondary_key="total_score", secondary_label="Исторический рейтинг", page=page)

    def render_top_season(self, page: int = 1) -> str:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """SELECT user_id, first_name, username, level, prestige, rank_name, rank_badge, total_score, season_score
                FROM progression_profiles
                WHERE season_score > 0
                ORDER BY season_score DESC, total_score DESC"""
            ).fetchall()
        def build_line(idx: int, row: object) -> List[str]:
            label = clean_display_name(row["first_name"] or row["username"] or str(row["user_id"]), limit=22)
            rank_marker = ordinal_marker(idx)
            lines = [f"{rank_marker} {label} {get_level_medal(safe_int(row['level']))}"]
            season_score = safe_int(row["season_score"])
            total_score = safe_int(row["total_score"])
            meta_parts = [compact_metric("Очки сезона", season_score)]
            if total_score != season_score:
                meta_parts.append(compact_metric("Исторический рейтинг", total_score))
            lines.append("   " + " • ".join(meta_parts))
            return lines
        return self._render_paginated_rows(
            rows,
            title="🏁 ТОП • СЕЗОН",
            page=page,
            line_builder=build_line,
            empty_text="📊 За сезон пока нет новой активности.",
        )

    def render_top_reactions_received(self, page: int = 1) -> str:
        return self._render_top(
            "✨ ТОП • РЕАКЦИИ ПОЛУЧЕНО",
            "reactions_received",
            "Получено",
            secondary_key="total_score",
            secondary_label="Исторический рейтинг",
            page=page,
        )

    def render_top_reactions_given(self, page: int = 1) -> str:
        return self._render_top(
            "🫶 ТОП • РЕАКЦИИ ОТПРАВЛЕНО",
            "reactions_given",
            "Отправлено",
            secondary_key="total_score",
            secondary_label="Исторический рейтинг",
            page=page,
        )

    def render_top_activity(self, page: int = 1) -> str:
        return self._render_top(
            "⚡ ТОП • АКТИВНОСТЬ",
            "activity_score",
            "Активность",
            secondary_key="msg_count",
            secondary_label="Сообщения",
            page=page,
        )

    def render_top_behavior(self, page: int = 1) -> str:
        return self._render_top(
            "🛡️ ТОП • ПОВЕДЕНИЕ",
            "behavior_score",
            "Поведение",
            secondary_key="total_score",
            secondary_label="Исторический рейтинг",
            page=page,
        )

    def render_top_achievements(self, page: int = 1) -> str:
        return self._render_top(
            "🏅 ТОП • ДОСТИЖЕНИЯ",
            "achievement_score",
            "Ачивки",
            secondary_key="total_score",
            secondary_label="Исторический рейтинг",
            page=page,
        )

    def render_top_messages(self, page: int = 1) -> str:
        return self._render_top(
            "💬 ТОП • СООБЩЕНИЯ",
            "msg_count",
            "Сообщения",
            secondary_key="activity_score",
            secondary_label="Активность",
            page=page,
        )

    def render_top_helpful(self, page: int = 1) -> str:
        return self._render_top(
            "🧠 ТОП • ПОЛЕЗНОСТЬ",
            "helpful_messages",
            "Полезные",
            secondary_key="contribution_score",
            secondary_label="Вклад",
            page=page,
        )

    def render_top_streak(self, page: int = 1) -> str:
        return self._render_top(
            "📅 ТОП • СТРИК",
            "best_streak",
            "Стрик",
            secondary_key="unique_days",
            secondary_label="Уникальные дни",
            page=page,
        )

    def render_profile_card(self, user_id: int) -> str:
        snapshot = self.recalculate_profile(user_id)
        if not snapshot:
            return "Профиль еще не сформирован. Напишите несколько сообщений в чате."
        with self.repository.connect() as conn:
            total_rows = conn.execute(
                "SELECT user_id, total_score FROM progression_profiles ORDER BY total_score DESC"
            ).fetchall()
            current_rows = conn.execute(
                f"""SELECT p.user_id, COALESCE(SUM(se.score_delta), 0) AS current_score
                FROM progression_profiles p
                LEFT JOIN score_events se ON se.user_id = p.user_id AND {self._non_legacy_filter_sql('se')}
                GROUP BY p.user_id
                ORDER BY current_score DESC, p.total_score DESC"""
            ).fetchall()
        level = safe_int(snapshot["level"])
        total_pos = self._rank_position(total_rows, user_id, "total_score")
        current_pos = self._rank_position(current_rows, user_id, "current_score")
        display_name = clean_display_name(snapshot.get("first_name") or snapshot.get("username") or str(user_id), fallback=str(user_id), limit=30)
        total_xp = safe_int(snapshot["total_xp"])
        current_threshold = LEVEL_THRESHOLDS[min(level, len(LEVEL_THRESHOLDS) - 1)]
        next_level = min(level + 1, len(LEVEL_THRESHOLDS) - 1)
        next_threshold = LEVEL_THRESHOLDS[next_level]
        need_xp = max(0, next_threshold - total_xp)
        progress = 100 if next_threshold <= current_threshold else int(
            max(0.0, min(1.0, (total_xp - current_threshold) / (next_threshold - current_threshold))) * 100
        )
        return "\n".join(
            [
                f"{get_level_medal(level)} {display_name}",
                f"{snapshot['rank_badge']} {snapshot['rank_name']} • {get_level_name(level)} • уровень {level}",
                "",
                f"🏆 Новый рейтинг: {place_label(current_pos[0], current_pos[1])}",
                f"🏛️ Исторический рейтинг: {place_label(total_pos[0], total_pos[1])}",
                f"⭐ XP: {compact_number(total_xp)} • Престиж: {snapshot['prestige']}",
                f"📈 Прогресс: [{progress_bar(progress, 100)}] {progress}%",
                f"🎯 До уровня: {compact_number(need_xp)} XP",
                "",
                f"💬 Сообщения: {compact_number(snapshot['msg_count'])}",
                f"✨ Реакции получено: {compact_number(snapshot['reactions_received'])}",
                f"🫶 Реакции отправлено: {compact_number(snapshot['reactions_given'])}",
                f"🤝 Вклад: {compact_number(snapshot['contribution_score'])}",
                f"⚡ Активность: {compact_number(snapshot['activity_score'])}",
                f"🛡️ Поведение: {snapshot['behavior_score']}/100",
                f"🏅 Ачивки: {compact_number(snapshot['achievement_score'])}",
            ]
        )

    def render_stats(self) -> str:
        with self.repository.connect() as conn:
            total_users = conn.execute("SELECT COUNT(*) FROM progression_profiles").fetchone()[0]
            total_achievements = conn.execute("SELECT COUNT(*) FROM user_achievement_state WHERE unlocked_at IS NOT NULL").fetchone()[0]
            total_messages = conn.execute("SELECT COALESCE(SUM(msg_count), 0) FROM progression_profiles").fetchone()[0]
            avg_behavior = conn.execute("SELECT COALESCE(AVG(behavior_score), 0) FROM progression_profiles").fetchone()[0]
            top = conn.execute("SELECT first_name, username, total_score FROM progression_profiles ORDER BY total_score DESC LIMIT 1").fetchone()
        label = (top["first_name"] or top["username"]) if top else "Неизвестно"
        sections = [
            block("Общее", [
                f"Профили: {compact_number(total_users)}",
                f"Сообщения: {compact_number(total_messages)}",
                f"Открыто ачивок: {compact_number(total_achievements)}",
            ]),
            block("Качество", [
                f"Среднее поведение: {float(avg_behavior):.1f}/100",
            ]),
            block("Лидер", [
                f"{clean_display_name(label)} • {compact_number(top['total_score'] if top else 0)}",
            ]),
        ]
        return "JARVIS • СТАТИСТИКА\n\n" + "\n\n".join(sections)
