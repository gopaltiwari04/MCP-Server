"""Real-time market quote and historical OHLCV price tools."""

import statistics
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from app.auth.permissions import require_scopes
from app.schemas.common import CalendarType, Pagination, ResponseEnvelope
from app.schemas.market_data import (
    HistoricalPricesData,
    HistoricalSummaryStats,
    MarketQuoteData,
    OHLCVBar,
)
from app.tools.helpers import (
    build_envelope,
    emit_protocol_log,
    get_runtime,
    mcp_tool_boundary,
    parse_utc_datetime,
)
from app.utils.errors import NoDataAvailableError
from app.utils.formatting import build_tool_result, compact_series_for_context, format_markdown_table
from app.utils.validators import (
    count_trading_days_approx,
    normalize_symbol,
    validate_date_range,
    validate_history_bar_limit,
)

_INTRADAY_INTERVALS = frozenset({"1m", "5m", "15m", "1h"})


def compute_historical_summary_stats(bars: list[OHLCVBar], *, adjusted: bool) -> HistoricalSummaryStats:
    """Compute exact deterministic descriptive statistics and volume-weighted VWAP over bars."""
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [
        (b.adjusted_close if (adjusted and b.adjusted_close is not None) else b.close)
        for b in bars
    ]
    total_volume = sum(b.volume for b in bars)

    vwap: float | None = None
    if total_volume > 0:
        weighted_sum = 0.0
        for b in bars:
            bar_vwap = b.vwap if b.vwap is not None else ((b.high + b.low + b.close) / 3.0)
            weighted_sum += bar_vwap * b.volume
        vwap = round(weighted_sum / total_volume, 6)

    std_close = statistics.stdev(closes) if len(closes) >= 2 else 0.0

    return HistoricalSummaryStats(
        period_high=max(highs),
        period_low=min(lows),
        vwap=vwap,
        mean_close=round(statistics.fmean(closes), 6),
        std_close=round(std_close, 6),
        total_volume=total_volume,
        trading_days_count=len(bars),
    )


