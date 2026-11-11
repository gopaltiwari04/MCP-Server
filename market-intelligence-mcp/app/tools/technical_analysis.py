"""Quantitative return/risk attribution and technical indicator tools."""

import math
import statistics
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from app.auth.permissions import require_scopes
from app.schemas.analytics import (
    IndicatorPoint,
    IndicatorSnapshot,
    ReturnsData,
    TechnicalIndicatorsData,
)
from app.schemas.common import CalendarType, ResponseEnvelope
from app.tools.helpers import (
    build_envelope,
    emit_protocol_log,
    get_runtime,
    mcp_tool_boundary,
    parse_utc_datetime,
)
from app.utils.errors import InvalidParametersError, NoDataAvailableError
from app.utils.formatting import build_tool_result, format_markdown_table
from app.utils.validators import normalize_symbol, resolve_period_dates

IndicatorName = Literal[
    "SMA_20",
    "SMA_50",
    "SMA_200",
    "EMA_12",
    "EMA_26",
    "RSI_14",
    "MACD",
    "BOLLINGER_BANDS",
    "ATR_14",
    "VWAP",
    "OBV",
]


def _compute_returns_from_series(
    *,
    symbol: str,
    benchmark_symbol: str,
    period: str,
    start_date: date,
    end_date: date,
    calendar_basis: Literal["TRADING_DAYS", "CALENDAR_DAYS"],
    closes: list[float],
    benchmark_closes: list[float] | None,
    risk_free_rate: float,
) -> ReturnsData:
    if len(closes) < 2 or closes[0] <= 0 or closes[-1] <= 0:
        raise NoDataAvailableError(f"Insufficient valid price observations for {symbol} return calculation.")

    annualization = 252.0 if calendar_basis == "TRADING_DAYS" else 365.0
    simple_returns = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0]
    if not simple_returns:
        raise NoDataAvailableError(f"Unable to compute simple returns for {symbol}.")

    n_obs = len(simple_returns)
    cum_ret = (closes[-1] / closes[0]) - 1.0
    log_ret = math.log(closes[-1] / closes[0])
    cagr = ((closes[-1] / closes[0]) ** (annualization / n_obs)) - 1.0

    vol_daily = statistics.stdev(simple_returns) if n_obs >= 2 else 0.0
    ann_vol = vol_daily * math.sqrt(annualization)
    ann_arith_ret = statistics.fmean(simple_returns) * annualization
    sharpe = ((ann_arith_ret - risk_free_rate) / ann_vol) if ann_vol > 0 else 0.0

    peak = closes[0]
    max_dd = 0.0
    for price in closes:
        if price > peak:
            peak = price
        dd = (price / peak) - 1.0
        if dd < max_dd:
            max_dd = dd

    alpha: float | None = None
    beta: float | None = None
    active_return_pct: float | None = None
    if benchmark_closes and len(benchmark_closes) == len(closes) and benchmark_closes[0] > 0:
        bench_returns = [
            (benchmark_closes[i] / benchmark_closes[i - 1]) - 1.0
            for i in range(1, len(benchmark_closes))
            if benchmark_closes[i - 1] > 0
        ]
        if len(bench_returns) == len(simple_returns) and len(bench_returns) >= 2:
            mean_s = statistics.fmean(simple_returns)
            mean_b = statistics.fmean(bench_returns)
            cov = sum((s - mean_s) * (b - mean_b) for s, b in zip(simple_returns, bench_returns, strict=True)) / (
                len(simple_returns) - 1
            )
            var_b = statistics.variance(bench_returns)
            if var_b > 0:
                beta = round(cov / var_b, 4)
                bench_ann_ret = mean_b * annualization
                alpha = round((ann_arith_ret - risk_free_rate) - beta * (bench_ann_ret - risk_free_rate), 4)
            bench_cum = (benchmark_closes[-1] / benchmark_closes[0]) - 1.0
            active_return_pct = round((cum_ret - bench_cum) * 100.0, 4)

    return ReturnsData(
        symbol=symbol,
        benchmark_symbol=benchmark_symbol,
        period=period,
        start_date=start_date,
        end_date=end_date,
        calendar_basis=calendar_basis,
        observations_count=len(closes),
        cumulative_return_pct=round(cum_ret * 100.0, 4),
        log_return=round(log_ret, 6),
        annualized_return_cagr_pct=round(cagr * 100.0, 4),
        annualized_volatility_pct=round(ann_vol * 100.0, 4),
        max_drawdown_pct=round(max_dd * 100.0, 4),
        sharpe_ratio=round(sharpe, 4),
        risk_free_rate_used=risk_free_rate,
        alpha=alpha,
        beta=beta,
        active_return_pct=active_return_pct,
    )


