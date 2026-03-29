import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from pipeline.diagnostics import build_attachment_bundle


def ask_codex_with_image(
    bridge: "TelegramBridge",
    chat_id: int,
    image_path: Path,
    caption: str,
    message: Optional[dict] = None,
    *,
    default_image_prompt: str,
    build_prompt_func,
    normalize_whitespace_func,
    truncate_text_func,
) -> str:
    prompt_text = caption or default_image_prompt
    persona = bridge.state.get_mode(chat_id)
    reply_context = bridge.build_reply_context(chat_id, message)
    active_subject_context = bridge.build_active_subject_context(chat_id, None, prompt_text, message)
    if active_subject_context:
        reply_context = f"{reply_context}\n\n{active_subject_context}" if reply_context else active_subject_context
    context_bundle = bridge.build_attachment_context_bundle(
        chat_id=chat_id,
        prompt_text=prompt_text,
        persona=persona,
        message=message,
        reply_context=reply_context,
    )
    attachment_bundle = build_attachment_bundle(
        attachment_type="image",
        extracted_text=caption or "",
        structured_features=f"path={image_path.name}; has_caption={'yes' if caption else 'no'}",
        source_message_link=f"chat:{chat_id}",
        relevance_score=0.92,
        used_in_response=True,
        normalize_whitespace_func=normalize_whitespace_func,
        truncate_text_func=truncate_text_func,
    )
    prompt = build_prompt_func(
        mode=persona,
        history=list(bridge.state.get_history(chat_id)),
        user_text=prompt_text,
        attachment_note=(
            "Пользователь прислал изображение. Анализируй само изображение и подпись вместе.\n"
            f"AttachmentBundle: type={attachment_bundle.attachment_type}; "
            f"features={attachment_bundle.structured_features}; "
            f"relevance={attachment_bundle.relevance_score:.2f}"
        ),
        summary_text=context_bundle.summary_text,
        facts_text=context_bundle.facts_text,
        event_context=context_bundle.event_context,
        database_context=context_bundle.database_context,
        reply_context=context_bundle.reply_context,
        discussion_context=context_bundle.discussion_context,
        route_summary=context_bundle.route_summary,
        guardrail_note=context_bundle.guardrail_note,
        self_model_text=context_bundle.self_model_text,
        autobiographical_text=context_bundle.autobiographical_text,
        skill_memory_text=context_bundle.skill_memory_text,
        world_state_text=context_bundle.world_state_text,
        drive_state_text=context_bundle.drive_state_text,
        user_memory_text=context_bundle.user_memory_text,
        relation_memory_text=context_bundle.relation_memory_text,
        chat_memory_text=context_bundle.chat_memory_text,
        summary_memory_text=context_bundle.summary_memory_text,
        task_context_text=context_bundle.task_context_text,
        memory_trace_text=context_bundle.memory_trace_text,
    )
    return bridge.run_codex(prompt, image_path=image_path)


