"""Async circuit breaker state machine (CLOSED, OPEN, HALF_OPEN) for upstream resilience."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, TypeVar

from app.config.logging import get_logger
from app.utils.errors import CircuitOpenError

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker finite states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Async three-state circuit breaker protecting the upstream FastAPI backend."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
        name: str = "fastapi-backend",
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be > 0")

        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self._clock = clock

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current logical state (evaluates cooldown expiry lazily)."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if (self._clock() - self._opened_at) >= self.recovery_timeout_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def before_request(self) -> None:
        """Gate an outbound call; fast-fail with CircuitOpenError if circuit is OPEN."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return

            if self._state == CircuitState.OPEN:
                assert self._opened_at is not None
                elapsed = self._clock() - self._opened_at
                if elapsed < self.recovery_timeout_seconds:
                    remaining = max(0.0, self.recovery_timeout_seconds - elapsed)
                    raise CircuitOpenError(
                        f"UPSTREAM_CIRCUIT_OPEN: Upstream circuit '{self.name}' is OPEN; retry in {remaining:.1f}s.",
                        details={
                            "circuit": self.name,
                            "state": CircuitState.OPEN.value,
                            "retry_after_seconds": round(remaining, 2),
                        },
                    )
                # Transition OPEN -> HALF_OPEN for exactly one probe request
                self._state = CircuitState.HALF_OPEN
                self._probe_in_flight = True
                logger.info("Circuit breaker transitioning OPEN -> HALF_OPEN", circuit=self.name)
                return

            # HALF_OPEN: allow only a single probe in flight
            if self._probe_in_flight:
                raise CircuitOpenError(
                    f"UPSTREAM_CIRCUIT_OPEN: Upstream circuit '{self.name}' is HALF_OPEN with probe in flight.",
                    details={"circuit": self.name, "state": CircuitState.HALF_OPEN.value},
                )
            self._probe_in_flight = True

    async def record_success(self) -> None:
        """Record a healthy upstream response; closes HALF_OPEN circuit."""
        async with self._lock:
            prev_state = self._state
            self._consecutive_failures = 0
            self._opened_at = None
            self._probe_in_flight = False
            self._state = CircuitState.CLOSED
            if prev_state != CircuitState.CLOSED:
                logger.info(
                    "Circuit breaker closed after successful probe",
                    circuit=self.name,
                    previous_state=prev_state.value,
                )

    async def record_failure(self) -> None:
        """Record an upstream 5xx/timeout failure; opens circuit at threshold."""
        async with self._lock:
            self._probe_in_flight = False
            self._consecutive_failures += 1

            if self._state == CircuitState.HALF_OPEN or self._consecutive_failures >= self.failure_threshold:
                prev_state = self._state
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                logger.warning(
                    "Circuit breaker tripped to OPEN",
                    circuit=self.name,
                    previous_state=prev_state.value,
                    consecutive_failures=self._consecutive_failures,
                    recovery_timeout_seconds=self.recovery_timeout_seconds,
                )

    async def call(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        is_upstream_failure: Callable[[Exception], bool] | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute an async callable protected by this circuit breaker."""
        await self.before_request()
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            counts_as_failure = is_upstream_failure(exc) if is_upstream_failure else True
            if counts_as_failure:
                await self.record_failure()
            else:
                # 4xx client errors indicate upstream reachability; close HALF_OPEN if needed
                await self.record_success()
            raise
        await self.record_success()
        return result

    def snapshot(self) -> dict[str, Any]:
        """Return diagnostic metrics for /health/ready."""
        current = self.state
        remaining = None
        if current == CircuitState.OPEN and self._opened_at is not None:
            remaining = round(max(0.0, self.recovery_timeout_seconds - (self._clock() - self._opened_at)), 2)
        return {
            "name": self.name,
            "state": current.value,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout_seconds,
            "remaining_cooldown_seconds": remaining,
        }
