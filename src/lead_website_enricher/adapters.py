from __future__ import annotations

import json
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

SOURCE_ALIASES = {
    "google": "gmaps",
    "google maps": "gmaps",
    "google_places": "gmaps",
    "google places": "gmaps",
    "osm": "osm",
    "openstreetmap": "osm",
    "open street map": "osm",
    "yellow pages": "yellowpages",
    "yellowpages": "yellowpages",
    "foursquare": "foursquare",
}


def normalize_lead_row(row: dict[str, Any], source: str | None = None) -> CanonicalLead:
    resolved_source = _normalize_source(source or row.get("source"))
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
    _apply_cross_source_fallbacks(lead, row)
    if resolved_source == "osm":
        _apply_osm_tag_fallbacks(lead, row)
    if not lead.source_record_id:
        lead.source_record_id = clean_string(row.get("id")) or clean_string(row.get("Id")) or lead.name
    if not lead.name:
        raise ValueError(f"Lead row from source {resolved_source} is missing a usable name.")
    return lead


def _normalize_source(value: object) -> str | None:
    cleaned = clean_string(value)
    if not cleaned:
        return None
    key = cleaned.casefold().replace("-", " ").replace("_", " ")
    key = " ".join(key.split())
    return SOURCE_ALIASES.get(key, key.replace(" ", ""))


def _first_clean(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = clean_string(row.get(key))
        if value:
            return value
    return None


def _apply_cross_source_fallbacks(lead: CanonicalLead, row: dict[str, Any]) -> None:
    lead.country = lead.country or _first_clean(row, "country", "country_name", "country_code", "lead_country")
    lead.category = lead.category or _first_clean(row, "subcategory", "category", "query_name", "industry_slug")
    lead.industry = lead.industry or _first_clean(row, "category", "industry_slug")
    lead.source_url = lead.source_url or _first_clean(row, "maps_link", "osm_url", "foursquare_url", "link", "source_url")
    lead.phone = lead.phone or _first_clean(row, "phone", "international_phone_number")
    lead.address = lead.address or _first_clean(row, "address", "formatted_address", "complete_address")
    lead.city = lead.city or _first_clean(row, "city", "locality")
    lead.state_region = lead.state_region or _first_clean(row, "state_region", "state", "region")
    lead.postcode = lead.postcode or _first_clean(row, "postcode", "postal_code", "zip")


def _apply_osm_tag_fallbacks(lead: CanonicalLead, row: dict[str, Any]) -> None:
    raw_tags = row.get("raw_tags_json")
    if not raw_tags:
        return
    try:
        tags = json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
    except (TypeError, json.JSONDecodeError):
        return
    if not isinstance(tags, dict):
        return

    lead.phone = lead.phone or _first_clean(tags, "phone", "contact:phone")
    lead.city = lead.city or _first_clean(tags, "addr:city")
    lead.state_region = lead.state_region or _first_clean(tags, "addr:state", "addr:province")
    lead.postcode = lead.postcode or _first_clean(tags, "addr:postcode")
    lead.country = lead.country or _first_clean(tags, "addr:country")
    lead.category = lead.category or _first_clean(tags, "cuisine", "amenity", "shop", "tourism")
    lead.industry = lead.industry or _first_clean(tags, "amenity", "shop", "tourism")

    if not lead.address:
        house_number = _first_clean(tags, "addr:housenumber")
        street = _first_clean(tags, "addr:street")
        address = clean_string(" ".join(part for part in [house_number, street] if part))
        if address:
            lead.address = address
