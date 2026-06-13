from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


def _classify_error(message: str) -> str:
    lowered = (message or "").casefold()
    if "429" in lowered or "captcha" in lowered:
        return "rate_limited"
    if "circuit_open" in lowered or "circuit breaker" in lowered:
        return "rate_limited"
    if "timed out" in lowered or "timeout" in lowered:
        return "timeout"
    return "error"


@dataclass(slots=True)
class EngineStats:
    engine: str
    success_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    rate_limit_count: int = 0
    consecutive_failures: int = 0
    total_latency_seconds: float = 0.0
    last_error: str | None = None
    last_error_kind: str | None = None
    last_result_count: int = 0
    cooldown_until: float = 0.0
    circuit_open_until: float = 0.0

    @property
    def average_latency_seconds(self) -> float:
        if self.success_count <= 0:
            return 0.0
        return self.total_latency_seconds / self.success_count

    def availability(self, now: float) -> tuple[bool, str | None]:
        if self.circuit_open_until > now:
            return False, "circuit_open"
        if self.cooldown_until > now:
            return False, "cooldown"
        return True, None


@dataclass(slots=True)
class CacheEntry:
    payload: dict[str, Any]
    expires_at: float


@dataclass(slots=True)
class RuntimeSnapshot:
    engines: dict[str, dict[str, Any]]
    cache_size: int


class EnrichmentRuntime:
    def __init__(self) -> None:
        self._engine_stats: dict[str, EngineStats] = {}
        self._lead_cache: dict[str, CacheEntry] = {}
        self._lock = Lock()

    def get_cached(self, key: str) -> dict[str, Any] | None:
        now = time.time()
        with self._lock:
            entry = self._lead_cache.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._lead_cache.pop(key, None)
                return None
            return entry.payload

    def put_cached(self, key: str, payload: dict[str, Any], *, ttl_seconds: int) -> None:
        with self._lock:
            self._lead_cache[key] = CacheEntry(payload=payload, expires_at=time.time() + ttl_seconds)

    def engine_plan(self, requested_engines: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
        now = time.time()
        with self._lock:
            considered: list[tuple[float, str]] = []
            skipped: list[dict[str, Any]] = []
            for raw_engine in requested_engines:
                engine = raw_engine.strip()
                if not engine:
                    continue
                stats = self._engine_stats.setdefault(engine, EngineStats(engine=engine))
                available, reason = stats.availability(now)
                if not available:
                    skipped.append({"engine": engine, "reason": reason})
                    continue
                score = 0.0
                score -= stats.average_latency_seconds * 10
                score -= stats.timeout_count * 2
                score -= stats.rate_limit_count * 4
                score += stats.success_count
                considered.append((score, engine))
        considered.sort(key=lambda item: (-item[0], item[1]))
        return [engine for _, engine in considered], skipped

    def record_success(self, engine: str, *, elapsed_seconds: float, result_count: int) -> None:
        with self._lock:
            stats = self._engine_stats.setdefault(engine, EngineStats(engine=engine))
            stats.success_count += 1
            stats.total_latency_seconds += elapsed_seconds
            stats.consecutive_failures = 0
            stats.last_result_count = result_count
            stats.last_error = None
            stats.last_error_kind = None
            stats.cooldown_until = 0.0

    def record_failure(self, engine: str, *, elapsed_seconds: float, message: str) -> str:
        error_kind = _classify_error(message)
        with self._lock:
            stats = self._engine_stats.setdefault(engine, EngineStats(engine=engine))
            stats.error_count += 1
            stats.consecutive_failures += 1
            stats.last_error = message
            stats.last_error_kind = error_kind
            if error_kind == "timeout":
                stats.timeout_count += 1
                if stats.consecutive_failures >= 2:
                    stats.cooldown_until = time.time() + 300
                if stats.consecutive_failures >= 4:
                    stats.circuit_open_until = time.time() + 900
            elif error_kind == "rate_limited":
                stats.rate_limit_count += 1
                stats.cooldown_until = time.time() + 900
                if stats.consecutive_failures >= 3:
                    stats.circuit_open_until = time.time() + 3600
            else:
                if stats.consecutive_failures >= 3:
                    stats.cooldown_until = time.time() + 180
            stats.total_latency_seconds += elapsed_seconds
        return error_kind

    def snapshot(self) -> RuntimeSnapshot:
        now = time.time()
        with self._lock:
            engines = {
                engine: {
                    "success_count": stats.success_count,
                    "error_count": stats.error_count,
                    "timeout_count": stats.timeout_count,
                    "rate_limit_count": stats.rate_limit_count,
                    "consecutive_failures": stats.consecutive_failures,
                    "average_latency_seconds": round(stats.average_latency_seconds, 3),
                    "last_error": stats.last_error,
                    "last_error_kind": stats.last_error_kind,
                    "last_result_count": stats.last_result_count,
                    "cooldown_seconds_remaining": max(0, int(stats.cooldown_until - now)),
                    "circuit_open_seconds_remaining": max(0, int(stats.circuit_open_until - now)),
                }
                for engine, stats in sorted(self._engine_stats.items())
            }
            return RuntimeSnapshot(engines=engines, cache_size=len(self._lead_cache))


RUNTIME = EnrichmentRuntime()
