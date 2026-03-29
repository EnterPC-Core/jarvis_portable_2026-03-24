import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from utils.message_utils import describe_message_media_kind, summarize_message_for_pin
from utils.text_utils import normalize_whitespace, truncate_text


def _voice_transcription_enabled(bridge: "TelegramBridge") -> bool:
    config = getattr(bridge, "config", None)
    return bool(getattr(config, "voice_transcription_enabled", False))


def _detect_transcribable_reply_kind(reply_to: dict, media_kind: str) -> str:
    if media_kind in {"voice", "audio"}:
        return media_kind
    document = reply_to.get("document") or {}
    mime_type = str(document.get("mime_type") or "").lower()
    file_name = str(document.get("file_name") or "").lower()
    if mime_type.startswith("audio/"):
        return "audio"
    if file_name.endswith((".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus", ".flac", ".aac", ".webm")):
        return "audio"
    return ""


def _transcribe_reply_media_if_needed(
    bridge: "TelegramBridge",
    chat_id: int,
    reply_to: dict,
    media_kind: str,
) -> str:
    if not _voice_transcription_enabled(bridge):
        return ""
    transcribe_kind = _detect_transcribable_reply_kind(reply_to, media_kind)
    if not transcribe_kind:
        return ""
    if reply_to.get("text") or reply_to.get("caption"):
        return ""
    file_blob = reply_to.get(transcribe_kind) or reply_to.get("document") or {}
    file_id = str(file_blob.get("file_id") or "")
    if not file_id:
        return ""
    try:
        with bridge.temp_workspace() as workspace:
            file_info = bridge.get_file_info(file_id)
            file_path = str(file_info.get("file_path") or "")
            if not file_path:
                return ""
            suffix = Path(file_path).suffix or (".ogg" if transcribe_kind == "voice" else ".bin")
            local_path = workspace / f"reply_{transcribe_kind}{suffix}"
            bridge.download_telegram_file(file_path, local_path)
            transcript = bridge.transcribe_voice_with_ai(local_path, chat_id=chat_id)
        transcript = normalize_whitespace(transcript or "")
        if not transcript:
            return ""
        reply_message_id = reply_to.get("message_id")
        if reply_message_id is not None:
            try:
                bridge.state.update_event_text(
                    chat_id,
                    int(reply_message_id),
                    f"[{'Голосовое сообщение' if transcribe_kind == 'voice' else 'Аудио'}: {transcript}]",
                    message_type=transcribe_kind,
                    has_media=1,
                    file_kind=transcribe_kind,
                )
            except Exception:
                pass
        return transcript
    except Exception as error:
        try:
            bridge.log(f"reply {transcribe_kind or media_kind} transcription failed chat={chat_id}: {error}")
        except Exception:
            pass
        return ""


