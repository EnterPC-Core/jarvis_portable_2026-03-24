from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

from search.search_models import ResearchMode, SearchResponse


@dataclass(frozen=True)
class FinalAnswerShape:
    headline: str
    bullets: Tuple[str, ...]
    short_disclaimer: str
    next_step: str


class FinalAnswerPolicy:
    """Transforms structured search output into concise user-facing Telegram UX."""

    def shape_search_response(self, response: SearchResponse) -> FinalAnswerShape:
        bullets = self._build_bullets(response)
        disclaimer = self._build_disclaimer(response)
        next_step = self._build_next_step(response)
        headline = response.summary.strip() or "Собрал краткий ответ по запросу."
        return FinalAnswerShape(
            headline=headline,
            bullets=bullets[:5],
            short_disclaimer=disclaimer,
            next_step=next_step,
        )

    def _build_bullets(self, response: SearchResponse) -> Tuple[str, ...]:
        items = []
        for evidence in response.evidence_bundle.items[:4]:
            snippet = (evidence.snippet or evidence.extracted_text or "").strip()
            if snippet:
                items.append(f"{evidence.title}: {snippet}")
            else:
                items.append(evidence.title or evidence.url)
        if not items and response.citations:
            items.extend(citation.title for citation in response.citations[:3])
        if not items:
            items.append("Могу сузить запрос и собрать более полезную выдачу.")
        return tuple(items)

    def _build_disclaimer(self, response: SearchResponse) -> str:
        if not response.disclaimer:
            return ""
        if response.mode == ResearchMode.QUICK:
            return "Если нужна максимально свежая картина, уточню запрос и доберу проверку."
        return "Если нужна точность до самых свежих обновлений, могу быстро уточнить проверку."

    def _build_next_step(self, response: SearchResponse) -> str:
        if response.intent.value == "comparison":
            return "Если хочешь, сведу это в короткое сравнение по ключевым различиям."
        if response.mode == ResearchMode.DEEP:
            return "Если хочешь, я сожму это до короткого вывода или разложу по источникам подробнее."
        return "Если хочешь, уточню ответ под конкретную страну, дату, бюджет или источник."

