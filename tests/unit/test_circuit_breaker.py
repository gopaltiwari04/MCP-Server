"""Unit tests for the async three-state CircuitBreaker state machine."""

import httpx
import pytest
import respx

from app.clients.backend_client import BackendClient
from app.clients.circuit_breaker import CircuitBreaker, CircuitState
from app.utils.errors import CircuitOpenError, InvalidParametersError, UpstreamProviderError
from tests.conftest import FakeClock, make_test_settings


@pytest.mark.asyncio
async def test_circuit_breaker_full_state_lifecycle() -> None:
    clock = FakeClock(1000.0)
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout_seconds=15.0, clock=clock)
    assert cb.state == CircuitState.CLOSED

    async def failing_op() -> None:
        raise UpstreamProviderError("HTTP 503")

    async def healthy_op() -> str:
        return "ok"

    # 4 failures keep circuit CLOSED
    for _ in range(4):
        with pytest.raises(UpstreamProviderError):
            await cb.call(failing_op)
        assert cb.state == CircuitState.CLOSED

    # 5th consecutive failure trips circuit to OPEN
    with pytest.raises(UpstreamProviderError):
        await cb.call(failing_op)
    assert cb.state == CircuitState.OPEN
    assert cb.consecutive_failures == 5

    # Fast fail while within 15s cooldown
    with pytest.raises(CircuitOpenError) as exc_info:
        await cb.call(healthy_op)
    assert exc_info.value.code.value == "UPSTREAM_CIRCUIT_OPEN"

    # Advance past cooldown -> transitions OPEN -> HALF_OPEN -> CLOSED on probe success
    clock.advance(15.1)
    assert cb.state == CircuitState.HALF_OPEN
    result = await cb.call(healthy_op)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED
    assert cb.consecutive_failures == 0


@pytest.mark.asyncio
async def test_circuit_breaker_reopens_on_failed_half_open_probe() -> None:
    clock = FakeClock(2000.0)
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=10.0, clock=clock)

    await cb.record_failure()
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN

    clock.advance(10.0)
    await cb.before_request()  # enters HALF_OPEN and claims single probe

    # A concurrent second caller must fast-fail while probe is in flight
    with pytest.raises(CircuitOpenError):
        await cb.before_request()

    # Probe fails -> reopens immediately for full cooldown
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_backend_client_4xx_does_not_trip_circuit_breaker(bind_full_security_context) -> None:
    settings = make_test_settings(backend_max_retries=0, circuit_breaker_failure_threshold=2)
    with respx.mock(base_url="http://backend.test") as mock:
        mock.get("/api/v1/market/quotes/BAD").mock(
            return_value=httpx.Response(400, json={"message": "Bad query"})
        )
        mock.get("/api/v1/market/quotes/DOWN").mock(
            return_value=httpx.Response(503, json={"message": "Service unavailable"})
        )

        client = BackendClient(settings)
        await client.open()
        try:
            # 3 consecutive HTTP 400s must NOT open the circuit
            for _ in range(3):
                with pytest.raises(InvalidParametersError):
                    await client.request("GET", "/api/v1/market/quotes/BAD")
            assert client.circuit_breaker.state == CircuitState.CLOSED

            # 2 consecutive 503s DO open the circuit
            for _ in range(2):
                with pytest.raises(UpstreamProviderError):
                    await client.request("GET", "/api/v1/market/quotes/DOWN")
            assert client.circuit_breaker.state == CircuitState.OPEN

            with pytest.raises(CircuitOpenError):
                await client.request("GET", "/api/v1/market/quotes/DOWN")
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_tenacity_retries_503_then_succeeds_and_never_retries_400(bind_full_security_context) -> None:
    settings = make_test_settings(backend_max_retries=2, circuit_breaker_failure_threshold=5)
    with respx.mock(base_url="http://backend.test") as mock:
        flaky_route = mock.get("/api/v1/market/quotes/FLAKY").mock(
            side_effect=[
                httpx.Response(503, json={"message": "Transient 503 #1"}),
                httpx.Response(504, json={"message": "Transient 504 #2"}),
                httpx.Response(200, json={"symbol": "FLAKY", "last_price": 99.5, "currency": "USD"}),
            ]
        )
        bad_route = mock.get("/api/v1/market/quotes/BAD400").mock(
            return_value=httpx.Response(400, json={"message": "Invalid query"})
        )

        client = BackendClient(settings)
        await client.open()
        try:
            resp = await client.request("GET", "/api/v1/market/quotes/FLAKY")
            assert resp.data["last_price"] == 99.5
            assert flaky_route.call_count == 3

            with pytest.raises(InvalidParametersError):
                await client.request("GET", "/api/v1/market/quotes/BAD400")
            assert bad_route.call_count == 1
        finally:
            await client.close()