def build_reply_context(bridge: "TelegramBridge", chat_id: int, message: Optional[dict]) -> str:
    state = getattr(bridge, "state", None)
    source = message or {}
    reply_to = source.get("reply_to_message") or {}
    if not reply_to or state is None:
        return ""
    lines: List[str] = []
    reply_message_id = reply_to.get("message_id")
    reply_user = reply_to.get("from") or {}
    actor = bridge.build_service_actor_name(reply_user) if reply_user else "участник"
    lines.append("Важно: это reply-target, а не текущий автор сообщения.")
    if reply_message_id is not None:
        lines.append(f"Reply target message_id: {reply_message_id}")
    lines.append(f"Reply target author: {actor}")
    summary = summarize_message_for_pin(reply_to, truncate_text)
    if summary:
        lines.append(f"Reply target summary: {truncate_text(summary, 220)}")
    if reply_to.get("text"):
        lines.append(f"Reply target text: {truncate_text(reply_to.get('text') or '', 900)}")
    elif reply_to.get("caption"):
        lines.append(f"Reply target caption: {truncate_text(reply_to.get('caption') or '', 900)}")
    media_kind = describe_message_media_kind(reply_to)
    if media_kind:
        lines.append(f"Reply target media: {media_kind}")
    reply_transcript = _transcribe_reply_media_if_needed(bridge, chat_id, reply_to, media_kind)
    if reply_transcript:
        lines.append(f"Reply target transcript: {truncate_text(reply_transcript, 900)}")
    if reply_message_id is not None:
        visual_row = state.get_visual_signal_for_message(chat_id, int(reply_message_id))
        if visual_row:
            visual_summary = truncate_text(
                normalize_visual_analysis_text(visual_row["analysis_text"] or visual_row["caption"] or ""),
                320,
            )
            if visual_summary:
                lines.append(f"Reply target visual analysis: {visual_summary}")
            try:
                visual_flags = json.loads(visual_row["risk_flags_json"] or "[]")
            except ValueError:
                visual_flags = []
            if visual_flags:
                translated_flags = ", ".join(translate_risk_flag(flag) for flag in visual_flags[:5])
                lines.append(f"Reply target visual flags: {translated_flags}")
    if reply_message_id is not None:
        thread_rows = state.get_thread_context(chat_id, int(reply_message_id), limit=8)
        if thread_rows:
            lines.append("Reply thread context:")
            for created_at, event_user_id, username, first_name, last_name, role, message_type, content in thread_rows:
                stamp = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else "--:--"
                event_actor = bridge.build_actor_name(event_user_id, username or "", first_name or "", last_name or "", role)
                lines.append(f"- [{stamp}] {event_actor} ({message_type}): {truncate_text(content, 180)}")
    return "\n".join(lines)


def message_refers_to_active_subject(user_text: str) -> bool:
    normalized = normalize_whitespace(user_text or "").lower()
    if not normalized:
        return False
    direct_markers = (
        "что на фото",
        "что на картинке",
        "что изображено",
        "кто на фото",
        "кто это",
        "что там",
        "и что там",
        "а там",
        "а тут",
        "что тут",
        "что на этом фото",
        "что на этой фотке",
        "что на фотке",
    )
    if any(marker in normalized for marker in direct_markers):
        return True
    return normalized in {"там?", "тут?", "и что?", "что?", "кто?", "что это?", "и кто это?"}


def build_active_subject_context(
    bridge: "TelegramBridge",
    chat_id: int,
    user_id: Optional[int],
    user_text: str,
    message: Optional[dict],
) -> str:
    state = getattr(bridge, "state", None)
    source = message or {}
    reply_to = source.get("reply_to_message") or {}
    target_message_id = 0
    target_subject_type = ""
    source_label = ""

    if state is None:
        return ""

    if reply_to.get("message_id") is not None:
        target_message_id = int(reply_to.get("message_id") or 0)
        target_subject_type = describe_message_media_kind(reply_to) or "message"
        source_label = "reply"
    elif message_refers_to_active_subject(user_text):
        active_subject = state.get_active_subject(chat_id, user_id)
        if active_subject:
            target_message_id = int(active_subject.get("message_id") or 0)
            target_subject_type = str(active_subject.get("subject_type") or "")
            source_label = "focus_memory"

    if target_message_id <= 0:
        return ""

    subject_row = state.get_message_subject(chat_id, target_message_id)
    visual_row = state.get_visual_signal_for_message(chat_id, target_message_id)
    subject_type = target_subject_type or (subject_row["subject_type"] if subject_row else "message")
    if source_label == "reply":
        state.set_active_subject(
            chat_id=chat_id,
            user_id=user_id,
            message_id=target_message_id,
            subject_type=subject_type,
            source=source_label,
        )

    lines = [
        "ACTIVE SUBJECT:",
        f"- source: {source_label or 'unknown'}",
        f"- message_id: {target_message_id}",
        f"- subject_type: {subject_type}",
    ]

    if subject_row:
        lines.append(f"- subject_memory: {truncate_text(subject_row['summary'] or '', 380)}")
        try:
            subject_details = json.loads(subject_row["details_json"] or "{}")
        except ValueError:
            subject_details = {}
        subject_caption = truncate_text(str(subject_details.get("caption") or ""), 240)
        if subject_caption:
            lines.append(f"- subject_caption: {subject_caption}")

    if visual_row:
        visual_summary = truncate_text(
            normalize_visual_analysis_text(visual_row["analysis_text"] or visual_row["caption"] or ""),
            380,
        )
        if visual_summary:
            lines.append(f"- visual_memory: {visual_summary}")
        try:
            visual_flags = json.loads(visual_row["risk_flags_json"] or "[]")
        except ValueError:
            visual_flags = []
        if visual_flags:
            lines.append("- visual_flags: " + ", ".join(translate_risk_flag(flag) for flag in visual_flags[:5]))

    if len(lines) <= 4:
        return ""
    lines.append("- instruction: resolve 'там/тут/это/на фото' through this subject first.")
    return "\n".join(lines)


