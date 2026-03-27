from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class SearchIntent(str, Enum):
    QUICK_LOOKUP = "quick_lookup"
    DEEP_RESEARCH = "deep_research"
    COMPARISON = "comparison"
    DOCUMENTATION = "documentation"
    CURRENT_FACT = "current_fact"
    NEWS = "news"
    LIVE_FACT = "live_fact"
    GENERAL_WEB = "general_web"


class ResearchMode(str, Enum):
    QUICK = "quick"
    DEEP = "deep"


class ProviderCapability(str, Enum):
    SEARCH = "search"
    FETCH = "fetch"
    EXTRACT = "extract"
    LIVE_FACT = "live_fact"


@dataclass(frozen=True)
class FreshnessPolicy:
    max_age_seconds: int
    require_live_data: bool = False
    prefer_recent: bool = True
    description: str = ""


@dataclass(frozen=True)
class SearchQuery:
    raw_query: str
    normalized_query: str
    user_id: Optional[int] = None
    chat_id: Optional[int] = None
    chat_type: str = "private"
    intent: SearchIntent = SearchIntent.GENERAL_WEB
    research_mode: ResearchMode = ResearchMode.QUICK
    require_citations: bool = True
    prefer_local_first: bool = True
    freshness_policy: FreshnessPolicy = field(default_factory=lambda: FreshnessPolicy(max_age_seconds=86400))


@dataclass(frozen=True)
class SearchTask:
    query: str
    provider_hint: str = ""
    capability: ProviderCapability = ProviderCapability.SEARCH
    depth: int = 1
    max_results: int = 5


@dataclass(frozen=True)
class SearchPlan:
    intent: SearchIntent
    research_mode: ResearchMode
    tasks: Tuple[SearchTask, ...]
    require_fetch: bool
    require_multiple_sources: bool
    notes: str = ""


@dataclass(frozen=True)
class SearchFetchResult:
    url: str
    final_url: str
    status_code: int
    title: str
    extracted_text: str
    snippet: str
    content_type: str
    published_at: Optional[str]
    fetched_at: str
    provider_name: str
    source_type: str
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    provider_name: str
    source_type: str
    published_at: Optional[str] = None
    fetched_at: Optional[str] = None
    domain: str = ""
    relevance_score: float = 0.0
    freshness_score: float = 0.0
    reliability_score: float = 0.0
    duplication_score: float = 0.0
    final_rank_score: float = 0.0
    cache_hit: bool = False
    extracted_text: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceItem:
    title: str
    url: str
    publisher: str
    snippet: str
    extracted_text: str
    published_at: Optional[str]
    fetched_at: Optional[str]
    reliability_score: float
    freshness_score: float
    relevance_score: float
    source_type: str
    provider_name: str
    cache_metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceBundle:
    query: str
    items: Tuple[EvidenceItem, ...]
    conflicts: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Citation:
    index: int
    title: str
    url: str
    publisher: str
    label: str


@dataclass(frozen=True)
class SearchDiagnostics:
    providers_attempted: Tuple[str, ...]
    providers_succeeded: Tuple[str, ...]
    cache_hits: int
    degraded: bool
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchResponse:
    answer: str
    summary: str
    citations: Tuple[Citation, ...]
    evidence_bundle: EvidenceBundle
    diagnostics: SearchDiagnostics
    mode: ResearchMode
    intent: SearchIntent
    self_check_notes: Tuple[str, ...] = ()
    disclaimer: str = ""

