"""Tiered TTL cache with SHA-256 tenant-scoped keys and Single-Flight coalescing."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from cachetools import LRUCache

T = TypeVar("T")


def build_cache_key(
    tenant_scope: str,
    method: str,
    endpoint: str,
    params: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
) -> str:
    """Build deterministic SHA-256 cache key partitioned strictly by tenant_scope."""
    canonical_params = json.dumps(params or {}, sort_keys=True, separators=(",", ":"), default=str)
    canonical_body = json.dumps(body or {}, sort_keys=True, separators=(",", ":"), default=str)
    material = f"{tenant_scope}|{method.upper()}|{endpoint}|{canonical_params}|{canonical_body}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class _CacheEntry:
    value: Any
    expires_at: float
    tags: tuple[str, ...]


class TieredTTLCache:
    """Bounded LRU cache supporting per-entry TTLs and tag-based invalidation."""

    def __init__(
        self,
        *,
        max_size: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store: LRUCache[str, _CacheEntry] = LRUCache(maxsize=max_size)
        self._tag_index: dict[str, set[str]] = {}
        self._clock = clock
        self._lock = asyncio.Lock()

        self.hits = 0
        self.misses = 0
        self.invalidations = 0

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            if self._clock() >= entry.expires_at:
                self._remove_key_unlocked(key)
                self.misses += 1
                return None
            self.hits += 1
            return copy.deepcopy(entry.value)

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: float,
        *,
        tags: Iterable[str] = (),
    ) -> None:
        if ttl_seconds <= 0:
            return
        tag_tuple = tuple(tags)
        expires_at = self._clock() + ttl_seconds
        async with self._lock:
            if key in self._store:
                self._remove_key_unlocked(key)
            self._store[key] = _CacheEntry(
                value=copy.deepcopy(value),
                expires_at=expires_at,
                tags=tag_tuple,
            )
            for tag in tag_tuple:
                self._tag_index.setdefault(tag, set()).add(key)

    async def invalidate_key(self, key: str) -> bool:
        async with self._lock:
            existed = key in self._store
            self._remove_key_unlocked(key)
            if existed:
                self.invalidations += 1
            return existed

    async def invalidate_tag(self, tag: str) -> int:
        async with self._lock:
            keys = list(self._tag_index.pop(tag, ()))
            removed = 0
            for key in keys:
                if key in self._store:
                    self._remove_key_unlocked(key)
                    removed += 1
            self.invalidations += removed
            return removed

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            self._tag_index.clear()

    def _remove_key_unlocked(self, key: str) -> None:
        entry = self._store.pop(key, None)
        if entry is not None:
            for tag in entry.tags:
                bucket = self._tag_index.get(tag)
                if bucket is not None:
                    bucket.discard(key)
                    if not bucket:
                        self._tag_index.pop(tag, None)

    def stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._store),
            "maxsize": self._store.maxsize,
            "hits": self.hits,
            "misses": self.misses,
            "invalidations": self.invalidations,
        }


class SingleFlightCache:
    """Request coalescer layered over TieredTTLCache to prevent thundering herds."""

    def __init__(self, cache: TieredTTLCache) -> None:
        self.cache = cache
        self._in_flight: dict[str, asyncio.Future[Any]] = {}
        self._flight_lock = asyncio.Lock()
        self.coalesced_hits = 0

    async def get_or_coalesce(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        *,
        ttl_seconds: float,
        tags: Iterable[str] = (),
    ) -> tuple[T, bool]:
        """Return (value, cache_hit_or_coalesced). Coalesces concurrent identical misses."""
        if ttl_seconds <= 0:
            # Non-cacheable request (mutations / simulations): execute directly without caching
            return await factory(), False

        async with self._flight_lock:
            cached = await self.cache.get(key)
            if cached is not None:
                return cached, True

            existing_future = self._in_flight.get(key)
            if existing_future is None:
                loop = asyncio.get_running_loop()
                leader_future: asyncio.Future[Any] = loop.create_future()
                self._in_flight[key] = leader_future
                is_leader = True
            else:
                leader_future = existing_future
                is_leader = False

        if not is_leader:
            result = await asyncio.shield(leader_future)
            self.coalesced_hits += 1
            return copy.deepcopy(result), True

        try:
            result = await factory()
            await self.cache.set(key, result, ttl_seconds, tags=tags)
        except BaseException as exc:
            async with self._flight_lock:
                self._in_flight.pop(key, None)
            if not leader_future.done():
                leader_future.set_exception(exc)
                # Retrieve exception once so asyncio never emits 'Future exception was never retrieved'
                leader_future.exception()
            raise
        else:
            async with self._flight_lock:
                self._in_flight.pop(key, None)
            if not leader_future.done():
                leader_future.set_result(result)
            return copy.deepcopy(result), False

    def stats(self) -> dict[str, Any]:
        return {
            **self.cache.stats(),
            "in_flight": len(self._in_flight),
            "coalesced_hits": self.coalesced_hits,
        }
