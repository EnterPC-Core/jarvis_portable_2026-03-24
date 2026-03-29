import re
from typing import List, Optional, TYPE_CHECKING

from utils.report_utils import render_event_rows


def get_event_context(state: "BridgeState", chat_id: int, user_text: str, limit: int = 24) -> str:
    rows = state.search_events(chat_id, user_text, limit=limit, prefer_fts=True)
    summary_recall = state.get_summary_recall_context(chat_id, user_text, limit=4)
    if not rows and not summary_recall:
        return "История событий пуста."
    blocks: List[str] = []
    if summary_recall:
        blocks.append(summary_recall)
    if rows:
        blocks.append(
            render_event_rows(
                rows,
                title="События",
                build_actor_name_func=state.build_actor_name,
                truncate_text_func=state.truncate_text,
            )
        )
    return "\n\n".join(block for block in blocks if block.strip())


def get_database_context(
    state: "BridgeState",
    chat_id: int,
    query: str,
    limit: int = 8,
    *,
    build_actor_name_func,
    truncate_text_func,
) -> str:
    query_text = (query or "").strip()
    lowered = query_text.lower()
    target_user_id: Optional[int] = None
    target_username = ""
    username_match = re.search(r"@([a-zA-Z0-9_]{3,})", query_text)
    if username_match:
        target_username = username_match.group(1).lower()
    else:
        for token in re.findall(r"-?\d{5,12}", query_text):
            try:
                value = int(token)
            except ValueError:
                continue
            if value > 0:
                target_user_id = value
                break

    lines: List[str] = ["DB context:"]
    with state.db_lock:
        chat_stats = state.db.execute(
            """SELECT
                COUNT(*) AS events_count,
                COUNT(DISTINCT CASE WHEN role = 'user' THEN user_id END) AS users_count
            FROM chat_events
            WHERE chat_id = ?""",
            (chat_id,),
        ).fetchone()
        facts_count = state.db.execute("SELECT COUNT(*) FROM memory_facts WHERE chat_id = ?", (chat_id,)).fetchone()[0]
        open_appeals = state.db.execute(
            "SELECT COUNT(*) FROM appeals WHERE status IN ('new', 'in_review')"
        ).fetchone()[0]
        active_sanctions = state.db.execute(
            "SELECT COUNT(*) FROM moderation_actions WHERE active = 1"
        ).fetchone()[0]
        profiles_count = state.db.execute("SELECT COUNT(*) FROM progression_profiles").fetchone()[0]
        lines.append(
            f"chat_id={chat_id}; chat_events={int(chat_stats[0] or 0)}; users={int(chat_stats[1] or 0)}; "
            f"facts={int(facts_count or 0)}; progression_profiles={int(profiles_count or 0)}; "
            f"open_appeals={int(open_appeals or 0)}; active_sanctions={int(active_sanctions or 0)}"
        )
        participants_context = state.get_chat_participants_context(chat_id, query_text, limit=10)
        if participants_context:
            lines.append(participants_context)

        if any(word in lowered for word in ("рейтинг", "топ", "лидер", "xp", "уров", "ачив", "достиж")):
            rows = state.db.execute(
                """SELECT user_id, first_name, username, total_score, weekly_score, season_score, level
                FROM progression_profiles
                ORDER BY total_score DESC
                LIMIT ?""",
                (limit,),
            ).fetchall()
            if rows:
                lines.append("rating_top:")
                for row in rows:
                    label = build_actor_name_func(row[0], row[2] or "", row[1] or "", "", "user")
                    lines.append(
                        f"- {label}; total={int(row[3] or 0)}; week={int(row[4] or 0)}; "
                        f"season={int(row[5] or 0)}; level={int(row[6] or 0)}"
                    )

        if any(word in lowered for word in ("апел", "appeal", "бан", "мут", "warn", "варн", "санкц", "модер")):
            rows = state.db.execute(
                """SELECT id, user_id, action, reason, active, created_at
                FROM moderation_actions
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?""",
                (chat_id, limit),
            ).fetchall()
            if rows:
                lines.append("recent_moderation:")
                for row in rows:
                    lines.append(
                        f"- #{int(row[0])}; user_id={int(row[1])}; action={row[2]}; active={int(row[4])}; "
                        f"reason={truncate_text_func(row[3] or '', 120)}"
                    )
            appeal_rows = state.db.execute(
                """SELECT id, user_id, status, decision_type, source_action, reason, created_at
                FROM appeals
                ORDER BY id DESC
                LIMIT ?""",
                (limit,),
            ).fetchall()
            if appeal_rows:
                lines.append("recent_appeals:")
                for row in appeal_rows:
                    lines.append(
                        f"- #{int(row[0])}; user_id={int(row[1])}; status={row[2]}; "
                        f"decision={row[3]}; source={row[4]}; "
                        f"reason={truncate_text_func(row[5] or '', 120)}"
                    )

        if target_user_id is None and target_username:
            user_row = state.db.execute(
                "SELECT user_id, username, first_name, last_name FROM chat_events WHERE lower(username) = ? ORDER BY id DESC LIMIT 1",
                (target_username,),
            ).fetchone()
            if user_row and user_row[0] is not None:
                target_user_id = int(user_row[0])

        if target_user_id is not None:
            profile = state.db.execute(
                """SELECT user_id, first_name, username, total_score, weekly_score, season_score, contribution_score,
                          achievement_score, activity_score, behavior_score, total_xp, level, prestige, msg_count
                   FROM progression_profiles WHERE user_id = ?""",
                (target_user_id,),
            ).fetchone()
            if profile:
                label = build_actor_name_func(profile[0], profile[2] or "", profile[1] or "", "", "user")
                lines.append("target_profile:")
                lines.append(
                    f"- {label}; total={int(profile[3] or 0)}; week={int(profile[4] or 0)}; "
                    f"season={int(profile[5] or 0)}; xp={int(profile[10] or 0)}; "
                    f"level={int(profile[11] or 0)}; prestige={int(profile[12] or 0)}; "
                    f"activity={int(profile[8] or 0)}; contribution={int(profile[6] or 0)}; "
                    f"achievements={int(profile[7] or 0)}; behavior={int(profile[9] or 0)}; "
                    f"messages={int(profile[13] or 0)}"
                )

            sanctions = state.db.execute(
                """SELECT id, chat_id, action, reason, active, expires_at, created_at
                FROM moderation_actions
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?""",
                (target_user_id, limit),
            ).fetchall()
            if sanctions:
                lines.append("target_sanctions:")
                for row in sanctions:
                    lines.append(
                        f"- #{int(row[0])}; chat_id={int(row[1])}; action={row[2]}; active={int(row[4])}; "
                        f"expires_at={int(row[5]) if row[5] is not None else 0}; "
                        f"reason={truncate_text_func(row[3] or '', 120)}"
                    )

            warnings = state.db.execute(
                """SELECT chat_id, reason, expires_at, created_at
                FROM warnings
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?""",
                (target_user_id, limit),
            ).fetchall()
            if warnings:
                lines.append("target_warnings:")
                for row in warnings:
                    lines.append(
                        f"- chat_id={int(row[0])}; expires_at={int(row[2]) if row[2] is not None else 0}; "
                        f"reason={truncate_text_func(row[1] or '', 120)}"
                    )

            appeals = state.db.execute(
                """SELECT id, status, decision_type, source_action, reason, resolution, created_at
                FROM appeals
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?""",
                (target_user_id, limit),
            ).fetchall()
            if appeals:
                lines.append("target_appeals:")
                for row in appeals:
                    lines.append(
                        f"- #{int(row[0])}; status={row[1]}; decision={row[2]}; "
                        f"source={row[3]}; reason={truncate_text_func(row[4] or '', 100)}; "
                        f"resolution={truncate_text_func(row[5] or '', 100)}"
                    )

            events = state.db.execute(
                """SELECT created_at, message_type, text
                FROM chat_events
                WHERE user_id = ? AND chat_id = ?
                ORDER BY id DESC
                LIMIT ?""",
                (target_user_id, chat_id, limit),
            ).fetchall()
            if events:
                lines.append("target_recent_chat_events:")
                for row in events:
                    lines.append(
                        f"- {row[1]}: {truncate_text_func(row[2] or '', 140)}"
                    )
            participant_row = state.db.execute(
                """SELECT username, first_name, last_name, is_admin, is_bot, last_status, first_seen_at, last_seen_at, last_join_at, last_leave_at
                FROM chat_participants
                WHERE chat_id = ? AND user_id = ?""",
                (chat_id, target_user_id),
            ).fetchone()
            if participant_row:
                label = build_actor_name_func(target_user_id, participant_row[0] or "", participant_row[1] or "", participant_row[2] or "", "user")
                lines.append("target_participant_registry:")
                lines.append(
                    f"- {label}; is_admin={int(participant_row[3] or 0)}; is_bot={int(participant_row[4] or 0)}; "
                    f"last_status={participant_row[5] or ''}; first_seen_at={int(participant_row[6] or 0)}; "
                    f"last_seen_at={int(participant_row[7] or 0)}; last_join_at={int(participant_row[8] or 0) if participant_row[8] is not None else 0}; "
                    f"last_leave_at={int(participant_row[9] or 0) if participant_row[9] is not None else 0}"
                )
    return "\n".join(lines[:120])


if TYPE_CHECKING:
    from tg_codex_bridge import BridgeState
