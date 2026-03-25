from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence


def render_user_memory_context(
    rows: Sequence[Any],
    participant_map: Dict[int, Any],
    relation_rows: Sequence[Any],
    *,
    build_actor_name_func: Callable[[Optional[int], str, str, str, str], str],
    truncate_text_func: Callable[[str, int], str],
) -> str:
    if not rows:
        return ""
    lines = ["User memory:"]
    for row in rows:
        label = row[2] or build_actor_name_func(row[0], row[1] or "", "", "", "user")
        lines.append(f"- {label}")
        preferred_summary = row[4] or row[3] or ""
        if preferred_summary:
            lines.append(f"  summary: {truncate_text_func(preferred_summary, 260)}")
        if row[3] and row[4] and row[4] != row[3]:
            lines.append(f"  heuristic: {truncate_text_func(row[3], 180)}")
        if row[5]:
            lines.append(f"  style: {truncate_text_func(row[5], 180)}")
        if row[6]:
            lines.append(f"  topics: {truncate_text_func(row[6], 180)}")
        participant = participant_map.get(int(row[0])) if row[0] is not None else None
        if participant:
            participant_bits: List[str] = []
            if int(participant[1] or 0):
                participant_bits.append("admin")
            if participant[2]:
                participant_bits.append(f"status={participant[2]}")
            participant_bits.append(f"last_seen={int(participant[3] or 0)}")
            if participant[4] is not None:
                participant_bits.append(f"join={int(participant[4] or 0)}")
            if participant[5] is not None:
                participant_bits.append(f"leave={int(participant[5] or 0)}")
            lines.append(f"  participant: {', '.join(participant_bits)}")
    if relation_rows:
        lines.append("Reply links:")
        for source_user_id, target_reply_user_id, count in relation_rows[:4]:
            source_row = next((row for row in rows if row[0] == source_user_id), None)
            target_row = next((row for row in rows if row[0] == target_reply_user_id), None)
            source_label = (source_row[2] if source_row else "") or build_actor_name_func(source_user_id, "", "", "", "user")
            target_label = (target_row[2] if target_row else "") or build_actor_name_func(target_reply_user_id, "", "", "", "user")
            lines.append(f"- {source_label} -> {target_label}: {int(count)}")
    return "\n".join(lines)


def render_relation_memory_context(
    rows: Sequence[Any],
    labels: Dict[int, str],
    *,
    limit: int,
    truncate_text_func: Callable[[str, int], str],
) -> str:
    if not rows:
        return ""
    lines = ["Relation memory:"]
    for row in rows[: max(2, limit)]:
        low_id = int(row[0])
        high_id = int(row[1])
        lines.append(
            f"- {labels.get(low_id, f'user_id={low_id}')} <-> {labels.get(high_id, f'user_id={high_id}')}: "
            f"replies {int(row[2])}/{int(row[3])}; co_presence={int(row[4])}; "
            f"confidence={float(row[11]):.2f}"
        )
        if row[9]:
            lines.append(f"  summary: {truncate_text_func(row[9], 260)}")
        if row[8]:
            lines.append(f"  topics: {truncate_text_func(row[8], 180)}")
        tone_bits: List[str] = []
        if int(row[5] or 0) > 0:
            tone_bits.append(f"humor={int(row[5])}")
        if int(row[6] or 0) > 0:
            tone_bits.append(f"rough={int(row[6])}")
        if int(row[7] or 0) > 0:
            tone_bits.append(f"support={int(row[7])}")
        if tone_bits:
            lines.append(f"  markers: {', '.join(tone_bits)}")
    return "\n".join(lines)


def render_self_model_context(row: Any, persona: str, truncate_text_func: Callable[[str, int], str]) -> str:
    style = row["enterprise_style_invariants"] if persona == "enterprise" else row["jarvis_style_invariants"]
    lines = [
        "Self model:",
        f"- identity: {truncate_text_func(row['identity'] or '', 180)}",
        f"- active_mode: {row['active_mode'] or ''}",
        f"- capabilities: {truncate_text_func(row['capabilities'] or '', 260)}",
        f"- hard_limitations: {truncate_text_func(row['hard_limitations'] or '', 320)}",
        f"- trusted_tools: {truncate_text_func(row['trusted_tools'] or '', 260)}",
        f"- confidence_policy: {truncate_text_func(row['confidence_policy'] or '', 220)}",
        f"- current_goals: {truncate_text_func(row['current_goals'] or '', 220)}",
        f"- active_constraints: {truncate_text_func(row['active_constraints'] or '', 220)}",
        f"- honesty_rules: {truncate_text_func(row['honesty_rules'] or '', 220)}",
        f"- style_invariants: {truncate_text_func(style or '', 220)}",
    ]
    if row["last_route_kind"] or row["last_outcome"]:
        lines.append(f"- recent_runtime: route={row['last_route_kind'] or '-'}; outcome={row['last_outcome'] or '-'}")
    return "\n".join(lines)


