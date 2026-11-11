"""Dynamic market instrument snapshot URI template resource."""

import asyncio
import json

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError

from app.auth.context import reset_current_tool_name, set_current_tool_name
from app.auth.permissions import assert_scopes
from app.tools.helpers import get_runtime
from app.utils.errors import MarketIntelligenceError, NoDataAvailableError, UnsupportedSymbolError
from app.utils.validators import normalize_symbol


async def read_instrument_snapshot(symbol: str, ctx: Context) -> str:
    """Concurrent composite snapshot of corporate profile, latest quote, and TTM metrics."""
    token = set_current_tool_name("resource:instrument_snapshot")
    try:
        assert_scopes("market:read")
        norm_symbol = normalize_symbol(symbol)
        runtime = get_runtime(ctx)

        profile_task = runtime.backend_client.request(
            "GET",
            f"/api/v1/fundamentals/profile/{norm_symbol}",
            tenant_scope="PUBLIC",
            ttl_seconds=runtime.settings.ttl_profile_seconds,
        )
        quote_task = runtime.backend_client.request(
            "GET",
            f"/api/v1/market/quotes/{norm_symbol}",
            tenant_scope="PUBLIC",
            ttl_seconds=runtime.settings.ttl_quote_seconds,
        )
        metrics_task = runtime.backend_client.request(
            "GET",
            f"/api/v1/fundamentals/metrics/{norm_symbol}",
            params={"period": "TTM", "limit": 1},
            tenant_scope="PUBLIC",
            ttl_seconds=runtime.settings.ttl_metrics_seconds,
        )

        profile_res, quote_res, metrics_res = await asyncio.gather(
            profile_task,
            quote_task,
            metrics_task,
            return_exceptions=True,
        )

        errors: list[str] = []
        profile_data = None
        quote_data = None
        metrics_data = None

        if isinstance(profile_res, BaseException):
            errors.append(f"profile: {profile_res}")
        else:
            profile_data = profile_res.data

        if isinstance(quote_res, BaseException):
            errors.append(f"quote: {quote_res}")
        else:
            quote_data = quote_res.data

        if isinstance(metrics_res, BaseException):
            errors.append(f"metrics: {metrics_res}")
        else:
            metrics_data = metrics_res.data

        if profile_data is None and quote_data is None and metrics_data is None:
            # Propagate primary domain error deterministically
            for candidate in (quote_res, profile_res, metrics_res):
                if isinstance(candidate, NoDataAvailableError | UnsupportedSymbolError):
                    raise ResourceNotFoundError(f"Unknown instrument {norm_symbol}: {candidate.message}")
                if isinstance(candidate, MarketIntelligenceError):
                    raise ResourceError(f"{candidate.code.value}: {candidate.message}")
            raise ResourceNotFoundError(f"No snapshot data found for {norm_symbol}.")

        snapshot = {
            "symbol": norm_symbol,
            "profile": profile_data,
            "quote": quote_data,
            "ttm_metrics": metrics_data,
            "partial_warnings": errors,
        }
        return (
            f"# Instrument Snapshot: {norm_symbol}\n\n"
            f"```json\n{json.dumps(snapshot, indent=2, default=str)}\n```"
        )
    except (ResourceError, ResourceNotFoundError):
        raise
    except MarketIntelligenceError as exc:
        raise ResourceError(f"{exc.code.value}: {exc.message}") from exc
    finally:
        reset_current_tool_name(token)


def register_market_resources(mcp: MCPServer) -> None:
    """Register dynamic market instrument snapshot resource template."""
    mcp.resource(
        "market://instrument/{symbol}/snapshot",
        name="instrument_snapshot",
        title="Composite Instrument Snapshot",
        description="High-density concurrent snapshot combining corporate profile, live quote, and TTM metrics.",
        mime_type="text/markdown",
    )(read_instrument_snapshot)
