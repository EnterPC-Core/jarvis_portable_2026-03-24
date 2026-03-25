from pathlib import Path
from typing import List


DEFAULT_TELEGRAM_TEXT_LIMIT = 4000


def trim_generic_followup(text: str) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return cleaned
    paragraphs = [part.strip() for part in cleaned.split("\n\n") if part.strip()]
    if len(paragraphs) < 2:
        return cleaned
    last = paragraphs[-1].lower()
    generic_starters = (
        "если хочешь, я могу",
        "если хочешь могу",
        "могу следующим сообщением",
        "если хочешь, следующим сообщением",
        "практический вывод для меня дальше",
        "дальше буду отвечать",
    )
    if any(last.startswith(starter) for starter in generic_starters):
        return "\n\n".join(paragraphs[:-1]).strip()
    return cleaned


def normalize_whitespace(text: str) -> str:
    lines = [line.rstrip() for line in (text or "").replace("\r", "").split("\n")]
    collapsed: List[str] = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                collapsed.append("")
            continue
        blank_count = 0
        collapsed.append(line.strip())
    return "\n".join(collapsed).strip()


def truncate_text(text: str, limit: int) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 3:
        return cleaned[:limit]
    return cleaned[: limit - 3].rstrip() + "..."


def split_long_message(text: str, limit: int = DEFAULT_TELEGRAM_TEXT_LIMIT) -> List[str]:
    cleaned = normalize_whitespace(text) or "Пустой ответ."
    if len(cleaned) <= limit:
        return [cleaned]

    chunks: List[str] = []
    remaining = cleaned
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at < limit // 3:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 3:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 3:
            split_at = limit

        chunk = remaining[:split_at].strip()
        if not chunk:
            chunk = remaining[:limit].strip()
            split_at = limit

        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)
    return chunks


def build_download_name(file_path: str, fallback_name: str) -> str:
    candidate = Path(file_path).name.strip()
    return candidate or fallback_name

