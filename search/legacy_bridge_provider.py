from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence
from urllib.parse import urlparse

from requests.exceptions import RequestException

from search.provider_registry import SearchProvider
from search.search_models import ProviderCapability, SearchFetchResult, SearchQuery, SearchResult


@dataclass(frozen=True)
class LegacyBridgeWebProviderDeps:
    request_text_with_retry: Callable[..., str]
    normalize_whitespace_func: Callable[[str], str]
    truncate_text_func: Callable[[str, int], str]
    log_func: Callable[[str], None]


class LegacyBridgeWebProvider(SearchProvider):
    """Optional web search provider using DuckDuckGo HTML results."""

    name = "legacy_bridge_web"

    def __init__(self, deps: LegacyBridgeWebProviderDeps) -> None:
        self.deps = deps

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> Sequence[ProviderCapability]:
        return (ProviderCapability.SEARCH, ProviderCapability.FETCH)

    def search(self, query: SearchQuery, *, limit: int = 5) -> Sequence[SearchResult]:
        try:
            response_text = self.deps.request_text_with_retry(
                "post",
                "https://html.duckduckgo.com/html/",
                data={"q": query.normalized_query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
        except RequestException as error:
            self.deps.log_func(f"legacy bridge web provider failed query={self.deps.truncate_text_func(query.normalized_query, 120)} error={error}")
            return ()
        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
            r'(?:<a[^>]*class="result__snippet"[^>]*>(?P<snippet_a>.*?)</a>|'
            r'<div[^>]*class="result__snippet"[^>]*>(?P<snippet_div>.*?)</div>)',
            re.S,
        )
        results = []
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for match in pattern.finditer(response_text):
            title = self.deps.normalize_whitespace_func(html.unescape(re.sub(r"<.*?>", " ", match.group("title") or "")))
            snippet = self.deps.normalize_whitespace_func(
                html.unescape(re.sub(r"<.*?>", " ", match.group("snippet_a") or match.group("snippet_div") or ""))
            )
            url = self.deps.normalize_whitespace_func(html.unescape(match.group("url") or ""))
            if not title or not url:
                continue
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=self.deps.truncate_text_func(snippet or "Фрагмент не найден.", 260),
                    provider_name=self.name,
                    source_type="web_search",
                    fetched_at=fetched_at,
                    domain=urlparse(url).netloc,
                )
            )
            if len(results) >= limit:
                break
        return tuple(results)

    def fetch(self, result: SearchResult) -> Optional[SearchFetchResult]:
        return None

    def reliability_score(self, result: SearchResult) -> float:
        domain = (result.domain or urlparse(result.url).netloc).lower()
        if domain.endswith((".gov", ".edu")):
            return 0.92
        if any(marker in domain for marker in ("wikipedia.org", "developer.", "docs.", "openai.com", "python.org")):
            return 0.86
        if any(marker in domain for marker in ("reddit.com", "medium.com", "vc.ru")):
            return 0.45
        return 0.68

    def freshness_score(self, result: SearchResult, *, max_age_seconds: int) -> float:
        if max_age_seconds <= 21600:
            return 0.72
        if max_age_seconds <= 172800:
            return 0.78
        return 0.84

