"""Resilient HTTPX client for the internal FastAPI Market Intelligence Backend."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.auth.context import get_current_tool_name, require_security_context
from app.clients.cache import SingleFlightCache, TieredTTLCache, build_cache_key
from app.clients.circuit_breaker import CircuitBreaker
from app.config.logging import get_logger
from app.config.settings import Settings
from app.utils.errors import (
    InvalidParametersError,
    NoDataAvailableError,
    PermissionDeniedError,
    RateLimitedError,
    UnsupportedSymbolError,
    UpstreamProviderError,
)

logger = get_logger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})
_RETRYABLE_TRANSPORT_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)


class _RetryableUpstreamStatus(Exception):
    """Internal signal for tenacity to retry HTTP 502/503/504 responses."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(f"Retryable upstream HTTP {response.status_code}")


@dataclass(frozen=True, slots=True)
class BackendResponse:
    """Parsed backend JSON payload with transport cache provenance."""

    data: dict[str, Any]
    cache_hit: bool
    status_code: int = 200


def _is_upstream_outage_error(exc: Exception) -> bool:
    return isinstance(exc, UpstreamProviderError)


class BackendClient:
    """Lifespan-managed FastAPI gateway client with auth propagation, retries, CB, and single-flight."""

    def __init__(
        self,
        settings: Settings,
        *,
        cache: TieredTTLCache | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.cache = cache or TieredTTLCache(max_size=settings.cache_max_size)
        self.single_flight = SingleFlightCache(self.cache)
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout_seconds=settings.circuit_breaker_recovery_timeout_seconds,
        )
        self._external_http_client = http_client is not None
        self._http_client = http_client
        self._transport = transport

    @property
    def is_open(self) -> bool:
        return self._http_client is not None and not self._http_client.is_closed

    async def open(self) -> None:
        """Initialize the pooled httpx.AsyncClient if not already open."""
        if self._http_client is not None and not self._http_client.is_closed:
            return
        limits = httpx.Limits(
            max_connections=self.settings.backend_max_connections,
            max_keepalive_connections=self.settings.backend_max_keepalive_connections,
            keepalive_expiry=self.settings.backend_keepalive_expiry_seconds,
        )
        timeout = httpx.Timeout(
            connect=self.settings.backend_connect_timeout_seconds,
            read=self.settings.backend_read_timeout_seconds,
            write=self.settings.backend_write_timeout_seconds,
            pool=self.settings.backend_pool_timeout_seconds,
        )
        self._http_client = httpx.AsyncClient(
            base_url=self.settings.backend_base_url.rstrip("/"),
            limits=limits,
            timeout=timeout,
            transport=self._transport,
        )

    async def close(self) -> None:
        """Close the managed httpx.AsyncClient pool."""
        if self._http_client is not None and not self._external_http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    def _build_outbound_headers(
        self,
        *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        sec_ctx = require_security_context()
        headers: dict[str, str] = {
            "X-Internal-API-Key": self.settings.backend_internal_api_key.get_secret_value(),
            "X-Request-ID": sec_ctx.request_id,
            "X-MCP-Tool-Name": get_current_tool_name(),
            "Accept": "application/json",
        }
        if sec_ctx.delegated_jwt:
            headers["Authorization"] = f"Bearer {sec_ctx.delegated_jwt}"
        if extra_headers:
            headers.update(extra_headers)
        return headers

    async def request(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        tenant_scope: str = "PUBLIC",
        ttl_seconds: float = 0.0,
        cache_tags: tuple[str, ...] = (),
        extra_headers: Mapping[str, str] | None = None,
        invalidate_tags: tuple[str, ...] = (),
    ) -> BackendResponse:
        """Execute an authenticated, circuit-broken, single-flight-cached FastAPI request."""
        if not self.is_open:
            await self.open()

        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        cache_key = build_cache_key(
            tenant_scope=tenant_scope,
            method=method,
            endpoint=endpoint,
            params=clean_params,
            body=json_body,
        )

        async def _execute_via_breaker() -> dict[str, Any]:
            headers = self._build_outbound_headers(extra_headers=extra_headers)
            return await self.circuit_breaker.call(
                self._send_with_retries,
                method,
                endpoint,
                params=clean_params,
                json_body=json_body,
                headers=headers,
                is_upstream_failure=_is_upstream_outage_error,
            )

        if ttl_seconds > 0:
            payload, cache_hit = await self.single_flight.get_or_coalesce(
                cache_key,
                _execute_via_breaker,
                ttl_seconds=ttl_seconds,
                tags=cache_tags,
            )
            return BackendResponse(data=payload, cache_hit=cache_hit)

        payload = await _execute_via_breaker()
        for tag in invalidate_tags:
            await self.cache.invalidate_tag(tag)
        return BackendResponse(data=payload, cache_hit=False)

    async def _send_with_retries(
        self,
        method: str,
        endpoint: str,
        *,
        params: Mapping[str, Any],
        json_body: Mapping[str, Any] | None,
        headers: Mapping[str, str],
    ) -> dict[str, Any]:
        assert self._http_client is not None
        max_attempts = 1 + self.settings.backend_max_retries

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_random_exponential(multiplier=0.2, max=2.0),
                retry=retry_if_exception_type((*_RETRYABLE_TRANSPORT_ERRORS, _RetryableUpstreamStatus)),
                reraise=True,
            ):
                with attempt:
                    try:
                        response = await self._http_client.request(
                            method=method,
                            url=endpoint,
                            params=params or None,
                            json=json_body,
                            headers=headers,
                        )
                    except _RETRYABLE_TRANSPORT_ERRORS as exc:
                        logger.warning(
                            "Backend transport error",
                            method=method,
                            endpoint=endpoint,
                            attempt=attempt.retry_state.attempt_number,
                            max_attempts=max_attempts,
                            error_type=type(exc).__name__,
                        )
                        raise
                    if response.status_code in _RETRYABLE_STATUS_CODES:
                        logger.warning(
                            "Retryable backend HTTP error",
                            method=method,
                            endpoint=endpoint,
                            status_code=response.status_code,
                            attempt=attempt.retry_state.attempt_number,
                        )
                        raise _RetryableUpstreamStatus(response)
                    return self._handle_response(endpoint, response)
        except _RetryableUpstreamStatus as exc:
            return self._handle_response(endpoint, exc.response)
        except _RETRYABLE_TRANSPORT_ERRORS as exc:
            raise UpstreamProviderError(
                f"Upstream backend connection failed calling {endpoint}: {type(exc).__name__}.",
                details={"endpoint": endpoint, "error_type": type(exc).__name__},
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamProviderError(
                f"Upstream HTTP transport error calling {endpoint}: {type(exc).__name__}.",
                details={"endpoint": endpoint},
            ) from exc

        raise UpstreamProviderError(f"Exhausted retries calling {endpoint}.")

    @staticmethod
    def _parse_error_payload(response: httpx.Response) -> tuple[str | None, str]:
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("detail")
                if isinstance(detail, dict):
                    code = detail.get("code") or body.get("code")
                    msg = detail.get("message") or str(detail)
                    return (str(code) if code else None), str(msg)
                code = body.get("code")
                msg = body.get("message") or (str(detail) if detail else response.text)
                return (str(code) if code else None), str(msg)
        except Exception:
            pass
        return None, response.text[:300] or f"HTTP {response.status_code}"

    def _handle_response(self, endpoint: str, response: httpx.Response) -> dict[str, Any]:
        status = response.status_code
        if 200 <= status < 300:
            if not response.content:
                return {}
            parsed = response.json()
            if isinstance(parsed, dict):
                return parsed
            return {"items": parsed}

        backend_code, message = self._parse_error_payload(response)

        if status in (400, 422):
            raise InvalidParametersError(
                message or f"Backend rejected request parameters for {endpoint}.",
                details={"endpoint": endpoint, "status_code": status},
            )
        if status in (401, 403):
            raise PermissionDeniedError(
                f"Backend authorization rejected for {endpoint}: {message}",
                details={"endpoint": endpoint, "status_code": status},
            )
        if status == 404:
            if backend_code == "UNSUPPORTED_SYMBOL" or "symbol" in message.lower() and "unsupported" in message.lower():
                raise UnsupportedSymbolError(
                    message,
                    details={"endpoint": endpoint, "status_code": 404},
                )
            raise NoDataAvailableError(
                message or f"No data available at {endpoint}.",
                details={"endpoint": endpoint, "status_code": 404},
            )
        if status == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimitedError(
                f"Upstream rate limit exceeded for {endpoint}.",
                details={"endpoint": endpoint, "retry_after": retry_after},
            )
        if status >= 500:
            raise UpstreamProviderError(
                f"Upstream backend error ({status}) for {endpoint}: {message}",
                details={"endpoint": endpoint, "status_code": status},
            )

        raise InvalidParametersError(
            f"Unexpected backend client error ({status}) for {endpoint}: {message}",
            details={"endpoint": endpoint, "status_code": status},
        )

    async def health_check(self) -> tuple[bool, dict[str, Any]]:
        """Probe upstream FastAPI /health endpoint for readiness checks."""
        if not self.is_open:
            await self.open()
        assert self._http_client is not None
        try:
            resp = await self._http_client.get(
                "/health",
                headers={"X-Internal-API-Key": self.settings.backend_internal_api_key.get_secret_value()},
                timeout=min(2.0, self.settings.backend_connect_timeout_seconds),
            )
            ok = 200 <= resp.status_code < 300
            payload = resp.json() if ok and resp.content else {"status_code": resp.status_code}
            return ok, payload
        except Exception as exc:
            return False, {"error": type(exc).__name__}
