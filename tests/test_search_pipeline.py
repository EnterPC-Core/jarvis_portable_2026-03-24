import tempfile
import unittest
from pathlib import Path

from search.citation_renderer import CitationRenderer
from search.classifier import SearchClassifier
from search.evidence_builder import EvidenceBuilder
from search.provider_registry import ProviderRegistry
from search.reranker import SearchReranker
from search.live_provider_adapters import LiveProviderAdapterDeps, WeatherLiveProvider, FxLiveProvider
from search.search_models import (
    ProviderCapability,
    ResearchMode,
    SearchFetchResult,
    SearchQuery,
    SearchResult,
)
from search.search_orchestrator import SearchOrchestrator, SearchOrchestratorDeps
from search.semantic_cache import SemanticCache
from search.self_check import SearchSelfCheck
from policy.final_answer_policy import FinalAnswerPolicy
from adapters.telegram.telegram_response_renderer import TelegramResponseRenderer
from adapters.telegram.answer_templates import build_quick_answer_model
from router.request_router import should_use_web_research


class _FakeProvider:
    name = "fake"

    def is_available(self):
        return True

    def capabilities(self):
        return (ProviderCapability.SEARCH, ProviderCapability.FETCH)

    def search(self, query: SearchQuery, *, limit: int = 5):
        return (
            SearchResult(
                title="Президент страны X",
                url="https://example.com/president",
                snippet="Актуальная статья про президента страны X.",
                provider_name=self.name,
                source_type="web",
                published_at="2026-03-27",
                domain="example.com",
            ),
            SearchResult(
                title="Курс валют сегодня",
                url="https://example.com/fx",
                snippet="Данные по курсам валют на сегодня.",
                provider_name=self.name,
                source_type="web",
                published_at="2026-03-27",
                domain="example.com",
            ),
        )[:limit]

    def fetch(self, result: SearchResult):
        return None

    def reliability_score(self, result: SearchResult) -> float:
        return 0.8

    def freshness_score(self, result: SearchResult, *, max_age_seconds: int) -> float:
        return 0.9


class SearchPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        cache = SemanticCache(Path(self.tmpdir.name) / "search_cache.sqlite3")
        registry = ProviderRegistry()
        registry.register(_FakeProvider())
        self.orchestrator = SearchOrchestrator(
            deps=SearchOrchestratorDeps(
                normalize_whitespace_func=lambda text: " ".join((text or "").split()),
                truncate_text_func=lambda text, limit: text[:limit],
                log_func=lambda _message: None,
            ),
            classifier=SearchClassifier(),
            registry=registry,
            cache=cache,
            reranker=SearchReranker(),
            evidence_builder=EvidenceBuilder(),
            citation_renderer=CitationRenderer(),
            self_check=SearchSelfCheck(),
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_classifier_detects_deep_research(self):
        classifier = SearchClassifier()
        query = classifier.classify("что нового за неделю по нескольким источникам про OpenAI")
        self.assertEqual(query.research_mode, ResearchMode.DEEP)

    def test_cache_roundtrip(self):
        cache = SemanticCache(Path(self.tmpdir.name) / "cache2.sqlite3")
        query = SearchQuery(raw_query="курс usd", normalized_query="курс usd")
        result = SearchResult(title="USD", url="https://example.com/usd", snippet="1 USD", provider_name="fake", source_type="web")
        cache.put_results(query, "fake", [result], ttl_seconds=3600)
        loaded = cache.get_results(query, "fake")
        self.assertEqual(len(loaded), 1)
        self.assertTrue(loaded[0].cache_hit)

    def test_reranker_deduplicates_urls(self):
        query = SearchQuery(raw_query="test", normalized_query="test")
        reranker = SearchReranker()
        results = [
            SearchResult(title="A", url="https://example.com/a", snippet="one", provider_name="fake", source_type="web", relevance_score=0.9, freshness_score=0.8, reliability_score=0.7),
            SearchResult(title="A2", url="https://example.com/a", snippet="two", provider_name="fake", source_type="web", relevance_score=0.7, freshness_score=0.8, reliability_score=0.7),
        ]
        ranked = reranker.rerank(query, results)
        self.assertEqual(len(ranked), 1)

    def test_citation_renderer(self):
        bundle = EvidenceBuilder().build(
            "test",
            [SearchResult(title="Doc", url="https://example.com/doc", snippet="doc", provider_name="fake", source_type="web", relevance_score=0.9, freshness_score=0.9, reliability_score=0.9)],
        )
        citations = CitationRenderer().build(bundle)
        self.assertEqual(citations[0].index, 1)

    def test_self_check_warns_on_single_source(self):
        bundle = EvidenceBuilder().build(
            "test",
            [SearchResult(title="Doc", url="https://example.com/doc", snippet="doc", provider_name="fake", source_type="web", relevance_score=0.9, freshness_score=0.9, reliability_score=0.9)],
        )
        notes, disclaimer = SearchSelfCheck().validate(bundle)
        self.assertTrue(notes)
        self.assertTrue(disclaimer)

    def test_orchestrator_returns_citations(self):
        response = self.orchestrator.research("кто сейчас президент страны X")
        self.assertIsNotNone(response)
        assert response is not None
        self.assertTrue(response.citations)
        self.assertIn("Ключевое", response.answer)

    def test_live_weather_provider_adapter(self):
        class _Gateway:
            def fetch_weather_answer(self, location):
                return (f"Погода в {location}: +20C", ())

        deps = LiveProviderAdapterDeps(
            detect_weather_location_func=lambda text: "Москва" if "погода" in text.lower() else "",
            detect_currency_pair_func=lambda _text: None,
            detect_crypto_asset_func=lambda _text: "",
            detect_stock_symbol_func=lambda _text: "",
            detect_current_fact_query_func=lambda _text: "",
            detect_news_query_func=lambda _text: "",
            truncate_text_func=lambda text, limit: text[:limit],
        )
        provider = WeatherLiveProvider(deps, _Gateway())
        results = provider.search(SearchQuery(raw_query="погода москва", normalized_query="погода москва"))
        self.assertEqual(len(results), 1)
        self.assertIn("Москва", results[0].title)

    def test_live_fx_provider_adapter(self):
        class _Gateway:
            def fetch_exchange_rate_answer(self, base, quote):
                return (f"Курс {base}/{quote}: 1 {base} = 90 {quote}", ())

        deps = LiveProviderAdapterDeps(
            detect_weather_location_func=lambda _text: "",
            detect_currency_pair_func=lambda text: ("USD", "RUB") if "курс" in text.lower() else None,
            detect_crypto_asset_func=lambda _text: "",
            detect_stock_symbol_func=lambda _text: "",
            detect_current_fact_query_func=lambda _text: "",
            detect_news_query_func=lambda _text: "",
            truncate_text_func=lambda text, limit: text[:limit],
        )
        provider = FxLiveProvider(deps, _Gateway())
        results = provider.search(SearchQuery(raw_query="курс доллара", normalized_query="курс доллара"))
        self.assertEqual(len(results), 1)
        self.assertIn("USD/RUB", results[0].title)

    def test_final_answer_policy_keeps_disclaimer_short(self):
        response = self.orchestrator.research("что нового за неделю по нескольким источникам про OpenAI")
        assert response is not None
        shaped = FinalAnswerPolicy().shape_search_response(response)
        self.assertTrue(shaped.headline)
        self.assertTrue(shaped.next_step)
        self.assertLessEqual(len(shaped.bullets), 5)

    def test_telegram_renderer_includes_next_step(self):
        model = build_quick_answer_model(
            title="JARVIS • БЫСТРЫЙ ОТВЕТ",
            summary="Короткий вывод по сути.",
            bullets=("Пункт 1", "Пункт 2"),
            warning="Если нужна максимальная точность, могу быстро уточнить.",
            next_step="Если хочешь, уточню ответ под страну или дату.",
        )
        rendered = "\n".join(TelegramResponseRenderer().render(model))
        self.assertIn("Следующий шаг", rendered)
        self.assertIn("Пункт 1", rendered)

    def test_final_answer_policy_hides_internal_notes_from_user_text(self):
        response = self.orchestrator.research("кто сейчас президент страны X")
        assert response is not None
        shaped = FinalAnswerPolicy().shape_search_response(response)
        combined = " ".join((shaped.headline, *shaped.bullets, shaped.short_disclaimer, shaped.next_step))
        self.assertNotIn("diagnostics", combined.lower())
        self.assertNotIn("self-check", combined.lower())
        self.assertNotIn("routing", combined.lower())

    def test_router_sends_new_device_releases_to_web_research(self):
        self.assertTrue(
            should_use_web_research(
                "А что там из новых смартфонов вышло?",
                normalize_whitespace_func=lambda text: " ".join((text or "").split()),
            )
        )


if __name__ == "__main__":
    unittest.main()
