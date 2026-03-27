from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Sequence
from urllib.parse import urlparse

from search.citation_renderer import CitationRenderer
from search.classifier import SearchClassifier
from search.evidence_builder import EvidenceBuilder
from search.provider_registry import ProviderRegistry, SearchProvider
from search.reranker import SearchReranker
from search.search_models import (
    ProviderCapability,
    ResearchMode,
    SearchDiagnostics,
    SearchQuery,
    SearchResponse,
    SearchResult,
)
from search.semantic_cache import SemanticCache
from search.self_check import SearchSelfCheck


@dataclass(frozen=True)
class SearchOrchestratorDeps:
    normalize_whitespace_func: Callable[[str], str]
    truncate_text_func: Callable[[str, int], str]
    log_func: Callable[[str], None]


class SearchOrchestrator:
    """Portable search/research orchestrator with evidence and citations."""

    def __init__(
        self,
        *,
        deps: SearchOrchestratorDeps,
        classifier: SearchClassifier,
        registry: ProviderRegistry,
        cache: SemanticCache,
        reranker: SearchReranker,
        evidence_builder: EvidenceBuilder,
        citation_renderer: CitationRenderer,
        self_check: SearchSelfCheck,
    ) -> None:
        self.deps = deps
        self.classifier = classifier
        self.registry = registry
        self.cache = cache
        self.reranker = reranker
        self.evidence_builder = evidence_builder
        self.citation_renderer = citation_renderer
        self.self_check = self_check

    def research(self, raw_query: str, *, user_id: int | None = None, chat_id: int | None = None, chat_type: str = "private") -> SearchResponse | None:
        query = self.classifier.classify(raw_query, user_id=user_id, chat_id=chat_id, chat_type=chat_type)
        plan = self.classifier.build_plan(query)
        providers = self.registry.pick(ProviderCapability.SEARCH)
        if not providers:
            return None
        attempted: List[str] = []
        succeeded: List[str] = []
        gathered: List[SearchResult] = []
        cache_hits = 0
        for task in plan.tasks:
            for provider in providers:
                attempted.append(provider.name)
                cached = self.cache.get_results(query, provider.name, limit=task.max_results)
                if cached:
                    gathered.extend(cached)
                    cache_hits += len(cached)
                    succeeded.append(provider.name)
                    continue
                try:
                    results = list(provider.search(query, limit=task.max_results))
                except Exception as error:
                    self.deps.log_func(f"search provider failed provider={provider.name} error={error}")
                    continue
                if not results:
                    continue
                enriched = [self._score_result(query, provider, result) for result in results]
                self.cache.put_results(query, provider.name, enriched, ttl_seconds=query.freshness_policy.max_age_seconds, limit=task.max_results)
                gathered.extend(enriched)
                succeeded.append(provider.name)
                if query.research_mode == ResearchMode.QUICK:
                    break
            if gathered and query.research_mode == ResearchMode.QUICK:
                break
        ranked = self.reranker.rerank(query, gathered)
        top_ranked = ranked[:6 if query.research_mode == ResearchMode.DEEP else 4]
        bundle = self.evidence_builder.build(query.normalized_query, top_ranked)
        citations = self.citation_renderer.build(bundle)
        notes, disclaimer = self.self_check.validate(bundle)
        summary = self._build_summary(query, top_ranked)
        answer = self._build_answer(query, top_ranked, citations, disclaimer)
        return SearchResponse(
            answer=answer,
            summary=summary,
            citations=citations,
            evidence_bundle=bundle,
            diagnostics=SearchDiagnostics(
                providers_attempted=tuple(attempted),
                providers_succeeded=tuple(dict.fromkeys(succeeded)),
                cache_hits=cache_hits,
                degraded=not bool(top_ranked),
                notes=(plan.notes,),
            ),
            mode=query.research_mode,
            intent=query.intent,
            self_check_notes=notes,
            disclaimer=disclaimer,
        )

    def _score_result(self, query: SearchQuery, provider: SearchProvider, result: SearchResult) -> SearchResult:
        freshness_score = provider.freshness_score(result, max_age_seconds=query.freshness_policy.max_age_seconds)
        reliability_score = provider.reliability_score(result)
        relevance_score = self._relevance_score(query.normalized_query, result)
        fetched = result.fetched_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return SearchResult(
            **{
                **result.__dict__,
                "domain": result.domain or urlparse(result.url).netloc,
                "fetched_at": fetched,
                "freshness_score": freshness_score,
                "reliability_score": reliability_score,
                "relevance_score": relevance_score,
            }
        )

    def _relevance_score(self, query_text: str, result: SearchResult) -> float:
        haystack = f"{result.title} {result.snippet} {result.extracted_text}".lower()
        query_tokens = [token for token in self.deps.normalize_whitespace_func(query_text).lower().split() if len(token) >= 3]
        if not query_tokens:
            return 0.4
        matched = sum(1 for token in query_tokens if token in haystack)
        return min(1.0, 0.25 + (matched / max(1, len(query_tokens))) * 0.75)

    def _build_summary(self, query: SearchQuery, ranked: Sequence[SearchResult]) -> str:
        if not ranked:
            return "По запросу пока не нашёл полезную внешнюю выдачу."
        top = ranked[0]
        return self.deps.truncate_text_func(f"{top.title}. {top.snippet}", 280)

    def _build_answer(self, query: SearchQuery, ranked: Sequence[SearchResult], citations, disclaimer: str) -> str:
        if not ranked:
            if disclaimer:
                return "Могу быстро сузить запрос и повторить поиск точнее."
            return "Могу быстро сузить запрос и собрать более полезную выдачу."
        lines = [self._build_summary(query, ranked), ""]
        if query.research_mode == ResearchMode.DEEP:
            lines.append("Ключевое по источникам:")
            for item in ranked[:4]:
                lines.append(f"- {self.deps.truncate_text_func(item.title or item.url, 140)}: {self.deps.truncate_text_func(item.snippet, 180)}")
        else:
            lines.append("Что нашлось по сути:")
            for item in ranked[:3]:
                lines.append(f"- {self.deps.truncate_text_func(item.title or item.url, 140)}")
        return "\n".join(lines)
