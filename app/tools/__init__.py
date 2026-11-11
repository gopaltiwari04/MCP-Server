"""MCP tool registration modules."""

from mcp.server.mcpserver import MCPServer

from app.tools.comparison import register_comparison_tools
from app.tools.discovery import register_discovery_tools
from app.tools.fundamentals import register_fundamentals_tools
from app.tools.market_data import register_market_data_tools
from app.tools.portfolio import register_portfolio_tools
from app.tools.technical_analysis import register_technical_analysis_tools
from app.tools.workspace_actions import register_workspace_tools


def register_all_tools(mcp: MCPServer) -> None:
    """Register all 15 Market Intelligence MCP tools."""
    register_discovery_tools(mcp)
    register_market_data_tools(mcp)
    register_fundamentals_tools(mcp)
    register_technical_analysis_tools(mcp)
    register_comparison_tools(mcp)
    register_portfolio_tools(mcp)
    register_workspace_tools(mcp)


__all__ = ["register_all_tools"]
