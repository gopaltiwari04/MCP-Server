"""Context-window compaction and dual Markdown + JSON MCP response formatters."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar

from mcp.types import CallToolResult, TextContent

from app.schemas.common import ResponseEnvelope

T = TypeVar("T")


def _escape_md_cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".") if abs(value) < 10 else f"{value:,.2f}"
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text


def format_markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a compact GitHub-flavored Markdown table."""
    if not headers:
        return ""
    header_line = "| " + " | ".join(_escape_md_cell(h) for h in headers) + " |"
    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = [
        "| " + " | ".join(_escape_md_cell(cell) for cell in row) + " |"
        for row in rows
    ]
    return "\n".join([header_line, sep_line, *body_lines])


def compact_series_for_context(
    items: Sequence[T],
    *,
    max_items: int = 120,
    head: int = 20,
    tail: int = 100,
) -> tuple[list[T], bool]:
    """Keep full data when within budget, or retain head + tail to protect LLM context windows."""
    if len(items) <= max_items:
        return list(items), False
    if head + tail >= len(items):
        return list(items), False
    compacted = [*items[:head], *items[-tail:]]
    return compacted, True


def build_tool_result(
    envelope: ResponseEnvelope[Any],
    markdown_summary: str | None = None,
    *,
    is_error: bool = False,
) -> CallToolResult:
    """Build a dual-format MCP CallToolResult carrying JSON + structuredContent + Markdown."""
    payload_json = envelope.model_dump_json(by_alias=True)
    payload_dict = envelope.model_dump(mode="json", by_alias=True)
    blocks: list[TextContent] = [TextContent(type="text", text=payload_json)]
    if markdown_summary:
        blocks.append(TextContent(type="text", text=markdown_summary))
    return CallToolResult(
        content=blocks,
        structured_content=payload_dict,
        is_error=is_error,
    )
