from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Protocol, Sequence

from search.search_models import ProviderCapability, SearchFetchResult, SearchQuery, SearchResult


class SearchProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def capabilities(self) -> Sequence[ProviderCapability]: ...

    def search(self, query: SearchQuery, *, limit: int = 5) -> Sequence[SearchResult]: ...

    def fetch(self, result: SearchResult) -> Optional[SearchFetchResult]: ...

    def reliability_score(self, result: SearchResult) -> float: ...

    def freshness_score(self, result: SearchResult, *, max_age_seconds: int) -> float: ...


@dataclass
class ProviderRegistry:
    providers: Dict[str, SearchProvider] = field(default_factory=dict)

    def register(self, provider: SearchProvider) -> None:
        self.providers[provider.name] = provider

    def available(self, capability: ProviderCapability | None = None) -> List[SearchProvider]:
        items = [provider for provider in self.providers.values() if provider.is_available()]
        if capability is None:
            return items
        return [provider for provider in items if capability in provider.capabilities()]

    def get(self, name: str) -> Optional[SearchProvider]:
        return self.providers.get(name)

    def pick(self, capability: ProviderCapability) -> List[SearchProvider]:
        return self.available(capability)