def ask_codex_with_document(
    bridge: "TelegramBridge",
    chat_id: int,
    document_path: Path,
    document: dict,
    caption: str,
    file_excerpt: str,
    message: Optional[dict] = None,
    *,
    build_prompt_func,
    format_file_size_func,
    normalize_whitespace_func,
    truncate_text_func,
) -> str:
    file_name = document.get("file_name") or document_path.name
    mime_type = document.get("mime_type") or "application/octet-stream"
    file_size = document.get("file_size") or 0
    prompt_text = caption or f"Разбери документ {file_name} и кратко скажи, что в нём важно."
    persona = bridge.state.get_mode(chat_id)
    reply_context = bridge.build_reply_context(chat_id, message)
    active_subject_context = bridge.build_active_subject_context(chat_id, None, prompt_text, message)
    if active_subject_context:
        reply_context = f"{reply_context}\n\n{active_subject_context}" if reply_context else active_subject_context
    context_bundle = bridge.build_attachment_context_bundle(
        chat_id=chat_id,
        prompt_text=prompt_text,
        persona=persona,
        message=message,
        reply_context=reply_context,
    )
    attachment_bundle = build_attachment_bundle(
        attachment_type="document",
        extracted_text=file_excerpt,
        structured_features=(
            f"file_name={file_name}; mime={mime_type}; "
            f"size={format_file_size_func(int(file_size)) if file_size else 'unknown'}"
        ),
        source_message_link=f"chat:{chat_id}",
        relevance_score=0.95 if file_excerpt else 0.72,
        used_in_response=True,
        normalize_whitespace_func=normalize_whitespace_func,
        truncate_text_func=truncate_text_func,
    )
    attachment_lines = [
        "Пользователь прислал документ.",
        f"Имя файла: {file_name}",
        f"MIME: {mime_type}",
        f"Размер: {format_file_size_func(int(file_size)) if file_size else 'неизвестно'}",
        f"AttachmentBundle: type={attachment_bundle.attachment_type}; features={attachment_bundle.structured_features}; relevance={attachment_bundle.relevance_score:.2f}",
    ]
    if file_excerpt:
        attachment_lines.append("Текстовый фрагмент файла:")
        attachment_lines.append(file_excerpt)
    else:
        attachment_lines.append("Текстовый фрагмент файла недоступен. Анализируй только метаданные, подпись и контекст.")
    prompt = build_prompt_func(
        mode=persona,
        history=list(bridge.state.get_history(chat_id)),
        user_text=prompt_text,
        attachment_note="\n".join(attachment_lines),
        summary_text=context_bundle.summary_text,
        facts_text=context_bundle.facts_text,
        event_context=context_bundle.event_context,
        database_context=context_bundle.database_context,
        reply_context=context_bundle.reply_context,
        discussion_context=context_bundle.discussion_context,
        route_summary=context_bundle.route_summary,
        guardrail_note=context_bundle.guardrail_note,
        self_model_text=context_bundle.self_model_text,
        autobiographical_text=context_bundle.autobiographical_text,
        skill_memory_text=context_bundle.skill_memory_text,
        world_state_text=context_bundle.world_state_text,
        drive_state_text=context_bundle.drive_state_text,
        user_memory_text=context_bundle.user_memory_text,
        relation_memory_text=context_bundle.relation_memory_text,
        chat_memory_text=context_bundle.chat_memory_text,
        summary_memory_text=context_bundle.summary_memory_text,
        task_context_text=context_bundle.task_context_text,
        memory_trace_text=context_bundle.memory_trace_text,
    )
    return bridge.run_codex(prompt)


def run_photo_task(
    bridge: "TelegramBridge",
    chat_id: int,
    file_id: str,
    caption: str,
    message: Optional[dict] = None,
    *,
    default_image_prompt: str,
    build_download_name_func,
    build_prompt_func,
    normalize_whitespace_func,
    truncate_text_func,
) -> None:
    message_id = int((message or {}).get("message_id") or 0) or None
    sender_user_id = int(((message or {}).get("from") or {}).get("id") or 0) or None
    task_id = f"media-photo-{chat_id}-{message_id or int(time.time() * 1000)}"
    bridge.state.upsert_task_run(
        task_id=task_id,
        chat_id=chat_id,
        user_id=sender_user_id,
        message_id=message_id,
        delivery_chat_id=chat_id,
        task_kind="media_photo_analysis",
        route_kind="attachment_analysis",
        persona=bridge.state.get_mode(chat_id),
        request_kind="chat_local_context",
        source="telegram_media",
        summary=caption or "photo analysis",
        status="running",
        verification_state="pending",
    )
    bridge.state.record_task_event(
        task_id=task_id,
        chat_id=chat_id,
        request_trace_id=task_id,
        phase="attachment_received",
        status="running",
        detail="photo queued for attachment analysis",
        evidence_text=caption or "",
    )
    try:
        with bridge.temp_workspace() as workspace:
            file_info = bridge.get_file_info(file_id)
            file_path = file_info.get("file_path")
            if not file_path:
                bridge.safe_send_text(chat_id, "Telegram не вернул путь к изображению.")
                return

            local_path = workspace / build_download_name_func(file_path, fallback_name="photo.jpg")
            bridge.download_telegram_file(file_path, local_path)
            answer = ask_codex_with_image(
                bridge,
                chat_id,
                local_path,
                caption,
                message=message,
                default_image_prompt=default_image_prompt,
                build_prompt_func=build_prompt_func,
                normalize_whitespace_func=normalize_whitespace_func,
                truncate_text_func=truncate_text_func,
            )

        summary = caption or "без подписи"
        if message_id > 0:
            bridge.state.record_message_subject(
                chat_id=chat_id,
                message_id=message_id,
                subject_type="photo",
                source_kind="direct_photo_analysis",
                user_id=sender_user_id,
                summary=answer,
                details={"caption": caption},
            )
            bridge.state.set_active_subject(
                chat_id=chat_id,
                user_id=sender_user_id or None,
                message_id=message_id,
                subject_type="photo",
                source="direct_photo_analysis",
            )
        bridge.state.append_history(chat_id, "user", f"[Пользователь отправил фото: caption={summary}]")
        bridge.state.append_history(chat_id, "assistant", answer)
        bridge.state.record_event(chat_id, None, "assistant", "answer", answer)
        bridge.state.update_task_run(
            task_id,
            status="completed",
            verification_state="tool_observed",
            outcome="ok",
            evidence_text=answer,
        )
        bridge.state.record_task_event(
            task_id=task_id,
            chat_id=chat_id,
            request_trace_id=task_id,
            phase="attachment_analysis",
            status="completed",
            detail="photo analyzed through attachment route",
            evidence_text=answer,
        )
        bridge.safe_send_text(chat_id, answer, reply_to_message_id=(message or {}).get("message_id"))
    except Exception as error:
        bridge.state.update_task_run(
            task_id,
            status="failed",
            verification_state="failed",
            outcome="error",
            error_text=str(error),
        )
        bridge.state.record_task_event(
            task_id=task_id,
            chat_id=chat_id,
            request_trace_id=task_id,
            phase="attachment_analysis",
            status="failed",
            detail="photo analysis failed",
            evidence_text=str(error),
        )
        raise
    finally:
        bridge.state.finish_chat_task(chat_id)


