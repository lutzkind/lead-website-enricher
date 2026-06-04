from __future__ import annotations

import json
from pathlib import Path

from ..models import SearchQuery, SearchResult
from .base import SearchProvider


class FixtureSearchProvider(SearchProvider):
    def __init__(self, fixture_file: str | Path):
        self.fixture_file = Path(fixture_file)
        payload = json.loads(self.fixture_file.read_text())
        self.data = payload

    def search(self, query: SearchQuery, *, engines: list[str], limit: int) -> list[SearchResult]:
        rows = self.data.get(query.value, [])
        results: list[SearchResult] = []
        for row in rows[:limit]:
            results.append(
                SearchResult(
                    provider="fixture",
                    engine=row.get("engine") or (engines[0] if engines else "fixture"),
                    url=row["url"],
                    title=row.get("title", ""),
                    snippet=row.get("snippet", ""),
                    position=row.get("position"),
                )
            )
        return results
