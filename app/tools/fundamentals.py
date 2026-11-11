"""Corporate fundamental ratios and historical earnings surprise tools."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from app.auth.permissions import require_scopes
from app.schemas.common import CalendarType, ResponseEnvelope
from app.schemas.fundamentals import (
    EarningsHistoryData,
    EarningsQuarter,
    FinancialMetricsData,
    FinancialMetricsPeriod,
)
from app.tools.helpers import (
    build_envelope,
    emit_protocol_log,
    get_runtime,
    mcp_tool_boundary,
    parse_utc_datetime,
)
from app.utils.errors import InvalidParametersError
from app.utils.formatting import build_tool_result, format_markdown_table
from app.utils.validators import normalize_symbol


@mcp_tool_boundary("get_financial_metrics")
@require_scopes("market:read")
async def get_financial_metrics(
    symbol: str,
    period: Literal["TTM", "ANNUAL", "QUARTERLY"] = "TTM",
    limit: int = 4,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[FinancialMetricsData]]:
    """Retrieve structured valuation, profitability, liquidity/leverage, and growth metrics.

    When to call:
    - Call for fundamental equity valuation, margin analysis, balance-sheet leverage checks,
      and multi-period growth comparison.

    Parameter rules:
    - `symbol`: Normalized equity ticker.
    - `period`: `TTM` (Trailing Twelve Months, default), `ANNUAL`, or `QUARTERLY`.
    - `limit`: Number of reporting periods to return (1 to 20, default 4).

    Calendar behavior:
    - Fiscal reporting periods (`CALENDAR_DAYS`); cached for 3,600s.

    Output guarantees:
    - Returns `ResponseEnvelope[FinancialMetricsData]` organized into `valuation`,
      `profitability`, `liquidity_leverage`, and `per_share_growth`.
    """
    norm_symbol = normalize_symbol(symbol)
    if limit < 1 or limit > 20:
        raise InvalidParametersError(f"limit must be between 1 and 20; got {limit}.")

    runtime = get_runtime(ctx)
    await emit_protocol_log(ctx, "info", f"Fetching {period} financial metrics for {norm_symbol}")

    resp = await runtime.backend_client.request(
        "GET",
        f"/api/v1/fundamentals/metrics/{norm_symbol}",
        params={"period": period, "limit": limit},
        tenant_scope="PUBLIC",
        ttl_seconds=runtime.settings.ttl_metrics_seconds,
    )
    raw = resp.data
    raw_periods = raw.get("periods", [])
    periods = [FinancialMetricsPeriod.model_validate(p) for p in raw_periods][:limit]
    currency = str(raw.get("currency", "USD"))

    payload = FinancialMetricsData(
        symbol=norm_symbol,
        period_type=period,
        currency=currency,
        periods=periods,
    )
    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))

    envelope = build_envelope(
        data=payload,
        source=str(raw.get("source", "fastapi-fundamentals")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_fundamentals_seconds,
        currency=currency,
        units="ratios_and_margins",
        calendar_type=CalendarType.CALENDAR_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        no_data=(len(periods) == 0),
        warnings=list(raw.get("warnings", [])),
    )

    md = format_markdown_table(
        ["Period", "P/E", "EV/EBITDA", "Gross Margin", "Op Margin", "ROE", "Rev YoY"],
        [
            [
                p.fiscal_period,
                p.valuation.pe_ratio,
                p.valuation.ev_to_ebitda,
                p.profitability.gross_margin,
                p.profitability.operating_margin,
                p.profitability.roe,
                p.per_share_growth.revenue_growth_yoy,
            ]
            for p in periods
        ],
    )
    return build_tool_result(envelope, md or f"No financial metrics returned for {norm_symbol}.")


@mcp_tool_boundary("get_earnings_history")
@require_scopes("market:read")
async def get_earnings_history(
    symbol: str,
    quarters: int = 8,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[EarningsHistoryData]]:
    """Retrieve historical quarterly EPS/revenue consensus vs. actuals and next earnings date.

    When to call:
    - Call before earnings events or to evaluate historical beat/miss consistency.

    Parameter rules:
    - `symbol`: Normalized equity ticker.
    - `quarters`: Number of historical quarters (1 to 24, default 8).

    Calendar behavior:
    - Fiscal announcement calendar (`CALENDAR_DAYS`); cached for 3,600s.

    Output guarantees:
    - Returns `ResponseEnvelope[EarningsHistoryData]` with EPS/revenue surprises and
      `next_earnings_date` if scheduled.
    """
    norm_symbol = normalize_symbol(symbol)
    if quarters < 1 or quarters > 24:
        raise InvalidParametersError(f"quarters must be between 1 and 24; got {quarters}.")

    runtime = get_runtime(ctx)
    await emit_protocol_log(ctx, "info", f"Fetching {quarters} quarters of earnings history for {norm_symbol}")

    resp = await runtime.backend_client.request(
        "GET",
        f"/api/v1/fundamentals/earnings/{norm_symbol}",
        params={"quarters": quarters},
        tenant_scope="PUBLIC",
        ttl_seconds=runtime.settings.ttl_earnings_seconds,
    )
    raw = resp.data
    raw_quarters = raw.get("quarters", [])
    parsed_quarters = [EarningsQuarter.model_validate(q) for q in raw_quarters][:quarters]
    currency = str(raw.get("currency", "USD"))

    payload = EarningsHistoryData(
        symbol=norm_symbol,
        currency=currency,
        next_earnings_date=raw.get("next_earnings_date"),
        quarters_returned=len(parsed_quarters),
        quarters=parsed_quarters,
    )
    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))

    envelope = build_envelope(
        data=payload,
        source=str(raw.get("source", "fastapi-fundamentals")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_fundamentals_seconds,
        currency=currency,
        units="eps_and_revenue",
        calendar_type=CalendarType.CALENDAR_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        no_data=(len(parsed_quarters) == 0),
        warnings=list(raw.get("warnings", [])),
    )

    md = format_markdown_table(
        ["Quarter", "Report Date", "EPS Est", "EPS Act", "Surprise %", "Rev Act"],
        [
            [
                q.fiscal_quarter,
                q.report_date.isoformat(),
                q.eps_consensus,
                q.eps_actual,
                q.eps_surprise_pct,
                q.revenue_actual,
            ]
            for q in parsed_quarters
        ],
    )
    return build_tool_result(envelope, md or f"No earnings history available for {norm_symbol}.")


def register_fundamentals_tools(mcp: MCPServer) -> None:
    """Register fundamental metrics and earnings history tools onto the MCPServer."""
    read_annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
    mcp.add_tool(get_financial_metrics, annotations=read_annotations)
    mcp.add_tool(get_earnings_history, annotations=read_annotations)
