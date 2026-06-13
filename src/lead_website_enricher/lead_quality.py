from __future__ import annotations

from .models import CanonicalLead
from .text import clean_string, extract_domain, normalize_phone, tokenize


GENERIC_BUSINESS_TOKENS = {
    "american",
    "bar",
    "bbq",
    "bistro",
    "cafe",
    "cuisine",
    "chinese",
    "coffee",
    "deli",
    "food",
    "grill",
    "hotel",
    "inn",
    "kitchen",
    "market",
    "mexican",
    "pizzeria",
    "restaurant",
    "saloon",
    "shop",
    "steakhouse",
    "store",
    "sushi",
    "tavern",
}


def is_generic_business_name(name: str) -> bool:
    tokens = tokenize(name)
    if not tokens:
        return True
    meaningful = [token for token in tokens if token not in GENERIC_BUSINESS_TOKENS]
    if meaningful:
        return False
    return True


def lead_context_score(lead: CanonicalLead) -> int:
    score = 0
    if clean_string(lead.address):
        score += 3
    if normalize_phone(lead.phone):
        score += 3
    if clean_string(lead.city):
        score += 2
    if clean_string(lead.state_region):
        score += 1
    if clean_string(lead.country):
        score += 1
    if clean_string(lead.category) or clean_string(lead.industry):
        score += 1
    return score


def weak_lead_reason(lead: CanonicalLead) -> str | None:
    if not clean_string(lead.name):
        return "missing-name"
    context_score = lead_context_score(lead)
    generic_name = is_generic_business_name(lead.name)
    if generic_name and context_score < 5:
        return "generic-business-name"
    if context_score < 3:
        return "insufficient-identifying-context"
    return None


def cache_key_for_lead(lead: CanonicalLead) -> str:
    parts = [
        lead.source,
        lead.name or "",
        lead.city or "",
        lead.state_region or "",
        lead.country or "",
        normalize_phone(lead.phone),
        lead.address or "",
        lead.category or "",
        lead.industry or "",
        extract_domain(lead.source_url),
    ]
    return "|".join(part.strip().casefold() for part in parts if part is not None)
