from __future__ import annotations

import time
from typing import Any

from .adapters import normalize_lead_row
from .models import EnrichmentResult
from .providers.base import SearchProvider
from .queries import build_queries
from .scoring import score_candidates
from .lead_quality import cache_key_for_lead, weak_lead_reason
from .runtime import RUNTIME
from .validation import fetch_page, validate_candidate


DEFAULT_HIGH_CONFIDENCE = "high"


def enrich_rows(
    rows: list[dict[str, Any]],
    provider: SearchProvider,
    *,
    engines: list[str],
    per_query_limit: int = 5,
    source_override: str | None = None,
    per_lead_timeout_seconds: float = 20.0,
    page_fetcher=None,
) -> list[EnrichmentResult]:
    results: list[EnrichmentResult] = []
    requested_engines = [str(engine).strip() for engine in engines if str(engine).strip()]
    engine_order = requested_engines[:]
    if not engine_order:
        engine_order = ["bing", "google", "duckduckgo", "ecosia"]

    for row in rows:
        lead = normalize_lead_row(row, source=source_override)
        cache_key = cache_key_for_lead(lead)
        cached = RUNTIME.get_cached(cache_key)
        if cached is not None:
            results.append(
                EnrichmentResult(
                    lead=lead,
                    queries=[],
                    candidates=[],
                    winner=None,
                    stats={**cached, "cache_hit": True},
                )
            )
            continue

        skip_reason = weak_lead_reason(lead)
        if skip_reason:
            stats = {
                "query_count": 0,
                "queries_attempted": [],
                "engines_considered": [],
                "engines_skipped": [],
                "engines_attempted": [],
                "search_result_count": 0,
                "candidate_domain_count": 0,
                "winner_confidence": None,
                "winner_score": None,
                "winner_domain": None,
                "winner_reasons": [],
                "blocked_candidates": [],
                "early_stop": False,
                "errors": [],
                "elapsed_seconds": 0.0,
                "skip_reason": skip_reason,
                "writable": False,
            }
            RUNTIME.put_cached(cache_key, stats, ttl_seconds=86400)
            results.append(EnrichmentResult(lead=lead, queries=[], candidates=[], winner=None, stats=stats))
            continue

        queries = build_queries(lead)
        search_results = []
        query_attempts: list[dict[str, Any]] = []
        engine_attempts: list[dict[str, Any]] = []
        blocked_candidates: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        early_stop = False
        winner = None
        candidates = []
        lead_started_at = time.monotonic()
        engines_considered, engines_skipped = RUNTIME.engine_plan(engine_order)

        for query in queries:
            if time.monotonic() - lead_started_at >= per_lead_timeout_seconds:
                errors.append({"type": "timeout", "message": "per-lead-timeout-exceeded"})
                break

            query_attempts.append(query.to_dict())
            useful_results_from_query = False
            for engine in engines_considered:
                if time.monotonic() - lead_started_at >= per_lead_timeout_seconds:
                    errors.append({"type": "timeout", "message": "per-lead-timeout-exceeded"})
                    break

                attempt_started_at = time.monotonic()
                try:
                    attempt_results = provider.search(query, engine=engine, limit=per_query_limit)
                    search_results.extend(attempt_results)
                    elapsed_seconds = round(time.monotonic() - attempt_started_at, 3)
                    RUNTIME.record_success(engine, elapsed_seconds=elapsed_seconds, result_count=len(attempt_results))
                    engine_attempts.append(
                        {
                            "query": query.value,
                            "strategy": query.strategy,
                            "engine": engine,
                            "result_count": len(attempt_results),
                            "elapsed_seconds": elapsed_seconds,
                        }
                    )
                except Exception as exc:  # pragma: no cover - exercised in integration.
                    elapsed_seconds = round(time.monotonic() - attempt_started_at, 3)
                    error_kind = RUNTIME.record_failure(engine, elapsed_seconds=elapsed_seconds, message=str(exc))
                    errors.append(
                        {
                            "query": query.value,
                            "strategy": query.strategy,
                            "engine": engine,
                            "error_kind": error_kind,
                            "message": str(exc),
                        }
                    )
                    engine_attempts.append(
                        {
                            "query": query.value,
                            "strategy": query.strategy,
                            "engine": engine,
                            "result_count": 0,
                            "elapsed_seconds": elapsed_seconds,
                            "error": str(exc),
                        }
                    )
                    continue

                candidates = score_candidates(lead, search_results)
                winner = candidates[0] if candidates else None
                for candidate in candidates[:3]:
                    validation = validate_candidate(
                        lead,
                        candidate,
                        page_fetcher=page_fetcher or fetch_page,
                    )
                    if validation.get("accepted") and candidate.confidence == DEFAULT_HIGH_CONFIDENCE:
                        winner = candidate
                        winner.url = validation.get("canonical_url") or candidate.url
                        winner.domain = validation.get("canonical_domain") or candidate.domain
                        winner.reasons = list(dict.fromkeys(candidate.reasons + (validation.get("reasons") or [])))
                        early_stop = True
                        break
                    blocked_reason = validation.get("blocked_reason")
                    if blocked_reason:
                        blocked_candidates.append(
                            {
                                "domain": candidate.domain,
                                "url": candidate.url,
                                "reason": blocked_reason,
                                "confidence": candidate.confidence,
                            }
                        )
                top_candidate = candidates[0] if candidates else None
                if top_candidate and top_candidate.score >= 70:
                    useful_results_from_query = True
                if winner and winner.confidence == DEFAULT_HIGH_CONFIDENCE:
                    break

            if early_stop:
                break
            if useful_results_from_query:
                continue

        stats = {
            "query_count": len(queries),
            "queries_attempted": query_attempts,
            "engines_considered": engines_considered,
            "engines_skipped": engines_skipped,
            "engines_attempted": engine_attempts,
            "search_result_count": len(search_results),
            "candidate_domain_count": len(candidates),
            "winner_confidence": winner.confidence if winner else None,
            "winner_score": winner.score if winner else None,
            "winner_domain": winner.domain if winner else None,
            "winner_reasons": winner.reasons if winner else [],
            "blocked_candidates": blocked_candidates,
            "early_stop": early_stop,
            "errors": errors,
            "elapsed_seconds": round(time.monotonic() - lead_started_at, 3),
            "skip_reason": None,
            "writable": bool(winner and winner.confidence == DEFAULT_HIGH_CONFIDENCE),
        }
        if winner is None and not errors and not blocked_candidates:
            RUNTIME.put_cached(cache_key, stats, ttl_seconds=21600)
        elif stats["skip_reason"]:
            RUNTIME.put_cached(cache_key, stats, ttl_seconds=86400)
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


