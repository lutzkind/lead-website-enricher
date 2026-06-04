from __future__ import annotations

from .models import CanonicalLead, SearchQuery
from .text import clean_string


def build_queries(lead: CanonicalLead) -> list[SearchQuery]:
    queries: list[SearchQuery] = []

    def add(strategy: str, *parts: str | None) -> None:
        value = clean_string(" ".join(part for part in parts if clean_string(part)))
        if not value:
            return
        if value in {query.value for query in queries}:
            return
        queries.append(SearchQuery(value=value, strategy=strategy))

    add("name-country", lead.name, lead.country)
    add("name-city", lead.name, lead.city, lead.country)
    add("name-state", lead.name, lead.state_region, lead.country)
    add("name-address", lead.name, lead.address, lead.country)
    add("name-category-country", lead.name, lead.category or lead.industry, lead.country)
    add("name-phone", lead.name, lead.phone)
    add("name-only", lead.name)

    return queries
