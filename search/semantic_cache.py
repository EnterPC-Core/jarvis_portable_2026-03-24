from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import List, Sequence

from search.search_models import SearchFetchResult, SearchQuery, SearchResult


class SemanticCache:
    """SQLite-first local cache for search results and fetched pages."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS search_cache_results(
                    cache_key TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_cache_fetches(
                    url TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def _result_cache_key(self, query: SearchQuery, provider_name: str, limit: int) -> str:
        return f"{provider_name}|{query.intent.value}|{query.research_mode.value}|{limit}|{query.normalized_query.lower()}"

    def get_results(self, query: SearchQuery, provider_name: str, *, limit: int = 5) -> List[SearchResult]:
        cache_key = self._result_cache_key(query, provider_name, limit)
        now_ts = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM search_cache_results WHERE cache_key = ? AND expires_at >= ?",
                (cache_key, now_ts),
            ).fetchone()
        if row is None:
            return []
        payload = json.loads(row["payload_json"])
        hydrated = []
        for item in payload:
            restored = dict(item)
            restored["cache_hit"] = True
            hydrated.append(SearchResult(**restored))
        return hydrated

    def put_results(self, query: SearchQuery, provider_name: str, results: Sequence[SearchResult], *, ttl_seconds: int, limit: int = 5) -> None:
        cache_key = self._result_cache_key(query, provider_name, limit)
        now_ts = int(time.time())
        payload = [asdict(item) for item in results]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO search_cache_results(cache_key, created_at, expires_at, payload_json)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    payload_json = excluded.payload_json
                """,
                (cache_key, now_ts, now_ts + max(60, ttl_seconds), json.dumps(payload, ensure_ascii=False)),
            )

    def get_fetch(self, url: str) -> SearchFetchResult | None:
        now_ts = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM search_cache_fetches WHERE url = ? AND expires_at >= ?",
                (url, now_ts),
            ).fetchone()
        if row is None:
            return None
        return SearchFetchResult(**json.loads(row["payload_json"]))

    def put_fetch(self, fetch_result: SearchFetchResult, *, ttl_seconds: int) -> None:
        now_ts = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO search_cache_fetches(url, created_at, expires_at, payload_json)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    payload_json = excluded.payload_json
                """,
                (fetch_result.url, now_ts, now_ts + max(60, ttl_seconds), json.dumps(asdict(fetch_result), ensure_ascii=False)),
            )
