"""Static MCP system capability and quantitative glossary resources."""

import json

from mcp.server.mcpserver import MCPServer

from app.config.settings import get_settings


def get_system_capabilities_json() -> str:
    """Return JSON specification of supported exchanges, intervals, indicators, SLAs, and scopes."""
    settings = get_settings()
    payload = {
        "service": settings.server_name,
        "version": settings.server_version,
        "transports": ["streamable-http", "stdio"],
        "supported_asset_types": ["EQUITY", "ETF", "INDEX", "CRYPTO", "FX"],
        "supported_exchanges": ["NYSE", "NASDAQ", "AMEX", "ARCA", "BATS", "LSE", "TSX", "FRA", "TSE", "HKEX"],
        "supported_intervals": ["1m", "5m", "15m", "1h", "1d", "1wk", "1mo"],
        "max_historical_bars_per_call": settings.max_historical_bars,
        "supported_technical_indicators": [
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
        ],
        "calendar_conventions": ["TRADING_DAYS", "CALENDAR_DAYS"],
        "scopes": list(settings.oauth_supported_scopes),
        "rate_limits": {
            "requests_per_window": settings.rate_limit_requests,
            "window_seconds": settings.rate_limit_window_seconds,
        },
        "cache_ttls_seconds": {
            "search_instruments": settings.ttl_search_seconds,
            "get_exchange_schedule": settings.ttl_schedule_seconds,
            "get_market_quote": settings.ttl_quote_seconds,
            "get_historical_prices_intraday": settings.ttl_history_intraday_seconds,
            "get_historical_prices_daily": settings.ttl_history_daily_seconds,
            "get_company_profile": settings.ttl_profile_seconds,
            "get_financial_metrics": settings.ttl_metrics_seconds,
            "get_earnings_history": settings.ttl_earnings_seconds,
            "analytics": settings.ttl_analytics_seconds,
            "analyse_portfolio": settings.ttl_portfolio_analysis_seconds,
        },
        "freshness_slas_seconds": {
            "quotes": settings.stale_quote_seconds,
            "history_intraday": settings.stale_history_intraday_seconds,
            "history_daily": settings.stale_history_daily_seconds,
            "fundamentals": settings.stale_fundamentals_seconds,
            "portfolio": settings.stale_portfolio_seconds,
            "schedule": settings.stale_schedule_seconds,
        },
    }
    return json.dumps(payload, indent=2)


def get_system_glossary_json() -> str:
    """Return mathematical definitions for quantitative risk, return, and valuation metrics."""
    glossary = {
        "SharpeRatio": {
            "formula": "(E[R_p] - R_f) / sigma_p",
            "annualization": "252 trading days or 365 calendar days based on calendar_basis",
            "notes": "Uses default risk-free rate configured on gateway when T-bill curve is not supplied.",
        },
        "SortinoRatio": {
            "formula": "(E[R_p] - R_f) / sigma_downside",
            "notes": "Penalizes only downside return deviations below the Minimum Acceptable Return (MAR = R_f).",
        },
        "HistoricalVaR": {
            "formula": "Percentile(R_portfolio, 1 - confidence_level)",
            "notes": "Empirical tail loss threshold over lookback_days (e.g., 95% confidence = 5th percentile loss).",
        },
        "ExpectedShortfallCVaR": {
            "formula": "E[R_portfolio | R_portfolio <= VaR_alpha]",
            "notes": "Coherent tail-risk metric measuring expected loss conditional on breaching VaR.",
        },
        "Beta": {
            "formula": "Cov(R_asset, R_benchmark) / Var(R_benchmark)",
            "notes": "Linear sensitivity to benchmark excess returns over the aligned observation window.",
        },
        "JensensAlpha": {
            "formula": "(R_asset_ann - R_f) - Beta * (R_benchmark_ann - R_f)",
            "notes": "Annualized risk-adjusted active return above CAPM expectation.",
        },
        "CAGR": {
            "formula": "(P_end / P_start)^(A / N) - 1",
            "notes": "Compound Annual Growth Rate where A is annualization factor (252 or 365) and N is intervals.",
        },
        "MaxDrawdown": {
            "formula": "min_t((P_t / max_{s <= t}(P_s)) - 1)",
            "notes": "Worst peak-to-trough percentage decline over the measurement window.",
        },
        "RSI_14": {
            "formula": "100 - (100 / (1 + AvgGain_14 / AvgLoss_14))",
            "notes": "Wilder 14-period Relative Strength Index; >= 70 OVERBOUGHT, <= 30 OVERSOLD.",
        },
        "MACD": {
            "formula": "MACD = EMA_12 - EMA_26; Signal = EMA_9(MACD); Histogram = MACD - Signal",
            "notes": "Trend-following momentum oscillator; MACD > Signal indicates BULLISH crossover.",
        },
        "EV_to_EBITDA": {
            "formula": "(MarketCap + TotalDebt - CashAndEquivalents) / EBITDA_TTM",
            "notes": "Capital-structure-neutral valuation multiple.",
        },
        "VWAP": {
            "formula": "sum(((High + Low + Close) / 3) * Volume) / sum(Volume)",
            "notes": "Volume-Weighted Average Price across bars in the requested horizon.",
        },
    }
    return json.dumps(glossary, indent=2)


def register_system_resources(mcp: MCPServer) -> None:
    """Register static system capability and glossary resources."""
    mcp.add_resource(
        _make_static_resource(
            uri="market://system/capabilities",
            name="system_capabilities",
            title="Market Intelligence System Capabilities & SLAs",
            description="Supported exchanges, intervals, indicators, rate limits, cache TTLs, and data freshness SLAs.",
            mime_type="application/json",
            fn=get_system_capabilities_json,
        )
    )
    mcp.add_resource(
        _make_static_resource(
            uri="market://system/glossary",
            name="quantitative_glossary",
            title="Quantitative Financial Formula Glossary",
            description="Canonical mathematical definitions for Sharpe, Sortino, VaR, CVaR, RSI, MACD, and EV/EBITDA.",
            mime_type="application/json",
            fn=get_system_glossary_json,
        )
    )


def _make_static_resource(
    *,
    uri: str,
    name: str,
    title: str,
    description: str,
    mime_type: str,
    fn,
):
    from mcp.server.mcpserver.resources import FunctionResource

    return FunctionResource.from_function(
        fn=fn,
        uri=uri,
        name=name,
        title=title,
        description=description,
        mime_type=mime_type,
    )
