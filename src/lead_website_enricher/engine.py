from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .adapters import normalize_lead_row
from .models import EnrichmentResult
from .providers.base import SearchProvider
from .queries import build_queries
from .scoring import score_candidates


def enrich_rows(
    rows: list[dict[str, Any]],
    provider: SearchProvider,
    *,
    engines: list[str],
    per_query_limit: int = 5,
    source_override: str | None = None,
) -> list[EnrichmentResult]:
    results: list[EnrichmentResult] = []
    for row in rows:
        lead = normalize_lead_row(row, source=source_override)
        queries = build_queries(lead)
        search_results = []
        for query in queries:
            search_results.extend(provider.search(query, engines=engines, limit=per_query_limit))
        candidates = score_candidates(lead, search_results)
        winner = candidates[0] if candidates else None
        stats = {
            "query_count": len(queries),
            "search_result_count": len(search_results),
            "candidate_domain_count": len(candidates),
            "winner_confidence": winner.confidence if winner else None,
            "winner_score": winner.score if winner else None,
        }
        results.append(
            EnrichmentResult(
                lead=lead,
                queries=queries,
                candidates=candidates,
                winner=winner,
                stats=stats,
            )
        )
    return results


def summarize_results(results: list[EnrichmentResult]) -> dict[str, Any]:
    confidence_counts = {"high": 0, "medium": 0, "low": 0, "none": 0}
    for result in results:
        if result.winner is None:
            confidence_counts["none"] += 1
        else:
            confidence_counts[result.winner.confidence] = confidence_counts.get(result.winner.confidence, 0) + 1

    return {
        "processed_count": len(results),
        "matched_count": sum(1 for result in results if result.winner is not None),
        "high_confidence_count": confidence_counts["high"],
        "medium_confidence_count": confidence_counts["medium"],
        "low_confidence_count": confidence_counts["low"],
        "unmatched_count": confidence_counts["none"],
        "results": [result.to_dict() for result in results],
    }
