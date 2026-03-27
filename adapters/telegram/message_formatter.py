from __future__ import annotations

import html


def escape_html(text: str) -> str:
    return html.escape(text or "", quote=False)


def bold(text: str) -> str:
    return f"<b>{escape_html(text)}</b>"


def italic(text: str) -> str:
    return f"<i>{escape_html(text)}</i>"


def bullet(text: str) -> str:
    return f"• {escape_html(text)}"

