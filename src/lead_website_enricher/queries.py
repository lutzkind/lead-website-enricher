from __future__ import annotations

from urllib.parse import urlparse

from .models import CanonicalLead, SearchQuery
from .text import clean_string
from .lead_quality import has_identifying_source_context, is_generic_business_name


def build_queries(lead: CanonicalLead) -> list[SearchQuery]:
    queries: list[SearchQuery] = []

    def add(strategy: str, *parts: str | None) -> None:
        value = clean_string(" ".join(part for part in parts if clean_string(part)))
        if not value:
            return
        if value in {query.value for query in queries}:
            return
        queries.append(SearchQuery(value=value, strategy=strategy))

    def add_when(condition: object, strategy: str, *parts: str | None) -> None:
        if condition:
            add(strategy, *parts)

    quoted_name = f'"{lead.name}"'
    location = clean_string(" ".join(part for part in [lead.city, lead.state_region, lead.country] if clean_string(part)))
    generic_name = is_generic_business_name(lead.name)
    source_host = None
    if has_identifying_source_context(lead):
        parsed = urlparse(lead.source_url if "://" in lead.source_url else f"https://{lead.source_url}")
        source_host = parsed.netloc or parsed.path

    has_location = clean_string(lead.city) or clean_string(lead.state_region)
    has_category = clean_string(lead.category) or clean_string(lead.industry)

    add_when(lead.address, "name-address", quoted_name, lead.address, lead.city, lead.country)
    add_when(lead.address, "name-address-official", quoted_name, lead.address, "official website")
    add_when(has_location, "name-city-state-official", quoted_name, lead.city, lead.state_region, lead.country, "official website")
    add_when(has_location, "name-city-state", quoted_name, lead.city, lead.state_region, lead.country)
    add_when(has_location and has_category, "name-city-country-category", quoted_name, lead.city, lead.state_region, lead.country, lead.category or lead.industry)
    add("name-country-category-official", quoted_name, lead.country, lead.category or lead.industry, "official website")
    if source_host:
        add_when(has_location, "name-source-host-location", quoted_name, source_host, lead.city, lead.state_region, lead.country)
        add("name-source-host-official", quoted_name, source_host, "official website")
    add_when(has_location, "name-city-country", quoted_name, lead.city, lead.state_region, lead.country)
    if not generic_name:
        add("name-category-country", quoted_name, lead.category or lead.industry, lead.country)
        add("name-official-website", quoted_name, "official website")
        add("name-country", quoted_name, lead.country)
        add("name-only", quoted_name)

    return queries
