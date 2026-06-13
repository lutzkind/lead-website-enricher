from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .engine import enrich_rows, summarize_results
from .providers.fixture import FixtureSearchProvider
from .providers.openserp import OpenSerpProvider
from .runtime import RUNTIME
from .adapters import normalize_lead_row
from .queries import build_queries


def _create_provider(payload: dict):
    provider_name = str(payload.get("provider") or "openserp").strip().lower()
    if provider_name == "fixture":
        fixture_file = payload.get("fixture_file")
        if not fixture_file:
            raise ValueError("fixture_file is required when provider=fixture")
        return FixtureSearchProvider(fixture_file)
    if provider_name == "openserp":
        return OpenSerpProvider(
            base_url=payload.get("openserp_base_url"),
            timeout_seconds=int(payload.get("openserp_timeout_seconds") or os.environ.get("LEAD_WEBSITE_ENRICHER_OPENSERP_TIMEOUT_SECONDS", "12")),
        )
    raise ValueError(f"Unsupported provider: {provider_name}")


class Handler(BaseHTTPRequestHandler):
    server_version = "lead-website-enricher/0.1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "lead-website-enricher",
                    "cache_size": RUNTIME.snapshot().cache_size,
                },
            )
            return
        if parsed.path == "/ready":
            self._handle_ready()
            return
        if parsed.path == "/diagnostics":
            self._handle_diagnostics(parse_qs(parsed.query))
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length)
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body"})
            return

        if self.path == "/queries":
            self._handle_queries(payload)
            return
        if self.path == "/enrich":
            self._handle_enrich(payload)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def log_message(self, format: str, *args) -> None:
        return

    def _handle_queries(self, payload: dict) -> None:
        rows = payload.get("rows") or []
        source_override = payload.get("source")
        results = []
        for row in rows:
            lead = normalize_lead_row(row, source=source_override)
            results.append(
                {
                    "source_record_id": lead.source_record_id,
                    "name": lead.name,
                    "queries": [query.to_dict() for query in build_queries(lead)],
                }
            )
        self._send_json(HTTPStatus.OK, {"results": results, "count": len(results)})

    def _handle_enrich(self, payload: dict) -> None:
        rows = payload.get("rows") or []
        if not isinstance(rows, list) or not rows:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "rows must be a non-empty array"})
            return

        provider = _create_provider(payload)
        engines = payload.get("engines") or os.environ.get(
            "LEAD_WEBSITE_ENRICHER_ENGINES", "bing,google,duckduckgo,ecosia"
        ).split(",")
        engines = [str(engine).strip() for engine in engines if str(engine).strip()]
        per_query_limit = int(payload.get("per_query_limit") or os.environ.get("LEAD_WEBSITE_ENRICHER_PER_QUERY_LIMIT", "5"))
        per_lead_timeout_seconds = float(
            payload.get("per_lead_timeout_seconds")
            or os.environ.get("LEAD_WEBSITE_ENRICHER_PER_LEAD_TIMEOUT_SECONDS", "20")
        )
        source_override = payload.get("source")

        results = enrich_rows(
            rows,
            provider,
            engines=engines,
            per_query_limit=per_query_limit,
            source_override=source_override,
            per_lead_timeout_seconds=per_lead_timeout_seconds,
        )
        provider_meta = {
            "provider": "fixture" if payload.get("provider") == "fixture" else "openserp",
            "openserp_base_url": getattr(provider, "base_url", None),
            "engines": engines,
            "per_query_limit": per_query_limit,
            "per_lead_timeout_seconds": per_lead_timeout_seconds,
            "openserp_timeout_seconds": getattr(provider, "timeout_seconds", None),
        }
        self._send_json(HTTPStatus.OK, summarize_results(results, provider_meta=provider_meta))

    def _handle_ready(self) -> None:
        provider = OpenSerpProvider(
            timeout_seconds=int(os.environ.get("LEAD_WEBSITE_ENRICHER_READY_TIMEOUT_SECONDS", "3"))
        )
        try:
            provider_ready = provider.ready()
        except Exception as exc:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "ok": False,
                    "service": "lead-website-enricher",
                    "provider": "openserp",
                    "base_url": provider.base_url,
                    "error": str(exc),
                },
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "service": "lead-website-enricher",
                "provider": "openserp",
                "base_url": provider.base_url,
                "provider_ready": provider_ready,
                "engine_status_summary": RUNTIME.snapshot().engines,
            },
        )

    def _handle_diagnostics(self, query: dict[str, list[str]]) -> None:
        provider = OpenSerpProvider(
            timeout_seconds=int(os.environ.get("LEAD_WEBSITE_ENRICHER_DIAGNOSTICS_TIMEOUT_SECONDS", "5"))
        )
        engines = (query.get("engine") or [os.environ.get("LEAD_WEBSITE_ENRICHER_HEALTH_ENGINES", "bing,google,duckduckgo")])[0]
        engine_candidates = [item.strip() for item in engines.split(",") if item.strip()]
        test_query = (query.get("test_query") or [os.environ.get("LEAD_WEBSITE_ENRICHER_HEALTH_QUERY", "starbucks seattle")])[0]
        errors = []
        provider_health = None
        engine_results = []
        for engine in engine_candidates:
            try:
                result = provider.health(test_query=test_query, engine=engine, limit=1)
                provider_health = result.get("health")
                engine_results.append(result)
            except Exception as exc:
                errors.append({"engine": engine, "error": str(exc)})
        if not engine_results:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "ok": False,
                    "service": "lead-website-enricher",
                    "provider": "openserp",
                    "base_url": provider.base_url,
                    "errors": errors,
                    "engine_status_summary": RUNTIME.snapshot().engines,
                },
            )
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "service": "lead-website-enricher",
                "provider": "openserp",
                "base_url": provider.base_url,
                "engines_attempted": engine_candidates,
                "provider_health": provider_health,
                "engine_results": engine_results,
                "engine_status_summary": RUNTIME.snapshot().engines,
                "errors": errors,
            },
        )

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"lead-website-enricher listening on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