def summarize_results(results: list[EnrichmentResult], *, provider_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    confidence_counts = {"high": 0, "medium": 0, "low": 0, "none": 0}
    early_stop_count = 0
    search_error_count = 0
    skipped_weak_context_count = 0
    blocked_candidate_count = 0
    engine_attempts: list[dict[str, Any]] = []
    per_lead_elapsed_seconds: dict[str, float] = {}

    for result in results:
        if result.winner is None:
            confidence_counts["none"] += 1
        else:
            confidence_counts[result.winner.confidence] = confidence_counts.get(result.winner.confidence, 0) + 1
        if result.stats.get("early_stop"):
            early_stop_count += 1
        search_error_count += len(result.stats.get("errors") or [])
        if result.stats.get("skip_reason") in {"generic-business-name", "insufficient-identifying-context"}:
            skipped_weak_context_count += 1
        blocked_candidate_count += len(result.stats.get("blocked_candidates") or [])
        engine_attempts.extend(result.stats.get("engines_attempted") or [])
        per_lead_elapsed_seconds[result.lead.source_record_id] = result.stats.get("elapsed_seconds") or 0.0

    payload = {
        "processed_count": len(results),
        "matched_count": sum(1 for result in results if result.winner is not None),
        "high_confidence_count": confidence_counts["high"],
        "medium_review_count": confidence_counts["medium"],
        "low_confidence_count": confidence_counts["low"],
        "unmatched_count": confidence_counts["none"],
        "below_threshold_count": confidence_counts["medium"] + confidence_counts["low"],
        "skipped_weak_context_count": skipped_weak_context_count,
        "blocked_candidate_count": blocked_candidate_count,
        "early_stop_count": early_stop_count,
        "search_error_count": search_error_count,
        "engine_attempts": engine_attempts,
        "per_lead_elapsed_seconds": per_lead_elapsed_seconds,
        "engine_status_summary": RUNTIME.snapshot().engines,
        "results": [result.to_dict() for result in results],
    }
    if provider_meta:
        payload["provider_meta"] = provider_meta
    return payload