def run_document_task(
    bridge: "TelegramBridge",
    chat_id: int,
    file_id: str,
    document: dict,
    caption: str,
    message: Optional[dict] = None,
    *,
    build_download_name_func,
    build_prompt_func,
    format_file_size_func,
    normalize_whitespace_func,
    read_document_excerpt_func,
    truncate_text_func,
) -> None:
    message_id = int((message or {}).get("message_id") or 0) or None
    sender_user_id = int(((message or {}).get("from") or {}).get("id") or 0) or None
    task_id = f"media-document-{chat_id}-{message_id or int(time.time() * 1000)}"
    bridge.state.upsert_task_run(
        task_id=task_id,
        chat_id=chat_id,
        user_id=sender_user_id,
        message_id=message_id,
        delivery_chat_id=chat_id,
        task_kind="media_document_analysis",
        route_kind="attachment_analysis",
        persona=bridge.state.get_mode(chat_id),
        request_kind="chat_local_context",
        source="telegram_media",
        summary=caption or str(document.get("file_name") or "document analysis"),
        status="running",
        verification_state="pending",
    )
    bridge.state.record_task_event(
        task_id=task_id,
        chat_id=chat_id,
        request_trace_id=task_id,
        phase="attachment_received",
        status="running",
        detail="document queued for attachment analysis",
        evidence_text=caption or str(document.get("file_name") or ""),
    )
    try:
        with bridge.temp_workspace() as workspace:
            file_info = bridge.get_file_info(file_id)
            file_path = file_info.get("file_path")
            if not file_path:
                bridge.safe_send_text(chat_id, "Telegram не вернул путь к документу.")
                return
            local_path = workspace / build_download_name_func(file_path, fallback_name=document.get("file_name") or "document.bin")
            bridge.download_telegram_file(file_path, local_path)
            file_excerpt = read_document_excerpt_func(local_path, document.get("mime_type") or "")
            answer = ask_codex_with_document(
                bridge,
                chat_id,
                local_path,
                document,
                caption,
                file_excerpt,
                message=message,
                build_prompt_func=build_prompt_func,
                format_file_size_func=format_file_size_func,
                normalize_whitespace_func=normalize_whitespace_func,
                truncate_text_func=truncate_text_func,
            )
        summary = caption or document.get("file_name") or "документ"
        bridge.state.append_history(chat_id, "user", f"[Пользователь отправил документ: {summary}]")
        bridge.state.append_history(chat_id, "assistant", answer)
        bridge.state.record_event(chat_id, None, "assistant", "answer", answer)
        bridge.state.update_task_run(
            task_id,
            status="completed",
            verification_state="tool_observed",
            outcome="ok",
            evidence_text=answer,
        )
        bridge.state.record_task_event(
            task_id=task_id,
            chat_id=chat_id,
            request_trace_id=task_id,
            phase="attachment_analysis",
            status="completed",
            detail="document analyzed through attachment route",
            evidence_text=answer,
        )
        bridge.safe_send_text(chat_id, answer, reply_to_message_id=(message or {}).get("message_id"))
    except Exception as error:
        bridge.state.update_task_run(
            task_id,
            status="failed",
            verification_state="failed",
            outcome="error",
            error_text=str(error),
        )
        bridge.state.record_task_event(
            task_id=task_id,
            chat_id=chat_id,
            request_trace_id=task_id,
            phase="attachment_analysis",
            status="failed",
            detail="document analysis failed",
            evidence_text=str(error),
        )
        raise
    finally:
        bridge.state.finish_chat_task(chat_id)


