from __future__ import annotations

import re
from urllib.parse import urlparse


SPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def clean_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return SPACE_RE.sub(" ", text)


def normalize_text(value: object) -> str:
    text = clean_string(value)
    if not text:
        return ""
    return NON_ALNUM_RE.sub(" ", text.casefold()).strip()


def tokenize(value: object) -> list[str]:
    normalized = normalize_text(value)
    if not normalized:
        return []
    return [token for token in normalized.split(" ") if token]


def normalize_phone(value: object) -> str:
    text = clean_string(value)
    if not text:
        return ""
    return "".join(ch for ch in text if ch.isdigit())


def extract_domain(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    host = host.casefold().strip()
    if host.startswith("www."):
        host = host[4:]
    return host
