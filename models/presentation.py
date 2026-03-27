from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class PresentationSection:
    title: str
    body: str


@dataclass(frozen=True)
class PresentationModel:
    template: str
    title: str
    summary: str
    bullets: Tuple[str, ...] = ()
    details: Tuple[PresentationSection, ...] = ()
    citations: Tuple[str, ...] = ()
    warning: str = ""
    next_step: str = ""
    footer: str = ""
