# Search Architecture

## Target Architecture

Jarvis Portable now has a dedicated modular search layer:

- `search/search_models.py`: strict contracts between routing, providers, evidence, citations and synthesis.
- `search/classifier.py`: structured classifier for quick lookup vs deep research.
- `search/provider_registry.py`: optional provider abstraction and fallback-ready registry.
- `search/legacy_bridge_provider.py`: compatibility adapter over the existing local-first web access path.
- `search/semantic_cache.py`: SQLite-first local cache for search results and fetched pages.
- `search/reranker.py`: scoring, deduplication and ranking.
- `search/evidence_builder.py`: evidence bundle assembly.
- `search/citation_renderer.py`: citation generation.
- `search/self_check.py`: unsupported-claim / weak-source guard.
- `search/search_orchestrator.py`: end-to-end research pipeline.

Telegram presentation is now separated from search logic:

- `models/presentation.py`: structured presentation model.
- `policy/final_answer_policy.py`: user-facing answer shaping policy for Telegram and concise practical answers.
- `adapters/telegram/answer_templates.py`: reusable answer templates.
- `adapters/telegram/message_formatter.py`: HTML-safe formatting.
- `adapters/telegram/chunking.py`: Telegram-safe chunking.
- `adapters/telegram/telegram_response_renderer.py`: presentation model -> outgoing Telegram messages.
- `services/research_service.py`: service facade that wires provider registry, cache and live/search orchestration for the bridge.

## Pipeline

`user query -> route decision -> search classifier -> search plan -> provider registry -> provider search -> rerank/dedup -> evidence bundle -> citations -> self-check -> presentation model -> Telegram renderer`

## Provider System

Providers are optional and registry-based. If a provider is unavailable or fails:

- the orchestrator degrades gracefully,
- the bot keeps the legacy route fallback,
- no cloud dependency is required by default.

Current baseline provider:

- `LegacyBridgeWebProvider`: compatibility provider using the existing DuckDuckGo HTML search path.
- `WeatherLiveProvider`, `FxLiveProvider`, `CryptoLiveProvider`, `StocksLiveProvider`, `NewsLiveProvider`, `CurrentFactLiveProvider`: adapters over the existing `LiveGateway`.

## Cache Behavior

- SQLite-first local cache
- portable file under `data/search_cache.sqlite3`
- TTL based on freshness policy
- ready for future embeddings or semantic metadata expansion

## Citations

Each evidence item tracks:

- title
- url
- publisher/domain
- snippet
- published_at
- fetched_at
- reliability score
- freshness score
- source type
- cache metadata

## Fallback Behavior

If structured search fails:

- existing web/live/local routes remain operational,
- owner-only/local-first mode remains unchanged,
- the bridge falls back to legacy summarization path.

## Final Answer Policy

Internal routing, diagnostics, self-check and provider-selection details must not leak into the normal user-facing answer.

Telegram UX target:

- 1 short line with the main answer
- 2-5 concrete bullets
- at most 1 short disclaimer when really needed
- 1 practical next step

Self-check still affects wording, but is not printed as an internal report.

Forbidden in normal user-facing Telegram answers:

- internal diagnostics
- routing decisions
- confidence notes
- chain-of-thought
- self-check narration
- system self-talk in the opener

## How To Add Provider

1. Implement the `SearchProvider` protocol.
2. Register it in `ProviderRegistry`.
3. Return `SearchResult` items with stable URL/domain/title/snippet fields.
4. Implement `reliability_score` and `freshness_score`.
5. Optionally implement `fetch`.

## Trade-Offs

- First integration keeps the giant bridge as compatibility composition root.
- Structured search is integrated for web routes first, but live adapters are already registered through `ResearchService`.
- Telegram presentation is enabled for the new structured search path first to avoid breaking legacy operational messages.
