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

    def search(self, query: SearchQuery, *, engine: str, limit: int) -> list[SearchResult]:
        rows = self.data.get(query.value, [])
        results: list[SearchResult] = []
        for row in rows[:limit]:
            results.append(
                SearchResult(
                    provider="fixture",
                    engine=row.get("engine") or engine,
                    url=row["url"],
                    title=row.get("title", ""),
                    snippet=row.get("snippet", ""),
                    position=row.get("position"),
                )
            )
        return results

    def health(self, *, test_query: str, engine: str, limit: int = 1) -> dict:
        return {
            "ok": True,
            "provider": "fixture",
            "engine": engine,
            "test_query": test_query,
            "result_count": len(self.data.get(test_query, [])[:limit]),
        }
