from pathlib import Path
from typing import Callable, Optional, Tuple

from utils.file_utils import (
    ensure_sdcard_save_target_writable as _ensure_sdcard_save_target_writable,
    extract_message_media_file as _extract_message_media_file,
    format_file_size as _format_file_size,
    normalize_sdcard_alias as _normalize_sdcard_alias,
    read_document_excerpt as _read_document_excerpt,
    resolve_sdcard_path as _resolve_sdcard_path,
    resolve_sdcard_save_target as _resolve_sdcard_save_target,
)


def resolve_sdcard_path(raw_path: str, *, allow_missing: bool, default_to_root: bool, usage_text: str) -> Path:
    return _resolve_sdcard_path(
        raw_path,
        allow_missing=allow_missing,
        default_to_root=default_to_root,
        usage_text=usage_text,
    )


def resolve_sdcard_save_target(raw_target: str, suggested_name: str, *, default_sd_save_alias: str, usage_text: str) -> Path:
    return _resolve_sdcard_save_target(
        raw_target,
        suggested_name,
        default_sd_save_alias=default_sd_save_alias,
        usage_text=usage_text,
    )


def ensure_sdcard_save_target_writable(destination: Path) -> None:
    _ensure_sdcard_save_target_writable(destination)


def normalize_sdcard_alias(raw_path: str) -> str:
    return _normalize_sdcard_alias(raw_path)


def extract_message_media_file(message: dict) -> Optional[Tuple[str, str]]:
    return _extract_message_media_file(message)


def format_file_size(size: int) -> str:
    return _format_file_size(size)


def read_document_excerpt(file_path: Path, mime_type: str, *, truncate_text_func: Callable[[str, int], str], max_chars: int = 3500) -> str:
    return _read_document_excerpt(file_path, mime_type, truncate_text_func, max_chars=max_chars)