def translate_risk_flag(flag: str) -> str:
    mapping = {
        "suspicious_visual": "подозрительный визуальный паттерн",
        "likely_bot_like": "похоже на неаутентичный/ботоподобный аккаунт",
        "likely_bot": "похоже на неаутентичный/ботоподобный аккаунт",
        "bot_like": "ботоподобный стиль",
        "engagement_bait": "вовлекающая приманка",
        "mass_bait": "массовая приманка",
        "fake_identity": "возможная фейковая личность",
        "promo_bait": "рекламная приманка",
        "scam_risk": "риск скама/развода",
        "romance_scam": "романтический скам",
        "sexual_bait": "сексуализированная приманка",
        "adult_promo": "18+ промо",
        "sexualized_profile": "сексуализированный профиль",
        "toxic": "токсичный",
        "high_conflict": "конфликтный",
        "spammy": "спамит",
        "flood_prone": "склонен к флуду",
        "emotionally_unstable": "эмоционально нестабилен",
        "helpful": "полезный",
        "technically_reliable": "технически надёжен",
        "owner_hostile": "враждебен к владельцу",
    }
    return mapping.get(flag, flag)


def normalize_visual_analysis_text(text: str) -> str:
    cleaned = normalize_whitespace(text or "")
    if not cleaned:
        return ""
    replacements = {
        "scene:": "Сцена:",
        "profile_style:": "Стиль профиля:",
        "risk_flags:": "Флаги риска:",
        "why:": "Почему:",
        "scene :": "Сцена:",
        "profile_style :": "Стиль профиля:",
        "risk_flags :": "Флаги риска:",
        "why :": "Почему:",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    for flag in (
        "suspicious_visual",
        "likely_bot_like",
        "likely_bot",
        "bot_like",
        "engagement_bait",
        "mass_bait",
        "fake_identity",
        "promo_bait",
        "scam_risk",
        "romance_scam",
        "sexual_bait",
        "adult_promo",
        "sexualized_profile",
    ):
        cleaned = re.sub(rf"\b{re.escape(flag)}\b", translate_risk_flag(flag), cleaned)
    replacements_text = {
        "dramatic motivational/freedom-themed stock-style image, not a personal photo": "драматичная мотивационная стоковая картинка в стиле свободы, не личное фото",
        "generic symbolic image, strong emotional framing, and non-personal stock-like visual often used by low-trust or mass-engagement accounts": "символическая картинка с сильной эмоциональной подачей; визуал не похож на личное фото и часто встречается у аккаунтов с низким доверием или bait-стилем",
        "silhouette of a person breaking chains at sunset": "силуэт человека, разрывающего цепи на фоне заката",
    }
    lowered = cleaned.lower()
    for source, target in replacements_text.items():
        if source in lowered:
            cleaned = re.sub(re.escape(source), target, cleaned, flags=re.IGNORECASE)
            lowered = cleaned.lower()
    return cleaned


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
