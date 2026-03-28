import json
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Set, Tuple

from utils.message_utils import describe_message_media_kind
from prompts.builders import extract_keywords


def analyze_participant_rows(
    rows: Sequence[sqlite3.Row],
    *,
    build_actor_name_func,
    is_owner_identity_func,
    normalize_whitespace_func,
) -> Dict[str, object]:
    rough_tokens = ("нах", "охуе", "говно", "заеб", "пизд", "заткнись", "иди ты", "долбо", "ебан")
    helpful_tokens = ("решение", "совет", "проверь", "источник", "сделай", "фикс", "ошибка", "лог")
    contradiction_tokens = ("неправ", "херня", "чуш", "бред", "врешь", "врет", "несешь")
    message_count = 0
    reply_count = 0
    reactions_given = 0
    conflict_score = 0
    toxicity_score = 0
    spam_score = 0
    flood_score = 0
    instability_score = 0
    helpfulness_score = 0
    owner_affinity_score = 0
    unique_days: Set[str] = set()
    recent_texts: List[str] = []
    seen_messages: Dict[str, int] = {}
    first_seen_at = 0
    last_seen_at = 0
    username = ""
    display_name = ""
    signal_examples: Dict[str, str] = {}
    message_times: List[int] = []
    for row in rows:
        created_at = int(row["created_at"] or 0)
        message_type = str(row["message_type"] or "")
        text = normalize_whitespace_func(row["text"] or "")
        lowered = text.lower()
        if not first_seen_at or (created_at and created_at < first_seen_at):
            first_seen_at = created_at
        if created_at > last_seen_at:
            last_seen_at = created_at
        if created_at:
            unique_days.add(datetime.fromtimestamp(created_at).strftime("%Y-%m-%d"))
            message_times.append(created_at)
        if not username:
            username = str(row["username"] or "")
        if not display_name:
            display_name = build_actor_name_func(row["user_id"], row["username"] or "", row["first_name"] or "", row["last_name"] or "", "user")
        if message_type == "reaction":
            reactions_given += 1
            continue
        message_count += 1
        if row["reply_to_user_id"] is not None:
            reply_count += 1
            if is_owner_identity_func(int(row["reply_to_user_id"] or 0)):
                if any(token in lowered for token in rough_tokens + contradiction_tokens):
                    owner_affinity_score -= 2
                    signal_examples.setdefault("owner_hostile", text)
                elif any(token in lowered for token in helpful_tokens) or ("спасибо" in lowered):
                    owner_affinity_score += 1
        if any(token in lowered for token in rough_tokens):
            toxicity_score += 3
            conflict_score += 2
            instability_score += 1
            signal_examples.setdefault("toxic", text)
        if any(token in lowered for token in contradiction_tokens):
            conflict_score += 2
            signal_examples.setdefault("conflict", text)
        if any(token in lowered for token in helpful_tokens):
            helpfulness_score += 2
            signal_examples.setdefault("helpful", text)
        if len(text) >= 180 and any(token in lowered for token in helpful_tokens):
            helpfulness_score += 2
        if text:
            seen_messages[text] = seen_messages.get(text, 0) + 1
            if seen_messages[text] >= 3:
                spam_score += 2
                signal_examples.setdefault("spam", text)
            recent_texts.append(text)
            if len(recent_texts) >= 3 and recent_texts[-1] == recent_texts[-2] == recent_texts[-3]:
                spam_score += 3
                signal_examples.setdefault("spam", text)
    for stamp in sorted(message_times):
        burst = sum(1 for item in message_times if stamp - 90 <= item <= stamp + 90)
        if burst >= 4:
            flood_score = max(flood_score, burst - 3)
    credibility_score = max(0, helpfulness_score * 2 - toxicity_score - spam_score)
    risk_flags: List[str] = []
    if toxicity_score >= 4:
        risk_flags.append("toxic")
    if conflict_score >= 4:
        risk_flags.append("high_conflict")
    if spam_score >= 3:
        risk_flags.append("spammy")
    if flood_score >= 2:
        risk_flags.append("flood_prone")
    if instability_score >= 2:
        risk_flags.append("emotionally_unstable")
    if helpfulness_score >= 6:
        risk_flags.append("helpful")
    if credibility_score >= 8:
        risk_flags.append("technically_reliable")
    if owner_affinity_score <= -2:
        risk_flags.append("owner_hostile")
    notes: List[str] = []
    if message_count:
        notes.append(f"сообщений={message_count}")
    if reply_count:
        notes.append(f"reply={reply_count}")
    if reactions_given:
        notes.append(f"reactions_given={reactions_given}")
    if helpfulness_score >= 6:
        notes.append("часто пишет по делу")
    if toxicity_score >= 4:
        notes.append("часто срывается в грубость")
    if spam_score >= 3:
        notes.append("склонен к повторам")
    if flood_score >= 2:
        notes.append("умеет зафлуживать окно")
    if owner_affinity_score <= -2:
        notes.append("часто жёстко отвечает владельцу")
    if owner_affinity_score >= 2:
        notes.append("обычно к владельцу лоялен")
    return {
        "username": username,
        "display_name": display_name,
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
        "message_count": message_count,
        "reply_count": reply_count,
        "reactions_given": reactions_given,
        "conflict_score": conflict_score,
        "toxicity_score": toxicity_score,
        "spam_score": spam_score,
        "flood_score": flood_score,
        "instability_score": instability_score,
        "helpfulness_score": helpfulness_score,
        "credibility_score": credibility_score,
        "owner_affinity_score": owner_affinity_score,
        "risk_flags": risk_flags,
        "notes_summary": "; ".join(notes),
        "signal_examples": signal_examples,
        "unique_days": len(unique_days),
    }


