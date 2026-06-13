from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lead_website_enricher.adapters import normalize_lead_row
from lead_website_enricher.engine import enrich_rows, summarize_results
from lead_website_enricher.models import SearchResult
from lead_website_enricher.providers.fixture import FixtureSearchProvider
from lead_website_enricher.queries import build_queries
from lead_website_enricher.runtime import RUNTIME
from lead_website_enricher.scoring import score_candidates


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
        self.assertTrue(any(query.value == '"Acme Landscaping" Austin US Landscaping' for query in queries))
        self.assertTrue(any(query.value == '"Acme Landscaping" Austin US' for query in queries))


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        RUNTIME._engine_stats.clear()
        RUNTIME._lead_cache.clear()

    def test_fixture_provider_finds_high_confidence_domain(self) -> None:
        fixture = FixtureSearchProvider(ROOT / "examples" / "sample-fixture-results.json")
        rows = json.loads((ROOT / "examples" / "sample-leads.json").read_text())
        page_map = {
            "https://acmelandscapingtx.com": {
                "final_url": "https://www.acmelandscapingtx.com/",
                "title": "Acme Landscaping | Austin TX Landscaping Services",
                "text": "Acme Landscaping serves Austin TX. Call 5125550100. 123 Main St Austin TX 78701.",
                "links": ["https://www.acmelandscapingtx.com/contact"],
                "schema_types": {"localbusiness"},
            },
            "https://www.acmelandscapingtx.com/contact": {
                "final_url": "https://www.acmelandscapingtx.com/contact",
                "title": "Contact Acme Landscaping",
                "text": "Acme Landscaping 123 Main St Austin TX 78701 5125550100.",
                "links": [],
                "schema_types": set(),
            },
            "https://blueharborhotel.co.uk": {
                "final_url": "https://www.blueharborhotel.co.uk/",
                "title": "Blue Harbor Hotel | London Boutique Hotel",
                "text": "Blue Harbor Hotel London Boutique Hotel. 7 Harbor Road London E1 6AN. +44 20 7946 0958.",
                "links": ["https://www.blueharborhotel.co.uk/contact"],
                "schema_types": {"lodgingbusiness"},
            },
            "https://www.blueharborhotel.co.uk/contact": {
                "final_url": "https://www.blueharborhotel.co.uk/contact",
                "title": "Contact Us | Blue Harbor Hotel",
                "text": "Blue Harbor Hotel 7 Harbor Road London E1 6AN +44 20 7946 0958.",
                "links": [],
                "schema_types": set(),
            },
        }

        def fake_page_fetcher(url: str, *, timeout_seconds: float = 4.0):
            payload = page_map.get(url)
            if payload is None:
                return None
            from lead_website_enricher.validation import PageData

            return PageData(
                url=url,
                final_url=payload["final_url"],
                title=payload["title"],
                text=payload["text"],
                links=payload["links"],
                schema_types=payload["schema_types"],
            )

        results = enrich_rows(rows, fixture, engines=["bing", "duckduckgo"], page_fetcher=fake_page_fetcher)
        summary = summarize_results(results, provider_meta={"provider": "fixture"})

        self.assertEqual(summary["processed_count"], 2)
        self.assertEqual(summary["high_confidence_count"], 2)
        self.assertEqual(summary["early_stop_count"], 2)
        self.assertEqual(results[0].winner.domain, "acmelandscapingtx.com")
        self.assertEqual(results[1].winner.domain, "blueharborhotel.co.uk")
        self.assertTrue(results[0].stats["early_stop"])
        self.assertEqual(results[0].stats["engines_attempted"][0]["engine"], "bing")

    def test_generic_content_domain_is_not_high_confidence(self) -> None:
        lead = normalize_lead_row(
            {
                "source": "osm",
                "Id": "630",
                "name": "Chinese Restaurant",
                "country": "United States",
                "category": "restaurant",
                "subcategory": "asian",
            }
        )
        candidates = score_candidates(
            lead,
            [
                SearchResult(
                    provider="fixture",
                    engine="bing",
                    url="https://www.thetakeout.com/2086300/best-chinese-restaurants-in-the-us-cuisine/",
                    title="The 13 Best Chinese Restaurants In The US",
                    snippet="A list of the best Chinese restaurants in the United States.",
                    position=1,
                )
            ],
        )

        self.assertEqual(candidates[0].domain, "thetakeout.com")
        self.assertEqual(candidates[0].confidence, "low")

    def test_domain_and_title_signals_can_still_be_high_confidence(self) -> None:
        lead = normalize_lead_row(
            {
                "source": "osm",
                "Id": "627",
                "name": "Harbor View",
                "country": "United States",
                "category": "restaurant",
            }
        )
        candidates = score_candidates(
            lead,
            [
                SearchResult(
                    provider="fixture",
                    engine="bing",
                    url="https://www.harborviewpepin.com/contact/",
                    title="Contact Us - Harbor View Cafe",
                    snippet="Harbor View Cafe. Contact. 314 First Street Pepin, WI 54759.",
                    position=1,
                )
            ],
        )

        self.assertEqual(candidates[0].domain, "harborviewpepin.com")
        self.assertEqual(candidates[0].confidence, "high")

    def test_generic_weak_lead_is_skipped_before_search(self) -> None:
        fixture = FixtureSearchProvider(ROOT / "examples" / "sample-fixture-results.json")
        rows = [
            {
                "source": "osm",
                "Id": "999",
                "name": "Chinese Restaurant",
                "country": "United States",
                "category": "restaurant",
            }
        ]
        results = enrich_rows(rows, fixture, engines=["bing"])
        self.assertIsNone(results[0].winner)
        self.assertEqual(results[0].stats["skip_reason"], "generic-business-name")

    def test_non_generic_but_contextless_lead_is_skipped(self) -> None:
        fixture = FixtureSearchProvider(ROOT / "examples" / "sample-fixture-results.json")
        rows = [
            {
                "source": "osm",
                "Id": "625",
                "name": "Bay 5",
                "country": "United States",
                "category": "restaurant",
                "subcategory": "mexican",
                "osm_url": "https://www.openstreetmap.org/node/4840740377",
            }
        ]
        results = enrich_rows(rows, fixture, engines=["bing"])
        self.assertIsNone(results[0].winner)
        self.assertEqual(results[0].stats["skip_reason"], "insufficient-identifying-context")

    def test_health_summary_uses_medium_review_count(self) -> None:
        fixture = FixtureSearchProvider(ROOT / "examples" / "sample-fixture-results.json")
        rows = [
            {
                "source": "yellowpages",
                "Id": "42",
                "name": "Acme Landscaping",
                "city": "Austin",
                "country": "US",
            }
        ]
        results = enrich_rows(rows, fixture, engines=["bing"], page_fetcher=lambda url, timeout_seconds=4.0: None)
        summary = summarize_results(results)
        self.assertIn("medium_review_count", summary)


if __name__ == "__main__":
    unittest.main()
