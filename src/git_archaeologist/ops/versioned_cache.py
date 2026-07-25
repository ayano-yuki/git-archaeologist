"""Version-aware cache primitives for repeated repository questions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Generic, TypeVar


T = TypeVar("T")


class CacheOperation(StrEnum):
    """Cacheable Phase2 operations."""

    TARGET_RESOLUTION = "target_resolution"
    SEARCH = "search"
    EMBEDDING = "embedding"
    EVIDENCE_PACK = "evidence_pack"


@dataclass(frozen=True)
class CacheKey:
    """Cache key that is invalidated by index or model changes."""

    operation: CacheOperation
    target_digest: str
    index_version: str
    model_version: str

    @classmethod
    def build(
        cls,
        *,
        operation: CacheOperation,
        target: str,
        index_version: str,
        model_version: str,
    ) -> "CacheKey":
        if not target:
            raise ValueError("target must be non-empty")
        digest = sha256(target.encode("utf-8")).hexdigest()
        return cls(operation, digest, index_version, model_version)


@dataclass(frozen=True)
class CacheStats:
    """Hit/miss counters for observability."""

    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


class VersionedCache(Generic[T]):
    """In-memory versioned cache used by deterministic tests and local runs."""

    def __init__(self) -> None:
        self._values: dict[CacheKey, T] = {}
        self._stats = CacheStats()

    @property
    def stats(self) -> CacheStats:
        return self._stats

    def put(self, key: CacheKey, value: T) -> None:
        self._values[key] = value

    def get(self, key: CacheKey) -> T | None:
        if key in self._values:
            self._stats = CacheStats(hits=self._stats.hits + 1, misses=self._stats.misses)
            return self._values[key]
        self._stats = CacheStats(hits=self._stats.hits, misses=self._stats.misses + 1)
        return None

    def invalidate_index_version(self, index_version: str) -> int:
        stale = [key for key in self._values if key.index_version == index_version]
        for key in stale:
            del self._values[key]
        return len(stale)
