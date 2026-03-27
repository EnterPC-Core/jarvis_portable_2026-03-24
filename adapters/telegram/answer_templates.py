from __future__ import annotations

from models.presentation import PresentationModel, PresentationSection


def build_quick_answer_model(*, title: str, summary: str, bullets: tuple[str, ...] = (), warning: str = "", next_step: str = "", footer: str = "", citations: tuple[str, ...] = ()) -> PresentationModel:
    return PresentationModel(template="quick_answer", title=title, summary=summary, bullets=bullets, citations=citations, warning=warning, next_step=next_step, footer=footer)


def build_deep_research_model(*, title: str, summary: str, bullets: tuple[str, ...], citations: tuple[str, ...], warning: str = "", next_step: str = "") -> PresentationModel:
    return PresentationModel(template="deep_research", title=title, summary=summary, bullets=bullets, citations=citations, warning=warning, next_step=next_step)


def build_comparison_model(*, title: str, summary: str, bullets: tuple[str, ...], citations: tuple[str, ...], next_step: str = "") -> PresentationModel:
    return PresentationModel(template="comparison", title=title, summary=summary, bullets=bullets, citations=citations, next_step=next_step)


def build_error_model(*, title: str, summary: str, warning: str, next_step: str = "") -> PresentationModel:
    return PresentationModel(template="error", title=title, summary=summary, warning=warning, next_step=next_step)


def build_citation_answer_model(*, title: str, summary: str, bullets: tuple[str, ...] = (), details: tuple[PresentationSection, ...] = (), citations: tuple[str, ...] = (), warning: str = "", next_step: str = "") -> PresentationModel:
    return PresentationModel(template="citation_based", title=title, summary=summary, bullets=bullets, details=details, citations=citations, warning=warning, next_step=next_step)
