import html
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from requests.exceptions import RequestException

from services.route_contracts import ExternalResearchTask, LiveProviderRecord


@dataclass(frozen=True)
class LiveGatewayDeps:
    request_json_with_retry: Callable[..., dict]
    request_text_with_retry: Callable[..., str]
    log_func: Callable[[str], None]
    normalize_whitespace_func: Callable[[str], str]
    truncate_text_func: Callable[[str, int], str]
    shorten_for_log_func: Callable[[str, int], str]
    normalize_location_query_func: Callable[[str], str]
    build_location_query_variants_func: Callable[[str], List[str]]
    format_signed_value_func: Callable[[object], str]
    weather_code_labels: dict


class LiveGateway:
    def __init__(self, deps: LiveGatewayDeps) -> None:
        self.deps = deps
        self._last_records: Tuple[LiveProviderRecord, ...] = ()

    def consume_records(self) -> Tuple[LiveProviderRecord, ...]:
        records = self._last_records
        self._last_records = ()
        return records

    def fetch_weather_answer(self, location_query: str) -> Tuple[str, Tuple[LiveProviderRecord, ...]]:
        normalize_location_query = self.deps.normalize_location_query_func
        build_location_query_variants = self.deps.build_location_query_variants_func
        format_signed_value = self.deps.format_signed_value_func
        weather_code_labels = self.deps.weather_code_labels
        log = self.deps.log_func
        shorten_for_log = self.deps.shorten_for_log_func
        normalized_location = normalize_location_query(location_query)
        if not normalized_location:
            return "", ()
        query_variants = build_location_query_variants(normalized_location)
        geo_record = self._build_record(
            "Open-Meteo Geocoding",
            "weather_geocoding",
            normalized_location,
            "request-time",
            "pending",
            0.0,
            False,
        )
        weather_record = self._build_record(
            "Open-Meteo",
            "weather",
            normalized_location,
            "request-time",
            "pending",
            0.0,
            False,
        )
        try:
            results: List[dict] = []
            matched_location = normalized_location
            for candidate_location in query_variants:
                geo_payload = self.deps.request_json_with_retry(
                    "get",
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={
                        "name": candidate_location,
                        "count": 1,
                        "language": "ru",
                        "format": "json",
                    },
                    timeout=20,
                )
                results = geo_payload.get("results") or []
                if results:
                    matched_location = candidate_location
                    geo_record = self._build_record(
                        provider="Open-Meteo Geocoding",
                        category="weather_geocoding",
                        data=f"match:{matched_location}",
                        freshness="request-time",
                        status="ok",
                        reliability=0.92,
                        normalized=True,
                    )
                    break
            if not results:
                geo_record = self._build_record(
                    provider="Open-Meteo Geocoding",
                    category="weather_geocoding",
                    data=f"lookup:{normalized_location}",
                    freshness="request-time",
                    status="failed",
                    reliability=0.0,
                    normalized=False,
                )
                return f"Не нашёл локацию: {normalized_location}.", self._store_records(geo_record)
            place = results[0]
            latitude = place.get("latitude")
            longitude = place.get("longitude")
            if latitude is None or longitude is None:
                weather_record = self._build_record(
                    provider="Open-Meteo",
                    category="weather",
                    data=f"coords-missing:{matched_location}",
                    freshness="request-time",
                    status="failed",
                    reliability=0.0,
                    normalized=False,
                )
                return f"Не удалось определить координаты для: {matched_location}.", self._store_records(geo_record, weather_record)
            place_name = place.get("name") or matched_location
            admin_name = place.get("admin1") or place.get("country") or ""
            display_name = f"{place_name}, {admin_name}".strip(", ")
            payload = self.deps.request_json_with_retry(
                "get",
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 1,
                },
                timeout=20,
            )
        except RequestException as error:
            log(f"weather lookup failed query={shorten_for_log(normalized_location, 160)} error={error}")
            weather_record = self._build_record(
                provider="Open-Meteo",
                category="weather",
                data=f"lookup:{normalized_location}",
                freshness="stale",
                status="failed",
                reliability=0.0,
                normalized=False,
            )
            return "Не удалось получить актуальную погоду из внешнего источника.", self._store_records(geo_record, weather_record)
        current = payload.get("current") or {}
        daily = payload.get("daily") or {}
        temperature = current.get("temperature_2m")
        apparent = current.get("apparent_temperature")
        weather_code = current.get("weather_code")
        wind_speed = current.get("wind_speed_10m")
        precipitation = current.get("precipitation")
        max_list = daily.get("temperature_2m_max") or []
        min_list = daily.get("temperature_2m_min") or []
        precip_prob_list = daily.get("precipitation_probability_max") or []
        weather_label = weather_code_labels.get(int(weather_code), "условия уточняются") if weather_code is not None else "условия уточняются"
        details = [
            f"Погода сейчас в {display_name}: {format_signed_value(temperature)}°C, {weather_label}.",
        ]
        if apparent is not None:
            details.append(f"Ощущается как {format_signed_value(apparent)}°C.")
        if max_list and min_list:
            details.append(f"За сегодня: от {format_signed_value(min_list[0])}°C до {format_signed_value(max_list[0])}°C.")
        if wind_speed is not None:
            details.append(f"Ветер: {float(wind_speed):.1f} м/с.")
        if precip_prob_list:
            details.append(f"Вероятность осадков: {int(precip_prob_list[0])}%.")
        elif precipitation is not None:
            details.append(f"Осадки сейчас: {float(precipitation):.1f} мм.")
        time_value = current.get("time")
        if time_value:
            details.append(f"Источник: Open-Meteo, обновление {time_value}.")
        weather_record = self._build_record(
            provider="Open-Meteo",
            category="weather",
            data=f"{display_name}:{current.get('time') or ''}",
            freshness="live",
            status="ok",
            reliability=0.94,
            normalized=True,
        )
        return " ".join(details), self._store_records(geo_record, weather_record)

    def fetch_exchange_rate_answer(self, base_currency: str, quote_currency: str) -> Tuple[str, Tuple[LiveProviderRecord, ...]]:
        base = (base_currency or "").upper()
        quote = (quote_currency or "").upper()
        if not base or not quote or base == quote:
            return "", ()
        records: List[LiveProviderRecord] = []
        try:
            payload = self.deps.request_json_with_retry(
                "get",
                "https://api.frankfurter.app/latest",
                params={"from": base, "to": quote},
                timeout=20,
            )
        except RequestException as error:
            self.deps.log_func(f"exchange lookup failed pair={base}/{quote} error={error}")
            records.append(self._build_record("Frankfurter", "fx", f"{base}/{quote}", "stale", "failed", 0.0, False))
            return self.fetch_exchange_rate_answer_yahoo(base, quote, records)
        rates = payload.get("rates") or {}
        value = rates.get(quote)
        if value is None:
            records.append(self._build_record("Frankfurter", "fx", f"{base}/{quote}", "stale", "degraded", 0.2, False))
            return self.fetch_exchange_rate_answer_yahoo(base, quote, records)
        date_value = payload.get("date") or ""
        records.append(self._build_record("Frankfurter", "fx", f"{base}/{quote}:{date_value}", "live", "ok", 0.9, True))
        return f"Курс {base}/{quote}: 1 {base} = {float(value):.4f} {quote}. Дата источника: {date_value}.", self._store_records(*records)

    def fetch_exchange_rate_answer_yahoo(
        self,
        base_currency: str,
        quote_currency: str,
        records: Sequence[LiveProviderRecord] = (),
    ) -> Tuple[str, Tuple[LiveProviderRecord, ...]]:
        next_records = list(records)
        symbol = f"{(base_currency or '').upper()}{(quote_currency or '').upper()}=X"
        try:
            payload = self.deps.request_json_with_retry(
                "get",
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": symbol},
                timeout=20,
            )
        except RequestException as error:
            self.deps.log_func(f"exchange yahoo lookup failed pair={base_currency}/{quote_currency} error={error}")
            next_records.append(self._build_record("Yahoo Finance", "fx", symbol, "stale", "failed", 0.0, False))
            return self.fetch_exchange_rate_answer_open_er(base_currency, quote_currency, next_records)
        results = ((payload.get("quoteResponse") or {}).get("result") or [])
        if not results:
            next_records.append(self._build_record("Yahoo Finance", "fx", symbol, "stale", "degraded", 0.2, False))
            return self.fetch_exchange_rate_answer_open_er(base_currency, quote_currency, next_records)
        item = results[0]
        price = item.get("regularMarketPrice")
        market_time = item.get("regularMarketTime")
        if price is None:
            next_records.append(self._build_record("Yahoo Finance", "fx", symbol, "stale", "degraded", 0.2, False))
            return self.fetch_exchange_rate_answer_open_er(base_currency, quote_currency, next_records)
        next_records.append(
            self._build_record(
                "Yahoo Finance",
                "fx",
                symbol,
                "live",
                "ok",
                0.89,
                True,
                timestamp=int(market_time or time.time()),
            )
        )
        answer = f"Курс {base_currency}/{quote_currency}: 1 {base_currency} = {float(price):.4f} {quote_currency}."
        if market_time:
            answer += f" Источник: Yahoo Finance, обновление {datetime.utcfromtimestamp(int(market_time)).strftime('%Y-%m-%d %H:%M:%S')} UTC."
        else:
            answer += " Источник: Yahoo Finance."
        return answer, self._store_records(*next_records)

    def fetch_exchange_rate_answer_open_er(
        self,
        base_currency: str,
        quote_currency: str,
        records: Sequence[LiveProviderRecord] = (),
    ) -> Tuple[str, Tuple[LiveProviderRecord, ...]]:
        next_records = list(records)
        base = (base_currency or "").upper()
        quote = (quote_currency or "").upper()
        try:
            payload = self.deps.request_json_with_retry(
                "get",
                f"https://open.er-api.com/v6/latest/{base}",
                timeout=20,
            )
        except RequestException as error:
            self.deps.log_func(f"exchange open.er lookup failed pair={base}/{quote} error={error}")
            next_records.append(self._build_record("open.er-api", "fx", f"{base}/{quote}", "stale", "failed", 0.0, False))
            return "Не удалось получить актуальный курс из внешнего источника.", self._store_records(*next_records)
        rates = payload.get("rates") or {}
        value = rates.get(quote)
        if value is None:
            next_records.append(self._build_record("open.er-api", "fx", f"{base}/{quote}", "stale", "failed", 0.0, False))
            return f"Не удалось получить курс {base}/{quote}.", self._store_records(*next_records)
        updated_at = self.deps.normalize_whitespace_func(str(payload.get("time_last_update_utc") or ""))
        next_records.append(self._build_record("open.er-api", "fx", f"{base}/{quote}:{updated_at}", "live", "ok", 0.82, True))
        answer = f"Курс {base}/{quote}: 1 {base} = {float(value):.4f} {quote}."
        if updated_at:
            answer += f" Источник: open.er-api, обновление {updated_at}."
        else:
            answer += " Источник: open.er-api."
        return answer, self._store_records(*next_records)

    def fetch_crypto_price_answer(self, crypto_id: str) -> Tuple[str, Tuple[LiveProviderRecord, ...]]:
        try:
            payload = self.deps.request_json_with_retry(
                "get",
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": crypto_id, "vs_currencies": "usd,rub", "include_last_updated_at": "true"},
                timeout=20,
            )
        except RequestException as error:
            self.deps.log_func(f"crypto lookup failed asset={crypto_id} error={error}")
            return "Не удалось получить актуальную цену криптовалюты.", self._store_records(
                self._build_record("CoinGecko", "crypto", crypto_id, "stale", "failed", 0.0, False)
            )
        item = payload.get(crypto_id) or {}
        usd = item.get("usd")
        rub = item.get("rub")
        updated_at = item.get("last_updated_at")
        if usd is None and rub is None:
            return f"Не удалось получить цену для {crypto_id}.", self._store_records(
                self._build_record("CoinGecko", "crypto", crypto_id, "stale", "degraded", 0.2, False)
            )
        parts = [f"Цена {crypto_id}:"]
        if usd is not None:
            parts.append(f"${float(usd):,.4f}".replace(",", " "))
        if rub is not None:
            parts.append(f"{float(rub):,.2f} RUB".replace(",", " "))
        answer = " ".join(parts) + "."
        if updated_at:
            answer += f" Источник: CoinGecko, обновление {datetime.utcfromtimestamp(int(updated_at)).strftime('%Y-%m-%d %H:%M:%S')} UTC."
        return answer, self._store_records(
            self._build_record(
                "CoinGecko",
                "crypto",
                crypto_id,
                "live",
                "ok",
                0.92,
                True,
                timestamp=int(updated_at or time.time()),
            )
        )

    def fetch_stock_price_answer(self, stock_symbol: str) -> Tuple[str, Tuple[LiveProviderRecord, ...]]:
        try:
            payload = self.deps.request_json_with_retry(
                "get",
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": stock_symbol},
                timeout=20,
            )
        except RequestException as error:
            self.deps.log_func(f"stock lookup failed symbol={stock_symbol} error={error}")
            return "Не удалось получить актуальную цену инструмента.", self._store_records(
                self._build_record("Yahoo Finance", "stocks", stock_symbol, "stale", "failed", 0.0, False)
            )
        results = ((payload.get("quoteResponse") or {}).get("result") or [])
        if not results:
            return f"Не удалось получить котировку {stock_symbol}.", self._store_records(
                self._build_record("Yahoo Finance", "stocks", stock_symbol, "stale", "degraded", 0.2, False)
            )
        item = results[0]
        price = item.get("regularMarketPrice")
        currency = item.get("currency") or "USD"
        market_state = item.get("marketState") or ""
        change_percent = item.get("regularMarketChangePercent")
        short_name = item.get("shortName") or stock_symbol
        market_time = item.get("regularMarketTime")
        if price is None:
            return f"Не удалось получить котировку {stock_symbol}.", self._store_records(
                self._build_record("Yahoo Finance", "stocks", stock_symbol, "stale", "degraded", 0.2, False)
            )
        answer = f"{short_name} ({stock_symbol}): {float(price):,.4f} {currency}".replace(",", " ")
        if change_percent is not None:
            answer += f", изменение {self.deps.format_signed_value_func(change_percent)}%"
        if market_state:
            answer += f", статус рынка: {market_state}"
        answer += ". Источник: Yahoo Finance."
        return answer, self._store_records(
            self._build_record(
                "Yahoo Finance",
                "stocks",
                stock_symbol,
                "live",
                "ok",
                0.9,
                True,
                timestamp=int(market_time or time.time()),
            )
        )

    def fetch_news_answer(self, query: str, limit: int = 3) -> Tuple[str, Tuple[LiveProviderRecord, ...]]:
        normalized_query = self.deps.normalize_whitespace_func(query)
        rss_query = normalized_query
        if any(marker in normalized_query.lower() for marker in ("за последний день", "за день", "за сутки", "сегодня", "последние", "свежие")):
            rss_query = f"{normalized_query} when:1d"
        try:
            response_text = self.deps.request_text_with_retry(
                "get",
                "https://news.google.com/rss/search",
                params={"q": rss_query, "hl": "ru", "gl": "RU", "ceid": "RU:ru"},
                timeout=20,
            )
        except RequestException as error:
            self.deps.log_func(f"news lookup failed query={self.deps.shorten_for_log_func(normalized_query, 160)} error={error}")
            return "Не удалось получить свежие новости по этому запросу.", self._store_records(
                self._build_record("Google News RSS", "news", normalized_query, "stale", "failed", 0.0, False)
            )
        try:
            root = ET.fromstring(response_text)
        except ET.ParseError as error:
            self.deps.log_func(f"news parse failed query={self.deps.shorten_for_log_func(normalized_query, 160)} error={error}")
            return "Источник новостей ответил в неожиданном формате.", self._store_records(
                self._build_record("Google News RSS", "news", normalized_query, "stale", "failed", 0.0, False)
            )
        items = root.findall("./channel/item")
        if not items:
            return f"По запросу «{normalized_query}» свежих новостей не нашёл.", self._store_records(
                self._build_record("Google News RSS", "news", normalized_query, "stale", "degraded", 0.2, False)
            )
        lines = [f"Свежие новости по запросу «{normalized_query}»:"] 
        latest_pub_date = ""
        for item in items[:limit]:
            title = self.deps.normalize_whitespace_func("".join(item.findtext("title", default="")).replace(" - ", " — "))
            link = self.deps.normalize_whitespace_func(item.findtext("link", default=""))
            pub_date = self.deps.normalize_whitespace_func(item.findtext("pubDate", default=""))
            if not title or not link:
                continue
            latest_pub_date = latest_pub_date or pub_date
            line = f"• {self.deps.truncate_text_func(title, 180)}"
            if pub_date:
                line += f"\n  {self.deps.truncate_text_func(pub_date, 64)}"
            line += f"\n  {self.deps.truncate_text_func(link, 280)}"
            lines.append(line)
        if len(lines) == 1:
            return f"По запросу «{normalized_query}» новости получить не удалось.", self._store_records(
                self._build_record("Google News RSS", "news", normalized_query, "stale", "degraded", 0.2, False)
            )
        return "\n".join(lines), self._store_records(
            self._build_record("Google News RSS", "news", f"{normalized_query}:{latest_pub_date}", "live", "ok", 0.86, True)
        )

    def fetch_current_fact_answer(self, query: str, limit: int = 3) -> Tuple[str, Tuple[LiveProviderRecord, ...]]:
        normalized_query = self.deps.normalize_whitespace_func(query)
        if not normalized_query:
            return "", ()
        try:
            response_text = self.deps.request_text_with_retry(
                "post",
                "https://html.duckduckgo.com/html/",
                data={"q": normalized_query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=20,
            )
        except RequestException as error:
            self.deps.log_func(f"current fact lookup failed query={self.deps.shorten_for_log_func(normalized_query, 160)} error={error}")
            return "Не удалось проверить актуальный факт по внешним источникам.", self._store_records(
                self._build_record("DuckDuckGo HTML", "current_fact", normalized_query, "stale", "failed", 0.0, False)
            )
        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
            r'(?:<a[^>]*class="result__snippet"[^>]*>(?P<snippet_a>.*?)</a>|'
            r'<div[^>]*class="result__snippet"[^>]*>(?P<snippet_div>.*?)</div>)',
            re.S,
        )
        items: List[Tuple[str, str, str]] = []
        for match in pattern.finditer(response_text):
            title = self.deps.normalize_whitespace_func(html.unescape(re.sub(r"<.*?>", " ", match.group("title") or "")))
            snippet_raw = match.group("snippet_a") or match.group("snippet_div") or ""
            snippet = self.deps.normalize_whitespace_func(html.unescape(re.sub(r"<.*?>", " ", snippet_raw)))
            url = self.deps.normalize_whitespace_func(html.unescape(match.group("url") or ""))
            if not title or not url:
                continue
            items.append((title, snippet, url))
            if len(items) >= limit:
                break
        if not items:
            return f"По запросу «{normalized_query}» не нашёл надёжных внешних результатов.", self._store_records(
                self._build_record("DuckDuckGo HTML", "current_fact", normalized_query, "stale", "degraded", 0.2, False)
            )
        lines = [
            (
                f"По запросу «{normalized_query}» нашёл внешние совпадения, но это только сниппеты поиска, "
                "а не прямое подтверждение факта."
            ),
            "Статус: inferred по внешним источникам; ниже результаты для ручной проверки.",
            "",
        ]
        lines.append(f"Источники по запросу «{normalized_query}»:")
        for title, snippet, url in items:
            line = f"• {self.deps.truncate_text_func(title, 180)}"
            if snippet:
                line += f"\n  {self.deps.truncate_text_func(snippet, 240)}"
            line += f"\n  {self.deps.truncate_text_func(url, 280)}"
            lines.append(line)
        return "\n".join(lines), self._store_records(
            self._build_record("DuckDuckGo HTML", "current_fact", normalized_query, "live", "ok", 0.55, True)
        )

    def collect_external_research_sections(
        self,
        query: str,
        tasks: Iterable[ExternalResearchTask],
        build_web_search_context_func: Callable[[str], str],
    ) -> List[Tuple[str, str]]:
        normalized_query = self.deps.normalize_whitespace_func(query)
        if not normalized_query:
            return []
        sections: List[Tuple[str, str]] = []
        for task in tasks:
            if task.kind == "news":
                result, _ = self.fetch_news_answer(task.payload, limit=3)
            elif task.kind == "current_fact":
                result, _ = self.fetch_current_fact_answer(task.payload, limit=3)
            elif task.kind == "weather":
                result, _ = self.fetch_weather_answer(task.payload)
            elif task.kind == "fx":
                base, quote = (task.payload.split("/", 1) + [""])[:2]
                result, _ = self.fetch_exchange_rate_answer(base, quote)
            elif task.kind == "crypto":
                result, _ = self.fetch_crypto_price_answer(task.payload)
            elif task.kind == "stocks":
                result, _ = self.fetch_stock_price_answer(task.payload)
            elif task.kind == "web_search":
                result = build_web_search_context_func(task.payload)
            else:
                result = ""
            cleaned_result = self.deps.normalize_whitespace_func(result)
            if not cleaned_result:
                continue
            sections.append((task.label, cleaned_result))
        return sections

    def _build_record(
        self,
        provider: str,
        category: str,
        data: str,
        freshness: str,
        status: str,
        reliability: float,
        normalized: bool,
        *,
        timestamp: Optional[int] = None,
    ) -> LiveProviderRecord:
        return LiveProviderRecord(
            provider=provider,
            category=category,
            data=data,
            timestamp=int(timestamp if timestamp is not None else time.time()),
            freshness=freshness,
            status=status,
            reliability=max(0.0, min(1.0, float(reliability))),
            normalized=normalized,
        )

    def _store_records(self, *records: LiveProviderRecord) -> Tuple[LiveProviderRecord, ...]:
        normalized = tuple(record for record in records if record.provider)
        self._last_records = normalized
        return normalized
