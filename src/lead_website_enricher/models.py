from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class CanonicalLead:
    source: str
    source_record_id: str
    name: str
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    area: str | None = None
    state_region: str | None = None
    postcode: str | None = None
    country: str | None = None
    industry: str | None = None
    category: str | None = None
    source_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SearchQuery:
    value: str
    strategy: str

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "strategy": self.strategy}


@dataclass(slots=True)
class SearchResult:
    provider: str
    engine: str
    url: str
    title: str
    snippet: str
    position: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CandidateScore:
    url: str
    domain: str
    score: int
    confidence: str
    reasons: list[str]
    result: SearchResult

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["result"] = self.result.to_dict()
        return payload


@dataclass(slots=True)
class EnrichmentResult:
    lead: CanonicalLead
    queries: list[SearchQuery]
    candidates: list[CandidateScore]
    winner: CandidateScore | None
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead": self.lead.to_dict(),
            "queries": [query.to_dict() for query in self.queries],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "winner": self.winner.to_dict() if self.winner else None,
            "stats": self.stats,
        }
