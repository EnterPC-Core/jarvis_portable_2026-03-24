import os
import time
from pathlib import Path
from typing import Callable, Optional, Tuple


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def normalize_sdcard_alias(raw_path: str) -> str:
    cleaned = (raw_path or "").strip()
    if not cleaned:
        return cleaned
    mappings = [
        ("/storage/emulated/0", "/sdcard"),
        ("/storage/internal", "/storage/internal"),
    ]
    for prefix, target in mappings:
        if cleaned == prefix:
            return target
        if cleaned.startswith(prefix + "/"):
            suffix = cleaned[len(prefix):]
            return target + suffix
    return cleaned


def resolve_sdcard_path(
    raw_path: str,
    *,
    allow_missing: bool,
    default_to_root: bool,
    usage_text: str,
) -> Path:
    base = Path("/sdcard").resolve()
    writable_base = Path("/storage/internal").resolve(strict=False)
    cleaned = normalize_sdcard_alias(raw_path)
    if not cleaned:
        if default_to_root:
            return base
        raise ValueError(usage_text)
    candidate = Path(cleaned)
    if candidate.is_absolute():
        target = candidate
    else:
        target = base / candidate
    resolved = target.resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError as error:
        raise ValueError("Разрешена работа только внутри /sdcard.") from error
    if str(resolved).startswith(str(base)) and writable_base.exists():
        relative = resolved.relative_to(base)
        translated = (writable_base / relative).resolve(strict=False)
        if translated.exists() or allow_missing:
            return translated
    if not allow_missing and not resolved.exists():
        return resolved
    return resolved


def resolve_sdcard_save_target(
    raw_target: str,
    suggested_name: str,
    *,
    default_sd_save_alias: str,
    usage_text: str,
) -> Path:
    base = Path("/sdcard").resolve()
    writable_base = Path("/storage/internal").resolve(strict=False)
    cleaned_name = Path(suggested_name or "file.bin").name or "file.bin"
    cleaned_target = normalize_sdcard_alias(raw_target)
    if not cleaned_target:
        default_target = normalize_sdcard_alias(default_sd_save_alias)
        destination = resolve_sdcard_path(default_target, allow_missing=True, default_to_root=True, usage_text=usage_text) / cleaned_name
    else:
        candidate = resolve_sdcard_path(cleaned_target, allow_missing=True, default_to_root=True, usage_text=usage_text)
        if cleaned_target.endswith("/") or candidate.exists() and candidate.is_dir():
            destination = candidate / cleaned_name
        else:
            destination = candidate
    destination = destination.resolve(strict=False)
    allowed_roots = [base]
    if writable_base.exists():
        allowed_roots.append(writable_base)
    if not any(_is_relative_to(destination, root) for root in allowed_roots):
        raise ValueError("Разрешена работа только внутри /sdcard.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def ensure_sdcard_save_target_writable(destination: Path) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"Каталог для сохранения недоступен: {destination.parent}") from error
    probe_name = f".jarvis-write-test-{os.getpid()}-{int(time.time() * 1000)}"
    probe_path = destination.parent / probe_name
    try:
        with probe_path.open("w", encoding="utf-8") as handle:
            handle.write("ok")
    except OSError as error:
        raise ValueError(
            "Нет доступа на запись в выбранный каталог /sdcard. "
            "В этой среде используй доступный путь или настрой монтирование storage."
        ) from error
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except OSError:
            pass


def extract_message_media_file(message: dict) -> Optional[Tuple[str, str]]:
    if not message:
        return None
    if message.get("document"):
        document = message.get("document") or {}
        file_id = document.get("file_id")
        file_name = document.get("file_name") or "document.bin"
        if file_id:
            return str(file_id), file_name
    if message.get("audio"):
        audio = message.get("audio") or {}
        file_id = audio.get("file_id")
        file_name = audio.get("file_name") or "audio.mp3"
        if file_id:
            return str(file_id), file_name
    if message.get("voice"):
        voice = message.get("voice") or {}
        file_id = voice.get("file_id")
        if file_id:
            return str(file_id), "voice.ogg"
    if message.get("video"):
        video = message.get("video") or {}
        file_id = video.get("file_id")
        file_name = video.get("file_name") or "video.mp4"
        if file_id:
            return str(file_id), file_name
    if message.get("photo"):
        photos = message.get("photo") or []
        if photos:
            best_photo = max(photos, key=lambda item: item.get("file_size", 0))
            file_id = best_photo.get("file_id")
            if file_id:
                return str(file_id), f"photo_{message.get('message_id') or int(time.time())}.jpg"
    return None


def format_file_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def read_document_excerpt(file_path: Path, mime_type: str, truncate_text_func: Callable[[str, int], str], max_chars: int = 3500) -> str:
    text_like_suffixes = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".csv", ".xml", ".html", ".js", ".ts", ".sh"}
    suffix = file_path.suffix.lower()
    mime_lower = (mime_type or "").lower()
    is_text_like = suffix in text_like_suffixes or mime_lower.startswith("text/") or "json" in mime_lower or "xml" in mime_lower
    if not is_text_like:
        return ""
    try:
        if file_path.stat().st_size > 256 * 1024:
            return f"[Файл большой, показан только header]\n{truncate_text_func(file_path.read_text(encoding='utf-8', errors='ignore')[:1200], 1200)}"
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return truncate_text_func(content.strip(), max_chars)
