from typing import Dict, List, Optional


def _fallback_build_actor_name(user_id: Optional[int], username: str, first_name: str, last_name: str, role: str) -> str:
    if role != "user":
        return role or "assistant"
    if username:
        handle = username if username.startswith("@") else f"@{username}"
        if user_id is not None:
            return f"{handle} id={user_id}"
        return handle
    full_name = " ".join(part for part in [first_name or "", last_name or ""] if part).strip()
    if full_name:
        return full_name
    return str(user_id or "user")


def _fallback_log_exception(_bridge: "TelegramBridge", _message: str, _error: Exception, limit: int = 10) -> None:
    del limit
    return


def _fallback_normalize_whitespace(text: str) -> str:
    return " ".join((text or "").split())


def _fallback_truncate_text(text: str, limit: int) -> str:
    cleaned = _fallback_normalize_whitespace(text)
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 3:
        return cleaned[:limit]
    return cleaned[: limit - 3].rstrip() + "..."


def _fallback_render_chat_troublemaker_summary(
    rows: List[tuple],
    *,
    build_actor_name_func,
) -> str:
    scores: Dict[str, int] = {}
    examples: Dict[str, str] = {}
    for _created_at, row_user_id, username, first_name, last_name, role, _message_type, content in rows:
        if role != "user":
            continue
        lowered = _fallback_normalize_whitespace(content).lower()
        score = 0
        if any(token in lowered for token in ("бред", "заткнись", "иди ты", "херня", "нах")):
            score += 2
        if lowered.isupper() and len(lowered) >= 8:
            score += 1
        actor = build_actor_name_func(row_user_id, username or "", first_name or "", last_name or "", role)
        if score <= 0:
            continue
        scores[actor] = scores.get(actor, 0) + score
        examples.setdefault(actor, _fallback_truncate_text(content or "", 120))
    if not scores:
        return "Сигналы трения:\n- по этой выборке явных конфликтных маркеров не видно"
    actor = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return f"Сигналы трения:\n- {actor}: {examples.get(actor, '')}".strip()


def _derive_chat_watch_confidence(rows: List[tuple]) -> Dict[str, str]:
    sample_size = len(rows)
    return {
        "activity": "высокая" if sample_size >= 40 else "средняя" if sample_size >= 15 else "низкая",
        "topic": "средняя" if sample_size >= 30 else "низкая",
        "interpretation": "средняя" if sample_size >= 50 else "низкая",
    }


def _build_chat_watch_truthfulness_footer(*, rows: List[tuple], from_stamp: str, to_stamp: str) -> str:
    confidence = _derive_chat_watch_confidence(rows)
    return "\n".join(
        [
            "",
            "6. Границы и уверенность",
            f"- вывод только по последним {len(rows)} сообщениям ({from_stamp} .. {to_stamp}), не по всей истории чата",
            "- что видно напрямую в сообщениях: тексты, их порядок и число сообщений по участникам в этой выборке",
            "- что является выводом: темы, расхождения мнений и practical focus на основе паттернов этой выборки",
            "- где есть неопределённость: мотивы людей, причины событий и любые выводы вне явных формулировок в сообщениях",
            f"- уверенность по активности участников: {confidence['activity']}",
            f"- уверенность по основным темам выборки: {confidence['topic']}",
            f"- уверенность по расхождениям мнений и интерпретации: {confidence['interpretation']}; это вывод, а не подтверждённый факт",
        ]
    )


def run_text_task(
    bridge: "TelegramBridge",
    chat_id: int,
    text: str,
    user_id: Optional[int] = None,
    chat_type: str = "private",
    assistant_persona: str = "",
    message: Optional[dict] = None,
    spontaneous_group_reply: bool = False,
) -> None:
    user_history_saved = False
    try:
        bridge.log(
            f"run_text_task start chat={chat_id} type={chat_type} user={user_id} "
            f"persona={assistant_persona or '-'} text={bridge.shorten_for_log(text)}"
        )
        bridge.state.append_history(chat_id, "user", text)
        user_history_saved = True
        answer = bridge.ask_codex(
            chat_id,
            text,
            user_id=user_id,
            chat_type=chat_type,
            assistant_persona=assistant_persona,
            message=message,
            spontaneous_group_reply=spontaneous_group_reply,
        )
        bridge.state.append_history(chat_id, "assistant", answer)
        bridge.state.record_event(chat_id, None, "assistant", "answer", answer)
        delivered_via_status = bridge.consume_answer_delivered_via_status(chat_id)
        if not delivered_via_status:
            delivery_chat_id = bridge.resolve_enterprise_delivery_chat_id(chat_id, chat_type, assistant_persona)
            reply_to_message_id = None
            if delivery_chat_id == chat_id and chat_type in {"group", "supergroup"}:
                reply_to_message_id = (message or {}).get("message_id")
            bridge.safe_send_text(delivery_chat_id, answer, reply_to_message_id=reply_to_message_id)
        bridge.clear_pending_enterprise_jobs_for_chat(chat_id)
        if chat_type in {"group", "supergroup"}:
            bridge.mark_active_group_discussion(chat_id, user_id, message)
        if spontaneous_group_reply:
            bridge.grant_group_followup_window(chat_id, user_id)
        bridge.log(f"run_text_task sent chat={chat_id} answer_len={len(answer or '')}")
    except Exception as error:
        bridge.log_exception(f"text task failed chat={chat_id}", error, limit=10)
        fallback_answer = "Не удалось обработать запрос. Ошибка записана в лог."
        if not user_history_saved:
            bridge.state.append_history(chat_id, "user", text)
        bridge.state.append_history(chat_id, "assistant", fallback_answer)
        bridge.state.record_event(chat_id, None, "assistant", "answer_error", fallback_answer)
        bridge.safe_send_text(chat_id, fallback_answer)
    finally:
        bridge.state.finish_chat_task(chat_id)


