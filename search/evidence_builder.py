from __future__ import annotations

from typing import List, Sequence
from urllib.parse import urlparse

from search.search_models import EvidenceBundle, EvidenceItem, SearchResult


class EvidenceBuilder:
    def build(self, query: str, results: Sequence[SearchResult]) -> EvidenceBundle:
        items: List[EvidenceItem] = []
        for result in results:
            items.append(
                EvidenceItem(
                    title=result.title,
                    url=result.url,
                    publisher=urlparse(result.url).netloc or result.domain,
                    snippet=result.snippet,
                    extracted_text=result.extracted_text,
                    published_at=result.published_at,
                    fetched_at=result.fetched_at,
                    reliability_score=result.reliability_score,
                    freshness_score=result.freshness_score,
                    relevance_score=result.relevance_score,
                    source_type=result.source_type,
                    provider_name=result.provider_name,
                    cache_metadata={"cache_hit": "yes" if result.cache_hit else "no"},
                )
            )
        warnings: List[str] = []
        if not items:
            warnings.append("Не удалось собрать evidence из внешних источников.")
        elif len(items) == 1:
            warnings.append("Найден только один источник, уверенность ограничена.")
        return EvidenceBundle(query=query, items=tuple(items), warnings=tuple(warnings))

