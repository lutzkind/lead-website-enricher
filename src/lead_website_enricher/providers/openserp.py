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

    def __init__(self, base_url: str | None = None, timeout_seconds: int = 12):
        self.base_url = (base_url or os.environ.get("OPENSERP_BASE_URL") or "http://127.0.0.1:7000").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, query: SearchQuery, *, engine: str, limit: int) -> list[SearchResult]:
        resolved_engine = self.ENGINE_ALIASES.get(engine, engine)
        payload = self._request_json(
            f"{self.base_url}/{quote(resolved_engine)}/search?text={quote(query.value)}&limit={limit}"
        )
        results: list[SearchResult] = []
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

    def liveness(self) -> dict:
        return self._request_json(f"{self.base_url}/health")

    def ready(self) -> dict:
        return {
            "ok": True,
            "provider": "openserp",
            "base_url": self.base_url,
            "health": self._request_json(f"{self.base_url}/health"),
        }

    def unavailable_engines(self) -> dict[str, str]:
        payload = self._request_json(f"{self.base_url}/health")
        unavailable: dict[str, str] = {}
        for row in payload.get("engines") or []:
            name = str(row.get("name") or "").strip()
            status = str(row.get("status") or "").strip()
            if name and status and status != "ready":
                unavailable[name] = status
                if name == "duckduckgo":
                    unavailable["duck"] = status
        return unavailable

    def health(self, *, test_query: str, engine: str, limit: int = 1) -> dict:
        resolved_engine = self.ENGINE_ALIASES.get(engine, engine)
        health_payload = self._request_json(f"{self.base_url}/health")
        search_payload = self._request_json(
            f"{self.base_url}/{quote(resolved_engine)}/search?text={quote(test_query)}&limit={limit}"
        )
        return {
            "ok": True,
            "provider": "openserp",
            "base_url": self.base_url,
            "engine": resolved_engine,
            "health": health_payload,
            "test_query": test_query,
            "test_result_count": len(search_payload.get("results") or []),
        }

    def _request_json(self, url: str) -> dict:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "lead-website-enricher/0.1.0"})
        try:
            with urlopen(req, timeout=self.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenSERP HTTP {exc.code} for {url}: {payload}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"OpenSERP request failed for {url}: {exc}") from exc
