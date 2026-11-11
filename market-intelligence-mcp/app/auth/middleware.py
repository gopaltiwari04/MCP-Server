"""Zero-Trust ASGI Authentication & Rate-Limiting Middleware."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable

import structlog
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from starlette.authentication import AuthCredentials
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth.context import (
    RequestSecurityContext,
    reset_security_context,
    set_security_context,
)
from app.auth.identity import (
    AuthenticationError,
    build_protected_resource_metadata,
    verify_delegated_jwt,
    verify_oauth_jwt,
)
from app.config.logging import get_logger
from app.config.settings import Settings

logger = get_logger(__name__)

_REQUEST_ID_SAFE_RE = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")

_PUBLIC_PATHS = frozenset(
    {
        "/health/live",
        "/health/ready",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    }
)


class SlidingWindowRateLimiter:
    """Async sliding-window per-principal rate limiter."""

    def __init__(
        self,
        *,
        max_requests: int = 120,
        window_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check_and_record(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = self._clock()
        cutoff = now - self.window_seconds
        async with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])) + 1)
                return False, retry_after
            bucket.append(now)
            return True, 0


def _resolve_request_id(headers: Headers) -> str:
    candidate = headers.get("x-request-id", "").strip()
    if candidate and _REQUEST_ID_SAFE_RE.fullmatch(candidate):
        return candidate
    return f"req-{uuid.uuid4().hex}"


def _extract_bearer_token(headers: Headers) -> str | None:
    auth_header = headers.get("authorization")
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


class ZeroTrustAuthMiddleware:
    """ASGI middleware enforcing dual-mode zero-trust authentication and ContextVar binding."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        rate_limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        self.app = app
        self.settings = settings
        self.rate_limiter = rate_limiter or SlidingWindowRateLimiter(
            max_requests=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = _resolve_request_id(headers)
        path = scope.get("path", "")
        method = str(scope.get("method", "GET")).upper()

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                if not any(k.lower() == b"x-request-id" for k, _ in raw_headers):
                    raw_headers.append((b"x-request-id", request_id.encode("ascii")))
                    message = {**message, "headers": raw_headers}
            await send(message)

        structlog.contextvars.bind_contextvars(request_id=request_id, http_path=path, http_method=method)
        try:
            # Public health & RFC 9728 OAuth protected resource discovery endpoints
            if path in _PUBLIC_PATHS and method in ("GET", "OPTIONS", "HEAD"):
                if path.startswith("/.well-known/oauth-protected-resource") and method == "GET":
                    await self._send_json(
                        send_with_request_id,
                        200,
                        build_protected_resource_metadata(self.settings),
                        extra_headers=[
                            (b"access-control-allow-origin", b"*"),
                            (b"cache-control", b"public, max-age=300"),
                        ],
                    )
                    return
                await self.app(scope, receive, send_with_request_id)
                return

            try:
                sec_ctx = self._authenticate(headers, request_id=request_id)
            except AuthenticationError as exc:
                logger.warning(
                    "Authentication rejected",
                    error_code=exc.error_code,
                    reason=exc.message,
                )
                await self._send_auth_error(send_with_request_id, 401, exc.error_code, exc.message)
                return

            principal_key = f"{sec_ctx.user_id}:{sec_ctx.client_id}"
            allowed, retry_after = await self.rate_limiter.check_and_record(principal_key)
            if not allowed:
                logger.warning("Principal rate limit exceeded", user_id=sec_ctx.user_id, retry_after=retry_after)
                await self._send_json(
                    send_with_request_id,
                    429,
                    {
                        "error": "RATE_LIMITED",
                        "error_description": f"Rate limit exceeded. Retry after {retry_after}s.",
                        "retry_after_seconds": retry_after,
                        "request_id": request_id,
                    },
                    extra_headers=[(b"retry-after", str(retry_after).encode("ascii"))],
                )
                return

            # Populate Starlette/MCP SDK user context so StreamableHTTPSessionManager
            # enforces session ownership per (client_id, issuer, subject).
            access_token = AccessToken(
                token=sec_ctx.delegated_jwt or "",
                client_id=sec_ctx.client_id,
                scopes=sorted(sec_ctx.scopes),
                expires_at=sec_ctx.token_expires_at,
                resource=sec_ctx.audience,
                subject=sec_ctx.user_id,
                claims={"iss": sec_ctx.issuer} if sec_ctx.issuer else None,
            )
            scope["user"] = AuthenticatedUser(access_token)
            scope["auth"] = AuthCredentials(sorted(sec_ctx.scopes))

            structlog.contextvars.bind_contextvars(
                user_id=sec_ctx.user_id,
                client_id=sec_ctx.client_id,
                auth_mode=sec_ctx.auth_mode,
            )

            ctx_token = set_security_context(sec_ctx)
            try:
                await self.app(scope, receive, send_with_request_id)
            finally:
                reset_security_context(ctx_token)
        finally:
            structlog.contextvars.clear_contextvars()

    def _authenticate(self, headers: Headers, *, request_id: str) -> RequestSecurityContext:
        internal_key = headers.get("x-internal-api-key")
        bearer_token = _extract_bearer_token(headers)
        session_id = headers.get("mcp-session-id")

        if internal_key is not None:
            expected_key = self.settings.internal_api_key.get_secret_value()
            if not expected_key or not secrets.compare_digest(internal_key, expected_key):
                raise AuthenticationError("Invalid X-Internal-API-Key credential.", error_code="invalid_client")
            if not bearer_token:
                raise AuthenticationError(
                    "Internal requests must include delegated user JWT in Authorization: Bearer <token>."
                )
            claims = verify_delegated_jwt(bearer_token, self.settings)
            return RequestSecurityContext(
                user_id=claims.subject,
                client_id=claims.client_id,
                auth_mode="INTERNAL_DELEGATED",
                scopes=claims.scopes,
                delegated_jwt=bearer_token,
                internal_api_key_verified=True,
                issuer=claims.issuer,
                audience=claims.audience,
                token_expires_at=claims.expires_at,
                request_id=request_id,
                session_id=session_id,
            )

        if not bearer_token:
            raise AuthenticationError("Missing Bearer token or internal service credentials.")

        claims = verify_oauth_jwt(bearer_token, self.settings)
        return RequestSecurityContext(
            user_id=claims.subject,
            client_id=claims.client_id,
            auth_mode="OAUTH2_BEARER",
            scopes=claims.scopes,
            delegated_jwt=bearer_token,
            internal_api_key_verified=False,
            issuer=claims.issuer,
            audience=claims.audience,
            token_expires_at=claims.expires_at,
            request_id=request_id,
            session_id=session_id,
        )

    async def _send_auth_error(self, send: Send, status_code: int, error: str, description: str) -> None:
        base_rs = self.settings.oauth_resource_server_url.rstrip("/")
        if base_rs.endswith("/mcp"):
            base_rs = base_rs[: -len("/mcp")]
        metadata_url = f"{base_rs}/.well-known/oauth-protected-resource"
        www_auth = f'Bearer error="{error}", error_description="{description}", resource_metadata="{metadata_url}"'
        await self._send_json(
            send,
            status_code,
            {"error": error, "error_description": description},
            extra_headers=[(b"www-authenticate", www_auth.encode("latin-1"))],
        )

    @staticmethod
    async def _send_json(
        send: Send,
        status_code: int,
        payload: dict[str, object],
        *,
        extra_headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            *(extra_headers or []),
        ]
        await send({"type": "http.response.start", "status": status_code, "headers": headers})
        await send({"type": "http.response.body", "body": body})
