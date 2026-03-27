from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import html
import re
from typing import Callable, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from models.contracts import ExternalResearchTask

from search.citation_renderer import CitationRenderer
from search.classifier import SearchClassifier
from search.evidence_builder import EvidenceBuilder
from search.legacy_bridge_provider import LegacyBridgeWebProvider, LegacyBridgeWebProviderDeps
from search.live_provider_adapters import (
    CryptoLiveProvider,
    CurrentFactLiveProvider,
    FxLiveProvider,
    LiveProviderAdapterDeps,
    NewsLiveProvider,
    StocksLiveProvider,
    WeatherLiveProvider,
)
from search.provider_registry import ProviderRegistry
from search.reranker import SearchReranker
from search.search_models import SearchResponse
from search.search_orchestrator import SearchOrchestrator, SearchOrchestratorDeps
from search.semantic_cache import SemanticCache
from search.self_check import SearchSelfCheck


@dataclass(frozen=True)
class ResearchServiceDeps:
    normalize_whitespace_func: Callable[[str], str]
    truncate_text_func: Callable[[str, int], str]
    log_func: Callable[[str], None]
    request_text_with_retry_func: Callable[..., str]
    detect_weather_location_func: Callable[[str], str]
    detect_currency_pair_func: Callable[[str], Optional[tuple[str, str]]]
    detect_crypto_asset_func: Callable[[str], str]
    detect_stock_symbol_func: Callable[[str], str]
    detect_current_fact_query_func: Callable[[str], str]
    detect_news_query_func: Callable[[str], str]
    plan_external_research_tasks_func: Callable[[str], List[ExternalResearchTask]]
    build_actor_name_func: Callable[[Optional[int], str, str, str, str], str]
    owner_user_id: int
    owner_username: str
    run_codex_short_func: Callable[..., str]
    extract_urls_func: Callable[[str], List[str]]
    shorten_for_log_func: Callable[[str, int], str]
    normalize_external_search_query_func: Callable[[str], str]
    is_irrelevant_web_search_result_func: Callable[[str, str, str], bool]
    is_query_too_broad_for_external_search_func: Callable[[str], bool]
    build_external_search_needs_object_reply_func: Callable[[str], str]
    build_external_search_not_confirmed_reply_func: Callable[[str], str]
    is_direct_url_antibot_block_func: Callable[..., bool]
    build_direct_url_blocked_reply_func: Callable[[str], str]