def run_recent_chat_report_task(
    bridge: "TelegramBridge",
    chat_id: int,
    user_id: Optional[int],
    text: str,
    message: Optional[dict] = None,
) -> None:
    user_history_saved = False
    try:
        from datetime import datetime

        rows = bridge.state.get_recent_chat_rows(chat_id, limit=100)
        bridge.state.append_history(chat_id, "user", text)
        user_history_saved = True
        if not rows:
            answer = "В памяти этого чата пока нет сообщений, поэтому отчёт собрать не из чего."
        else:
            chat = (message or {}).get("chat") or {}
            chat_title = bridge.state.get_chat_title(chat_id, chat.get("title") or "")
            from_stamp = datetime.fromtimestamp(rows[0][0]).strftime("%Y-%m-%d %H:%M") if rows[0][0] else "?"
            to_stamp = datetime.fromtimestamp(rows[-1][0]).strftime("%Y-%m-%d %H:%M") if rows[-1][0] else "?"
            participant_counts: Dict[str, int] = {}
            transcript_lines: List[str] = []
            build_actor_name_func = getattr(bridge, "build_actor_name", _fallback_build_actor_name)
            normalize_whitespace_func = getattr(bridge, "normalize_whitespace", _fallback_normalize_whitespace)
            truncate_text_func = getattr(bridge, "truncate_text", _fallback_truncate_text)
            for created_at, row_user_id, username, first_name, last_name, role, message_type, content in rows:
                stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                actor = build_actor_name_func(row_user_id, username or "", first_name or "", last_name or "", role)
                if role == "user":
                    participant_counts[actor] = participant_counts.get(actor, 0) + 1
                transcript_lines.append(
                    f"[{stamp}] {actor} [{message_type}]: {truncate_text_func(normalize_whitespace_func(content), 220)}"
                )
            activity_lines = ["Активность участников:"]
            for actor, count in sorted(participant_counts.items(), key=lambda item: (-item[1], item[0]))[:8]:
                activity_lines.append(f"- {actor}: {count}")
            troublemaker_summary_func = getattr(bridge, "render_chat_troublemaker_summary", None)
            if callable(troublemaker_summary_func):
                troublemaker_summary = troublemaker_summary_func(rows)
            else:
                troublemaker_summary = _fallback_render_chat_troublemaker_summary(
                    rows,
                    build_actor_name_func=build_actor_name_func,
                )
            prompt = (
                "Сделай краткий отчёт по содержанию Telegram-чата на основе последних 100 сообщений.\n"
                "Опирайся только на реально доступные локальные сообщения и контекст этой выборки.\n"
                "Нельзя выдумывать факты, причины, мотивы и действия людей вне лога.\n"
                "Всегда явно отделяй: что видно напрямую, что является выводом, где есть неопределённость.\n"
                "Если данных мало или контекст слабый, прямо скажи это.\n"
                "Явно указывай, что вывод относится только к этой выборке, а не ко всей истории чата.\n"
                "Не используй унижающие или провокационные ярлыки.\n"
                "Ответ нужен на русском и строго в формате:\n"
                "1. Главная тема обсуждения\n"
                "2. Самые активные участники\n"
                "3. Где мнения расходятся\n"
                "4. Что подтверждено / что пока только предположение\n"
                "5. Что сейчас обсуждают practically\n"
                "Если явного расхождения мнений нет, так и напиши.\n\n"
                f"Чат: {chat_title or chat_id}\n"
                f"chat_id={chat_id}\n"
                f"Сообщений в выборке: {len(rows)}\n"
                f"Период выборки: {from_stamp} .. {to_stamp}\n\n"
                + "\n".join(activity_lines)
                + "\n\n"
                + "Внутренние сигналы трения для grounding, не выводи их отдельным блоком:\n"
                + troublemaker_summary
                + "\n\n"
                "Лог сообщений:\n"
                + "\n".join(transcript_lines)
            )
            answer = bridge.ask_codex(
                chat_id,
                prompt,
                user_id=user_id,
                chat_type=((message or {}).get("chat") or {}).get("type") or "private",
                assistant_persona="jarvis",
                message=message,
                suppress_status_messages=True,
            )
            answer = (answer or "").rstrip() + _build_chat_watch_truthfulness_footer(
                rows=rows,
                from_stamp=from_stamp,
                to_stamp=to_stamp,
            )
        bridge.state.append_history(chat_id, "assistant", answer)
        bridge.state.record_event(chat_id, user_id, "assistant", "chat_watch_report", answer)
        bridge.safe_send_text(chat_id, answer, reply_to_message_id=(message or {}).get("message_id"))
    except Exception as error:
        getattr(bridge, "log_exception", lambda message, err, limit=10: _fallback_log_exception(bridge, message, err, limit))(
            f"recent chat report failed chat={chat_id}",
            error,
            limit=10,
        )
        fallback_answer = "Не удалось собрать отчёт по последним сообщениям. Ошибка записана в лог."
        if not user_history_saved:
            bridge.state.append_history(chat_id, "user", text)
        bridge.state.append_history(chat_id, "assistant", fallback_answer)
        bridge.state.record_event(chat_id, user_id, "assistant", "chat_watch_report_error", fallback_answer)
        bridge.safe_send_text(chat_id, fallback_answer, reply_to_message_id=(message or {}).get("message_id"))
    finally:
        bridge.state.finish_chat_task(chat_id)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