def run_voice_task(
    bridge: "TelegramBridge",
    chat_id: int,
    user_id: Optional[int],
    file_id: str,
    message: Optional[dict] = None,
    *,
    safe_mode_reply: str,
    build_download_name_func,
    build_voice_transcription_help_func,
    contains_voice_trigger_name_func,
    should_process_group_message_func,
    is_dangerous_request_func,
) -> None:
    try:
        message = message or {}
        message_id = message.get("message_id")
        chat = message.get("chat") or {}
        chat_type = (chat.get("type") or "private").lower()
        from_user = message.get("from") or {}
        owner_label = bridge.build_user_autofix_label(from_user)
        status_message_id = bridge.send_status_message(chat_id, "Распознаю голосовое...")

        with bridge.temp_workspace() as workspace:
            file_info = bridge.get_file_info(file_id)
            file_path = file_info.get("file_path")
            if not file_path:
                bridge.safe_send_text(chat_id, "Telegram не вернул путь к голосовому сообщению.")
                return

            local_path = workspace / build_download_name_func(file_path, fallback_name="voice.ogg")
            bridge.download_telegram_file(file_path, local_path)
            transcript = bridge.transcribe_voice_with_ai(local_path, chat_id=chat_id)

        if not transcript:
            bridge.safe_send_text(chat_id, build_voice_transcription_help_func(bridge.config))
            return

        bridge.log(f"voice transcript chat={chat_id} text={bridge.shorten_for_log(transcript)}")
        transcript_message = (
            f"Голосовое от {owner_label}\n\nРасшифровка:\n{transcript}"
            if chat_type in {"group", "supergroup"}
            else f"Расшифровка голосового:\n{transcript}"
        )
        bridge.state.update_event_text(
            chat_id,
            message_id,
            f"[Голосовое сообщение: {transcript}]",
            message_type="voice",
            has_media=1,
            file_kind="voice",
        )
        if status_message_id is not None:
            if not bridge.edit_status_message(chat_id, status_message_id, transcript_message):
                bridge.safe_send_text(chat_id, transcript_message)
        else:
            bridge.safe_send_text(chat_id, transcript_message)

        if chat_type in {"group", "supergroup"}:
            should_handle_as_bot = (
                should_process_group_message_func(
                    message,
                    transcript,
                    bridge.bot_username,
                    bridge.config.trigger_name,
                    bot_user_id=bridge.bot_user_id,
                    allow_owner_reply=False,
                )
                or contains_voice_trigger_name_func(transcript, bridge.config.trigger_name, bridge.bot_username)
            )
            if not should_handle_as_bot:
                bridge.log(f"voice trigger not found chat={chat_id} text={bridge.shorten_for_log(transcript)}")
                return

        if bridge.config.safe_chat_only and is_dangerous_request_func(transcript):
            bridge.state.append_history(chat_id, "user", f"[Голосовое сообщение: {transcript}]")
            bridge.safe_send_text(chat_id, safe_mode_reply)
            return

        bridge.send_chat_action(chat_id, "typing")
        answer = bridge.ask_codex(chat_id, transcript)
        bridge.state.append_history(chat_id, "user", f"[Голосовое сообщение: {transcript}]")
        bridge.state.append_history(chat_id, "assistant", answer)
        bridge.state.record_event(chat_id, None, "assistant", "answer", answer)
        delivered_via_status = bridge.consume_answer_delivered_via_status(chat_id)
        if not delivered_via_status:
            bridge.safe_send_text(chat_id, answer, reply_to_message_id=message_id if chat_type in {"group", "supergroup"} else None)
        bridge.clear_pending_enterprise_jobs_for_chat(chat_id)
    finally:
        bridge.state.finish_chat_task(chat_id)


