from __future__ import annotations

from typing import List


def chunk_text(text: str, *, limit: int = 3800) -> List[str]:
    source = (text or "").strip()
    if not source:
        return [""]
    if len(source) <= limit:
        return [source]
    chunks: List[str] = []
    current = []
    current_len = 0
    for line in source.splitlines():
        line_len = len(line) + 1
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current).strip())
            current = [line]
            current_len = line_len
            continue
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current).strip())
    return chunks or [source[:limit]]

