from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lead_website_enricher.adapters import normalize_lead_row
from lead_website_enricher.engine import enrich_rows, summarize_results
from lead_website_enricher.providers.fixture import FixtureSearchProvider
from lead_website_enricher.queries import build_queries


ROOT = Path(__file__).resolve().parent.parent


class AdapterTests(unittest.TestCase):
    def test_normalizes_yellowpages_row(self) -> None:
        row = {
            "source": "yellowpages",
            "Id": "42",
            "name": "Acme Landscaping",
            "phone": "123",
            "country": "US",
            "category": "Landscaping",
        }
        lead = normalize_lead_row(row)
        self.assertEqual(lead.source, "yellowpages")
        self.assertEqual(lead.source_record_id, "42")
        self.assertEqual(lead.name, "Acme Landscaping")
        self.assertEqual(lead.country, "US")

    def test_builds_queries_from_available_fields(self) -> None:
        lead = normalize_lead_row(
            {
                "source": "yellowpages",
                "Id": "42",
                "name": "Acme Landscaping",
                "city": "Austin",
                "country": "US",
                "category": "Landscaping",
            }
        )
        queries = build_queries(lead)
        self.assertTrue(any(query.value == "Acme Landscaping US" for query in queries))
        self.assertTrue(any(query.value == "Acme Landscaping Austin US" for query in queries))


class EngineTests(unittest.TestCase):
    def test_fixture_provider_finds_high_confidence_domain(self) -> None:
        fixture = FixtureSearchProvider(ROOT / "examples" / "sample-fixture-results.json")
        rows = json.loads((ROOT / "examples" / "sample-leads.json").read_text())
        results = enrich_rows(rows, fixture, engines=["bing", "duckduckgo"])
        summary = summarize_results(results)

        self.assertEqual(summary["processed_count"], 2)
        self.assertEqual(summary["high_confidence_count"], 2)
        self.assertEqual(results[0].winner.domain, "acmelandscapingtx.com")
        self.assertEqual(results[1].winner.domain, "blueharborhotel.co.uk")


if __name__ == "__main__":
    unittest.main()
