"""MCPServer initialization, lifespan resource management, and capability registration."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from mcp.server.context import ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.server.subscriptions import InMemorySubscriptionBus
from mcp.types import (
    EmptyResult,
    SetLevelRequestParams,
    SubscribeRequestParams,
    UnsubscribeRequestParams,
)

from app.auth.context import get_security_context
from app.clients.backend_client import BackendClient
from app.clients.cache import TieredTTLCache
from app.clients.circuit_breaker import CircuitBreaker
from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.prompts import register_all_prompts
from app.resources import register_all_resources
from app.tools import register_all_tools
from app.tools.helpers import ServerRuntime, set_fallback_runtime

logger = get_logger(__name__)

_SERVER_INSTRUCTIONS = (
    "Market Intelligence MCP Server: institutional market data, quantitative return/risk analytics, "
    "portfolio VaR/CVaR attribution, stateless rebalance simulation, and workspace actions. "
    "Always verify data provenance (`data_timestamp`, `is_stale`, `source`, `request_id`) in every response. "
    "Never extrapolate or invent financial numbers when `NO_DATA_AVAILABLE` or `STALE_DATA` is reported."
)


def create_mcp_server(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> MCPServer[ServerRuntime]:
    """Build and wire the MCPServer instance with all tools, resources, prompts, and lifespan."""
    cfg = settings or get_settings()
    subscribed_uris: dict[str, set[str]] = {}
    subscription_bus = InMemorySubscriptionBus()

    @asynccontextmanager
    async def server_lifespan(_server: MCPServer[ServerRuntime]) -> AsyncIterator[ServerRuntime]:
        cache = TieredTTLCache(max_size=cfg.cache_max_size)
        circuit_breaker = CircuitBreaker(
            failure_threshold=cfg.circuit_breaker_failure_threshold,
            recovery_timeout_seconds=cfg.circuit_breaker_recovery_timeout_seconds,
        )
        backend_client = BackendClient(
            cfg,
            cache=cache,
            circuit_breaker=circuit_breaker,
            http_client=http_client,
            transport=transport,
        )
        await backend_client.open()
        runtime = ServerRuntime(
            settings=cfg,
            cache=cache,
            circuit_breaker=circuit_breaker,
            backend_client=backend_client,
        )
        set_fallback_runtime(runtime)
        logger.info(
            "Market Intelligence MCP Server lifespan initialized",
            server_name=cfg.server_name,
            version=cfg.server_version,
            backend_base_url=cfg.backend_base_url,
        )
        try:
            yield runtime
        finally:
            set_fallback_runtime(None)
            await backend_client.close()
            logger.info("Market Intelligence MCP Server lifespan closed")

    mcp: MCPServer[ServerRuntime] = MCPServer(
        name=cfg.server_name,
        title="Market Intelligence MCP Gateway",
        description="Zero-Trust Quantitative Market Intelligence & Portfolio Risk MCP Gateway",
        instructions=_SERVER_INSTRUCTIONS,
        version=cfg.server_version,
        lifespan=server_lifespan,
        log_level=cfg.log_level,
        subscriptions=subscription_bus,
    )

    # Register legacy 2025 handshake-era subscription & logging handlers alongside
    # 2026-07-28 subscriptions/listen so every MCP client class has full capabilities.
    async def _handle_subscribe_resource(
        _ctx: ServerRequestContext[ServerRuntime],
        params: SubscribeRequestParams,
    ) -> EmptyResult:
        sec_ctx = get_security_context()
        principal = sec_ctx.user_id if sec_ctx else "anonymous"
        subscribed_uris.setdefault(principal, set()).add(str(params.uri))
        logger.info("Resource subscribed", uri=str(params.uri), principal=principal)
        return EmptyResult()

    async def _handle_unsubscribe_resource(
        _ctx: ServerRequestContext[ServerRuntime],
        params: UnsubscribeRequestParams,
    ) -> EmptyResult:
        sec_ctx = get_security_context()
        principal = sec_ctx.user_id if sec_ctx else "anonymous"
        if principal in subscribed_uris:
            subscribed_uris[principal].discard(str(params.uri))
        logger.info("Resource unsubscribed", uri=str(params.uri), principal=principal)
        return EmptyResult()

    async def _handle_set_logging_level(
        _ctx: ServerRequestContext[ServerRuntime],
        params: SetLevelRequestParams,
    ) -> EmptyResult:
        logger.info("Client requested MCP protocol log level", level=str(params.level))
        return EmptyResult()

    mcp._lowlevel_server.add_request_handler(
        "resources/subscribe",
        SubscribeRequestParams,
        _handle_subscribe_resource,
    )
    mcp._lowlevel_server.add_request_handler(
        "resources/unsubscribe",
        UnsubscribeRequestParams,
        _handle_unsubscribe_resource,
    )
    mcp._lowlevel_server.add_request_handler(
        "logging/setLevel",
        SetLevelRequestParams,
        _handle_set_logging_level,
    )

    register_all_tools(mcp)
    register_all_resources(mcp)
    register_all_prompts(mcp)

    return mcp
