from __future__ import annotations

from typing import List

from adapters.telegram.chunking import chunk_text
from adapters.telegram.message_formatter import bold, bullet, escape_html, italic
from models.presentation import PresentationModel


class TelegramResponseRenderer:
    """Renders structured answers to Telegram-friendly HTML chunks."""

    def render(self, model: PresentationModel) -> List[str]:
        parts = [bold(model.title), "", escape_html(model.summary)]
        if model.bullets:
            parts.extend(["", *[bullet(item) for item in model.bullets]])
        if model.details:
            for section in model.details:
                parts.extend(["", bold(section.title), escape_html(section.body)])
        if model.citations:
            parts.extend(["", bold("Источники"), *[escape_html(item) for item in model.citations]])
        if model.warning:
            parts.extend(["", italic(model.warning)])
        if model.next_step:
            parts.extend(["", bold("Следующий шаг"), escape_html(model.next_step)])
        if model.footer:
            parts.extend(["", escape_html(model.footer)])
        return chunk_text("\n".join(parts))
