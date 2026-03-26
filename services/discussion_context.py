from datetime import datetime
from typing import Callable, Dict, List, Optional, Set, Tuple


def extract_keywords(text: str) -> Set[str]:
    words: List[str] = []
    for raw_word in (text or "").lower().replace("\n", " ").split():
        word = "".join(ch for ch in raw_word if ch.isalnum() or ch in {"_", "-"})
        if len(word) >= 4:
            words.append(word)
    return set(words[:12])


def score_discussion_row(
    row: Tuple[int, Optional[int], str, str, str, str, str, str],
    *,
    current_user_id: Optional[int],
    reply_user_id: Optional[int],
    keywords: Set[str],
) -> int:
    created_at, event_user_id, username, first_name, last_name, role, message_type, content = row
    score = 0
    if role == "assistant":
        score += 1
    if current_user_id is not None and event_user_id == current_user_id:
        score += 6
    if reply_user_id is not None and event_user_id == reply_user_id:
        score += 5
    lowered = " ".join((content or "", username or "", first_name or "", last_name or "", message_type or "")).lower()
    if keywords and any(keyword in lowered for keyword in keywords):
        score += 4
    if message_type == "answer":
        score += 2
    if message_type == "question":
        score += 2
    return score


def select_ranked_recent_rows(
    rows: List[Tuple[int, Optional[int], str, str, str, str, str, str]],
    *,
    current_user_id: Optional[int],
    reply_user_id: Optional[int],
    query_text: str,
    limit: int = 36,
) -> List[Tuple[int, Optional[int], str, str, str, str, str, str]]:
    if len(rows) <= limit:
        return rows
    keywords = extract_keywords(query_text)
    scored = []
    for index, row in enumerate(rows):
        score = score_discussion_row(
            row,
            current_user_id=current_user_id,
            reply_user_id=reply_user_id,
            keywords=keywords,
        )
        # Favor recency without flooding the prompt with only the latest noise.
        score += min(12, max(0, index - max(0, len(rows) - 24)))
        scored.append((score, index, row))
    selected = sorted(scored, key=lambda item: (-item[0], -item[1]))[:limit]
    selected_indices = {index for _score, index, _row in selected}
    ordered_rows = [row for index, row in enumerate(rows) if index in selected_indices]
    return ordered_rows


