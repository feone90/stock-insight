"""ResultCache — spec §8.1 + plan-eng-review concurrent Lock case (5 unit)."""
import asyncio

import pytest

from app.services.external_data_adapters.cache import ResultCache


@pytest.mark.asyncio
async def test_cache_hit_returns_stored_value_without_refetch():
    cache = ResultCache(max_size=4, ttl=600)
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return "v"

    r1 = await cache.get_or_fetch(("A", "x"), fetch)
    r2 = await cache.get_or_fetch(("A", "x"), fetch)
    assert r1 == r2 == "v"
    assert calls == 1


@pytest.mark.asyncio
async def test_cache_miss_invokes_fetcher_per_key():
    cache = ResultCache(max_size=4, ttl=600)
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return calls

    r_a = await cache.get_or_fetch(("A", "x"), fetch)
    r_b = await cache.get_or_fetch(("B", "x"), fetch)
    assert r_a == 1
    assert r_b == 2
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_lru_evicts_oldest_when_max_exceeded():
    cache = ResultCache(max_size=2, ttl=600)

    async def make_a(): return "a"
    async def make_b(): return "b"
    async def make_c(): return "c"

    await cache.get_or_fetch(("A",), make_a)
    await cache.get_or_fetch(("B",), make_b)
    await cache.get_or_fetch(("C",), make_c)  # evicts A (LRU)

    assert len(cache) == 2

    refetched = []

    async def re_a():
        refetched.append(1)
        return "a2"

    val = await cache.get_or_fetch(("A",), re_a)
    assert val == "a2"
    assert refetched == [1]  # had to refetch — A was evicted


@pytest.mark.asyncio
async def test_cache_ttl_expiry_triggers_refetch():
    cache = ResultCache(max_size=4, ttl=1)
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return f"v{calls}"

    r1 = await cache.get_or_fetch(("X",), fetch)
    await asyncio.sleep(1.05)
    r2 = await cache.get_or_fetch(("X",), fetch)
    assert r1 == "v1"
    assert r2 == "v2"
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_concurrent_same_key_runs_fetcher_once():
    """plan-eng-review §2 P1: parallel callers must share single fetch."""
    cache = ResultCache(max_size=4, ttl=600)
    calls = 0

    async def slow_fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return calls

    r1, r2, r3 = await asyncio.gather(
        cache.get_or_fetch(("Y",), slow_fetch),
        cache.get_or_fetch(("Y",), slow_fetch),
        cache.get_or_fetch(("Y",), slow_fetch),
    )
    assert r1 == r2 == r3 == 1
    assert calls == 1
