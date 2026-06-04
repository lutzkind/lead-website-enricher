from __future__ import annotations

from typing import Any

from .models import CanonicalLead
from .text import clean_string


FIELD_MAPS: dict[str, dict[str, str]] = {
    "gmaps": {
        "source_record_id": "Id",
        "name": "name",
        "website": "website",
        "phone": "phone",
        "email": "email",
        "address": "address",
        "city": "city",
        "area": "area",
        "state_region": "state_region",
        "postcode": "postcode",
        "country": "lead_country",
        "industry": "category",
        "category": "subcategory",
        "source_url": "maps_link",
    },
    "yellowpages": {
        "source_record_id": "Id",
        "name": "name",
        "website": "website",
        "phone": "phone",
        "email": "email",
        "address": "address",
        "city": "city",
        "area": "area",
        "state_region": "state_region",
        "postcode": "postcode",
        "country": "country",
        "industry": "category",
        "category": "category",
        "source_url": "link",
    },
    "osm": {
        "source_record_id": "Id",
        "name": "name",
        "website": "website",
        "phone": "phone",
        "email": "email",
        "address": "address",
        "city": "city",
        "area": "area",
        "state_region": "state_region",
        "postcode": "postcode",
        "country": "country",
        "industry": "category",
        "category": "subcategory",
        "source_url": "osm_url",
    },
    "foursquare": {
        "source_record_id": "Id",
        "name": "name",
        "website": "website",
        "phone": "phone",
        "email": "email",
        "address": "address",
        "city": "city",
        "area": "area",
        "state_region": "state_region",
        "postcode": "postcode",
        "country": "country",
        "industry": "category",
        "category": "category",
        "source_url": "foursquare_url",
    },
}


def normalize_lead_row(row: dict[str, Any], source: str | None = None) -> CanonicalLead:
    resolved_source = clean_string(source or row.get("source"))
    if not resolved_source:
        raise ValueError("Lead row must include a source or be passed with --source.")
    if resolved_source not in FIELD_MAPS:
        raise ValueError(f"Unsupported lead source: {resolved_source}")

    mapping = FIELD_MAPS[resolved_source]

    def pick(field_name: str) -> str | None:
        raw_key = mapping.get(field_name)
        if not raw_key:
            return None
        return clean_string(row.get(raw_key))

    lead = CanonicalLead(
        source=resolved_source,
        source_record_id=pick("source_record_id") or "",
        name=pick("name") or "",
        website=pick("website"),
        phone=pick("phone"),
        email=pick("email"),
        address=pick("address"),
        city=pick("city"),
        area=pick("area"),
        state_region=pick("state_region"),
        postcode=pick("postcode"),
        country=pick("country"),
        industry=pick("industry"),
        category=pick("category"),
        source_url=pick("source_url"),
        raw=row,
    )
    if not lead.source_record_id:
        lead.source_record_id = clean_string(row.get("id")) or clean_string(row.get("Id")) or lead.name
    if not lead.name:
        raise ValueError(f"Lead row from source {resolved_source} is missing a usable name.")
    return lead
