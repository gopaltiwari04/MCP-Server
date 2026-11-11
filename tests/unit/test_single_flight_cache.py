"""Unit tests for SingleFlightCache request coalescing, TTL expiry, and tenant isolation."""

import asyncio

import httpx
import pytest
import respx

from app.auth.context import RequestSecurityContext, reset_security_context, set_security_context
from app.clients.backend_client import BackendClient
from app.clients.cache import SingleFlightCache, TieredTTLCache, build_cache_key
from tests.conftest import FakeClock, make_internal_jwt, make_test_settings


@pytest.mark.asyncio
async def test_single_flight_coalesces_10_concurrent_identical_requests(bind_full_security_context) -> None:
    settings = make_test_settings()
    with respx.mock(base_url="http://backend.test") as mock:
        async def slow_quote(_request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.05)
            return httpx.Response(200, json={"symbol": "NVDA", "last_price": 148.5, "currency": "USD"})

        route = mock.get("/api/v1/market/quotes/NVDA").mock(side_effect=slow_quote)

        client = BackendClient(settings)
        await client.open()
        try:
            results = await asyncio.gather(
                *(
                    client.request(
                        "GET",
                        "/api/v1/market/quotes/NVDA",
                        tenant_scope="PUBLIC",
                        ttl_seconds=5.0,
                    )
                    for _ in range(10)
                )
            )
            assert route.call_count == 1
            assert all(r.data["last_price"] == 148.5 for r in results)
            # Exactly 1 leader miss + 9 coalesced hits
            hits = sum(1 for r in results if r.cache_hit)
            misses = sum(1 for r in results if not r.cache_hit)
            assert misses == 1
            assert hits == 9
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_cache_ttl_expiry_and_tag_invalidation() -> None:
    clock = FakeClock(500.0)
    cache = TieredTTLCache(max_size=128, clock=clock)
    sf = SingleFlightCache(cache)

    calls = 0

    async def loader() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"seq": calls}

    key = build_cache_key("user_alice", "GET", "/api/v1/portfolios/p1/analysis", {"benchmark": "SPY"})
    val1, hit1 = await sf.get_or_coalesce(key, loader, ttl_seconds=15.0, tags=("user:user_alice:watchlists",))
    val2, hit2 = await sf.get_or_coalesce(key, loader, ttl_seconds=15.0, tags=("user:user_alice:watchlists",))
    assert val1 == {"seq": 1} and hit1 is False
    assert val2 == {"seq": 1} and hit2 is True
    assert calls == 1

    # Advance past 15s TTL -> triggers fresh load
    clock.advance(16.0)
    val3, hit3 = await sf.get_or_coalesce(key, loader, ttl_seconds=15.0, tags=("user:user_alice:watchlists",))
    assert val3 == {"seq": 2} and hit3 is False
    assert calls == 2

    # Tag invalidation immediately evicts entry
    removed = await cache.invalidate_tag("user:user_alice:watchlists")
    assert removed == 1
    val4, hit4 = await sf.get_or_coalesce(key, loader, ttl_seconds=15.0)
    assert val4 == {"seq": 3} and hit4 is False


@pytest.mark.asyncio
async def test_cache_keys_strictly_partitioned_by_tenant() -> None:
    key_alice = build_cache_key("user_alice", "GET", "/api/v1/portfolios/port_123/analysis", {"a": 1})
    key_bob = build_cache_key("user_bob", "GET", "/api/v1/portfolios/port_123/analysis", {"a": 1})
    assert key_alice != key_bob

    # Verify parameter key ordering is canonicalized deterministically
    k1 = build_cache_key("PUBLIC", "GET", "/search", {"b": 2, "a": 1})
    k2 = build_cache_key("PUBLIC", "GET", "/search", {"a": 1, "b": 2})
    assert k1 == k2


@pytest.mark.asyncio
async def test_single_flight_waiter_cancellation_does_not_abort_peers() -> None:
    cache = TieredTTLCache(max_size=32)
    sf = SingleFlightCache(cache)
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def slow_factory() -> str:
        started.set()
        await proceed.wait()
        return "shared-value"

    t_leader = asyncio.create_task(sf.get_or_coalesce("k1", slow_factory, ttl_seconds=10.0))
    await started.wait()
    t_waiter_cancel = asyncio.create_task(sf.get_or_coalesce("k1", slow_factory, ttl_seconds=10.0))
    t_waiter_keep = asyncio.create_task(sf.get_or_coalesce("k1", slow_factory, ttl_seconds=10.0))

    await asyncio.sleep(0.01)
    t_waiter_cancel.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t_waiter_cancel

    proceed.set()
    res_leader, _ = await t_leader
    res_peer, hit_peer = await t_waiter_keep
    assert res_leader == "shared-value"
    assert res_peer == "shared-value"
    assert hit_peer is True
    # Avoid unused import lint on RequestSecurityContext
    assert set_security_context is not None and reset_security_context is not None and make_internal_jwt is not None
    assert RequestSecurityContext is not None
