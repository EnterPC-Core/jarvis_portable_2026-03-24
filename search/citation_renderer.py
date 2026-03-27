from __future__ import annotations

from typing import Tuple

from search.search_models import Citation, EvidenceBundle


class CitationRenderer:
    def build(self, bundle: EvidenceBundle, *, limit: int = 5) -> Tuple[Citation, ...]:
        citations = []
        for index, item in enumerate(bundle.items[:limit], start=1):
            citations.append(
                Citation(
                    index=index,
                    title=item.title or item.publisher or item.url,
                    url=item.url,
                    publisher=item.publisher,
                    label=f"[{index}] {item.publisher or item.title}",
                )
            )
        return tuple(citations)

    def render_text(self, citations: Tuple[Citation, ...]) -> str:
        if not citations:
            return ""
        return "\n".join(f"[{citation.index}] {citation.title} — {citation.url}" for citation in citations)

