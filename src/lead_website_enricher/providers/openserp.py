from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..models import SearchQuery, SearchResult
from .base import SearchProvider


class OpenSerpProvider(SearchProvider):
    ENGINE_ALIASES = {
        "duckduckgo": "duck",
    }

    def __init__(self, base_url: str | None = None, timeout_seconds: int = 6):
        self.base_url = (base_url or os.environ.get("OPENSERP_BASE_URL") or "http://127.0.0.1:7000").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, query: SearchQuery, *, engines: list[str], limit: int) -> list[SearchResult]:
        if not engines:
            engines = ["bing"]

        results: list[SearchResult] = []
        for engine in engines:
            resolved_engine = self.ENGINE_ALIASES.get(engine, engine)
            url = f"{self.base_url}/{quote(resolved_engine)}/search?text={quote(query.value)}&limit={limit}"
            req = Request(url, headers={"Accept": "application/json", "User-Agent": "lead-website-enricher/0.1.0"})
            try:
                with urlopen(req, timeout=self.timeout_seconds) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError):
                continue

            engine_results = payload.get("results") or []
            for row in engine_results:
                position = row.get("position")
                if isinstance(position, dict):
                    position = position.get("absolute") or position.get("page") or position.get("rank")
                if not isinstance(position, int):
                    rank = row.get("rank")
                    position = rank if isinstance(rank, int) else None
                results.append(
                    SearchResult(
                        provider="openserp",
                        engine=resolved_engine,
                        url=row.get("url") or row.get("link") or "",
                        title=row.get("title") or "",
                        snippet=row.get("description") or row.get("snippet") or "",
                        position=position,
                    )
                )
        return results
