from __future__ import annotations

from .models import CanonicalLead, SearchQuery
from .text import clean_string
from .lead_quality import is_generic_business_name


def build_queries(lead: CanonicalLead) -> list[SearchQuery]:
    queries: list[SearchQuery] = []

    def add(strategy: str, *parts: str | None) -> None:
        value = clean_string(" ".join(part for part in parts if clean_string(part)))
        if not value:
            return
        if value in {query.value for query in queries}:
            return
        queries.append(SearchQuery(value=value, strategy=strategy))

    quoted_name = f'"{lead.name}"'
    location = clean_string(" ".join(part for part in [lead.city, lead.state_region, lead.country] if clean_string(part)))
    generic_name = is_generic_business_name(lead.name)
    source_host = None
    if lead.source_url:
        source_host = lead.source_url.split("/")[2] if "://" in lead.source_url else lead.source_url

    add("name-address", quoted_name, lead.address, lead.city, lead.country)
    add("name-city-state", quoted_name, lead.city, lead.state_region, lead.country)
    add("name-phone-location", quoted_name, lead.phone, location)
    add("phone-name-location", lead.phone, quoted_name, lead.city, lead.state_region)
    add("name-city-country-category", quoted_name, lead.city, lead.state_region, lead.country, lead.category or lead.industry)
    if source_host:
        add("name-source-host-location", quoted_name, source_host, lead.city, lead.state_region, lead.country)
    add("name-city-country", quoted_name, lead.city, lead.state_region, lead.country)
    if not generic_name:
        add("name-category-country", quoted_name, lead.category or lead.industry, lead.country)
        add("name-country", quoted_name, lead.country)
        add("name-only", quoted_name)

    return queries
