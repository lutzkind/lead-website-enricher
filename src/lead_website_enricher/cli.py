from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import enrich_rows, summarize_results
from .io import dump_json, load_rows
from .providers.fixture import FixtureSearchProvider
from .providers.openserp import OpenSerpProvider
from .queries import build_queries
from .adapters import normalize_lead_row


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lead-website-enricher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    enrich = subparsers.add_parser("enrich-file", help="Enrich a file of raw lead rows.")
    enrich.add_argument("--input", required=True, help="JSON, JSONL, or CSV file of raw lead rows.")
    enrich.add_argument("--output", required=True, help="Where to write the JSON result.")
    enrich.add_argument("--source", help="Override source for all rows in the file.")
    enrich.add_argument("--provider", choices=["openserp", "fixture"], default="openserp")
    enrich.add_argument("--fixture-file", help="Fixture result file, required for fixture provider.")
    enrich.add_argument("--engine", action="append", default=[], help="Search engine to query. Repeatable.")
    enrich.add_argument("--per-query-limit", type=int, default=5)
    enrich.add_argument("--per-lead-timeout-seconds", type=float, default=20.0)

    query = subparsers.add_parser("print-queries", help="Print generated queries for each lead.")
    query.add_argument("--input", required=True, help="JSON, JSONL, or CSV file of raw lead rows.")
    query.add_argument("--source", help="Override source for all rows in the file.")

    return parser


def create_provider(args: argparse.Namespace):
    if args.provider == "fixture":
        if not args.fixture_file:
            raise SystemExit("--fixture-file is required when --provider fixture is used.")
        return FixtureSearchProvider(args.fixture_file)
    return OpenSerpProvider()


def command_enrich_file(args: argparse.Namespace) -> int:
    rows = load_rows(args.input)
    provider = create_provider(args)
    results = enrich_rows(
        rows,
        provider,
        engines=args.engine,
        per_query_limit=args.per_query_limit,
        source_override=args.source,
        per_lead_timeout_seconds=args.per_lead_timeout_seconds,
    )
    payload = summarize_results(
        results,
        provider_meta={
            "provider": args.provider,
            "openserp_base_url": getattr(provider, "base_url", None),
            "engines": args.engine,
            "per_query_limit": args.per_query_limit,
            "per_lead_timeout_seconds": args.per_lead_timeout_seconds,
        },
    )
    dump_json(args.output, payload)
    print(json.dumps({k: v for k, v in payload.items() if k != "results"}, indent=2, sort_keys=True))
    return 0


def command_print_queries(args: argparse.Namespace) -> int:
    rows = load_rows(args.input)
    payload = []
    for row in rows:
        lead = normalize_lead_row(row, source=args.source)
        payload.append(
            {
                "source_record_id": lead.source_record_id,
                "name": lead.name,
                "queries": [query.to_dict() for query in build_queries(lead)],
            }
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "enrich-file":
        return command_enrich_file(args)
    if args.command == "print-queries":
        return command_print_queries(args)
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
