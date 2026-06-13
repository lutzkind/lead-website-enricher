from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .models import CandidateScore, CanonicalLead
from .scoring import blocked_domain_reason
from .text import extract_domain, normalize_phone, normalize_text, tokenize


TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
CANONICAL_RE = re.compile(
    r"<link[^>]+rel=[\"']canonical[\"'][^>]+href=[\"']([^\"']+)[\"'][^>]*>",
    re.IGNORECASE,
)
HREF_RE = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)
JSON_LD_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<script.*?</script>|<style.*?</style>", re.IGNORECASE | re.DOTALL)


@dataclass(slots=True)
class PageData:
    url: str
    final_url: str
    title: str
    text: str
    links: list[str]
    schema_types: set[str]


def _extract_json_ld_types(html: str) -> set[str]:
    schema_types: set[str] = set()
    for raw_block in JSON_LD_RE.findall(html):
        try:
            payload = json.loads(unescape(raw_block))
        except json.JSONDecodeError:
            continue
        for node in _iter_jsonld_nodes(payload):
            node_type = node.get("@type")
            if isinstance(node_type, str):
                schema_types.add(node_type.casefold())
            elif isinstance(node_type, list):
                for entry in node_type:
                    if isinstance(entry, str):
                        schema_types.add(entry.casefold())
    return schema_types


def _iter_jsonld_nodes(payload: object):
    if isinstance(payload, dict):
        yield payload
        graph = payload.get("@graph")
        if isinstance(graph, list):
            for entry in graph:
                yield from _iter_jsonld_nodes(entry)
    elif isinstance(payload, list):
        for entry in payload:
            yield from _iter_jsonld_nodes(entry)


def fetch_page(url: str, *, timeout_seconds: float = 4.0) -> PageData | None:
    req = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "lead-website-enricher/0.1.0",
        },
    )
    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type:
                return None
            html = response.read().decode("utf-8", errors="replace")
            final_url = response.geturl()
    except (HTTPError, URLError, TimeoutError):
        return None

    cleaned = SCRIPT_RE.sub(" ", html)
    text = TAG_RE.sub(" ", cleaned)
    title_match = TITLE_RE.search(html)
    title = unescape(title_match.group(1)).strip() if title_match else ""
    links = [urljoin(final_url, href) for href in HREF_RE.findall(html)]
    schema_types = _extract_json_ld_types(html)
    canonical_match = CANONICAL_RE.search(html)
    if canonical_match:
        final_url = urljoin(final_url, canonical_match.group(1))
    return PageData(
        url=url,
        final_url=final_url,
        title=title,
        text=unescape(" ".join(text.split())),
        links=links,
        schema_types=schema_types,
    )


def canonical_root_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    scheme = parsed.scheme or "https"
    host = parsed.netloc or parsed.path
    host = host.casefold().strip()
    if host.startswith("www."):
        host = host[4:]
    return f"{scheme}://{host}"


def validate_candidate(
    lead: CanonicalLead,
    candidate: CandidateScore,
    *,
    page_fetcher=fetch_page,
) -> dict:
    root_url = canonical_root_url(candidate.url or candidate.domain)
    root_domain = extract_domain(root_url)
    blocked_reason = blocked_domain_reason(root_domain)
    if blocked_reason:
        return {
            "accepted": False,
            "blocked_reason": blocked_reason,
            "canonical_url": root_url,
            "canonical_domain": root_domain,
            "reasons": [],
        }

    fetched_pages: list[PageData] = []
    home = page_fetcher(root_url)
    if home is not None:
        fetched_pages.append(home)
        for link in home.links:
            parsed = urlparse(link)
            if extract_domain(link) != extract_domain(home.final_url):
                continue
            if not any(token in parsed.path.casefold() for token in ("/contact", "/about", "/location", "/visit")):
                continue
            page = page_fetcher(link)
            if page is not None:
                fetched_pages.append(page)
            if len(fetched_pages) >= 3:
                break

    if not fetched_pages:
        return {
            "accepted": False,
            "blocked_reason": "page-fetch-failed",
            "canonical_url": root_url,
            "canonical_domain": root_domain,
            "reasons": [],
        }

    canonical_url = canonical_root_url(fetched_pages[0].final_url)
    canonical_domain = extract_domain(canonical_url)
    blocked_reason = blocked_domain_reason(canonical_domain)
    if blocked_reason:
        return {
            "accepted": False,
            "blocked_reason": blocked_reason,
            "canonical_url": canonical_url,
            "canonical_domain": canonical_domain,
            "reasons": [],
        }

    combined_text = " ".join(
        " ".join([page.title, page.text, page.final_url]) for page in fetched_pages
    )
    normalized_text = normalize_text(combined_text)
    lead_tokens = tokenize(lead.name)
    matched_name_tokens = [token for token in lead_tokens if token in normalized_text]
    reasons: list[str] = []
    if lead_tokens and len(matched_name_tokens) == len(lead_tokens):
        reasons.append("validated-name-match")

    phone = normalize_phone(lead.phone)
    if phone and phone in normalize_phone(combined_text):
        reasons.append("validated-phone-match")

    city = normalize_text(lead.city)
    state_region = normalize_text(lead.state_region)
    country = normalize_text(lead.country)
    address = normalize_text(lead.address)
    if address and address in normalized_text:
        reasons.append("validated-address-match")
    if city and city in normalized_text:
        reasons.append("validated-city-match")
    if state_region and state_region in normalized_text:
        reasons.append("validated-state-match")
    if country and country in normalized_text:
        reasons.append("validated-country-match")

    category = normalize_text(lead.category or lead.industry)
    if category and category in normalized_text:
        reasons.append("validated-category-match")

    schema_types = {schema_type for page in fetched_pages for schema_type in page.schema_types}
    if {"localbusiness", "restaurant", "hotel", "lodgingbusiness"} & schema_types:
        reasons.append("validated-localbusiness-schema")

    domain_tokens = tokenize(canonical_domain.replace(".", " "))
    if lead_tokens and any(token in domain_tokens for token in lead_tokens):
        reasons.append("validated-domain-name-match")

    accepted = False
    reason_set = set(reasons)
    if "validated-name-match" in reason_set and {"validated-phone-match", "validated-address-match"} & reason_set:
        accepted = True
    elif "validated-name-match" in reason_set and "validated-localbusiness-schema" in reason_set and {
        "validated-city-match",
        "validated-state-match",
        "validated-category-match",
    } & reason_set:
        accepted = True
    elif "validated-name-match" in reason_set and "validated-domain-name-match" in reason_set and {
        "validated-city-match",
        "validated-state-match",
        "validated-category-match",
    } & reason_set:
        accepted = True

    return {
        "accepted": accepted,
        "blocked_reason": None if accepted else "insufficient-official-site-evidence",
        "canonical_url": canonical_url,
        "canonical_domain": canonical_domain,
        "reasons": reasons,
    }
