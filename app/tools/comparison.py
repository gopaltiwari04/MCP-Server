"""Multi-asset comparison tool with progress notifications and cross-exchange alignment."""

import asyncio
import math
import statistics
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from app.auth.permissions import require_scopes
from app.schemas.analytics import (
    CompareInstrumentsData,
    InstrumentComparisonRow,
    InstrumentRankings,
)
from app.schemas.common import CalendarType, ResponseEnvelope
from app.tools.helpers import (
    build_envelope,
    emit_progress,
    emit_protocol_log,
    get_runtime,
    mcp_tool_boundary,
    parse_utc_datetime,
)
from app.utils.errors import NoDataAvailableError
from app.utils.formatting import build_tool_result, format_markdown_table
from app.utils.validators import normalize_symbols, resolve_period_dates

ComparisonMetric = Literal[
    "RETURNS",
    "VOLATILITY",
    "SHARPE",
    "MAX_DRAWDOWN",
    "VALUATION",
    "CORRELATION_MATRIX",
]


def _pearson_correlation(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return 0.0
    return round(max(-1.0, min(1.0, num / (den_x * den_y))), 4)


def align_and_compute_from_series(
    *,
    symbols: list[str],
    series_by_symbol: dict[str, list[dict[str, Any]]],
    risk_free_rate: float,
) -> tuple[
    date | None,
    date | None,
    int,
    dict[str, list[str]],
    list[InstrumentComparisonRow],
    dict[str, dict[str, float]],
]:
    """Align timestamps across the common trading-day intersection and compute comparison metrics."""
    dated_maps: dict[str, dict[str, float]] = {}
    for sym in symbols:
        points = series_by_symbol.get(sym, [])
        dated_maps[sym] = {
            str(pt["date"])[:10]: float(pt["close"])
            for pt in points
            if pt.get("date") is not None and pt.get("close") is not None
        }

    if not dated_maps or any(not m for m in dated_maps.values()):
        raise NoDataAvailableError("Insufficient aligned historical series to compare requested symbols.")

    common_dates = sorted(set.intersection(*(set(m.keys()) for m in dated_maps.values())))
    if len(common_dates) < 2:
        raise NoDataAvailableError("Fewer than 2 common trading dates exist across requested instruments.")

    common_set = set(common_dates)
    dropped_by_symbol: dict[str, list[str]] = {
        sym: sorted(d for d in dated_maps[sym] if d not in common_set)
        for sym in symbols
    }

    returns_by_symbol: dict[str, list[float]] = {}
    rows: list[InstrumentComparisonRow] = []

    for sym in symbols:
        closes = [dated_maps[sym][d] for d in common_dates]
        rets = [(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0]
        returns_by_symbol[sym] = rets
        cum_ret = ((closes[-1] / closes[0]) - 1.0) * 100.0 if closes[0] > 0 else 0.0
        vol = (statistics.stdev(rets) * math.sqrt(252.0) * 100.0) if len(rets) >= 2 else 0.0
        ann_ret = (statistics.fmean(rets) * 252.0) if rets else 0.0
        sharpe = ((ann_ret - risk_free_rate) / (vol / 100.0)) if vol > 0 else 0.0

        peak = closes[0]
        max_dd = 0.0
        for p in closes:
            if p > peak:
                peak = p
            dd = (p / peak) - 1.0
            if dd < max_dd:
                max_dd = dd

        rows.append(
            InstrumentComparisonRow(
                symbol=sym,
                cumulative_return_pct=round(cum_ret, 4),
                annualized_volatility_pct=round(vol, 4),
                sharpe_ratio=round(sharpe, 4),
                max_drawdown_pct=round(max_dd * 100.0, 4),
            )
        )

    corr_matrix: dict[str, dict[str, float]] = {}
    for sym_a in symbols:
        corr_matrix[sym_a] = {}
        for sym_b in symbols:
            if sym_a == sym_b:
                corr_matrix[sym_a][sym_b] = 1.0
            else:
                corr_matrix[sym_a][sym_b] = _pearson_correlation(
                    returns_by_symbol[sym_a],
                    returns_by_symbol[sym_b],
                )

    return (
        date.fromisoformat(common_dates[0]),
        date.fromisoformat(common_dates[-1]),
        len(common_dates),
        dropped_by_symbol,
        rows,
        corr_matrix,
    )


def _compute_rankings(
    rows: list[InstrumentComparisonRow],
    metrics: list[ComparisonMetric],
) -> list[InstrumentRankings]:
    rankings: list[InstrumentRankings] = []
    metric_extractors: dict[str, tuple[Any, bool]] = {
        "RETURNS": (lambda r: r.cumulative_return_pct, True),
        "SHARPE": (lambda r: r.sharpe_ratio, True),
        "VOLATILITY": (lambda r: r.annualized_volatility_pct, False),
        "MAX_DRAWDOWN": (lambda r: r.max_drawdown_pct, True),  # least negative is best (-3% > -20%)
        "VALUATION": (lambda r: r.pe_ratio, False),
    }
    for metric in metrics:
        if metric not in metric_extractors:
            continue
        extractor, descending = metric_extractors[metric]
        valid = [r for r in rows if extractor(r) is not None]
        if not valid:
            continue
        ordered = sorted(valid, key=lambda r: extractor(r), reverse=descending)
        rankings.append(InstrumentRankings(metric=metric, ordered_symbols=[r.symbol for r in ordered]))
    return rankings


@mcp_tool_boundary("compare_instruments")
@require_scopes("market:read")
async def compare_instruments(
    symbols: list[str],
    period: Literal["5D", "1M", "3M", "6M", "YTD", "1Y", "3Y"] = "1M",
    metrics: list[ComparisonMetric] = ["RETURNS", "VOLATILITY", "SHARPE", "VALUATION", "CORRELATION_MATRIX"],
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[CompareInstrumentsData]]:
    """Compare 2 to 10 instruments side-by-side with aligned returns, correlations, and rankings.

    When to call:
    - Call for peer valuation screens, relative momentum/risk comparisons, or pairs/basket
      correlation analysis.

    Parameter rules:
    - `symbols`: List of 2 to 10 tickers (normalized and deduplicated automatically).
    - `period`: `5D`, `1M` (default), `3M`, `6M`, `YTD`, `1Y`, or `3Y`.
    - `metrics`: Subset of `RETURNS`, `VOLATILITY`, `SHARPE`, `MAX_DRAWDOWN`, `VALUATION`,
      `CORRELATION_MATRIX`.

    Calendar behavior:
    - Uses `TRADING_DAYS` and aligns observations across the common trading-day intersection,
      explicitly reporting any dropped dates per symbol due to cross-exchange holidays.

    Output guarantees:
    - Emits MCP progress notifications during concurrent gathering and returns a unified
      comparison table, pairwise correlation matrix, and per-metric relative rankings.
    """
    norm_symbols = normalize_symbols(symbols, min_count=2, max_count=10)
    start_dt, end_dt = resolve_period_dates(period, calendar_basis="TRADING_DAYS")
    runtime = get_runtime(ctx)

    total_steps = len(norm_symbols)
    await emit_protocol_log(ctx, "info", f"Comparing {len(norm_symbols)} instruments over {period}: {norm_symbols}")
    await emit_progress(ctx, 0, total_steps, f"Initializing comparison for {len(norm_symbols)} symbols")

    resp = await runtime.backend_client.request(
        "POST",
        "/api/v1/analytics/compare",
        json_body={
            "symbols": norm_symbols,
            "period": period,
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "metrics": list(dict.fromkeys(metrics)),
            "risk_free_rate": runtime.settings.default_risk_free_rate,
        },
        tenant_scope="PUBLIC",
        ttl_seconds=runtime.settings.ttl_analytics_seconds,
    )

    raw = resp.data
    completed = 0

    async def _process_symbol_stage(sym: str) -> tuple[str, dict[str, Any] | None]:
        nonlocal completed
        # Enrich valuation concurrently if requested and absent from compare payload
        enrichment: dict[str, Any] | None = None
        existing_row = next(
            (r for r in raw.get("comparison_table", []) if str(r.get("symbol", "")).upper() == sym),
            None,
        )
        needs_valuation = (
            "VALUATION" in metrics
            and (existing_row is None or existing_row.get("pe_ratio") is None)
        )
        if needs_valuation:
            val_resp = await runtime.backend_client.request(
                "GET",
                f"/api/v1/fundamentals/metrics/{sym}",
                params={"period": "TTM", "limit": 1},
                tenant_scope="PUBLIC",
                ttl_seconds=runtime.settings.ttl_metrics_seconds,
            )
            periods = val_resp.data.get("periods", [])
            if periods:
                enrichment = periods[0].get("valuation")
        completed += 1
        await emit_progress(ctx, completed, total_steps, f"Processed comparison metrics for {sym}")
        return sym, enrichment

    stage_results = await asyncio.gather(*(_process_symbol_stage(s) for s in norm_symbols))
    enrichment_map = {sym: data for sym, data in stage_results if data is not None}

    if "series_by_symbol" in raw and not raw.get("comparison_table"):
        (
            aligned_start,
            aligned_end,
            aligned_obs,
            dropped_dates,
            rows,
            corr_matrix,
        ) = align_and_compute_from_series(
            symbols=norm_symbols,
            series_by_symbol=raw["series_by_symbol"],
            risk_free_rate=runtime.settings.default_risk_free_rate,
        )
    else:
        rows = [InstrumentComparisonRow.model_validate(r) for r in raw.get("comparison_table", [])]
        for row in rows:
            if row.symbol in enrichment_map:
                val = enrichment_map[row.symbol]
                row.pe_ratio = row.pe_ratio or val.get("pe_ratio")
                row.ev_to_ebitda = row.ev_to_ebitda or val.get("ev_to_ebitda")
        aligned_start = date.fromisoformat(str(raw["aligned_start_date"])[:10]) if raw.get("aligned_start_date") else start_dt
        aligned_end = date.fromisoformat(str(raw["aligned_end_date"])[:10]) if raw.get("aligned_end_date") else end_dt
        aligned_obs = int(raw.get("aligned_observations", 0))
        dropped_dates = dict(raw.get("dropped_dates_by_symbol", {}))
        corr_matrix = dict(raw.get("correlation_matrix", {}))

    if raw.get("rankings"):
        rankings = [InstrumentRankings.model_validate(rk) for rk in raw["rankings"]]
    else:
        rankings = _compute_rankings(rows, metrics)

    warnings = list(raw.get("warnings", []))
    total_dropped = sum(len(v) for v in dropped_dates.values())
    if total_dropped > 0:
        warnings.append(
            f"Aligned across common trading-day intersection; dropped {total_dropped} mismatched exchange dates."
        )

    payload = CompareInstrumentsData(
        symbols=norm_symbols,
        period=period,
        aligned_start_date=aligned_start,
        aligned_end_date=aligned_end,
        aligned_observations=aligned_obs,
        dropped_dates_by_symbol=dropped_dates,
        comparison_table=rows,
        correlation_matrix=corr_matrix if "CORRELATION_MATRIX" in metrics else {},
        rankings=rankings,
    )
    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))

    envelope = build_envelope(
        data=payload,
        source=str(raw.get("source", "fastapi-quant-compare")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_history_daily_seconds,
        currency=str(raw.get("currency", "USD")),
        units="multi_asset_comparison",
        calendar_type=CalendarType.TRADING_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        enforce_staleness=False,
        no_data=(len(rows) == 0),
        warnings=warnings,
    )

    md = format_markdown_table(
        ["Symbol", "Return %", "Vol %", "Sharpe", "Max DD %", "P/E", "EV/EBITDA"],
        [
            [
                r.symbol,
                r.cumulative_return_pct,
                r.annualized_volatility_pct,
                r.sharpe_ratio,
                r.max_drawdown_pct,
                r.pe_ratio,
                r.ev_to_ebitda,
            ]
            for r in rows
        ],
    )
    return build_tool_result(envelope, md or "No comparison results available.")


def register_comparison_tools(mcp: MCPServer) -> None:
    """Register multi-asset comparison tools onto the MCPServer."""
    mcp.add_tool(
        compare_instruments,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
