from __future__ import annotations

from dataclasses import dataclass

from search.search_models import FreshnessPolicy, ResearchMode, SearchIntent, SearchPlan, SearchQuery, SearchTask


@dataclass(frozen=True)
class SearchClassifier:
    """Deterministic classifier for research/search routing."""

    def classify(self, raw_query: str, *, user_id: int | None = None, chat_id: int | None = None, chat_type: str = "private") -> SearchQuery:
        normalized = " ".join((raw_query or "").split())
        lowered = normalized.lower()
        intent = SearchIntent.GENERAL_WEB
        mode = ResearchMode.QUICK
        freshness = FreshnessPolicy(max_age_seconds=86400, require_live_data=False, prefer_recent=True, description="default web lookup")

        if any(marker in lowered for marker in ("сравни", "сравнить", "vs", "versus", "чем отличается")):
            intent = SearchIntent.COMPARISON
            mode = ResearchMode.DEEP
            freshness = FreshnessPolicy(max_age_seconds=604800, require_live_data=False, prefer_recent=True, description="comparison wants multiple sources")
        elif any(marker in lowered for marker in ("что нового", "новости", "за неделю", "сегодня", "latest", "сейчас")):
            intent = SearchIntent.NEWS
            mode = ResearchMode.DEEP
            freshness = FreshnessPolicy(max_age_seconds=172800, require_live_data=True, prefer_recent=True, description="news needs fresh sources")
        elif any(marker in lowered for marker in ("документац", "docs", "api", "reference", "how to", "guide")):
            intent = SearchIntent.DOCUMENTATION
            mode = ResearchMode.QUICK
            freshness = FreshnessPolicy(max_age_seconds=2592000, require_live_data=False, prefer_recent=True, description="documentation lookup")
        elif any(marker in lowered for marker in ("президент", "курс", "погода", "btc", "bitcoin", "акции", "stock", "fx", "сейчас")):
            intent = SearchIntent.LIVE_FACT
            mode = ResearchMode.QUICK
            freshness = FreshnessPolicy(max_age_seconds=21600, require_live_data=True, prefer_recent=True, description="live fact")
        elif any(marker in lowered for marker in ("нескольким источникам", "проверь актуальность", "исследуй", "разбери по источникам")):
            intent = SearchIntent.DEEP_RESEARCH
            mode = ResearchMode.DEEP
            freshness = FreshnessPolicy(max_age_seconds=604800, require_live_data=False, prefer_recent=True, description="deep research")

        return SearchQuery(
            raw_query=raw_query,
            normalized_query=normalized,
            user_id=user_id,
            chat_id=chat_id,
            chat_type=chat_type,
            intent=intent,
            research_mode=mode,
            freshness_policy=freshness,
        )

    def build_plan(self, query: SearchQuery) -> SearchPlan:
        tasks = [SearchTask(query=query.normalized_query, max_results=5)]
        if query.research_mode == ResearchMode.DEEP:
            tasks.append(SearchTask(query=f"{query.normalized_query} source comparison", max_results=5, depth=2))
        return SearchPlan(
            intent=query.intent,
            research_mode=query.research_mode,
            tasks=tuple(tasks),
            require_fetch=True,
            require_multiple_sources=query.research_mode == ResearchMode.DEEP or query.intent in {SearchIntent.COMPARISON, SearchIntent.NEWS, SearchIntent.DEEP_RESEARCH},
            notes=f"classified as {query.intent.value}/{query.research_mode.value}",
        )

