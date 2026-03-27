from __future__ import annotations

from difflib import SequenceMatcher
from typing import List, Sequence
from urllib.parse import urlparse

from search.search_models import SearchQuery, SearchResult


class SearchReranker:
    """Scores, deduplicates and ranks results."""

    def rerank(self, query: SearchQuery, results: Sequence[SearchResult]) -> List[SearchResult]:
        deduped: List[SearchResult] = []
        seen_urls: set[str] = set()
        for result in results:
            normalized_url = self._normalize_url(result.url)
            if not normalized_url or normalized_url in seen_urls:
                continue
            duplicate_score = self._duplication_score(result, deduped)
            final_score = (result.relevance_score * 0.45) + (result.freshness_score * 0.25) + (result.reliability_score * 0.30) - duplicate_score
            deduped.append(
                SearchResult(
                    **{**result.__dict__, "url": normalized_url, "duplication_score": duplicate_score, "final_rank_score": round(final_score, 4)}
                )
            )
            seen_urls.add(normalized_url)
        deduped.sort(key=lambda item: (-item.final_rank_score, -item.reliability_score, -item.freshness_score, item.url))
        return deduped

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url or "")
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}"

    def _duplication_score(self, candidate: SearchResult, current: Sequence[SearchResult]) -> float:
        best = 0.0
        candidate_text = f"{candidate.title} {candidate.snippet}".lower().strip()
        for item in current:
            other_text = f"{item.title} {item.snippet}".lower().strip()
            if not candidate_text or not other_text:
                continue
            best = max(best, SequenceMatcher(a=candidate_text, b=other_text).ratio())
        return round(best * 0.2, 4)

