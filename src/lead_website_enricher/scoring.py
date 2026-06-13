from __future__ import annotations

from collections import defaultdict

from .models import CandidateScore, CanonicalLead, SearchResult
from .lead_quality import has_identifying_source_context
from .text import extract_domain, normalize_phone, normalize_text, tokenize


DIRECTORY_DOMAINS = {
    "account.microsoft.com",
    "amazon.com",
    "amazon.co.uk",
    "apple.com",
    "baike.baidu.com",
    "booking.com",
    "britannica.com",
    "dictionary.cambridge.org",
    "facebook.com",
    "forum.elite-it.com",
    "forum.voo.be",
    "instagram.com",
    "imdb.com",
    "linkedin.com",
    "merriam-webster.com",
    "outlook.live.com",
    "pinterest.com",
    "reddit.com",
    "support.microsoft.com",
    "tiktok.com",
    "travelandleisure.com",
    "tripadvisor.com",
    "ubereats.com",
    "wiktionary.org",
    "wikipedia.org",
    "yahoo.com",
    "finance.yahoo.com",
    "tripadvisor.com",
    "youtube.com",
    "yellowpages.com",
    "yelp.com",
    "foursquare.com",
    "mapquest.com",
    "localsearch.com",
    "thetakeout.com",
    "doordash.com",
    "grubhub.com",
    "seamless.com",
    "postmates.com",
    "restaurantguru.com",
    "restaurantji.com",
    "usarestaurants.info",
    "findmeglutenfree.com",
    "allmenus.com",
    "menuism.com",
}
LOW_QUALITY_DOMAINS = {
    "foodeist.com",
    "foodplacee.com",
    "goto-where.com",
    "goto-restaurants.com",
    "hey-restaurants.com",
    "menu-world.com",
    "menustic.com",
    "menufyy.com",
    "placesguru.com",
    "res-menu.net",
    "res-cuisine.com",
    "res-discover.com",
    "restaurants-world.net",
    "restaurants-us.com",
    "weeblyte.com",
    "wheree.com",
    "wherevi.com",
    "maptons.com",
    "eniplaces.com",
    "menu-res.com",
    "gotoeat.net",
    "menu-world.net",
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
        if blocked_domain_reason(domain):
            score -= 100
            reasons.append("blocked-domain")
        confidence = confidence_for_score(lead, domain, score, reasons)
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


def confidence_for_score(lead: CanonicalLead, domain: str, score: int, reasons: list[str]) -> str:
    if blocked_domain_reason(domain):
        return "low"
    if score >= 85 and _has_high_confidence_evidence(lead, reasons):
        return "high"
    if score >= 85:
        return "medium"
    if score >= 70:
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
            score += 55
            reasons.append("exact-name-token-coverage")
        elif coverage >= 0.75:
            score += 38
            reasons.append("strong-name-token-coverage")
        elif coverage >= 0.5:
            score += 20
            reasons.append("partial-name-token-coverage")

    domain = extract_domain(result.url)
    domain_tokens = tokenize(domain)
    if lead_tokens and domain_tokens:
        domain_coverage = len([token for token in lead_tokens if token in domain_tokens]) / len(lead_tokens)
        if domain_coverage == 1:
            score += 24
            reasons.append("exact-domain-token-coverage")
        elif domain_coverage >= 0.5:
            score += 12
            reasons.append("partial-domain-token-coverage")

    compact_name = normalize_text(lead.name).replace(" ", "")
    compact_domain = domain.replace(".", "").replace("-", "")
    if compact_name and compact_name in compact_domain:
        score += 18
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

    normalized_address = normalize_text(lead.address)
    if normalized_address and normalized_address in normalized_searchable:
        score += 25
        reasons.append("address-match")

    lead_phone = normalize_phone(lead.phone)
    if lead_phone and lead_phone in normalize_phone(searchable_text):
        score += 30
        reasons.append("phone-match")

    source_domain = extract_domain(lead.source_url) if has_identifying_source_context(lead) else ""
    if source_domain and domain == source_domain:
        score += 35
        reasons.append("source-url-domain-match")

    if result.title and normalize_text(lead.name) in normalize_text(result.title):
        score += 8
        reasons.append("title-name-match")

    if isinstance(result.position, int) and result.position <= 3:
        score += 5
        reasons.append("top-serp-position")

    return score, reasons


def blocked_domain_reason(domain: str) -> str | None:
    blocked_domains = DIRECTORY_DOMAINS | LOW_QUALITY_DOMAINS
    if domain == "":
        return "empty-domain"
    if domain in blocked_domains or any(domain == blocked or domain.endswith(f".{blocked}") for blocked in blocked_domains):
        return "blocked-domain"
    return None


def _has_high_confidence_evidence(lead: CanonicalLead, reasons: list[str]) -> bool:
    reason_set = set(reasons)
    if {"phone-match", "address-match", "source-url-domain-match"} & reason_set:
        return True

    domain_signals = {
        "exact-domain-token-coverage",
        "partial-domain-token-coverage",
        "compact-domain-name-match",
    }
    corroborating_signals = {
        "title-name-match",
        "city-match",
        "state-match",
        "country-match",
        "category-match",
        "industry-match",
    }
    if reason_set & domain_signals and reason_set & corroborating_signals:
        return True

    return False
