from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .engine import enrich_rows, summarize_results
from .providers.fixture import FixtureSearchProvider
from .providers.openserp import OpenSerpProvider
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
        return OpenSerpProvider(base_url=payload.get("openserp_base_url"))
    raise ValueError(f"Unsupported provider: {provider_name}")


class Handler(BaseHTTPRequestHandler):
    server_version = "lead-website-enricher/0.1.0"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "service": "lead-website-enricher"})
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
        engines = payload.get("engines") or os.environ.get("LEAD_WEBSITE_ENRICHER_ENGINES", "duck,ecosia,bing").split(",")
        engines = [str(engine).strip() for engine in engines if str(engine).strip()]
        per_query_limit = int(payload.get("per_query_limit") or os.environ.get("LEAD_WEBSITE_ENRICHER_PER_QUERY_LIMIT", "5"))
        source_override = payload.get("source")

        results = enrich_rows(
            rows,
            provider,
            engines=engines,
            per_query_limit=per_query_limit,
            source_override=source_override,
        )
        self._send_json(HTTPStatus.OK, summarize_results(results))

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
