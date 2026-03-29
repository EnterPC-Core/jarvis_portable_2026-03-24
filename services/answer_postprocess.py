import re
from datetime import datetime
from typing import Callable, List, Optional


def strip_banned_openers(text: str) -> str:
    banned_prefixes = [
        "я умею",
        "я могу",
        "я способен",
        "как ии",
        "вот список",
        "мои возможности",
        "в чат я бы ответил так",
        "я бы ответил так",
    ]
    lowered = text.lower()
    for prefix in banned_prefixes:
        if lowered.startswith(prefix):
            return text.split("\n", 1)[-1].strip() or text
    return text


def strip_meta_reply_wrapper(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    wrapper_patterns = (
        r"(?is)^\s*текст\s+для\s+отправки\s+в\s+чат\s*:?\s*",
        r"(?is)^\s*в\s+чат\s+я\s+бы\s+ответил\s+так\s*:?\s*",
        r"(?is)^\s*я\s+бы\s+ответил\s+так\s*:?\s*",
        r"(?is)^\s*я\s+бы\s+ответил\s+в\s+чат\s+так\s*:?\s*",
        r"(?is)^\s*лучше\s+отвечать\s+так\s*:?\s*",
        r"(?is)^\s*я\s+бы\s+написал\s+так\s*:?\s*",
        r"(?is)^\s*тогда\s+финально\s+лучше\s+закрыть\s+так\s*:?\s*",
        r"(?is)^\s*финально\s+лучше\s+закрыть\s+так\s*:?\s*",
    )
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        for pattern in wrapper_patterns:
            cleaned = re.sub(pattern, "", cleaned, count=1).strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"`", '"', "'"}:
            cleaned = cleaned[1:-1].strip()
    return cleaned


def collapse_duplicate_answer_blocks(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    for separator in ("\n\n", "\n"):
        parts = [part.strip() for part in cleaned.split(separator)]
        if len(parts) >= 2 and len(parts) % 2 == 0:
            midpoint = len(parts) // 2
            if parts[:midpoint] == parts[midpoint:]:
                collapsed = separator.join(part for part in parts[:midpoint] if part).strip()
                if collapsed:
                    cleaned = collapsed
    lines = [line.rstrip() for line in cleaned.splitlines()]
    deduped_lines: List[str] = []
    for line in lines:
        if deduped_lines and line and line == deduped_lines[-1]:
            continue
        deduped_lines.append(line)
    return "\n".join(deduped_lines).strip()


def rewrite_model_identity_leak(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    identity_markers = (
        "я работаю",
        "я модель",
        "я построен",
        "я основан",
        "моя модель",
        "я использую",
    )
    lowered = cleaned.lower()
    if any(marker in lowered for marker in identity_markers) and re.search(r"(?i)\b(gpt|openai|codex)\b", cleaned):
        return "Я работаю как Enterprise Core v194.95., модель Дмитрия."
    return cleaned


def collapse_structured_runtime_meta(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if "observed:" not in lowered and "inferred:" not in lowered and "unknown:" not in lowered:
        return cleaned
    compact_lines = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered_line = line.lower()
        if lowered_line in {"jarvis ai:", "enterprise core:"}:
            continue
        if lowered_line.startswith(("observed:", "inferred:", "unknown:")):
            continue
        if lowered_line.startswith("коротко:"):
            summary = line.split(":", 1)[1].strip()
            return summary or cleaned
        compact_lines.append(line)
    return compact_lines[0] if compact_lines else cleaned


def strip_markdown_emphasis(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"(?<!_)__(?!_)", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def postprocess_answer(
    text: str,
    *,
    latency_ms: Optional[int],
    normalize_whitespace_func: Callable[[str], str],
    trim_generic_followup_func: Callable[[str], str],
    truncate_text_func: Callable[[str, int], str],
    display_timezone,
    max_output_chars: int,
) -> str:
    cleaned = normalize_whitespace_func(text)
    cleaned = strip_meta_reply_wrapper(cleaned)
    cleaned = strip_banned_openers(cleaned)
    cleaned = collapse_duplicate_answer_blocks(cleaned)
    cleaned = collapse_structured_runtime_meta(cleaned)
    cleaned = rewrite_model_identity_leak(cleaned)
    cleaned = strip_markdown_emphasis(cleaned)
    cleaned = trim_generic_followup_func(cleaned)
    timestamp = datetime.now(display_timezone).strftime("%Y-%m-%d %H:%M:%S MSK")
    footer = f"🕒 {timestamp}"
    if latency_ms is not None:
        footer = f"{footer}\n🏓 {latency_ms} ms"
    if cleaned:
        cleaned = f"{cleaned}\n\n{footer}"
    else:
        cleaned = footer
    return truncate_text_func(cleaned, max_output_chars)