class ResearchService:
    """Facade around search and live research providers."""

    def __init__(self, *, deps: ResearchServiceDeps, live_gateway: object, cache_path: Path) -> None:
        self.deps = deps
        self.live_gateway = live_gateway
        self.registry = ProviderRegistry()
        self._register_default_providers(cache_path)
        self.search_orchestrator = SearchOrchestrator(
            deps=SearchOrchestratorDeps(
                normalize_whitespace_func=deps.normalize_whitespace_func,
                truncate_text_func=deps.truncate_text_func,
                log_func=deps.log_func,
            ),
            classifier=SearchClassifier(),
            registry=self.registry,
            cache=SemanticCache(cache_path),
            reranker=SearchReranker(),
            evidence_builder=EvidenceBuilder(),
            citation_renderer=CitationRenderer(),
            self_check=SearchSelfCheck(),
        )

    def _register_default_providers(self, cache_path: Path) -> None:
        del cache_path
        self.registry.register(
            LegacyBridgeWebProvider(
                LegacyBridgeWebProviderDeps(
                    request_text_with_retry=self.deps.request_text_with_retry_func,
                    normalize_whitespace_func=self.deps.normalize_whitespace_func,
                    truncate_text_func=self.deps.truncate_text_func,
                    log_func=self.deps.log_func,
                )
            )
        )
        live_deps = LiveProviderAdapterDeps(
            detect_weather_location_func=self.deps.detect_weather_location_func,
            detect_currency_pair_func=self.deps.detect_currency_pair_func,
            detect_crypto_asset_func=self.deps.detect_crypto_asset_func,
            detect_stock_symbol_func=self.deps.detect_stock_symbol_func,
            detect_current_fact_query_func=self.deps.detect_current_fact_query_func,
            detect_news_query_func=self.deps.detect_news_query_func,
            truncate_text_func=self.deps.truncate_text_func,
        )
        for provider in (
            WeatherLiveProvider(live_deps, self.live_gateway),
            FxLiveProvider(live_deps, self.live_gateway),
            CryptoLiveProvider(live_deps, self.live_gateway),
            StocksLiveProvider(live_deps, self.live_gateway),
            NewsLiveProvider(live_deps, self.live_gateway),
            CurrentFactLiveProvider(live_deps, self.live_gateway),
        ):
            self.registry.register(provider)

    def research(self, query: str, *, user_id: int | None = None, chat_id: int | None = None, chat_type: str = "private") -> SearchResponse | None:
        return self.search_orchestrator.research(query, user_id=user_id, chat_id=chat_id, chat_type=chat_type)

    def try_handle_live_query(self, query: str, *, route_kind: str = "") -> str:
        weather_location = self.deps.detect_weather_location_func(query)
        if weather_location and route_kind in {"", "live_weather"}:
            answer, _ = self.live_gateway.fetch_weather_answer(weather_location)
            return answer
        currency_pair = self.deps.detect_currency_pair_func(query)
        if currency_pair and route_kind in {"", "live_fx"}:
            answer, _ = self.live_gateway.fetch_exchange_rate_answer(currency_pair[0], currency_pair[1])
            return answer
        crypto_id = self.deps.detect_crypto_asset_func(query)
        if crypto_id and route_kind in {"", "live_crypto"}:
            answer, _ = self.live_gateway.fetch_crypto_price_answer(crypto_id)
            return answer
        stock_symbol = self.deps.detect_stock_symbol_func(query)
        if stock_symbol and route_kind in {"", "live_stocks"}:
            answer, _ = self.live_gateway.fetch_stock_price_answer(stock_symbol)
            return answer
        current_fact_query = self.deps.detect_current_fact_query_func(query)
        if current_fact_query and route_kind in {"", "live_current_fact"}:
            answer, _ = self.live_gateway.fetch_current_fact_answer(current_fact_query)
            return answer
        news_query = self.deps.detect_news_query_func(query)
        if news_query and route_kind in {"", "live_news"}:
            answer, _ = self.live_gateway.fetch_news_answer(news_query)
            return answer
        return ""

    def collect_external_research_sections(
        self,
        query: str,
        *,
        build_web_search_context_func: Callable[[str], str],
    ) -> List[Tuple[str, str]]:
        normalized_query = self.deps.normalize_whitespace_func(query)
        if not normalized_query:
            return []
        return self.live_gateway.collect_external_research_sections(
            normalized_query,
            self.deps.plan_external_research_tasks_func(normalized_query),
            build_web_search_context_func,
        )

    def build_external_research_context(
        self,
        query: str,
        *,
        build_web_search_context_func: Callable[[str], str],
    ) -> str:
        rendered_sections: List[str] = []
        for label, body in self.collect_external_research_sections(
            query,
            build_web_search_context_func=build_web_search_context_func,
        ):
            if label == "Web":
                rendered_sections.append(body)
            else:
                rendered_sections.append(f"{label}:\n{body}")
        return "\n\n".join(section.strip() for section in rendered_sections if section.strip())

    def build_observed_mixed_answer(
        self,
        *,
        chat_id: int,
        user_text: str,
        user_id: Optional[int],
        build_web_search_context_func: Callable[[str], str],
        get_daily_summary_context_func: Callable[[int, str], Tuple[str, Sequence[Tuple[int, Optional[int], str, str, str, str, str, str]]]],
    ) -> str:
        external_sections = self.collect_external_research_sections(
            user_text,
            build_web_search_context_func=build_web_search_context_func,
        )
        lowered = self.deps.normalize_whitespace_func(user_text).lower()
        local_lines: List[str] = []
        if "как меня звать" in lowered and user_id == self.deps.owner_user_id:
            owner_name = self.deps.owner_username.lstrip("@") or "Дмитрий"
            local_lines.append(f"Тебя зовут {owner_name}.")
        if "кто в чате" in lowered or "кто сегодня общался" in lowered:
            day, rows = get_daily_summary_context_func(chat_id, "")
            speakers: List[str] = []
            for _created_at, event_user_id, username, first_name, last_name, role, _message_type, _content in rows:
                if role != "user":
                    continue
                actor = self.deps.build_actor_name_func(event_user_id, username or "", first_name or "", last_name or "", role)
                if actor not in speakers:
                    speakers.append(actor)
            if speakers:
                local_lines.append(f"Сегодня в чате ({day}) писали: {', '.join(speakers[:12])}.")
            else:
                local_lines.append("Сегодня в чате подтверждённых пользовательских сообщений не найдено.")
        if not external_sections and not local_lines:
            return ""
        lines = ["Коротко по сути."]
        weather_summaries: List[str] = []
        web_fallback = ""
        for label, body in external_sections:
            if label == "Новости":
                lines.append(f"- Мир: {self._build_observed_news_summary(body)}")
            elif label == "Смартфон":
                lines.append(f"- Смартфон: {self._build_observed_current_fact_summary(body)}")
            elif label.startswith("Погода:"):
                weather_summaries.append(self._build_observed_weather_summary(label, body))
            elif label == "Курс":
                lines.append(f"- Курс: {self._build_observed_rate_summary(body)}")
            elif label == "Bitcoin price":
                lines.append(f"- Биткойн: {self._build_observed_crypto_summary(body)}")
            elif label == "Bitcoin outlook":
                lines.append(f"- Рынок: {self._build_observed_current_fact_summary(body, fallback_limit=220)}")
            elif label == "Web":
                web_fallback = self.deps.truncate_text_func(self.deps.normalize_whitespace_func(body), 220)
        if weather_summaries:
            lines.append(f"- Погода: {'; '.join(weather_summaries)}")
        if local_lines:
            lines.append(f"- По чату: {' '.join(local_lines)}")
        if web_fallback and len(external_sections) <= 1:
            lines.append(f"- По вебу: {web_fallback}")
        source_labels = self._collect_observed_source_labels(external_sections)
        if source_labels:
            lines.append("")
            lines.append("Источники: " + ", ".join(source_labels) + ".")
        return "\n".join(lines).strip()

    def _build_observed_news_summary(self, body: str) -> str:
        titles = []
        for line in (body or "").splitlines():
            cleaned = self.deps.normalize_whitespace_func(line)
            if cleaned.startswith("• "):
                titles.append(cleaned[2:].strip())
            if len(titles) >= 2:
                break
        if not titles:
            return self.deps.truncate_text_func(self.deps.normalize_whitespace_func(body), 220)
        return "Главные сюжеты: " + "; ".join(titles) + "."

    def _build_observed_current_fact_summary(self, body: str, fallback_limit: int = 260) -> str:
        cleaned = self.deps.normalize_whitespace_func(body)
        if not cleaned:
            return ""
        for marker in ("\n\nПодтверждение:", "\n\nИсточники по запросу", "Источники по запросу"):
            if marker in body:
                head = self.deps.normalize_whitespace_func(body.split(marker, 1)[0])
                if head:
                    return self.deps.truncate_text_func(head, fallback_limit)
        return self.deps.truncate_text_func(cleaned, fallback_limit)

    def _build_observed_weather_summary(self, label: str, body: str) -> str:
        cleaned = self.deps.normalize_whitespace_func(body)
        cleaned = re.sub(r"\s*Источник:\s.*$", "", cleaned)
        location = label.split(":", 1)[1] if ":" in label else label
        cleaned = cleaned.replace("Погода сейчас в ", "")
        return f"{location}: {self.deps.truncate_text_func(cleaned, 180)}"

    def _build_observed_rate_summary(self, body: str) -> str:
        return self.deps.truncate_text_func(self.deps.normalize_whitespace_func(body), 180)

    def _build_observed_crypto_summary(self, body: str) -> str:
        return self.deps.truncate_text_func(self.deps.normalize_whitespace_func(body), 180)

    def _collect_observed_source_labels(self, external_sections: List[Tuple[str, str]]) -> List[str]:
        labels: List[str] = []
        for label, body in external_sections:
            lowered = label.lower()
            if label == "Новости" and "Google News RSS" not in labels:
                labels.append("Google News RSS")
            elif lowered.startswith("погода") and "Open-Meteo" not in labels:
                labels.append("Open-Meteo")
            elif label == "Курс":
                if "open.er-api" in body and "open.er-api" not in labels:
                    labels.append("open.er-api")
                elif "Yahoo Finance" in body and "Yahoo Finance" not in labels:
                    labels.append("Yahoo Finance")
                elif "Frankfurter" not in labels:
                    labels.append("Frankfurter")
            elif label == "Bitcoin price" and "CoinGecko" not in labels:
                labels.append("CoinGecko")
            elif label in {"Смартфон", "Bitcoin outlook"} and "DuckDuckGo snippets" not in labels:
                labels.append("DuckDuckGo snippets")
        return labels

    def build_direct_url_context(self, query: str, *, limit_chars: int = 3500) -> str:
        urls = self.deps.extract_urls_func(query)
        if not urls:
            return ""
        url = urls[0]
        host = urlparse(url).netloc or url
        try:
            response_text = self.deps.request_text_with_retry_func(
                "get",
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
        except Exception as error:
            self.deps.log_func(f"url fetch failed url={self.deps.shorten_for_log_func(url, 240)} error={error}")
            if self.deps.is_direct_url_antibot_block_func(url, "", "", error=error):
                return self.deps.build_direct_url_blocked_reply_func(url)
            return ""
        cleaned_html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\\1>", " ", response_text)
        title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", cleaned_html)
        title = self.deps.normalize_whitespace_func(html.unescape(re.sub(r"<.*?>", " ", title_match.group(1) if title_match else "")))
        meta_match = re.search(
            r"""(?is)<meta[^>]+(?:name|property)=["'](?:description|og:description)["'][^>]+content=["'](.*?)["']""",
            cleaned_html,
        )
        meta_description = self.deps.normalize_whitespace_func(html.unescape(re.sub(r"<.*?>", " ", meta_match.group(1) if meta_match else "")))
        if self.deps.is_direct_url_antibot_block_func(url, title, meta_description, response_text=response_text):
            return self.deps.build_direct_url_blocked_reply_func(url)
        text_content = self.deps.normalize_whitespace_func(html.unescape(re.sub(r"<[^>]+>", " ", cleaned_html)))
        excerpt = self.deps.truncate_text_func(text_content, limit_chars)
        lines = [f"Прямой контекст страницы: {host}"]
        if title:
            lines.append(f"Title: {title}")
        if meta_description:
            lines.append(f"Description: {self.deps.truncate_text_func(meta_description, 500)}")
        if excerpt:
            lines.append(f"Page excerpt: {excerpt}")
        lines.append(f"URL: {self.deps.truncate_text_func(url, 400)}")
        return "\n".join(lines)

    def build_web_search_context(self, query: str, *, limit: int = 5) -> str:
        normalized_query = self.deps.normalize_whitespace_func(query)
        if not normalized_query:
            return ""
        direct_url_context = self.build_direct_url_context(normalized_query)
        if not direct_url_context and self.deps.is_query_too_broad_for_external_search_func(normalized_query):
            return self.deps.build_external_search_needs_object_reply_func(normalized_query)
        search_query = self.deps.normalize_external_search_query_func(normalized_query)
        if direct_url_context and not search_query:
            return direct_url_context
        if not search_query:
            return direct_url_context
        try:
            response_text = self.deps.request_text_with_retry_func(
                "post",
                "https://html.duckduckgo.com/html/",
                data={"q": search_query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
        except Exception as error:
            self.deps.log_func(f"web search failed query={self.deps.shorten_for_log_func(search_query, 180)} error={error}")
            return direct_url_context
        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
            r'(?:<a[^>]*class="result__snippet"[^>]*>(?P<snippet_a>.*?)</a>|'
            r'<div[^>]*class="result__snippet"[^>]*>(?P<snippet_div>.*?)</div>)',
            re.S,
        )
        raw_results = 0
        irrelevant_results = 0
        items: List[str] = []
        for match in pattern.finditer(response_text):
            raw_results += 1
            title = html.unescape(re.sub(r"<.*?>", " ", match.group("title") or ""))
            snippet_raw = match.group("snippet_a") or match.group("snippet_div") or ""
            snippet = html.unescape(re.sub(r"<.*?>", " ", snippet_raw))
            url = html.unescape(match.group("url") or "")
            title = self.deps.normalize_whitespace_func(title)
            snippet = self.deps.normalize_whitespace_func(snippet)
            url = self.deps.normalize_whitespace_func(url)
            if not title or not url:
                continue
            if self.deps.is_irrelevant_web_search_result_func(title, snippet, url):
                irrelevant_results += 1
                continue
            items.append(
                f"- {self.deps.truncate_text_func(title, 180)}\n  URL: {self.deps.truncate_text_func(url, 300)}\n  Фрагмент: {self.deps.truncate_text_func(snippet or 'Фрагмент не найден.', 260)}"
            )
            if len(items) >= limit:
                break
        if irrelevant_results and not items:
            return self.deps.build_external_search_needs_object_reply_func(normalized_query)
        if raw_results >= 3 and irrelevant_results >= max(2, raw_results - 1) and len(items) <= 1:
            return self.deps.build_external_search_not_confirmed_reply_func(normalized_query)
        if not items:
            return direct_url_context
        web_context = f"Свежий веб-контекст по запросу «{self.deps.truncate_text_func(search_query, 180)}»:\n" + "\n".join(items)
        if direct_url_context:
            return direct_url_context + "\n\n" + web_context
        return web_context

    def build_web_route_fallback_answer(self, query: str, web_context: str) -> str:
        normalized_query = self.deps.truncate_text_func(self.deps.normalize_whitespace_func(query), 180)
        cleaned_context = (web_context or "").strip()
        if not cleaned_context:
            return "Сейчас не получилось собрать полезные внешние данные по этому запросу."
        return f"Коротко по запросу «{normalized_query}».\n\n{cleaned_context}"

    def summarize_web_context(self, query: str, web_context: str) -> str:
        cleaned_context = (web_context or "").strip()
        if not cleaned_context:
            return ""
        prompt = (
            "Ниже есть внешний веб-контекст по запросу пользователя.\n"
            "Сделай короткий полезный ответ на русском.\n"
            "Требования:\n"
            "- сначала дай прямой вывод по сути запроса\n"
            "- не выдумывай то, чего нет в источниках\n"
            "- не объясняй внутренние ограничения системы\n"
            "- если данных мало, дай краткий полезный вывод без служебного self-talk\n\n"
            f"Запрос пользователя: {self.deps.normalize_whitespace_func(query)}\n\n"
            f"Веб-контекст:\n{self.deps.truncate_text_func(cleaned_context, 5000)}"
        )
        return self.deps.run_codex_short_func(prompt, timeout_seconds=20)
