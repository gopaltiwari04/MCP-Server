"""User-scoped portfolio risk analytics and stateless rebalance simulation tools."""

from datetime import UTC, datetime
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from app.auth.context import require_security_context
from app.auth.permissions import require_scopes
from app.schemas.common import CalendarType, ResponseEnvelope
from app.schemas.portfolio import (
    ConcentrationContributor,
    ConstraintViolation,
    PortfolioAnalysisData,
    ProposedTrade,
    RebalanceSimulationData,
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
from app.utils.validators import normalize_symbol, validate_identifier


@mcp_tool_boundary("analyse_portfolio")
@require_scopes("portfolio:read")
async def analyse_portfolio(
    portfolio_id: str,
    benchmark_symbol: str = "SPY",
    confidence_level: float = 0.95,
    lookback_days: int = 252,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[PortfolioAnalysisData]]:
    """Run user-scoped portfolio attribution, tail risk (VaR/CVaR), and concentration analysis.

    When to call:
    - Call to inspect a user's portfolio NAV, cash balance, position P&L, sector weights,
      beta, Sharpe/Sortino, historical & parametric VaR, Expected Shortfall (CVaR), and
      top concentration risk contributors.

    Parameter rules:
    - `portfolio_id`: Safe portfolio identifier (never accepts user_id; identity is bound
      strictly via verified RequestSecurityContext).
    - `benchmark_symbol`: Benchmark ticker (default `SPY`).
    - `confidence_level`: Strictly between 0.50 and 0.999 (default `0.95`).
    - `lookback_days`: Between 20 and 1260 trading days (default `252`).

    Calendar behavior:
    - Uses `TRADING_DAYS`; cached 15s using a strict user-isolated SHA-256 cache key.

    Output guarantees:
    - Returns `ResponseEnvelope[PortfolioAnalysisData]` enforcing tenant isolation.
    """
    clean_portfolio_id = validate_identifier(portfolio_id, name="portfolio_id")
    norm_benchmark = normalize_symbol(benchmark_symbol)
    if confidence_level <= 0.5 or confidence_level >= 1.0:
        raise InvalidParametersError(
            f"confidence_level must be strictly between 0.5 and 1.0; got {confidence_level}."
        )
    if lookback_days < 20 or lookback_days > 1260:
        raise InvalidParametersError(
            f"lookback_days must be between 20 and 1260; got {lookback_days}."
        )

    sec_ctx = require_security_context()
    runtime = get_runtime(ctx)
    await emit_protocol_log(
        ctx,
        "info",
        f"Analysing portfolio {clean_portfolio_id} (benchmark={norm_benchmark}, cl={confidence_level})",
    )

    resp = await runtime.backend_client.request(
        "GET",
        f"/api/v1/portfolios/{clean_portfolio_id}/analysis",
        params={
            "benchmark_symbol": norm_benchmark,
            "confidence_level": confidence_level,
            "lookback_days": lookback_days,
        },
        tenant_scope=sec_ctx.user_id,
        ttl_seconds=runtime.settings.ttl_portfolio_analysis_seconds,
        cache_tags=(f"user:{sec_ctx.user_id}:portfolio:{clean_portfolio_id}",),
    )

    raw = resp.data
    payload_dict = {
        "portfolio_id": clean_portfolio_id,
        "benchmark_symbol": norm_benchmark,
        "confidence_level": confidence_level,
        "lookback_days": lookback_days,
        **raw,
    }
    analysis = PortfolioAnalysisData.model_validate(payload_dict)
    if not analysis.top_concentration_contributors and analysis.positions:
        top_positions = sorted(analysis.positions, key=lambda p: p.weight_pct, reverse=True)[:3]
        analysis.top_concentration_contributors = [
            ConcentrationContributor(symbol=pos.symbol, weight_pct=pos.weight_pct)
            for pos in top_positions
        ]
    else:
        analysis.top_concentration_contributors = analysis.top_concentration_contributors[:3]
    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))

    envelope = build_envelope(
        data=analysis,
        source=str(raw.get("source", "fastapi-portfolio-risk")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_portfolio_seconds,
        currency=analysis.base_currency,
        units="nav_and_risk_pct",
        calendar_type=CalendarType.TRADING_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        warnings=list(raw.get("warnings", [])),
    )

    md = format_markdown_table(
        ["Symbol", "Weight %", "Market Value", "Unrealized P&L", "Sector"],
        [
            [p.symbol, p.weight_pct, p.market_value, p.unrealized_pnl, p.sector]
            for p in analysis.positions
        ],
    )
    header = (
        f"### Portfolio `{analysis.portfolio_id}` ({analysis.base_currency})\n"
        f"- **NAV:** {analysis.nav:,.2f} | **Cash:** {analysis.cash_balance:,.2f} ({analysis.cash_weight_pct:.2f}%)\n"
        f"- **Beta:** {analysis.portfolio_beta} | **Sharpe:** {analysis.sharpe_ratio} | "
        f"**VaR ({int(analysis.confidence_level * 100)}%):** {analysis.historical_var_pct}% | "
        f"**CVaR:** {analysis.expected_shortfall_cvar_pct}%\n\n"
    )
    return build_tool_result(envelope, header + md)


@mcp_tool_boundary("simulate_portfolio_rebalance")
@require_scopes("simulation:execute")
async def simulate_portfolio_rebalance(
    portfolio_id: str,
    proposed_trades: list[ProposedTrade],
    benchmark_symbol: str = "SPY",
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[RebalanceSimulationData]]:
    """Stateless what-if rebalance simulator comparing pre-trade vs. post-trade risk & guardrails.

    When to call:
    - Call before recommending trades or hedging adjustments to verify projected beta shift,
      VaR delta, cash sufficiency, and single-stock concentration limits without mutating state.

    Parameter rules:
    - `portfolio_id`: Target portfolio identifier.
    - `proposed_trades`: Non-empty list of 1 to 25 `ProposedTrade` orders (`symbol`, `side`,
      and exactly one of `weight_delta_pct` or `share_delta`).
    - `benchmark_symbol`: Benchmark ticker (default `SPY`).

    Calendar behavior:
    - Uses `TRADING_DAYS`; simulation calls are NEVER cached (`ttl=0s`).

    Output guarantees:
    - Returns pre-trade vs. post-trade snapshots, cash impact, VaR/beta deltas, and flags
      guardrail violations (negative cash, single-stock concentration > 25%).
    """
    clean_portfolio_id = validate_identifier(portfolio_id, name="portfolio_id")
    norm_benchmark = normalize_symbol(benchmark_symbol)
    if not proposed_trades or len(proposed_trades) > 25:
        raise InvalidParametersError("proposed_trades must contain between 1 and 25 trade legs.")

    normalized_trades = [
        ProposedTrade(
            symbol=normalize_symbol(t.symbol),
            side=t.side,
            weight_delta_pct=t.weight_delta_pct,
            share_delta=t.share_delta,
        )
        for t in proposed_trades
    ]

    sec_ctx = require_security_context()
    runtime = get_runtime(ctx)
    await emit_protocol_log(
        ctx,
        "info",
        f"Simulating {len(normalized_trades)} rebalance legs on portfolio {clean_portfolio_id}",
    )

    resp = await runtime.backend_client.request(
        "POST",
        f"/api/v1/portfolios/{clean_portfolio_id}/simulate",
        json_body={
            "benchmark_symbol": norm_benchmark,
            "proposed_trades": [t.model_dump(exclude_none=True) for t in normalized_trades],
        },
        tenant_scope=sec_ctx.user_id,
        ttl_seconds=0.0,
    )

    raw = resp.data
    sim = RebalanceSimulationData.model_validate(
        {
            "portfolio_id": clean_portfolio_id,
            "benchmark_symbol": norm_benchmark,
            "is_stateless_simulation": True,
            **raw,
        }
    )
    if (
        sim.beta_shift is None
        and sim.pre_trade.portfolio_beta is not None
        and sim.post_trade.portfolio_beta is not None
    ):
        sim.beta_shift = round(sim.post_trade.portfolio_beta - sim.pre_trade.portfolio_beta, 4)
    if (
        sim.var_delta_pct is None
        and sim.pre_trade.var_95_pct is not None
        and sim.post_trade.var_95_pct is not None
    ):
        sim.var_delta_pct = round(sim.post_trade.var_95_pct - sim.pre_trade.var_95_pct, 4)

    # Enforce deterministic gateway risk guardrails if backend omitted them
    existing_codes = {(v.rule_code, v.symbol) for v in sim.constraint_violations}
    if sim.post_trade.cash_balance < 0 and ("NEGATIVE_CASH", None) not in existing_codes:
        sim.constraint_violations.append(
            ConstraintViolation(
                rule_code="NEGATIVE_CASH",
                severity="BREACH",
                message=f"Simulated post-trade cash balance is negative ({sim.post_trade.cash_balance:,.2f}).",
                observed_value=sim.post_trade.cash_balance,
                limit_value=0.0,
            )
        )
    max_conc = runtime.settings.max_single_position_concentration_pct
    for sym, weight in sim.post_trade.position_weights_pct.items():
        if weight > max_conc and ("SINGLE_STOCK_CONCENTRATION", sym) not in existing_codes:
            sim.constraint_violations.append(
                ConstraintViolation(
                    rule_code="SINGLE_STOCK_CONCENTRATION",
                    severity="BREACH",
                    symbol=sym,
                    message=f"Post-trade weight for {sym} ({weight:.2f}%) exceeds {max_conc:.1f}% limit.",
                    observed_value=weight,
                    limit_value=max_conc,
                )
            )

    warnings = list(raw.get("warnings", []))
    for v in sim.constraint_violations:
        warnings.append(f"[{v.severity}] {v.rule_code}: {v.message}")

    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))
    envelope = build_envelope(
        data=sim,
        source=str(raw.get("source", "fastapi-portfolio-simulator")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_portfolio_seconds,
        currency=str(raw.get("base_currency", "USD")),
        units="simulation_delta",
        calendar_type=CalendarType.TRADING_DAYS,
        cache_hit=False,
        backend_is_stale=bool(raw.get("is_stale", False)),
        warnings=warnings,
    )

    md = (
        f"### Stateless Rebalance Simulation: `{sim.portfolio_id}`\n"
        f"- **Estimated Cash Impact:** {sim.estimated_cash_impact:+,.2f} | "
        f"**Beta Shift:** {sim.beta_shift} | **VaR Delta:** {sim.var_delta_pct}%\n"
        f"- **Constraint Violations:** {len(sim.constraint_violations)}"
    )
    return build_tool_result(envelope, md)


def register_portfolio_tools(mcp: MCPServer) -> None:
    """Register portfolio analytics and what-if simulation tools onto the MCPServer."""
    mcp.add_tool(
        analyse_portfolio,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    mcp.add_tool(
        simulate_portfolio_rebalance,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