def refresh_participant_behavior_profile(
    state: "BridgeState",
    user_id: int,
    *,
    chat_id: Optional[int],
    truncate_text_func,
    normalize_visual_analysis_text_func,
    build_actor_name_func,
    is_owner_identity_func,
) -> None:
    if not user_id:
        return

    def _merge_visual_signals(stats: Dict[str, object], signal_rows: List[sqlite3.Row]) -> Dict[str, object]:
        if not signal_rows:
            return stats
        merged = dict(stats)
        risk_flags = list(merged.get("risk_flags") or [])
        signal_examples = dict(merged.get("signal_examples") or {})
        notes_summary = str(merged.get("notes_summary") or "")
        suspicious_hits = 0
        scam_hits = 0
        sexual_hits = 0
        bot_hits = 0
        for row in signal_rows:
            try:
                flags = json.loads(row["risk_flags_json"] or "[]")
            except ValueError:
                flags = []
            analysis_text = truncate_text_func(normalize_visual_analysis_text_func(row["analysis_text"] or row["caption"] or ""), 280)
            if any(flag in flags for flag in ("suspicious_visual", "fake_identity", "engagement_bait")):
                suspicious_hits += 1
                signal_examples.setdefault("suspicious_visual", analysis_text)
            if any(flag in flags for flag in ("romance_scam", "scam_risk", "promo_bait")):
                scam_hits += 1
                signal_examples.setdefault("scam_risk", analysis_text)
            if any(flag in flags for flag in ("sexual_bait", "adult_promo", "sexualized_profile")):
                sexual_hits += 1
                signal_examples.setdefault("sexual_bait", analysis_text)
            if any(flag in flags for flag in ("likely_bot", "bot_like", "mass_bait")):
                bot_hits += 1
                signal_examples.setdefault("likely_bot", analysis_text)
        if suspicious_hits:
            risk_flags.append("suspicious_visual")
        if scam_hits:
            risk_flags.append("scam_risk")
        if sexual_hits:
            risk_flags.append("sexual_bait")
        if bot_hits:
            risk_flags.append("likely_bot_like")
        merged["risk_flags"] = list(dict.fromkeys(risk_flags))
        merged["signal_examples"] = signal_examples
        merged["spam_score"] = int(merged.get("spam_score") or 0) + suspicious_hits + bot_hits
        merged["instability_score"] = int(merged.get("instability_score") or 0) + sexual_hits
        merged["conflict_score"] = int(merged.get("conflict_score") or 0) + scam_hits
        visual_notes: List[str] = []
        if suspicious_hits:
            visual_notes.append("подозрительный визуальный паттерн")
        if scam_hits:
            visual_notes.append("визуально похож на bait/scam")
        if sexual_hits:
            visual_notes.append("есть sexualized bait сигналы")
        if bot_hits:
            visual_notes.append("есть признаки неаутентичного аккаунта")
        merged["notes_summary"] = "; ".join(part for part in [notes_summary, ", ".join(visual_notes)] if part)
        return merged

    with state.db_lock:
        table_names = {
            str(row["name"])
            for row in state.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        global_rows = state.db.execute(
            """SELECT created_at, user_id, username, first_name, last_name, message_type, text, reply_to_user_id, message_id
            FROM chat_events
            WHERE role = 'user' AND user_id = ?
            ORDER BY id ASC""",
            (user_id,),
        ).fetchall()
        if not global_rows:
            return
        global_stats = analyze_participant_rows(
            global_rows,
            build_actor_name_func=build_actor_name_func,
            is_owner_identity_func=is_owner_identity_func,
            normalize_whitespace_func=state.normalize_whitespace,
        )
        visual_global_rows = state.db.execute(
            """SELECT risk_flags_json, analysis_text, caption
            FROM participant_visual_signals
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20""",
            (user_id,),
        ).fetchall()
        global_stats = _merge_visual_signals(global_stats, visual_global_rows)
        reactions_received = 0
        if "score_events" in table_names:
            reactions_received = int(state.db.execute("SELECT COUNT(*) FROM score_events WHERE user_id = ? AND event_type = 'reaction_received'", (user_id,)).fetchone()[0] or 0)
        state.db.execute("DELETE FROM participant_observations WHERE user_id = ? AND chat_id = 0", (user_id,))
        for signal_type, example in dict(global_stats.get("signal_examples") or {}).items():
            score_delta = int(global_stats.get("toxicity_score", 0) or 0) if signal_type == "toxic" else 1
            state.db.execute(
                """INSERT INTO participant_observations(user_id, chat_id, signal_type, score_delta, evidence_text, created_at)
                VALUES(?, 0, ?, ?, ?, strftime('%s','now'))""",
                (user_id, signal_type, score_delta, truncate_text_func(example, 280)),
            )
        state.db.execute(
            """INSERT INTO participant_profiles(
                user_id, username, display_name, first_seen_at, last_seen_at, message_count, reply_count,
                reactions_given, reactions_received, conflict_score, toxicity_score, spam_score, flood_score,
                instability_score, helpfulness_score, credibility_score, owner_affinity_score, risk_flags_json,
                notes_summary, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                first_seen_at = excluded.first_seen_at,
                last_seen_at = excluded.last_seen_at,
                message_count = excluded.message_count,
                reply_count = excluded.reply_count,
                reactions_given = excluded.reactions_given,
                reactions_received = excluded.reactions_received,
                conflict_score = excluded.conflict_score,
                toxicity_score = excluded.toxicity_score,
                spam_score = excluded.spam_score,
                flood_score = excluded.flood_score,
                instability_score = excluded.instability_score,
                helpfulness_score = excluded.helpfulness_score,
                credibility_score = excluded.credibility_score,
                owner_affinity_score = excluded.owner_affinity_score,
                risk_flags_json = excluded.risk_flags_json,
                notes_summary = excluded.notes_summary,
                updated_at = excluded.updated_at""",
            (
                user_id,
                str(global_stats.get("username") or ""),
                str(global_stats.get("display_name") or str(user_id)),
                int(global_stats.get("first_seen_at") or 0),
                int(global_stats.get("last_seen_at") or 0),
                int(global_stats.get("message_count") or 0),
                int(global_stats.get("reply_count") or 0),
                int(global_stats.get("reactions_given") or 0),
                reactions_received,
                int(global_stats.get("conflict_score") or 0),
                int(global_stats.get("toxicity_score") or 0),
                int(global_stats.get("spam_score") or 0),
                int(global_stats.get("flood_score") or 0),
                int(global_stats.get("instability_score") or 0),
                int(global_stats.get("helpfulness_score") or 0),
                int(global_stats.get("credibility_score") or 0),
                int(global_stats.get("owner_affinity_score") or 0),
                json.dumps(global_stats.get("risk_flags") or [], ensure_ascii=False),
                truncate_text_func(str(global_stats.get("notes_summary") or ""), 320),
            ),
        )
        if chat_id is not None:
            chat_rows = state.db.execute(
                """SELECT created_at, user_id, username, first_name, last_name, message_type, text, reply_to_user_id, message_id
                FROM chat_events
                WHERE role = 'user' AND chat_id = ? AND user_id = ?
                ORDER BY id ASC""",
                (chat_id, user_id),
            ).fetchall()
            if chat_rows:
                chat_stats = analyze_participant_rows(
                    chat_rows,
                    build_actor_name_func=build_actor_name_func,
                    is_owner_identity_func=is_owner_identity_func,
                    normalize_whitespace_func=state.normalize_whitespace,
                )
                visual_chat_rows = state.db.execute(
                    """SELECT risk_flags_json, analysis_text, caption
                    FROM participant_visual_signals
                    WHERE chat_id = ? AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 12""",
                    (chat_id, user_id),
                ).fetchall()
                chat_stats = _merge_visual_signals(chat_stats, visual_chat_rows)
                state.db.execute("DELETE FROM participant_observations WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
                for signal_type, example in dict(chat_stats.get("signal_examples") or {}).items():
                    score_delta = int(chat_stats.get("toxicity_score", 0) or 0) if signal_type == "toxic" else 1
                    state.db.execute(
                        """INSERT INTO participant_observations(user_id, chat_id, signal_type, score_delta, evidence_text, created_at)
                        VALUES(?, ?, ?, ?, ?, strftime('%s','now'))""",
                        (user_id, chat_id, signal_type, score_delta, truncate_text_func(example, 280)),
                    )
                chat_reactions_received = 0
                if "score_events" in table_names:
                    chat_reactions_received = int(
                        state.db.execute(
                            "SELECT COUNT(*) FROM score_events WHERE user_id = ? AND chat_id = ? AND event_type = 'reaction_received'",
                            (user_id, chat_id),
                        ).fetchone()[0]
                        or 0
                    )
                state.db.execute(
                    """INSERT INTO participant_chat_profiles(
                        chat_id, user_id, username, display_name, first_seen_at, last_seen_at, message_count, reply_count,
                        reactions_given, reactions_received, conflict_score, toxicity_score, spam_score, flood_score,
                        instability_score, helpfulness_score, credibility_score, risk_flags_json, notes_summary, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                    ON CONFLICT(chat_id, user_id) DO UPDATE SET
                        username = excluded.username,
                        display_name = excluded.display_name,
                        first_seen_at = excluded.first_seen_at,
                        last_seen_at = excluded.last_seen_at,
                        message_count = excluded.message_count,
                        reply_count = excluded.reply_count,
                        reactions_given = excluded.reactions_given,
                        reactions_received = excluded.reactions_received,
                        conflict_score = excluded.conflict_score,
                        toxicity_score = excluded.toxicity_score,
                        spam_score = excluded.spam_score,
                        flood_score = excluded.flood_score,
                        instability_score = excluded.instability_score,
                        helpfulness_score = excluded.helpfulness_score,
                        credibility_score = excluded.credibility_score,
                        risk_flags_json = excluded.risk_flags_json,
                        notes_summary = excluded.notes_summary,
                        updated_at = excluded.updated_at""",
                    (
                        chat_id,
                        user_id,
                        str(chat_stats.get("username") or ""),
                        str(chat_stats.get("display_name") or str(user_id)),
                        int(chat_stats.get("first_seen_at") or 0),
                        int(chat_stats.get("last_seen_at") or 0),
                        int(chat_stats.get("message_count") or 0),
                        int(chat_stats.get("reply_count") or 0),
                        int(chat_stats.get("reactions_given") or 0),
                        chat_reactions_received,
                        int(chat_stats.get("conflict_score") or 0),
                        int(chat_stats.get("toxicity_score") or 0),
                        int(chat_stats.get("spam_score") or 0),
                        int(chat_stats.get("flood_score") or 0),
                        int(chat_stats.get("instability_score") or 0),
                        int(chat_stats.get("helpfulness_score") or 0),
                        int(chat_stats.get("credibility_score") or 0),
                        json.dumps(chat_stats.get("risk_flags") or [], ensure_ascii=False),
                        truncate_text_func(str(chat_stats.get("notes_summary") or ""), 320),
                    ),
                )
        state.db.commit()


def get_participant_behavior_context(
    state: "BridgeState",
    chat_id: int,
    *,
    target_user_id: Optional[int],
    translate_risk_flag_func,
    truncate_text_func,
    normalize_whitespace_func,
    normalize_visual_analysis_text_func,
) -> str:
    if target_user_id is None:
        return ""
    with state.db_lock:
        global_row = state.db.execute("SELECT * FROM participant_profiles WHERE user_id = ?", (target_user_id,)).fetchone()
        chat_row = state.db.execute("SELECT * FROM participant_chat_profiles WHERE chat_id = ? AND user_id = ?", (chat_id, target_user_id)).fetchone()
        observation_rows = state.db.execute(
            """SELECT signal_type, evidence_text
            FROM participant_observations
            WHERE user_id = ? AND chat_id IN (0, ?)
            ORDER BY created_at DESC
            LIMIT 6""",
            (target_user_id, chat_id),
        ).fetchall()
        visual_rows = state.db.execute(
            """SELECT analysis_text, risk_flags_json
            FROM participant_visual_signals
            WHERE user_id = ? AND chat_id IN (?, 0)
            ORDER BY created_at DESC
            LIMIT 3""",
            (target_user_id, chat_id),
        ).fetchall()
    if not global_row and not chat_row:
        return ""
    lines = ["Поведенческий профиль:"]
    if chat_row:
        flags = ", ".join(translate_risk_flag_func(flag) for flag in json.loads(chat_row["risk_flags_json"] or "[]")) or "нет"
        lines.append(
            f"- по чату: сообщений={int(chat_row['message_count'] or 0)}; конфликт={int(chat_row['conflict_score'] or 0)}; токсичность={int(chat_row['toxicity_score'] or 0)}; спам={int(chat_row['spam_score'] or 0)}; флуд={int(chat_row['flood_score'] or 0)}; полезность={int(chat_row['helpfulness_score'] or 0)}; доверие={int(chat_row['credibility_score'] or 0)}; флаги={flags}"
        )
        if chat_row["notes_summary"]:
            lines.append(f"- заметки по чату: {chat_row['notes_summary']}")
    if global_row:
        flags = ", ".join(translate_risk_flag_func(flag) for flag in json.loads(global_row["risk_flags_json"] or "[]")) or "нет"
        lines.append(
            f"- глобально: сообщений={int(global_row['message_count'] or 0)}; reply={int(global_row['reply_count'] or 0)}; реакций отправлено={int(global_row['reactions_given'] or 0)}; реакций получено={int(global_row['reactions_received'] or 0)}; отношение к владельцу={int(global_row['owner_affinity_score'] or 0)}; флаги={flags}"
        )
        if global_row["notes_summary"]:
            lines.append(f"- глобальные заметки: {global_row['notes_summary']}")
    if observation_rows:
        lines.append("Последние сигналы:")
        for row in observation_rows[:4]:
            lines.append(f"- {row['signal_type']}: {truncate_text_func(normalize_whitespace_func(row['evidence_text'] or ''), 180)}")
    if visual_rows:
        lines.append("Визуальные сигналы:")
        for row in visual_rows:
            try:
                flags = ", ".join(translate_risk_flag_func(flag) for flag in json.loads(row["risk_flags_json"] or "[]")[:4]) or "нет"
            except ValueError:
                flags = "нет"
            lines.append(f"- {flags}: {truncate_text_func(normalize_visual_analysis_text_func(row['analysis_text'] or ''), 180)}")
    return "\n".join(lines)


def record_participant_visual_signal(
    state: "BridgeState",
    *,
    chat_id: int,
    user_id: int,
    message_id: int,
    file_unique_id: str,
    media_sha256: str,
    caption: str,
    analysis_text: str,
    risk_flags: List[str],
    truncate_text_func,
    normalize_visual_analysis_text_func,
) -> None:
    with state.db_lock:
        state.db.execute(
            """INSERT INTO participant_visual_signals(
                chat_id, user_id, message_id, file_unique_id, media_sha256, caption, analysis_text, risk_flags_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
            ON CONFLICT(chat_id, message_id) DO UPDATE SET
                file_unique_id = excluded.file_unique_id,
                media_sha256 = excluded.media_sha256,
                caption = excluded.caption,
                analysis_text = excluded.analysis_text,
                risk_flags_json = excluded.risk_flags_json,
                created_at = excluded.created_at""",
            (
                chat_id,
                user_id,
                message_id,
                file_unique_id or "",
                media_sha256 or "",
                truncate_text_func(caption or "", 500),
                truncate_text_func(normalize_visual_analysis_text_func(analysis_text or ""), 1200),
                json.dumps(risk_flags or [], ensure_ascii=False),
            ),
        )
        state.db.commit()


def get_visual_signal_for_message(state: "BridgeState", chat_id: int, message_id: int) -> Optional[sqlite3.Row]:
    with state.db_lock:
        row = state.db.execute(
            """SELECT user_id, caption, analysis_text, risk_flags_json, created_at
            FROM participant_visual_signals
            WHERE chat_id = ? AND message_id = ?
            LIMIT 1""",
            (chat_id, message_id),
        ).fetchone()
    return row


def record_message_subject(
    state: "BridgeState",
    *,
    chat_id: int,
    message_id: int,
    subject_type: str,
    source_kind: str,
    user_id: int = 0,
    summary: str = "",
    details: Optional[Dict[str, object]] = None,
    truncate_text_func,
    normalize_whitespace_func,
) -> None:
    if not chat_id or not message_id or not subject_type.strip():
        return
    with state.db_lock:
        state.db.execute(
            """INSERT INTO message_subjects(
                chat_id, message_id, subject_type, source_kind, user_id, summary, details_json, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
            ON CONFLICT(chat_id, message_id) DO UPDATE SET
                subject_type = excluded.subject_type,
                source_kind = excluded.source_kind,
                user_id = excluded.user_id,
                summary = excluded.summary,
                details_json = excluded.details_json,
                updated_at = excluded.updated_at""",
            (
                chat_id,
                message_id,
                subject_type.strip(),
                source_kind.strip(),
                int(user_id or 0),
                truncate_text_func(normalize_whitespace_func(summary or ""), 1200),
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )
        state.db.commit()


def get_message_subject(state: "BridgeState", chat_id: int, message_id: int) -> Optional[sqlite3.Row]:
    with state.db_lock:
        row = state.db.execute(
            """SELECT chat_id, message_id, subject_type, source_kind, user_id, summary, details_json, updated_at
            FROM message_subjects
            WHERE chat_id = ? AND message_id = ?
            LIMIT 1""",
            (chat_id, message_id),
        ).fetchone()
    return row


def set_active_subject(
    state: "BridgeState",
    *,
    chat_id: int,
    user_id: Optional[int],
    message_id: int,
    subject_type: str,
    source: str = "",
) -> None:
    if not chat_id or not message_id or not subject_type.strip():
        return
    scope_user_id = int(user_id or 0)
    payload = {
        "chat_id": int(chat_id),
        "user_id": scope_user_id,
        "message_id": int(message_id),
        "subject_type": subject_type.strip(),
        "source": source.strip(),
        "updated_at": int(time.time()),
    }
    state.set_meta(f"active_subject:{chat_id}:{scope_user_id}", json.dumps(payload, ensure_ascii=False))


def get_active_subject(state: "BridgeState", chat_id: int, user_id: Optional[int]) -> Optional[Dict[str, object]]:
    scope_user_id = int(user_id or 0)
    raw = state.get_meta(f"active_subject:{chat_id}:{scope_user_id}", "")
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if int(payload.get("chat_id") or 0) != int(chat_id):
        return None
    updated_at = int(payload.get("updated_at") or 0)
    if updated_at and int(time.time()) - updated_at > 600:
        return None
    return payload


def refresh_user_memory_profile(
    state: "BridgeState",
    chat_id: int,
    user_id: Optional[int],
    *,
    username: str,
    first_name: str,
    last_name: str,
    owner_user_id: int,
    owner_memory_chat_id: int,
    build_actor_name_func,
    truncate_text_func,
) -> None:
    if user_id is None:
        return

    def _build_profile_payload(source_rows: List[sqlite3.Row], *, label: str, owner_scope: bool = False) -> Tuple[str, str, str, int]:
        recent_rows = list(reversed(source_rows))
        type_counts: Dict[str, int] = {}
        keyword_counts: Dict[str, int] = {}
        text_messages = 0
        media_messages = 0
        total_chars = 0
        for created_at, message_type, text in recent_rows:
            type_counts[message_type] = type_counts.get(message_type, 0) + 1
            if message_type in {"text", "edited_text", "caption", "edited_caption"}:
                text_messages += 1
                total_chars += len(text or "")
            else:
                media_messages += 1
            for keyword in extract_keywords(text or ""):
                if keyword.isdigit():
                    continue
                keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
        average_length = int(total_chars / max(1, text_messages)) if text_messages else 0
        style_notes: List[str] = []
        if owner_scope:
            style_notes.append("владелец проекта")
        if average_length >= 220:
            style_notes.append("пишет развёрнуто")
        elif average_length >= 90:
            style_notes.append("обычно пишет средними сообщениями")
        elif text_messages > 0:
            style_notes.append("пишет коротко")
        if media_messages >= max(2, text_messages):
            style_notes.append("часто использует медиа и сервисные форматы")
        if type_counts.get("voice", 0) >= 2:
            style_notes.append("регулярно шлёт голосовые")
        if type_counts.get("photo", 0) >= 2:
            style_notes.append("часто отправляет фото")
        top_topics = [word for word, _count in sorted(keyword_counts.items(), key=lambda item: (-item[1], item[0]))[:6]]
        summary_parts = [
            f"{label}: сообщений в выборке {len(recent_rows)}",
            "память по всем чатам владельца" if owner_scope else "",
            f"форматы: {', '.join(f'{name}={count}' for name, count in sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[:5])}" if type_counts else "",
            f"стиль: {', '.join(style_notes)}" if style_notes else "",
            f"темы: {', '.join(top_topics)}" if top_topics else "",
        ]
        summary = ". ".join(part for part in summary_parts if part).strip()
        last_message_at = int(recent_rows[-1][0] or 0)
        return (
            truncate_text_func(summary, 900),
            truncate_text_func(", ".join(style_notes), 320),
            truncate_text_func(", ".join(top_topics), 320),
            last_message_at,
        )

    with state.db_lock:
        rows = state.db.execute(
            """SELECT created_at, message_type, text
            FROM chat_events
            WHERE chat_id = ? AND role = 'user' AND user_id = ?
            ORDER BY id DESC
            LIMIT 40""",
            (chat_id, user_id),
        ).fetchall()
    if not rows:
        return
    label = build_actor_name_func(user_id, username, first_name, last_name, "user")
    summary, style_notes_text, topics_text, last_message_at = _build_profile_payload(rows, label=label)
    with state.db_lock:
        state.db.execute(
            """INSERT INTO user_memory_profiles(
                chat_id, user_id, username, display_name, summary, ai_summary, style_notes, topics, last_message_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, '', ?, ?, ?, strftime('%s','now'))
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                summary = excluded.summary,
                ai_summary = user_memory_profiles.ai_summary,
                style_notes = excluded.style_notes,
                topics = excluded.topics,
                last_message_at = excluded.last_message_at,
                updated_at = excluded.updated_at""",
            (
                chat_id,
                user_id,
                username or "",
                label,
                summary,
                style_notes_text,
                topics_text,
                last_message_at,
            ),
        )
        if user_id == owner_user_id:
            global_rows = state.db.execute(
                """SELECT created_at, message_type, text
                FROM chat_events
                WHERE role = 'user' AND user_id = ?
                ORDER BY id DESC
                LIMIT 120""",
                (user_id,),
            ).fetchall()
            if global_rows:
                owner_label = build_actor_name_func(user_id, username, first_name, last_name, "user")
                global_summary, global_style_notes, global_topics, global_last_message_at = _build_profile_payload(
                    global_rows,
                    label=owner_label,
                    owner_scope=True,
                )
                state.db.execute(
                    """INSERT INTO user_memory_profiles(
                        chat_id, user_id, username, display_name, summary, ai_summary, style_notes, topics, last_message_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, '', ?, ?, ?, strftime('%s','now'))
                    ON CONFLICT(chat_id, user_id) DO UPDATE SET
                        username = excluded.username,
                        display_name = excluded.display_name,
                        summary = excluded.summary,
                        ai_summary = user_memory_profiles.ai_summary,
                        style_notes = excluded.style_notes,
                        topics = excluded.topics,
                        last_message_at = excluded.last_message_at,
                        updated_at = excluded.updated_at""",
                    (
                        owner_memory_chat_id,
                        user_id,
                        username or "",
                        owner_label,
                        global_summary,
                        global_style_notes,
                        global_topics,
                        global_last_message_at,
                    ),
                )
        state.db.commit()


def get_user_memory_context(
    state: "BridgeState",
    chat_id: int,
    *,
    user_id: Optional[int] = None,
    reply_to_user_id: Optional[int] = None,
    limit: int = 2,
    render_user_memory_context_func,
    owner_user_id: int,
    owner_memory_chat_id: int,
    build_actor_name_func,
    truncate_text_func,
) -> str:
    target_ids: List[int] = []
    for candidate in [user_id, reply_to_user_id]:
        if candidate is None:
            continue
        if candidate not in target_ids:
            target_ids.append(candidate)
    if not target_ids:
        return ""
    selected_ids = target_ids[:limit]
    placeholders = ",".join("?" for _ in selected_ids)
    params: List[object] = [chat_id, *selected_ids]
    with state.db_lock:
        rows = state.db.execute(
            f"""SELECT chat_id, user_id, username, display_name, summary, ai_summary, style_notes, topics, updated_at
            FROM user_memory_profiles
            WHERE chat_id = ? AND user_id IN ({placeholders})
            ORDER BY updated_at DESC""",
            params,
        ).fetchall()
        if owner_user_id in selected_ids:
            owner_global_rows = state.db.execute(
                """SELECT chat_id, user_id, username, display_name, summary, ai_summary, style_notes, topics, updated_at
                FROM user_memory_profiles
                WHERE chat_id = ? AND user_id = ?
                ORDER BY updated_at DESC""",
                (owner_memory_chat_id, owner_user_id),
            ).fetchall()
            if owner_global_rows:
                rows = list(owner_global_rows) + list(rows)
        participant_rows = state.db.execute(
            f"""SELECT user_id, is_admin, last_status, last_seen_at, last_join_at, last_leave_at
            FROM chat_participants
            WHERE chat_id = ? AND user_id IN ({placeholders})""",
            params,
        ).fetchall()
        relation_rows = state.db.execute(
            f"""SELECT user_id, reply_to_user_id, COUNT(*) AS cnt
            FROM chat_events
            WHERE chat_id = ? AND role = 'user'
              AND ((user_id IN ({placeholders}) AND reply_to_user_id IS NOT NULL)
                OR (reply_to_user_id IN ({placeholders}) AND user_id IS NOT NULL))
            GROUP BY user_id, reply_to_user_id
            ORDER BY cnt DESC
            LIMIT 8""",
            [chat_id, *selected_ids, *selected_ids],
        ).fetchall()
    if not rows:
        return ""
    participant_map = {int(row[0]): row for row in participant_rows if row[0] is not None}
    rendered = render_user_memory_context_func(
        rows,
        participant_map,
        relation_rows,
        build_actor_name_func=build_actor_name_func,
        truncate_text_func=truncate_text_func,
    )
    if owner_user_id in selected_ids:
        cross_chat_context = state.get_owner_cross_chat_memory_context(limit=4)
        if cross_chat_context:
            return f"{rendered}\n\n{cross_chat_context}".strip()
    return rendered


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import BridgeState