def _derive_regime_signal(indicator: str, latest: dict[str, float | None], latest_price: float | None) -> str | None:
    if indicator == "RSI_14":
        val = latest.get("rsi") or latest.get("value")
        if val is None:
            return None
        if val >= 70.0:
            return "OVERBOUGHT"
        if val <= 30.0:
            return "OVERSOLD"
        return "NEUTRAL"
    if indicator == "MACD":
        macd = latest.get("macd")
        sig = latest.get("signal")
        if macd is not None and sig is not None:
            return "BULLISH" if macd >= sig else "BEARISH"
    if indicator.startswith(("SMA_", "EMA_")) and latest_price is not None:
        val = latest.get("value") or latest.get(indicator.lower())
        if val is not None:
            if indicator == "SMA_200":
                return "PRICE_ABOVE_200SMA" if latest_price >= val else "PRICE_BELOW_200SMA"
            return "PRICE_ABOVE_MA" if latest_price >= val else "PRICE_BELOW_MA"
    if indicator == "BOLLINGER_BANDS" and latest_price is not None:
        upper = latest.get("upper")
        lower = latest.get("lower")
        if upper is not None and latest_price > upper:
            return "ABOVE_UPPER_BAND"
        if lower is not None and latest_price < lower:
            return "BELOW_LOWER_BAND"
        if upper is not None and lower is not None:
            return "WITHIN_BANDS"
    return None


def _detect_macd_crossover_ts(tail_series: list[IndicatorPoint]) -> datetime | None:
    """Detect most recent MACD / Signal crossover timestamp across tail_series points."""
    prev_diff: float | None = None
    latest_cross: datetime | None = None
    for pt in tail_series:
        macd = pt.values.get("MACD") if "MACD" in pt.values else pt.values.get("macd")
        signal = pt.values.get("MACD_SIGNAL") if "MACD_SIGNAL" in pt.values else pt.values.get("signal")
        if macd is None or signal is None:
            continue
        diff = macd - signal
        if prev_diff is not None and ((prev_diff <= 0 < diff) or (prev_diff >= 0 > diff)):
            latest_cross = pt.timestamp
        prev_diff = diff
    return latest_cross


