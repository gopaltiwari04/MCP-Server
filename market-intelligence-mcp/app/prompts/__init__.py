"""MCP institutional prompt workflow registration."""

from mcp.server.mcpserver import MCPServer

from app.prompts.workflows import register_workflow_prompts


def register_all_prompts(mcp: MCPServer) -> None:
    """Register institutional quantitative workflow prompts and completions."""
    register_workflow_prompts(mcp)


__all__ = ["register_all_prompts"]