def build_discussion_summary(
    rows: List[Tuple[int, Optional[int], str, str, str, str, str, str]],
    *,
    current_speaker: str,
    reply_target: str,
    query_text: str,
    truncate_text_func: Callable[[str, int], str],
) -> str:
    if not rows:
        return ""
    keywords = sorted(extract_keywords(query_text))
    participant_counts = {}
    latest_user_points: List[str] = []
    for created_at, event_user_id, username, first_name, last_name, role, message_type, content in rows:
        actor = (
            "Jarvis"
            if role == "assistant"
            else " ".join(part for part in [first_name or "", last_name or ""] if part).strip()
            or (f"@{username}" if username else (f"user_id={event_user_id}" if event_user_id is not None else "user"))
        )
        participant_counts[actor] = participant_counts.get(actor, 0) + 1
        if current_speaker and actor == current_speaker and (content or "").strip():
            latest_user_points.append(truncate_text_func(content or "", 120))
    lines = ["Discussion summary:"]
    if current_speaker:
        lines.append(f"- focus_speaker: {current_speaker}")
    if reply_target:
        lines.append(f"- focus_reply_target: {reply_target}")
    if keywords:
        lines.append(f"- query_keywords: {', '.join(keywords[:8])}")
    top_participants = ", ".join(
        f"{name} x{count}" for name, count in sorted(participant_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
    )
    if top_participants:
        lines.append(f"- discussion_top_participants: {truncate_text_func(top_participants, 260)}")
    if latest_user_points:
        lines.append(f"- current_speaker_latest_points: {truncate_text_func(' | '.join(latest_user_points[-3:]), 320)}")
    return "\n".join(lines)


def build_current_discussion_context(
    *,
    state: object,
    chat_id: int,
    message: Optional[dict],
    user_id: Optional[int],
    query_text: str,
    active_group_followup: bool,
    active_thread: Optional[Dict[str, object]],
    build_actor_name_func: Callable[[Optional[int], str, str, str, str], str],
    build_service_actor_name_func: Callable[[dict], str],
    truncate_text_func: Callable[[str, int], str],
) -> str:
    chat = (message or {}).get("chat") or {}
    chat_type = (chat.get("type") or "").lower()
    if chat_type not in {"group", "supergroup"}:
        return ""
    blocks: List[str] = []
    source_user = (message or {}).get("from") or {}
    current_speaker = (
        build_actor_name_func(
            source_user.get("id"),
            source_user.get("username") or "",
            source_user.get("first_name") or "",
            source_user.get("last_name") or "",
            "user",
        )
        if source_user and not source_user.get("is_bot")
        else ""
    )
    reply_to = (message or {}).get("reply_to_message") or {}
    reply_from = reply_to.get("from") or {}
    reply_target = build_service_actor_name_func(reply_from) if reply_from else ""
    reply_user_id = reply_from.get("id") if reply_from and not reply_from.get("is_bot") else None

    recent_rows = state.get_recent_chat_rows(chat_id, limit=100)
    thread_participants = {
        int(item) for item in (active_thread or {}).get("participants") or [] if str(item).lstrip("-").isdigit()
    }
    thread_keywords = [str(item).lower() for item in (active_thread or {}).get("topic_keywords") or [] if str(item).strip()]
    thread_anchor_message_id = int((active_thread or {}).get("anchor_message_id") or 0)
    focused_rows = []
    if active_thread:
        for row in recent_rows:
            _created_at, event_user_id, username, first_name, last_name, role, message_type, content = row
            lowered = " ".join((content or "", username or "", first_name or "", last_name or "", message_type or "")).lower()
            if event_user_id is not None and int(event_user_id) in thread_participants:
                focused_rows.append(row)
                continue
            if thread_keywords and any(keyword in lowered or (len(keyword) >= 4 and keyword[:4] in lowered) for keyword in thread_keywords[:8]):
                focused_rows.append(row)
                continue
            if role == "assistant" and focused_rows:
                focused_rows.append(row)
    source_rows = focused_rows if len(focused_rows) >= 8 else recent_rows
    ranked_recent_rows = select_ranked_recent_rows(
        source_rows,
        current_user_id=user_id,
        reply_user_id=reply_user_id,
        query_text=query_text,
        limit=36,
    )
    if current_speaker or reply_target or recent_rows:
        participant_counts = {}
        for _created_at, event_user_id, username, first_name, last_name, role, _message_type, _content in recent_rows[-100:]:
            actor = build_actor_name_func(event_user_id, username or "", first_name or "", last_name or "", role)
            participant_counts[actor] = participant_counts.get(actor, 0) + 1
        header_lines = ["Discussion participants:"]
        if current_speaker:
            header_lines.append(f"- current_speaker: {current_speaker}")
        if reply_target:
            header_lines.append(f"- reply_target: {reply_target}")
        if participant_counts:
            top_participants = ", ".join(
                f"{name} x{count}"
                for name, count in sorted(participant_counts.items(), key=lambda item: (-item[1], item[0]))[:12]
            )
            header_lines.append(f"- active_participants: {truncate_text_func(top_participants, 400)}")
        if active_thread:
            header_lines.append(f"- active_thread_anchor_message_id: {thread_anchor_message_id}")
            if thread_keywords:
                header_lines.append(f"- active_thread_keywords: {truncate_text_func(', '.join(thread_keywords[:8]), 220)}")
        blocks.append("\n".join(header_lines))

    discussion_summary = build_discussion_summary(
        ranked_recent_rows,
        current_speaker=current_speaker,
        reply_target=reply_target,
        query_text=query_text,
        truncate_text_func=truncate_text_func,
    )
    if discussion_summary:
        blocks.append(discussion_summary)

    if ranked_recent_rows:
        window_label = "Focused active thread window:" if active_thread and focused_rows else "Recent chat window (ranked selection from last 100 messages):"
        lines = [window_label]
        for created_at, event_user_id, username, first_name, last_name, role, message_type, content in ranked_recent_rows:
            stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
            actor = build_actor_name_func(event_user_id, username or "", first_name or "", last_name or "", role)
            lines.append(f"- [{stamp}] {actor} ({message_type}): {truncate_text_func(content or '', 180)}")
        blocks.append("\n".join(lines))

    if user_id is not None:
        user_rows = state.get_recent_user_rows(chat_id, user_id, limit=12)
        if user_rows:
            lines = ["Current speaker recent messages:"]
            for created_at, event_user_id, username, first_name, last_name, message_type, content in user_rows:
                stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                actor = build_actor_name_func(event_user_id, username or "", first_name or "", last_name or "", "user")
                lines.append(f"- [{stamp}] {actor} ({message_type}): {truncate_text_func(content or '', 180)}")
            blocks.append("\n".join(lines))

    reply_message_id = reply_to.get("message_id")
    if reply_message_id is not None:
        thread_rows = state.get_thread_context(chat_id, int(reply_message_id), limit=18)
        if thread_rows:
            lines = ["Reply thread context:"]
            for created_at, event_user_id, username, first_name, last_name, role, message_type, content in thread_rows:
                stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                actor = build_actor_name_func(event_user_id, username or "", first_name or "", last_name or "", role)
                lines.append(f"- [{stamp}] {actor} ({message_type}): {truncate_text_func(content or '', 180)}")
            blocks.append("\n".join(lines))

    if reply_user_id is not None and not reply_from.get("is_bot"):
        target_rows = state.get_recent_user_rows(chat_id, int(reply_user_id), limit=10)
        if target_rows:
            lines = ["Reply target recent messages:"]
            for created_at, event_user_id, username, first_name, last_name, message_type, content in target_rows:
                stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                actor = build_actor_name_func(event_user_id, username or "", first_name or "", last_name or "", "user")
                lines.append(f"- [{stamp}] {actor} ({message_type}): {truncate_text_func(content or '', 180)}")
            blocks.append("\n".join(lines))

    if active_group_followup and user_id is not None:
        user_rows = state.get_recent_user_rows(chat_id, user_id, limit=24)
        if user_rows:
            lines = ["Recent messages from this participant:"]
            for created_at, event_user_id, username, first_name, last_name, message_type, content in user_rows:
                stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                actor = build_actor_name_func(event_user_id, username or "", first_name or "", last_name or "", "user")
                lines.append(f"- [{stamp}] {actor} ({message_type}): {truncate_text_func(content or '', 180)}")
            blocks.append("\n".join(lines))

    return "\n\n".join(block for block in blocks if block.strip())