@mcp_tool_boundary("calculate_returns")
@require_scopes("market:read")
async def calculate_returns(
    symbol: str,
    period: Literal["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "CUSTOM"] = "1M",
    start_date: date | None = None,
    end_date: date | None = None,
    benchmark_symbol: str = "SPY",
    calendar_basis: Literal["TRADING_DAYS", "CALENDAR_DAYS"] = "TRADING_DAYS",
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[ReturnsData]]:
    """Calculate cumulative/log return, CAGR, volatility, drawdown, Sharpe, alpha, and beta.

    When to call:
    - Call whenever quantitative return, risk-adjusted performance, or benchmark attribution
      is requested over a standard or custom window.

    Parameter rules:
    - `symbol` & `benchmark_symbol`: Normalized ticker symbols (default benchmark `SPY`).
    - `period`: `1D`, `5D`, `1M`, `3M`, `6M`, `YTD`, `1Y`, `3Y`, `5Y`, or `CUSTOM`.
    - `start_date` / `end_date`: Required when `period='CUSTOM'`; optional anchor otherwise.
    - `calendar_basis`: `TRADING_DAYS` (1M=21d, 1Y=252d; annualizes by 252) or
      `CALENDAR_DAYS` (1M=30d, 1Y=365d; annualizes by 365).

    Output guarantees:
    - Returns `ResponseEnvelope[ReturnsData]` including `risk_free_rate_used`, benchmark alpha/beta,
      and active return in percentage points (`pct`).
    """
    norm_symbol = normalize_symbol(symbol)
    norm_benchmark = normalize_symbol(benchmark_symbol)
    resolved_start, resolved_end = resolve_period_dates(
        period,
        start_date=start_date,
        end_date=end_date,
        calendar_basis=calendar_basis,
    )

    runtime = get_runtime(ctx)
    await emit_protocol_log(
        ctx,
        "info",
        f"Calculating {period} ({calendar_basis}) returns for {norm_symbol} vs {norm_benchmark}",
    )

    resp = await runtime.backend_client.request(
        "POST",
        "/api/v1/analytics/returns",
        json_body={
            "symbol": norm_symbol,
            "benchmark_symbol": norm_benchmark,
            "period": period,
            "start_date": resolved_start.isoformat(),
            "end_date": resolved_end.isoformat(),
            "calendar_basis": calendar_basis,
            "risk_free_rate": runtime.settings.default_risk_free_rate,
        },
        tenant_scope="PUBLIC",
        ttl_seconds=runtime.settings.ttl_analytics_seconds,
    )

    raw = resp.data
    if "cumulative_return_pct" in raw:
        raw_payload: dict[str, Any] = {
            "symbol": norm_symbol,
            "benchmark_symbol": norm_benchmark,
            "period": period,
            "start_date": resolved_start,
            "end_date": resolved_end,
            "calendar_basis": calendar_basis,
            "risk_free_rate_used": runtime.settings.default_risk_free_rate,
            **raw,
        }
        returns_data = ReturnsData.model_validate(raw_payload)
    elif "closes" in raw:
        returns_data = _compute_returns_from_series(
            symbol=norm_symbol,
            benchmark_symbol=norm_benchmark,
            period=period,
            start_date=resolved_start,
            end_date=resolved_end,
            calendar_basis=calendar_basis,
            closes=[float(x) for x in raw["closes"]],
            benchmark_closes=[float(x) for x in raw["benchmark_closes"]] if raw.get("benchmark_closes") else None,
            risk_free_rate=float(raw.get("risk_free_rate_used", runtime.settings.default_risk_free_rate)),
        )
    else:
        raise NoDataAvailableError(f"No return analytics or closing series returned for {norm_symbol}.")

    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))
    cal_enum = CalendarType.TRADING_DAYS if calendar_basis == "TRADING_DAYS" else CalendarType.CALENDAR_DAYS
    envelope = build_envelope(
        data=returns_data,
        source=str(raw.get("source", "fastapi-quant-analytics")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_history_daily_seconds,
        currency=str(raw.get("currency", "USD")),
        units="pct_and_ratios",
        calendar_type=cal_enum,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        enforce_staleness=False,
        warnings=list(raw.get("warnings", [])),
    )

    md = format_markdown_table(
        ["Symbol", "Benchmark", "Cum Return", "CAGR", "Ann Vol", "Max DD", "Sharpe", "Beta", "Alpha"],
        [
            [
                returns_data.symbol,
                returns_data.benchmark_symbol,
                f"{returns_data.cumulative_return_pct:+.2f}%",
                f"{returns_data.annualized_return_cagr_pct:+.2f}%",
                f"{returns_data.annualized_volatility_pct:.2f}%",
                f"{returns_data.max_drawdown_pct:.2f}%",
                returns_data.sharpe_ratio,
                returns_data.beta,
                returns_data.alpha,
            ]
        ],
    )
    return build_tool_result(envelope, md)


@mcp_tool_boundary("calculate_technical_indicators")
@require_scopes("market:read")
async def calculate_technical_indicators(
    symbol: str,
    indicators: list[IndicatorName],
    interval: Literal["1h", "1d", "1wk"] = "1d",
    lookback_bars: int = 100,
    tail_values: int = 10,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[TechnicalIndicatorsData]]:
    """Compute technical indicators, deterministic regime signals, and recent tail series.

    When to call:
    - Call for trend, momentum, volatility, or volume regime analysis (RSI, MACD, SMAs,
      Bollinger Bands, ATR, VWAP, OBV).

    Parameter rules:
    - `symbol`: Normalized ticker symbol.
    - `indicators`: Non-empty list from `SMA_20`, `SMA_50`, `SMA_200`, `EMA_12`, `EMA_26`,
      `RSI_14`, `MACD`, `BOLLINGER_BANDS`, `ATR_14`, `VWAP`, `OBV`.
    - `interval`: `1h`, `1d` (default), or `1wk`.
    - `lookback_bars`: 20 to 500 bars (default 100).
    - `tail_values`: 1 to 50 recent indicator observations returned for trend context (default 10).

    Calendar behavior:
    - Uses `TRADING_DAYS`; cached for 60s.

    Output guarantees:
    - Returns latest indicator snapshots, deterministic regime signals (`OVERBOUGHT`,
      `OVERSOLD`, `BULLISH`/`BEARISH`), and `tail_series` bounded to `tail_values`.
    """
    norm_symbol = normalize_symbol(symbol)
    if not indicators:
        raise InvalidParametersError("indicators list must contain at least one indicator.")
    dedup_indicators = list(dict.fromkeys(indicators))
    if lookback_bars < 20 or lookback_bars > 500:
        raise InvalidParametersError(f"lookback_bars must be between 20 and 500; got {lookback_bars}.")
    if tail_values < 1 or tail_values > 50:
        raise InvalidParametersError(f"tail_values must be between 1 and 50; got {tail_values}.")

    runtime = get_runtime(ctx)
    await emit_protocol_log(
        ctx,
        "info",
        f"Calculating technical indicators {dedup_indicators} for {norm_symbol} ({interval})",
    )

    resp = await runtime.backend_client.request(
        "POST",
        "/api/v1/analytics/indicators",
        json_body={
            "symbol": norm_symbol,
            "indicators": dedup_indicators,
            "interval": interval,
            "lookback_bars": lookback_bars,
            "tail_values": tail_values,
        },
        tenant_scope="PUBLIC",
        ttl_seconds=runtime.settings.ttl_analytics_seconds,
    )

    raw = resp.data
    latest_price = float(raw["latest_price"]) if raw.get("latest_price") is not None else None
    tail_series = [IndicatorPoint.model_validate(pt) for pt in raw.get("tail_series", [])][-tail_values:]
    macd_cross_ts = _detect_macd_crossover_ts(tail_series)

    raw_snapshots = raw.get("snapshots", [])
    snapshots: list[IndicatorSnapshot] = []
    for item in raw_snapshots:
        snap = IndicatorSnapshot.model_validate(item)
        if snap.regime_signal is None:
            snap.regime_signal = _derive_regime_signal(snap.indicator, snap.latest, latest_price)
        if snap.indicator == "MACD" and snap.crossover_timestamp is None and macd_cross_ts is not None:
            snap.crossover_timestamp = macd_cross_ts
        snapshots.append(snap)

    payload = TechnicalIndicatorsData(
        symbol=norm_symbol,
        interval=interval,
        lookback_bars=lookback_bars,
        tail_values_count=len(tail_series),
        latest_price=latest_price,
        overall_regime=raw.get("overall_regime"),
        snapshots=snapshots,
        tail_series=tail_series,
    )
    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))

    envelope = build_envelope(
        data=payload,
        source=str(raw.get("source", "fastapi-quant-indicators")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_history_intraday_seconds
        if interval == "1h"
        else runtime.settings.stale_history_daily_seconds,
        currency=str(raw.get("currency", "USD")),
        units="indicator_values",
        calendar_type=CalendarType.TRADING_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        enforce_staleness=False,
        no_data=(len(snapshots) == 0 and len(tail_series) == 0),
        warnings=list(raw.get("warnings", [])),
    )

    md = format_markdown_table(
        ["Indicator", "Latest Values", "Regime Signal"],
        [[s.indicator, s.latest, s.regime_signal] for s in snapshots],
    )
    return build_tool_result(envelope, md or f"No indicator values returned for {norm_symbol}.")


def register_technical_analysis_tools(mcp: MCPServer) -> None:
    """Register quantitative returns and technical indicator tools onto the MCPServer."""
    read_annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
    mcp.add_tool(calculate_returns, annotations=read_annotations)
    mcp.add_tool(calculate_technical_indicators, annotations=read_annotations)
