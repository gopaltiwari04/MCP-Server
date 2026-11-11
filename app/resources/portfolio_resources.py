"""User-isolated portfolio summary URI template resource."""

import json

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError

from app.auth.context import reset_current_tool_name, set_current_tool_name
from app.auth.permissions import assert_scopes
from app.tools.helpers import get_runtime
from app.utils.errors import MarketIntelligenceError, NoDataAvailableError
from app.utils.validators import validate_identifier


async def read_portfolio_summary(portfolio_id: str, ctx: Context) -> str:
    """User-isolated resource returning current portfolio holdings and risk snapshot."""
    token = set_current_tool_name("resource:portfolio_summary")
    try:
        sec_ctx = assert_scopes("portfolio:read")
        clean_id = validate_identifier(portfolio_id, name="portfolio_id")
        runtime = get_runtime(ctx)

        resp = await runtime.backend_client.request(
            "GET",
            f"/api/v1/portfolios/{clean_id}/analysis",
            params={"benchmark_symbol": "SPY", "confidence_level": 0.95, "lookback_days": 252},
            tenant_scope=sec_ctx.user_id,
            ttl_seconds=runtime.settings.ttl_portfolio_analysis_seconds,
            cache_tags=(f"user:{sec_ctx.user_id}:portfolio:{clean_id}",),
        )
        summary = {
            "portfolio_id": clean_id,
            "owner_subject": sec_ctx.user_id,
            "cache_hit": resp.cache_hit,
            "analysis": resp.data,
        }
        return (
            f"# Portfolio Summary: {clean_id}\n\n"
            f"```json\n{json.dumps(summary, indent=2, default=str)}\n```"
        )
    except NoDataAvailableError as exc:
        raise ResourceNotFoundError(f"Portfolio {portfolio_id!r} not found.") from exc
    except MarketIntelligenceError as exc:
        raise ResourceError(f"{exc.code.value}: {exc.message}") from exc
    finally:
        reset_current_tool_name(token)


def register_portfolio_resources(mcp: MCPServer) -> None:
    """Register user-isolated portfolio summary resource template."""
    mcp.resource(
        "portfolio://user/{portfolio_id}/summary",
        name="portfolio_summary",
        title="User Portfolio Holdings & Risk Summary",
        description="Tenant-isolated snapshot of portfolio holdings, allocations, NAV, and VaR/CVaR metrics.",
        mime_type="text/markdown",
    )(read_portfolio_summary)
