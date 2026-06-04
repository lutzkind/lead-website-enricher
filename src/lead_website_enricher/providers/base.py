from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import SearchQuery, SearchResult


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: SearchQuery, *, engines: list[str], limit: int) -> list[SearchResult]:
        raise NotImplementedError
