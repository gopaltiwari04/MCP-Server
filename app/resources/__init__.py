"""MCP resource registration modules."""

from mcp.server.mcpserver import MCPServer

from app.resources.market_resources import register_market_resources
from app.resources.portfolio_resources import register_portfolio_resources
from app.resources.system_resources import register_system_resources


def register_all_resources(mcp: MCPServer) -> None:
    """Register static and dynamic URI template resources onto the MCPServer."""
    register_system_resources(mcp)
    register_market_resources(mcp)
    register_portfolio_resources(mcp)


__all__ = ["register_all_resources"]
