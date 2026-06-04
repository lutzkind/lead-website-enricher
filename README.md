# Lead Website Enricher

Standalone website discovery engine for scraper leads that do not have a `website`.

This repo is intentionally independent from Windmill. The core logic lives here so it can be:

- tested locally with fixtures
- run from a CLI
- called later from Windmill as a thin wrapper
- extended with new search providers and source adapters without turning Windmill scripts into a codebase

## What It Does

1. Normalizes source-specific lead rows into one canonical model
2. Builds website-discovery queries from available fields
3. Calls a search provider such as `OpenSERP`
4. Scores returned candidate URLs using lead-aware heuristics
5. Produces structured enrichment results with confidence, evidence, and audit stats

This repo does not use `crawl4ai` in the current discovery stage. It scores search results from titles, snippets, and URLs only.

## HTTP API

The repo also exposes a small HTTP API for deployment behind Coolify.

Endpoints:

- `GET /health`
- `POST /queries`
- `POST /enrich`

Example:

```bash
curl -X POST http://127.0.0.1:8000/enrich \
  -H 'content-type: application/json' \
  -d '{
    "rows": [{"source": "yellowpages", "Id": "1", "name": "Acme Landscaping", "country": "US"}],
    "provider": "openserp",
    "engines": ["bing", "duckduckgo"]
  }'
```

## Current Source Adapters

- `gmaps`
- `yellowpages`
- `osm`
- `foursquare`

## Current Providers

- `openserp`
- `fixture` for deterministic local testing

## Quick Start

```bash
cd /root/lead-website-enricher
python3 -m unittest discover -s tests
```

Create an input file containing raw lead rows:

```json
[
  {
    "source": "yellowpages",
    "Id": "123",
    "name": "Acme Landscaping",
    "phone": "(512) 555-0100",
    "address": "123 Main St, Austin, TX 78701",
    "city": "Austin",
    "state_region": "TX",
    "postcode": "78701",
    "country": "US",
    "category": "Landscaping"
  }
]
```

Run in fixture mode:

```bash
python3 -m lead_website_enricher.cli enrich-file \
  --input examples/sample-leads.json \
  --provider fixture \
  --fixture-file examples/sample-fixture-results.json \
  --output /tmp/lead-website-results.json
```

Run against OpenSERP:

```bash
export OPENSERP_BASE_URL=http://127.0.0.1:7000

python3 -m lead_website_enricher.cli enrich-file \
  --input examples/sample-leads.json \
  --provider openserp \
  --engine bing \
  --engine duckduckgo \
  --output /tmp/lead-website-results.json
```

## CLI Commands

```bash
lead-website-enricher enrich-file --input leads.json --provider openserp
lead-website-enricher print-queries --input leads.json
```

Run the HTTP API locally:

```bash
PYTHONPATH=src python3 -m lead_website_enricher.api
```

## Output Shape

Each lead result includes:

- normalized lead payload
- generated queries
- candidate domains
- winning candidate
- confidence
- match reason
- audit stats

## Recommended Next Step

Use this repo as the core engine and later wrap it in:

- one Windmill batch script
- one Windmill flow for scheduling and retries

## License

MIT
