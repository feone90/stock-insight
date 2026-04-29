"""ResultCache — per-key LRU + TTL + asyncio.Lock for concurrent fetch safety.

Caches normalized adapter *results* (FinancialSeries, SectorInfo, IdentityFacts),
NOT the upstream vendor objects. Decision rationale: dartlab `Company` instances
weigh ~1.5GB at first load (BoundedCache FATAL warning observed during probe);
caching 5 of those would risk OOM. The vendor objects are recreated each call
and freed by GC; only their normalized output sits in this cache (~50KB / entry).

Concurrent callers on the same key share a single fetch via per-key
`asyncio.Lock`, so the heavy upstream call never duplicates within the lock
window.

Spec §8.1 + plan-eng-review concurrency requirement.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable

from app.services.external_data_adapters.constants import (
    CACHE_MAX_SIZE,
    CACHE_TTL_SEC,
)

CacheKey = tuple  # Conventionally (ticker: str, method: str); generic by design.


@dataclass
class _Entry:
    value: Any
    expires_at: float


class ResultCache:
    """Per-key LRU + TTL + per-key `asyncio.Lock`."""

    def __init__(
        self,
        max_size: int = CACHE_MAX_SIZE,
        ttl: int = CACHE_TTL_SEC,
    ) -> None:
        self._entries: OrderedDict[CacheKey, _Entry] = OrderedDict()
        self._locks: dict[CacheKey, asyncio.Lock] = {}
        self._max_size = max_size
        self._ttl = ttl

    async def get_or_fetch(
        self, key: CacheKey, fetcher: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Cache hit returns stored value; miss runs `fetcher` once even under
        concurrent callers, then stores + LRU-evicts as needed."""
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = monotonic()
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at > now:
                self._entries.move_to_end(key)
                return entry.value
            value = await fetcher()
            self._entries[key] = _Entry(value, now + self._ttl)
            self._entries.move_to_end(key)
            self._evict_lru()
            return value

    def _evict_lru(self) -> None:
        while len(self._entries) > self._max_size:
            evicted_key, _ = self._entries.popitem(last=False)
            self._locks.pop(evicted_key, None)

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()
