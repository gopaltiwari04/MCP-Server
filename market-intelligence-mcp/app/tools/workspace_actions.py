"""Controlled write & workspace mutation tools (watchlists, alerts, research memos)."""

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from app.auth.permissions import assert_any_scope, assert_scopes, require_scopes
from app.schemas.common import CalendarType, ResponseEnvelope
from app.schemas.portfolio import PriceAlertData, ResearchMemoData, WatchlistData
from app.tools.helpers import (
    build_envelope,
    emit_protocol_log,
    get_runtime,
    mcp_tool_boundary,
    parse_utc_datetime,
)
from app.utils.errors import InvalidParametersError
from app.utils.formatting import build_tool_result
from app.utils.validators import normalize_symbol, normalize_symbols, slugify_watchlist_id


def _derive_idempotency_key(user_id: str, op: str, material: str, explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()[:64]
    digest = hashlib.sha256(f"{user_id}|{op}|{material}".encode("utf-8")).hexdigest()[:32]
    return f"mcp-{digest}"


@mcp_tool_boundary("manage_watchlist")
async def manage_watchlist(
    action: Literal["LIST", "ADD", "REMOVE"],
    watchlist_name: str = "Default",
    symbols: list[str] | None = None,
    idempotency_key: str | None = None,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[WatchlistData]]:
    """List, add, or remove symbols in a user's watchlist with idempotent mutation semantics.

    When to call:
    - Call when the user explicitly asks to inspect, add tickers to, or remove tickers from
      their watchlist.

    Parameter rules:
    - `action`: `LIST`, `ADD`, or `REMOVE`.
    - `watchlist_name`: Target watchlist name (default `Default`).
    - `symbols`: Required non-empty list (1-25 tickers) for `ADD` and `REMOVE`.
    - `idempotency_key`: Optional caller-supplied idempotency key for safe retries.

    Security & Side Effects:
    - `LIST` requires `portfolio:read` or `portfolio:write`.
    - `ADD` / `REMOVE` require `portfolio:write`, send `Idempotency-Key`, invalidate cached
      watchlist reads for the user, and emit MCP resource update notifications.
    """
    if action == "LIST":
        sec_ctx = assert_any_scope("portfolio:read", "portfolio:write")
        norm_symbols = normalize_symbols(symbols, min_count=1, max_count=25) if symbols else []
    else:
        sec_ctx = assert_scopes("portfolio:write")
        if not symbols:
            raise InvalidParametersError(f"symbols list is required when action={action!r}.")
        norm_symbols = normalize_symbols(symbols, min_count=1, max_count=25)

    watchlist_id = slugify_watchlist_id(watchlist_name)
    runtime = get_runtime(ctx)
    idem_key = _derive_idempotency_key(
        sec_ctx.user_id,
        f"watchlist:{action}",
        f"{watchlist_id}:{','.join(norm_symbols)}:{sec_ctx.request_id}",
        idempotency_key,
    )

    await emit_protocol_log(
        ctx,
        "info",
        f"Watchlist {action} on '{watchlist_name}' ({watchlist_id}) symbols={norm_symbols}",
    )

    is_list = action == "LIST"
    read_ttl = float(runtime.settings.ttl_portfolio_analysis_seconds) if is_list else 0.0
    cache_tags = (f"user:{sec_ctx.user_id}:watchlists",) if is_list else ()
    invalidate_tags = (f"user:{sec_ctx.user_id}:watchlists",) if not is_list else ()
    extra_headers = {"Idempotency-Key": idem_key} if not is_list else None

    resp = await runtime.backend_client.request(
        "POST",
        f"/api/v1/watchlists/{watchlist_id}/items",
        json_body={
            "action": action,
            "watchlist_name": watchlist_name.strip(),
            "symbols": norm_symbols,
        },
        tenant_scope=sec_ctx.user_id,
        ttl_seconds=read_ttl,
        cache_tags=cache_tags,
        extra_headers=extra_headers,
        invalidate_tags=invalidate_tags,
    )

    raw = resp.data
    wl = WatchlistData.model_validate(
        {
            "watchlist_id": watchlist_id,
            "watchlist_name": watchlist_name.strip(),
            "action": action,
            **raw,
        }
    )

    if not is_list and ctx is not None:
        try:
            await ctx.notify_resource_updated(f"portfolio://user/{watchlist_id}/summary")
        except Exception:
            pass

    data_ts = parse_utc_datetime(raw.get("data_timestamp") or wl.updated_at, default=datetime.now(UTC))
    envelope = build_envelope(
        data=wl,
        source=str(raw.get("source", "fastapi-watchlists")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_portfolio_seconds,
        currency=None,
        units="watchlist_symbols",
        calendar_type=CalendarType.CALENDAR_DAYS,
        cache_hit=resp.cache_hit,
        warnings=list(raw.get("warnings", [])),
    )

    md = (
        f"### Watchlist `{wl.watchlist_name}` (`{wl.action}`)\n"
        f"- **Symbols ({len(wl.symbols)}):** {', '.join(wl.symbols) if wl.symbols else 'Empty'}"
    )
    return build_tool_result(envelope, md)


@mcp_tool_boundary("create_price_alert")
@require_scopes("portfolio:write")
async def create_price_alert(
    symbol: str,
    condition: Literal["CROSSES_ABOVE", "CROSSES_BELOW", "PCT_CHANGE_1D_EXCEEDS"],
    threshold_value: float,
    note: str | None = None,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[PriceAlertData]]:
    """Create a user-scoped market price or 1-day percentage change alert rule.

    When to call:
    - Call when the user asks to be alerted on a price breakout, support breakdown, or
      single-day move threshold.

    Parameter rules:
    - `symbol`: Normalized ticker symbol.
    - `condition`: `CROSSES_ABOVE`, `CROSSES_BELOW`, or `PCT_CHANGE_1D_EXCEEDS`.
    - `threshold_value`: Strictly positive price or percentage threshold.
    - `note`: Optional memo up to 280 characters.

    Security:
    - Requires `portfolio:write` scope; scoped strictly to the authenticated JWT subject.
    """
    norm_symbol = normalize_symbol(symbol)
    if threshold_value <= 0:
        raise InvalidParametersError(f"threshold_value must be > 0; got {threshold_value}.")
    cleaned_note = note.strip()[:280] if note and note.strip() else None

    sec_ctx = assert_scopes("portfolio:write")
    runtime = get_runtime(ctx)
    idem_key = _derive_idempotency_key(
        sec_ctx.user_id,
        "alert:create",
        f"{norm_symbol}:{condition}:{threshold_value}:{sec_ctx.request_id}",
        None,
    )

    await emit_protocol_log(
        ctx,
        "info",
        f"Creating price alert for {norm_symbol}: {condition} {threshold_value}",
    )

    resp = await runtime.backend_client.request(
        "POST",
        "/api/v1/alerts",
        json_body={
            "symbol": norm_symbol,
            "condition": condition,
            "threshold_value": threshold_value,
            "note": cleaned_note,
        },
        tenant_scope=sec_ctx.user_id,
        ttl_seconds=0.0,
        extra_headers={"Idempotency-Key": idem_key},
    )

    raw = resp.data
    alert = PriceAlertData.model_validate(
        {
            "symbol": norm_symbol,
            "condition": condition,
            "threshold_value": threshold_value,
            "note": cleaned_note,
            **raw,
        }
    )
    data_ts = parse_utc_datetime(raw.get("data_timestamp") or alert.created_at, default=datetime.now(UTC))

    envelope = build_envelope(
        data=alert,
        source=str(raw.get("source", "fastapi-alerts")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_portfolio_seconds,
        currency=None,
        units="alert_rule",
        calendar_type=CalendarType.TRADING_DAYS,
        cache_hit=False,
        warnings=list(raw.get("warnings", [])),
    )

    md = (
        f"### Price Alert Created (`{alert.alert_id}`)\n"
        f"- **Rule:** `{alert.symbol}` `{alert.condition}` `{alert.threshold_value}` (`{alert.status}`)"
    )
    return build_tool_result(envelope, md)


@mcp_tool_boundary("save_research_memo")
@require_scopes("research:write")
async def save_research_memo(
    title: str,
    symbols: list[str],
    thesis_markdown: str,
    sentiment: Literal["BULLISH", "NEUTRAL", "BEARISH"],
    cited_data_timestamps: list[str],
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[ResearchMemoData]]:
    """Persist an AI-generated equity/macro research memo grounded in cited data timestamps.

    When to call:
    - Call at the end of a research workflow to persist the synthesized investment thesis
      and exact `data_timestamp` provenance values into the user's workspace.

    Parameter rules:
    - `title`: Non-empty title (3-160 characters).
    - `symbols`: 1 to 15 related ticker symbols.
    - `thesis_markdown`: Non-empty Markdown investment thesis (up to 32,000 chars).
    - `sentiment`: `BULLISH`, `NEUTRAL`, or `BEARISH`.
    - `cited_data_timestamps`: Non-empty list of ISO-8601 timestamps from tool provenance
      metadata backing the numbers in the memo.

    Security:
    - Requires `research:write` scope; scoped strictly to the authenticated JWT subject.
    """
    cleaned_title = title.strip()
    if len(cleaned_title) < 3 or len(cleaned_title) > 160:
        raise InvalidParametersError("title must be between 3 and 160 characters.")
    norm_symbols = normalize_symbols(symbols, min_count=1, max_count=15)
    cleaned_thesis = thesis_markdown.strip()
    if len(cleaned_thesis) < 10 or len(cleaned_thesis) > 32000:
        raise InvalidParametersError("thesis_markdown must be between 10 and 32000 characters.")
    if not cited_data_timestamps or any(not str(ts).strip() for ts in cited_data_timestamps):
        raise InvalidParametersError(
            "cited_data_timestamps must contain at least one non-empty ISO-8601 provenance timestamp."
        )

    sec_ctx = assert_scopes("research:write")
    runtime = get_runtime(ctx)
    idem_key = _derive_idempotency_key(
        sec_ctx.user_id,
        "memo:save",
        f"{cleaned_title}:{','.join(norm_symbols)}:{sec_ctx.request_id}",
        None,
    )

    await emit_protocol_log(
        ctx,
        "info",
        f"Saving research memo {cleaned_title!r} for symbols={norm_symbols} ({sentiment})",
    )

    resp = await runtime.backend_client.request(
        "POST",
        "/api/v1/research/memos",
        json_body={
            "title": cleaned_title,
            "symbols": norm_symbols,
            "thesis_markdown": cleaned_thesis,
            "sentiment": sentiment,
            "cited_data_timestamps": [str(ts).strip() for ts in cited_data_timestamps],
        },
        tenant_scope=sec_ctx.user_id,
        ttl_seconds=0.0,
        extra_headers={"Idempotency-Key": idem_key},
    )

    raw = resp.data
    memo = ResearchMemoData.model_validate(
        {
            "title": cleaned_title,
            "symbols": norm_symbols,
            "sentiment": sentiment,
            "cited_data_timestamps": [str(ts).strip() for ts in cited_data_timestamps],
            **raw,
        }
    )
    data_ts = parse_utc_datetime(raw.get("data_timestamp") or memo.created_at, default=datetime.now(UTC))

    envelope = build_envelope(
        data=memo,
        source=str(raw.get("source", "fastapi-research-notes")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_portfolio_seconds,
        currency=None,
        units="research_memo",
        calendar_type=CalendarType.CALENDAR_DAYS,
        cache_hit=False,
        warnings=list(raw.get("warnings", [])),
    )

    md = (
        f"### Research Memo Saved (`{memo.memo_id}`)\n"
        f"- **Title:** {memo.title} | **Sentiment:** `{memo.sentiment}`\n"
        f"- **Symbols:** {', '.join(memo.symbols)} | **Citations:** {len(memo.cited_data_timestamps)}"
    )
    return build_tool_result(envelope, md)


def register_workspace_tools(mcp: MCPServer) -> None:
    """Register controlled workspace write tools onto the MCPServer."""
    mcp.add_tool(
        manage_watchlist,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    mcp.add_tool(
        create_price_alert,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    mcp.add_tool(
        save_research_memo,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
