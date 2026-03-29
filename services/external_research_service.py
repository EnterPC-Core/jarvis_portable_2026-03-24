from __future__ import annotations

import html
import re
from typing import Callable, List, Optional, Sequence

from models.contracts import ExternalResearchTask, RouteDecision


def build_external_research_tasks(
    *,
    query: str,
    route_decision: RouteDecision,
    detect_news_query_func: Callable[[str], str],
    detect_current_fact_query_func: Callable[[str], str],
    detect_weather_location_func: Callable[[str], str],
    detect_currency_pair_func: Callable[[str], Optional[tuple[str, str]]],
    detect_crypto_asset_func: Callable[[str], str],
    detect_stock_symbol_func: Callable[[str], str],
) -> tuple[ExternalResearchTask, ...]:
    normalized = (query or "").strip()
    if not normalized or not route_decision.use_web:
        return ()
    tasks: List[ExternalResearchTask] = []
    news_query = detect_news_query_func(normalized)
    if news_query:
        tasks.append(ExternalResearchTask(kind="news", label="News evidence", payload=news_query))
    current_fact_query = detect_current_fact_query_func(normalized)
    if current_fact_query:
        tasks.append(ExternalResearchTask(kind="current_fact", label="Current fact evidence", payload=current_fact_query))
    weather_query = detect_weather_location_func(normalized)
    if weather_query:
        tasks.append(ExternalResearchTask(kind="weather", label="Weather evidence", payload=weather_query))
    currency_pair = detect_currency_pair_func(normalized)
    if currency_pair:
        tasks.append(ExternalResearchTask(kind="fx", label="FX evidence", payload=f"{currency_pair[0]}/{currency_pair[1]}"))
    crypto_asset = detect_crypto_asset_func(normalized)
    if crypto_asset:
        tasks.append(ExternalResearchTask(kind="crypto", label="Crypto evidence", payload=crypto_asset))
    stock_symbol = detect_stock_symbol_func(normalized)
    if stock_symbol:
        tasks.append(ExternalResearchTask(kind="stocks", label="Stock evidence", payload=stock_symbol))
    if not tasks:
        tasks.append(ExternalResearchTask(kind="web_search", label="Web findings", payload=normalized))
    return tuple(tasks)


def build_web_search_context(
    query: str,
    *,
    request_text_with_retry_func: Callable[..., str],
    normalize_whitespace_func: Callable[[str], str],
    truncate_text_func: Callable[[str, int], str],
    limit: int = 4,
) -> str:
    normalized_query = normalize_whitespace_func(query)
    if not normalized_query:
        return ""
    try:
        response_text = request_text_with_retry_func(
            "post",
            "https://html.duckduckgo.com/html/",
            data={"q": normalized_query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
    except Exception:
        return ""
    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
        r'(?:<a[^>]*class="result__snippet"[^>]*>(?P<snippet_a>.*?)</a>|'
        r'<div[^>]*class="result__snippet"[^>]*>(?P<snippet_div>.*?)</div>)',
        re.S,
    )
    lines = [f"Web search context for query: {truncate_text_func(normalized_query, 180)}"]
    found = 0
    for match in pattern.finditer(response_text):
        title = normalize_whitespace_func(html.unescape(re.sub(r"<.*?>", " ", match.group("title") or "")))
        snippet_raw = match.group("snippet_a") or match.group("snippet_div") or ""
        snippet = normalize_whitespace_func(html.unescape(re.sub(r"<.*?>", " ", snippet_raw)))
        url = normalize_whitespace_func(html.unescape(match.group("url") or ""))
        if not title or not url:
            continue
        lines.append(
            f"- {truncate_text_func(title, 180)}\n"
            f"  {truncate_text_func(snippet or 'нет фрагмента', 260)}\n"
            f"  {truncate_text_func(url, 280)}"
        )
        found += 1
        if found >= max(1, int(limit)):
            break
    return "\n".join(lines) if found else ""


def build_external_research_context(
    *,
    query: str,
    route_decision: RouteDecision,
    live_gateway: "LiveGateway",
    request_text_with_retry_func: Callable[..., str],
    normalize_whitespace_func: Callable[[str], str],
    truncate_text_func: Callable[[str, int], str],
    detect_news_query_func: Callable[[str], str],
    detect_current_fact_query_func: Callable[[str], str],
    detect_weather_location_func: Callable[[str], str],
    detect_currency_pair_func: Callable[[str], Optional[tuple[str, str]]],
    detect_crypto_asset_func: Callable[[str], str],
    detect_stock_symbol_func: Callable[[str], str],
) -> str:
    tasks = build_external_research_tasks(
        query=query,
        route_decision=route_decision,
        detect_news_query_func=detect_news_query_func,
        detect_current_fact_query_func=detect_current_fact_query_func,
        detect_weather_location_func=detect_weather_location_func,
        detect_currency_pair_func=detect_currency_pair_func,
        detect_crypto_asset_func=detect_crypto_asset_func,
        detect_stock_symbol_func=detect_stock_symbol_func,
    )
    if not tasks:
        return ""
    sections = live_gateway.collect_external_research_sections(
        query,
        tasks,
        lambda payload: build_web_search_context(
            payload,
            request_text_with_retry_func=request_text_with_retry_func,
            normalize_whitespace_func=normalize_whitespace_func,
            truncate_text_func=truncate_text_func,
        ),
    )
    if not sections:
        return ""
    lines: List[str] = []
    for label, section_text in sections:
        cleaned = normalize_whitespace_func(section_text)
        if not cleaned:
            continue
        lines.append(f"{label}:\n{truncate_text_func(cleaned, 2400)}")
    return "\n\n".join(lines)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.live_gateway import LiveGateway
