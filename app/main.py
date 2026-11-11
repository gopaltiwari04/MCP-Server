"""ASGI application factory, health probes, and Streamable HTTP / stdio entrypoints."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import httpx
import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.auth.context import RequestSecurityContext, reset_security_context, set_security_context
from app.auth.middleware import SlidingWindowRateLimiter, ZeroTrustAuthMiddleware
from app.config.logging import configure_logging, get_logger
from app.config.settings import Settings, get_settings
from app.server import create_mcp_server
from app.tools.helpers import get_runtime

logger = get_logger(__name__)


def create_asgi_app(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    rate_limiter: SlidingWindowRateLimiter | None = None,
    configure_logs: bool = True,
) -> ASGIApp:
    """Build the production ASGI application wrapping Streamable HTTP with Zero-Trust auth."""
    cfg = settings or get_settings()
    if configure_logs:
        configure_logging(cfg, stream=sys.stderr)

    mcp_server = create_mcp_server(cfg, http_client=http_client, transport=transport)

    @mcp_server.custom_route("/health/live", methods=["GET"], include_in_schema=False)
    async def health_live(_request: Request) -> Response:
        return JSONResponse(
            {
                "status": "live",
                "service": cfg.server_name,
                "version": cfg.server_version,
            }
        )

    @mcp_server.custom_route("/health/ready", methods=["GET"], include_in_schema=False)
    async def health_ready(_request: Request) -> Response:
        try:
            runtime = get_runtime()
        except RuntimeError:
            return JSONResponse(
                {"status": "not_ready", "reason": "runtime_uninitialized"},
                status_code=503,
            )

        backend_ok, backend_details = await runtime.backend_client.health_check()
        cb_snapshot = runtime.circuit_breaker.snapshot()
        cache_stats = runtime.backend_client.single_flight.stats()
        is_ready = backend_ok and cb_snapshot["state"] != "OPEN"

        return JSONResponse(
            {
                "status": "ready" if is_ready else "degraded",
                "service": cfg.server_name,
                "version": cfg.server_version,
                "backend": {"reachable": backend_ok, **backend_details},
                "circuit_breaker": cb_snapshot,
                "cache": cache_stats,
            },
            status_code=200 if is_ready else 503,
        )

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=cfg.enable_dns_rebinding_protection,
        allowed_hosts=cfg.allowed_hosts,
        allowed_origins=cfg.allowed_origins,
    )

    starlette_app = mcp_server.streamable_http_app(
        streamable_http_path=cfg.streamable_http_path,
        json_response=cfg.json_response,
        stateless_http=cfg.stateless_http,
        max_request_body_size=cfg.max_request_body_size,
        transport_security=transport_security,
        host=cfg.host,
    )

    return ZeroTrustAuthMiddleware(
        starlette_app,
        settings=cfg,
        rate_limiter=rate_limiter,
    )


def run_stdio(settings: Settings | None = None) -> None:
    """Run the MCP server over stdio transport with a local non-HTTP security context."""
    cfg = settings or get_settings()
    configure_logging(cfg, stream=sys.stderr)
    mcp_server = create_mcp_server(cfg)

    stdio_ctx = RequestSecurityContext(
        user_id=cfg.stdio_user_id,
        client_id=cfg.stdio_client_id,
        auth_mode="STDIO_LOCAL",
        scopes=frozenset(cfg.stdio_scopes),
        delegated_jwt=None,
        internal_api_key_verified=False,
        issuer="stdio://local",
        audience=cfg.server_name,
        token_expires_at=None,
        request_id="stdio-session",
    )
    token = set_security_context(stdio_ctx)
    try:
        logger.info("Starting Market Intelligence MCP Server on stdio transport")
        mcp_server.run(transport="stdio")
    finally:
        reset_security_context(token)


def run_http(settings: Settings | None = None, *, host: str | None = None, port: int | None = None) -> None:
    """Run the MCP server over Streamable HTTP transport via Uvicorn."""
    cfg = settings or get_settings()
    asgi_app = create_asgi_app(cfg)
    uvicorn.run(
        asgi_app,
        host=host or cfg.host,
        port=port or cfg.port,
        log_level=cfg.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


def cli(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint supporting `--transport streamable-http` and `--transport stdio`."""
    parser = argparse.ArgumentParser(description="Market Intelligence MCP Server")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        default="streamable-http",
        help="MCP transport protocol (default: streamable-http)",
    )
    parser.add_argument("--host", default=None, help="Bind host for streamable-http transport")
    parser.add_argument("--port", type=int, default=None, help="Bind port for streamable-http transport")
    args = parser.parse_args(list(argv) if argv is not None else None)

    settings = get_settings()
    if args.transport == "stdio":
        run_stdio(settings)
    else:
        run_http(settings, host=args.host, port=args.port)


# Module-level ASGI app for `uvicorn app.main:app`
app = create_asgi_app(configure_logs=False)


if __name__ == "__main__":
    cli()