def run_audio_task(
    bridge: "TelegramBridge",
    chat_id: int,
    user_id: Optional[int],
    file_id: str,
    message: Optional[dict] = None,
    *,
    safe_mode_reply: str,
    build_download_name_func,
    build_voice_transcription_help_func,
    contains_voice_trigger_name_func,
    should_process_group_message_func,
    is_dangerous_request_func,
) -> None:
    try:
        message = message or {}
        message_id = message.get("message_id")
        chat = message.get("chat") or {}
        chat_type = (chat.get("type") or "private").lower()
        from_user = message.get("from") or {}
        owner_label = bridge.build_user_autofix_label(from_user)
        status_message_id = bridge.send_status_message(chat_id, "Распознаю аудио...")

        with bridge.temp_workspace() as workspace:
            file_info = bridge.get_file_info(file_id)
            file_path = file_info.get("file_path")
            if not file_path:
                bridge.safe_send_text(chat_id, "Telegram не вернул путь к аудиофайлу.")
                return

            local_path = workspace / build_download_name_func(file_path, fallback_name="audio.bin")
            bridge.download_telegram_file(file_path, local_path)
            transcript = bridge.transcribe_voice_with_ai(local_path, chat_id=chat_id)

        if not transcript:
            bridge.safe_send_text(chat_id, build_voice_transcription_help_func(bridge.config))
            return

        bridge.log(f"audio transcript chat={chat_id} text={bridge.shorten_for_log(transcript)}")
        transcript_message = (
            f"Аудио от {owner_label}\n\nРасшифровка:\n{transcript}"
            if chat_type in {"group", "supergroup"}
            else f"Расшифровка аудио:\n{transcript}"
        )
        bridge.state.update_event_text(
            chat_id,
            message_id,
            f"[Аудио: {transcript}]",
            message_type="audio",
            has_media=1,
            file_kind="audio",
        )
        if status_message_id is not None:
            if not bridge.edit_status_message(chat_id, status_message_id, transcript_message):
                bridge.safe_send_text(chat_id, transcript_message)
        else:
            bridge.safe_send_text(chat_id, transcript_message)

        if chat_type in {"group", "supergroup"}:
            should_handle_as_bot = (
                should_process_group_message_func(
                    message,
                    transcript,
                    bridge.bot_username,
                    bridge.config.trigger_name,
                    bot_user_id=bridge.bot_user_id,
                    allow_owner_reply=False,
                )
                or contains_voice_trigger_name_func(transcript, bridge.config.trigger_name, bridge.bot_username)
            )
            if not should_handle_as_bot:
                bridge.log(f"audio trigger not found chat={chat_id} text={bridge.shorten_for_log(transcript)}")
                return

        if bridge.config.safe_chat_only and is_dangerous_request_func(transcript):
            bridge.state.append_history(chat_id, "user", f"[Аудио: {transcript}]")
            bridge.safe_send_text(chat_id, safe_mode_reply)
            return

        bridge.send_chat_action(chat_id, "typing")
        answer = bridge.ask_codex(chat_id, transcript)
        bridge.state.append_history(chat_id, "user", f"[Аудио: {transcript}]")
        bridge.state.append_history(chat_id, "assistant", answer)
        bridge.state.record_event(chat_id, None, "assistant", "answer", answer)
        delivered_via_status = bridge.consume_answer_delivered_via_status(chat_id)
        if not delivered_via_status:
            bridge.safe_send_text(chat_id, answer, reply_to_message_id=message_id if chat_type in {"group", "supergroup"} else None)
        bridge.clear_pending_enterprise_jobs_for_chat(chat_id)
    finally:
        bridge.state.finish_chat_task(chat_id)


if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
