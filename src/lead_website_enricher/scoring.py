from __future__ import annotations

from collections import defaultdict

from .models import CandidateScore, CanonicalLead, SearchResult
from .text import extract_domain, normalize_phone, normalize_text, tokenize


DIRECTORY_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tripadvisor.com",
    "yellowpages.com",
    "yelp.com",
    "foursquare.com",
    "mapquest.com",
    "localsearch.com",
}


def score_candidates(lead: CanonicalLead, results: list[SearchResult]) -> list[CandidateScore]:
    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    for result in results:
        domain = extract_domain(result.url)
        if domain:
            grouped[domain].append(result)

    candidates: list[CandidateScore] = []
    for domain, grouped_results in grouped.items():
        best = max(grouped_results, key=lambda row: _score_single_result(lead, row)[0])
        score, reasons = _score_single_result(lead, best)
        if domain in DIRECTORY_DOMAINS:
            score -= 35
            reasons.append("directory-domain-penalty")
        confidence = confidence_for_score(score)
        candidates.append(
            CandidateScore(
                url=best.url,
                domain=domain,
                score=score,
                confidence=confidence,
                reasons=reasons,
                result=best,
            )
        )

    candidates.sort(key=lambda candidate: (-candidate.score, candidate.domain))
    return candidates


def confidence_for_score(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _score_single_result(lead: CanonicalLead, result: SearchResult) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    searchable_text = " ".join([result.title, result.snippet, result.url])
    normalized_searchable = normalize_text(searchable_text)

    lead_tokens = tokenize(lead.name)
    matched_tokens = [token for token in lead_tokens if token in normalized_searchable]
    if lead_tokens:
        coverage = len(matched_tokens) / len(lead_tokens)
        if coverage == 1:
            score += 50
            reasons.append("exact-name-token-coverage")
        elif coverage >= 0.75:
            score += 35
            reasons.append("strong-name-token-coverage")
        elif coverage >= 0.5:
            score += 20
            reasons.append("partial-name-token-coverage")

    domain = extract_domain(result.url)
    domain_tokens = tokenize(domain)
    if lead_tokens and domain_tokens:
        domain_coverage = len([token for token in lead_tokens if token in domain_tokens]) / len(lead_tokens)
        if domain_coverage == 1:
            score += 15
            reasons.append("exact-domain-token-coverage")
        elif domain_coverage >= 0.5:
            score += 8
            reasons.append("partial-domain-token-coverage")

    compact_name = normalize_text(lead.name).replace(" ", "")
    compact_domain = domain.replace(".", "").replace("-", "")
    if compact_name and compact_name in compact_domain:
        score += 12
        reasons.append("compact-domain-name-match")

    if lead.category and normalize_text(lead.category) in normalized_searchable:
        score += 10
        reasons.append("category-match")
    elif lead.industry and normalize_text(lead.industry) in normalized_searchable:
        score += 10
        reasons.append("industry-match")

    for location_value, label in (
        (lead.city, "city-match"),
        (lead.state_region, "state-match"),
        (lead.country, "country-match"),
    ):
        normalized_location = normalize_text(location_value)
        if normalized_location and normalized_location in normalized_searchable:
            score += 8
            reasons.append(label)

    lead_phone = normalize_phone(lead.phone)
    if lead_phone and lead_phone in normalize_phone(searchable_text):
        score += 25
        reasons.append("phone-match")

    if result.position and result.position <= 3:
        score += 5
        reasons.append("top-serp-position")

    return score, reasons
