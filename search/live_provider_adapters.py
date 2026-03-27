from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence
from urllib.parse import quote_plus

from search.provider_registry import SearchProvider
from search.search_models import ProviderCapability, SearchFetchResult, SearchQuery, SearchResult


@dataclass(frozen=True)
class LiveProviderAdapterDeps:
    detect_weather_location_func: Callable[[str], str]
    detect_currency_pair_func: Callable[[str], Optional[tuple[str, str]]]
    detect_crypto_asset_func: Callable[[str], str]
    detect_stock_symbol_func: Callable[[str], str]
    detect_current_fact_query_func: Callable[[str], str]
    detect_news_query_func: Callable[[str], str]
    truncate_text_func: Callable[[str, int], str]


class _BaseLiveProvider(SearchProvider):
    source_type = "live_fact"

    def __init__(self, deps: LiveProviderAdapterDeps, live_gateway: object) -> None:
        self.deps = deps
        self.live_gateway = live_gateway

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> Sequence[ProviderCapability]:
        return (ProviderCapability.SEARCH, ProviderCapability.LIVE_FACT)

    def fetch(self, result: SearchResult) -> Optional[SearchFetchResult]:
        return None

    def reliability_score(self, result: SearchResult) -> float:
        return result.reliability_score or 0.88

    def freshness_score(self, result: SearchResult, *, max_age_seconds: int) -> float:
        if max_age_seconds <= 21600:
            return 0.96
        if max_age_seconds <= 172800:
            return 0.9
        return 0.82

    def _now_text(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def _build_result(self, *, title: str, url: str, snippet: str, provider_name: str, reliability_score: float = 0.9) -> SearchResult:
        return SearchResult(
            title=title,
            url=url,
            snippet=self.deps.truncate_text_func(snippet, 280),
            provider_name=provider_name,
            source_type=self.source_type,
            fetched_at=self._now_text(),
            relevance_score=0.95,
            freshness_score=0.95,
            reliability_score=reliability_score,
        )


class WeatherLiveProvider(_BaseLiveProvider):
    name = "live_weather"

    def search(self, query: SearchQuery, *, limit: int = 5) -> Sequence[SearchResult]:
        location = self.deps.detect_weather_location_func(query.normalized_query)
        if not location:
            return ()
        answer, _records = self.live_gateway.fetch_weather_answer(location)
        if not answer:
            return ()
        return (self._build_result(title=f"Погода: {location}", url=f"https://open-meteo.com/en/docs?city={quote_plus(location)}", snippet=answer, provider_name="Open-Meteo", reliability_score=0.94),)


class FxLiveProvider(_BaseLiveProvider):
    name = "live_fx"

    def search(self, query: SearchQuery, *, limit: int = 5) -> Sequence[SearchResult]:
        pair = self.deps.detect_currency_pair_func(query.normalized_query)
        if not pair:
            return ()
        answer, _records = self.live_gateway.fetch_exchange_rate_answer(pair[0], pair[1])
        if not answer:
            return ()
        return (self._build_result(title=f"Курс {pair[0]}/{pair[1]}", url=f"https://www.frankfurter.app/docs/", snippet=answer, provider_name="Frankfurter", reliability_score=0.9),)


class CryptoLiveProvider(_BaseLiveProvider):
    name = "live_crypto"

    def search(self, query: SearchQuery, *, limit: int = 5) -> Sequence[SearchResult]:
        asset = self.deps.detect_crypto_asset_func(query.normalized_query)
        if not asset:
            return ()
        answer, _records = self.live_gateway.fetch_crypto_price_answer(asset)
        if not answer:
            return ()
        return (self._build_result(title=f"Crypto {asset}", url=f"https://www.coingecko.com/en/coins/{quote_plus(asset)}", snippet=answer, provider_name="CoinGecko", reliability_score=0.92),)


class StocksLiveProvider(_BaseLiveProvider):
    name = "live_stocks"

    def search(self, query: SearchQuery, *, limit: int = 5) -> Sequence[SearchResult]:
        symbol = self.deps.detect_stock_symbol_func(query.normalized_query)
        if not symbol:
            return ()
        answer, _records = self.live_gateway.fetch_stock_price_answer(symbol)
        if not answer:
            return ()
        return (self._build_result(title=f"Акция {symbol}", url=f"https://finance.yahoo.com/quote/{quote_plus(symbol)}", snippet=answer, provider_name="Yahoo Finance", reliability_score=0.9),)


class NewsLiveProvider(_BaseLiveProvider):
    name = "live_news"

    def search(self, query: SearchQuery, *, limit: int = 5) -> Sequence[SearchResult]:
        news_query = self.deps.detect_news_query_func(query.normalized_query)
        if not news_query:
            return ()
        answer, _records = self.live_gateway.fetch_news_answer(news_query, limit=min(5, limit))
        if not answer:
            return ()
        return (self._build_result(title=f"Новости: {news_query}", url=f"https://news.google.com/search?q={quote_plus(news_query)}", snippet=answer, provider_name="Google News RSS", reliability_score=0.86),)


class CurrentFactLiveProvider(_BaseLiveProvider):
    name = "live_current_fact"

    def search(self, query: SearchQuery, *, limit: int = 5) -> Sequence[SearchResult]:
        fact_query = self.deps.detect_current_fact_query_func(query.normalized_query)
        if not fact_query:
            return ()
        answer, _records = self.live_gateway.fetch_current_fact_answer(fact_query, limit=min(5, limit))
        if not answer:
            return ()
        return (self._build_result(title=f"Актуальный факт: {fact_query}", url=f"https://duckduckgo.com/?q={quote_plus(fact_query)}", snippet=answer, provider_name="DuckDuckGo HTML", reliability_score=0.68),)