def render_autobiographical_context(selected: Sequence[Any], truncate_text_func: Callable[[str, int], str]) -> str:
    if not selected:
        return ""
    lines = ["Autobiographical memory:"]
    for row in selected:
        stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
        lines.append(
            f"- [{stamp}] {row['category']}/{row['event_type']}: {truncate_text_func(row['title'] or '', 140)}; "
            f"status={row['status'] or '-'}; open={row['open_state'] or '-'}; importance={int(row['importance'] or 0)}"
        )
        if row["details"]:
            lines.append(f"  details: {truncate_text_func(row['details'] or '', 220)}")
    return "\n".join(lines)


def render_reflection_context(rows: Sequence[Any], truncate_text_func: Callable[[str, int], str]) -> str:
    if not rows:
        return ""
    lines = ["Recent reflections:"]
    for row in rows:
        stamp = datetime.fromtimestamp(int(row["created_at"] or 0)).strftime("%m-%d %H:%M") if row["created_at"] else "--:--"
        lines.append(f"- [{stamp}] {row['route_kind'] or '-'}: {truncate_text_func(row['lesson'] or row['observed_outcome'] or '', 220)}")
    return "\n".join(lines)


def render_skill_memory_context(matched: Sequence[Any], truncate_text_func: Callable[[str, int], str], limit: int) -> str:
    if not matched:
        return ""
    lines = ["Skill memory:"]
    for row in matched[:limit]:
        lines.append(
            f"- {row['skill_key']}: reliability={float(row['reliability'] or 0):.2f}; uses={int(row['use_count'] or 0)}; "
            f"triggers={truncate_text_func(row['trigger_tags'] or '', 120)}"
        )
        lines.append(f"  procedure: {truncate_text_func(row['procedure'] or '', 220)}")
    return "\n".join(lines)


def render_world_state_context(rows: Sequence[Any], truncate_text_func: Callable[[str, int], str]) -> str:
    if not rows:
        return ""
    lines = ["World state:"]
    for row in rows:
        value_parts: List[str] = [row["status"] or "-"]
        if row["value_number"] is not None:
            value_parts.append(f"value={float(row['value_number']):.1f}")
        if row["value_text"]:
            value_parts.append(truncate_text_func(row["value_text"] or "", 160))
        if row["source"]:
            value_parts.append(f"source={row['source']}")
        lines.append(f"- {row['category']}/{row['state_key']}: {'; '.join(value_parts)}")
    return "\n".join(lines)


def render_drive_context(rows: Sequence[Any], truncate_text_func: Callable[[str, int], str]) -> str:
    if not rows:
        return ""
    lines = ["Drive pressures:"]
    for row in rows:
        lines.append(f"- {row['drive_name']}: {float(row['score'] or 0):.1f}; reason={truncate_text_func(row['reason'] or '', 180)}")
    return "\n".join(lines)


def render_summary_memory_context(rows: Sequence[Any], truncate_text_func: Callable[[str, int], str]) -> str:
    if not rows:
        return ""
    lines = ["Summary memory:"]
    for scope, summary, created_at in reversed(rows):
        stamp = datetime.fromtimestamp(int(created_at)).strftime("%m-%d %H:%M") if created_at else "--:--"
        lines.append(f"- [{stamp}] {scope}: {truncate_text_func(summary or '', 220)}")
    return "\n".join(lines)


def render_chat_memory_context(
    *,
    summary: str,
    rows: Sequence[Any],
    facts: Sequence[str],
    dynamics: str,
    build_actor_name_func: Callable[[Optional[int], str, str, str, str], str],
    truncate_text_func: Callable[[str, int], str],
) -> str:
    lines = ["Chat memory:"]
    if summary:
        lines.append(f"- rolling summary: {truncate_text_func(summary, 260)}")
    if rows:
        active = ", ".join(
            f"{build_actor_name_func(row[0], row[1] or '', row[2] or '', row[3] or '', 'user')}={int(row[4])}"
            for row in rows
        )
        lines.append(f"- most active participants: {truncate_text_func(active, 260)}")
    if facts:
        lines.append("- remembered facts:")
        lines.extend(f"  • {truncate_text_func(fact, 140)}" for fact in facts[:4])
    if dynamics:
        lines.append(dynamics)
    return "\n".join(lines) if len(lines) > 1 else ""