@mcp_tool_boundary("get_market_quote")
@require_scopes("market:read")
async def get_market_quote(
    symbol: str,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[MarketQuoteData]]:
    """Fetch latest level-1 quote, bid/ask spread, intraday range, volume, and market cap.

    When to call:
    - Call whenever current price, intraday change, bid/ask spread, or market capitalization
      is required. Do NOT rely on training-data prices.

    Parameter rules:
    - `symbol`: Ticker symbol (1-16 uppercase chars `[A-Z0-9.-^=]`).

    Calendar behavior:
    - `TRADING_DAYS` convention; cached for 5s. Flags `STALE_DATA` automatically if quote
      timestamp lags beyond the configured quote SLA (`stale_quote_seconds`).

    Output guarantees:
    - Returns `ResponseEnvelope[MarketQuoteData]` with exact currency, units (`price_per_share`),
      `is_delayed`, `delay_minutes`, and UTC `data_timestamp`.
    """
    norm_symbol = normalize_symbol(symbol)
    runtime = get_runtime(ctx)
    await emit_protocol_log(ctx, "info", f"Fetching market quote for {norm_symbol}")

    resp = await runtime.backend_client.request(
        "GET",
        f"/api/v1/market/quotes/{norm_symbol}",
        tenant_scope="PUBLIC",
        ttl_seconds=runtime.settings.ttl_quote_seconds,
    )
    raw = resp.data
    if not raw or raw.get("last_price") is None:
        raise NoDataAvailableError(f"No live or delayed quote available for {norm_symbol}.")

    quote = MarketQuoteData.model_validate(raw)
    if quote.spread_bps is None and quote.bid is not None and quote.ask is not None and quote.last_price > 0:
        quote.spread_bps = round(((quote.ask - quote.bid) / quote.last_price) * 10000.0, 2)

    data_ts = parse_utc_datetime(raw.get("data_timestamp") or quote.quote_timestamp, default=datetime.now(UTC))
    warnings = list(raw.get("warnings", []))
    if quote.is_delayed:
        warnings.append(f"Quote is delayed by {quote.delay_minutes} minute(s).")

    envelope = build_envelope(
        data=quote,
        source=str(raw.get("source", "fastapi-market-quotes")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_quote_seconds,
        currency=quote.currency,
        units="price_per_share",
        calendar_type=CalendarType.TRADING_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        warnings=warnings,
    )
    chg_str = f"{quote.change_pct:+.2f}%" if quote.change_pct is not None else "—"
    md = (
        f"### `{quote.symbol}` Quote ({quote.exchange})\n"
        f"- **Last:** {quote.last_price:,.4f} {quote.currency} ({chg_str})\n"
        f"- **Bid / Ask:** {quote.bid or '—'} / {quote.ask or '—'} (Spread: {quote.spread_bps or '—'} bps)\n"
        f"- **Volume:** {quote.volume or '—'} | **Timestamp:** `{envelope.metadata.data_timestamp.isoformat()}`"
    )
    return build_tool_result(envelope, md)


@mcp_tool_boundary("get_historical_prices")
@require_scopes("market:read")
async def get_historical_prices(
    symbol: str,
    start_date: date,
    end_date: date,
    interval: Literal["1m", "5m", "15m", "1h", "1d", "1wk", "1mo"] = "1d",
    adjusted: bool = True,
    include_summary_stats: bool = True,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[HistoricalPricesData]]:
    """Fetch historical OHLCV bars and deterministic period summary statistics.

    When to call:
    - Call when inspecting price history, support/resistance levels, or computing custom windows.

    Parameter rules:
    - `symbol`: Ticker symbol normalized automatically.
    - `start_date`, `end_date`: ISO dates (`YYYY-MM-DD`) with `start_date <= end_date`.
    - `interval`: `1m`, `5m`, `15m`, `1h`, `1d` (default), `1wk`, `1mo`.
    - Maximum 500 bars per call: requests exceeding ~500 bars at the chosen interval return
      `INVALID_PARAMETERS` advising a coarser interval or narrower date window.
    - `adjusted`: Split/dividend adjusted closes when `True` (default).
    - `include_summary_stats`: Computes `period_high`, `period_low`, `vwap`, `mean_close`,
      `std_close`, `total_volume`, and `trading_days_count` deterministically.

    Calendar behavior:
    - Uses `TRADING_DAYS`; intraday intervals cached 60s, daily/weekly/monthly cached 3600s.

    Output guarantees:
    - Returns `ResponseEnvelope[HistoricalPricesData]` with provenance metadata and exact summary
      stats so the caller does not perform mental arithmetic across bars.
    """
    norm_symbol = normalize_symbol(symbol)
    validate_date_range(start_date, end_date)
    runtime = get_runtime(ctx)
    validate_history_bar_limit(start_date, end_date, interval, max_bars=runtime.settings.max_historical_bars)

    await emit_protocol_log(
        ctx,
        "info",
        f"Fetching historical prices for {norm_symbol} ({start_date.isoformat()}..{end_date.isoformat()}, {interval})",
    )

    is_intraday = interval in _INTRADAY_INTERVALS
    ttl = (
        runtime.settings.ttl_history_intraday_seconds
        if is_intraday
        else runtime.settings.ttl_history_daily_seconds
    )
    stale_sla = (
        runtime.settings.stale_history_intraday_seconds
        if is_intraday
        else runtime.settings.stale_history_daily_seconds
    )

    resp = await runtime.backend_client.request(
        "GET",
        f"/api/v1/market/history/{norm_symbol}",
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "interval": interval,
            "adjusted": str(adjusted).lower(),
        },
        tenant_scope="PUBLIC",
        ttl_seconds=ttl,
    )

    raw = resp.data
    raw_bars = raw.get("bars", [])
    bars = [OHLCVBar.model_validate(b) for b in raw_bars]
    warnings = list(raw.get("warnings", []))

    if count_trading_days_approx(start_date, end_date) == 0:
        warnings.append("Requested date window falls entirely on a weekend.")

    has_more = False
    if len(bars) > runtime.settings.max_historical_bars:
        bars = bars[: runtime.settings.max_historical_bars]
        has_more = True
        warnings.append(
            f"Truncated response to {runtime.settings.max_historical_bars} bars; narrow date window for remaining bars."
        )

    summary_stats: HistoricalSummaryStats | None = None
    if include_summary_stats and bars:
        summary_stats = compute_historical_summary_stats(bars, adjusted=adjusted)

    currency = str(raw.get("currency", "USD"))
    payload = HistoricalPricesData(
        symbol=norm_symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        adjusted=adjusted,
        currency=currency,
        bars_count=len(bars),
        was_compacted=False,
        summary_stats=summary_stats,
        bars=bars,
    )

    latest_bar_ts = bars[-1].timestamp if bars else datetime.now(UTC)
    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=latest_bar_ts)
    today_utc = datetime.now(UTC).date()
    enforce_staleness = end_date >= (today_utc - timedelta(days=1))

    envelope = build_envelope(
        data=payload,
        source=str(raw.get("source", "fastapi-market-history")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=stale_sla,
        currency=currency,
        units="ohlcv_bars",
        calendar_type=CalendarType.TRADING_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        enforce_staleness=enforce_staleness,
        no_data=(len(bars) == 0),
        warnings=warnings,
        pagination=Pagination(
            limit=runtime.settings.max_historical_bars,
            offset=0,
            total_count=len(raw_bars),
            has_more=has_more,
        ),
    )

    preview_bars, compacted = compact_series_for_context(bars, max_items=15, head=5, tail=10)
    md = format_markdown_table(
        ["Timestamp", "Open", "High", "Low", "Close", "Volume"],
        [
            [b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume]
            for b in preview_bars
        ],
    )
    if compacted:
        md = f"*Preview showing {len(preview_bars)} of {len(bars)} bars (head + tail).*\n\n" + md
    return build_tool_result(envelope, md or f"No historical bars available for {norm_symbol}.")


def register_market_data_tools(mcp: MCPServer) -> None:
    """Register quote and historical OHLCV tools onto the MCPServer."""
    read_annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
    mcp.add_tool(get_market_quote, annotations=read_annotations)
    mcp.add_tool(get_historical_prices, annotations=read_annotations)
