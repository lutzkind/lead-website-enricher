from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import SearchQuery, SearchResult


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: SearchQuery, *, engine: str, limit: int) -> list[SearchResult]:
        raise NotImplementedError

    @abstractmethod
    def health(self, *, test_query: str, engine: str, limit: int = 1) -> dict:
        raise NotImplementedError
