"""Institutional MCP workflow prompts and argument autocompletion handlers."""

from mcp.server.mcpserver import MCPServer, UserMessage
from mcp.types import Completion, PromptReference, ResourceTemplateReference


def institutional_equity_tearsheet(
    symbol: str,
    benchmark: str = "SPY",
) -> list[UserMessage]:
    """Generate an institutional equity tearsheet grounded strictly in live MCP tool outputs."""
    norm_sym = symbol.strip().upper()
    norm_bench = benchmark.strip().upper()
    text = (
        f"Produce an institutional-grade equity research tearsheet for `{norm_sym}` "
        f"benchmarked against `{norm_bench}`.\n\n"
        "Required Execution Sequence:\n"
        f"1. Call `get_company_profile(symbol='{norm_sym}')` to establish GICS sector, business model, and listing metadata.\n"
        f"2. Call `get_market_quote(symbol='{norm_sym}')` for live price, spread, market cap, and intraday volume.\n"
        f"3. Call `get_financial_metrics(symbol='{norm_sym}', period='TTM', limit=4)` and `get_earnings_history(symbol='{norm_sym}', quarters=8)` to evaluate valuation multiples against margins, ROIC, leverage, and YoY growth.\n"
        f"4. Call `calculate_returns(symbol='{norm_sym}', period='1Y', benchmark_symbol='{norm_bench}', calendar_basis='TRADING_DAYS')` for CAGR, volatility, max drawdown, Sharpe, alpha, and beta.\n"
        f"5. Call `calculate_technical_indicators(symbol='{norm_sym}', indicators=['SMA_50','SMA_200','RSI_14','MACD'], interval='1d')` for trend & momentum regime.\n\n"
        "Analytical Standards:\n"
        "- Cross-check valuation multiples (Forward P/E, EV/EBITDA, PEG) explicitly against revenue/EPS growth and ROIC.\n"
        "- NEVER cite any price, ratio, or date not present in tool responses; report `STALE_DATA` or `NO_DATA_AVAILABLE` warnings verbatim if present.\n"
        "- End with a **Data Provenance Footer** listing every tool called, its `data_timestamp`, `source`, and `request_id`."
    )
    return [UserMessage(text)]


def multi_stock_relative_value_comparison(
    symbols_csv: str,
    period: str = "1M",
) -> list[UserMessage]:
    """Produce a multi-stock relative-value and momentum attribution report."""
    symbols = [s.strip().upper() for s in symbols_csv.split(",") if s.strip()]
    text = (
        f"Conduct a relative-value, momentum, and correlation comparison across `{symbols}` over `{period}`.\n\n"
        "Required Execution Sequence:\n"
        f"1. Call `compare_instruments(symbols={symbols!r}, period='{period}', metrics=['RETURNS','VOLATILITY','SHARPE','MAX_DRAWDOWN','VALUATION','CORRELATION_MATRIX'])`.\n"
        "2. For the top and bottom ranked performers, inspect `get_historical_prices` over the exact aligned window and `get_financial_metrics(period='TTM')` to verify whether outperformance is multiple expansion or fundamental margin/growth acceleration.\n"
        "3. Report any dropped cross-exchange holiday dates explicitly and include the pairwise correlation matrix table.\n"
        "4. Include a **Data Provenance Footer** citing every `data_timestamp` and `request_id`."
    )
    return [UserMessage(text)]


def pairs_trading_screen(
    symbol_a: str,
    symbol_b: str,
    lookback_period: str = "6M",
) -> list[UserMessage]:
    """Evaluate a statistical pairs-trading / relative-value spread candidate pair."""
    sym_a = symbol_a.strip().upper()
    sym_b = symbol_b.strip().upper()
    text = (
        f"Evaluate `{sym_a}` vs `{sym_b}` as a relative-value pairs-trading candidate over `{lookback_period}`.\n\n"
        "Required Execution Sequence:\n"
        f"1. Call `compare_instruments(symbols=['{sym_a}', '{sym_b}'], period='{lookback_period}', metrics=['RETURNS','VOLATILITY','SHARPE','VALUATION','CORRELATION_MATRIX'])`.\n"
        f"2. Call `calculate_technical_indicators` (`RSI_14`, `BOLLINGER_BANDS`, `ATR_14`) on both `{sym_a}` and `{sym_b}`.\n"
        f"3. Call `get_earnings_history` on both tickers to flag upcoming binary catalyst dates (`next_earnings_date`).\n"
        "4. Summarize return correlation, volatility ratio, relative valuation spread, and catalyst risks with a full **Data Provenance Footer**."
    )
    return [UserMessage(text)]


def portfolio_tail_risk_audit(portfolio_id: str) -> list[UserMessage]:
    """Audit portfolio concentration, VaR/CVaR tail risk, and simulate hedging trades."""
    clean_id = portfolio_id.strip()
    text = (
        f"Perform an institutional tail-risk and concentration audit on portfolio `{clean_id}`.\n\n"
        "Required Execution Sequence:\n"
        f"1. Call `analyse_portfolio(portfolio_id='{clean_id}', benchmark_symbol='SPY', confidence_level=0.95, lookback_days=252)`.\n"
        "2. Identify the top 3 concentration risk contributors, sector overweights, and historical vs. parametric VaR/CVaR gap.\n"
        "3. Propose 1-3 concrete risk-mitigating trades and validate them via `simulate_portfolio_rebalance(portfolio_id=..., proposed_trades=...)` to verify projected VaR delta, beta shift, cash sufficiency, and zero concentration breaches (>25%).\n"
        "4. Present pre-trade vs. post-trade comparison tables and a **Data Provenance Footer**."
    )
    return [UserMessage(text)]


def register_workflow_prompts(mcp: MCPServer) -> None:
    """Register institutional workflow prompts and argument completions onto MCPServer."""
    mcp.prompt(
        name="institutional_equity_tearsheet",
        title="Institutional Equity Tearsheet",
        description="End-to-end single-stock fundamental, return attribution, and technical regime workflow.",
    )(institutional_equity_tearsheet)

    mcp.prompt(
        name="multi_stock_relative_value_comparison",
        title="Multi-Stock Relative Value Comparison",
        description="Cross-asset peer comparison combining aligned returns, correlation matrix, and valuation multiples.",
    )(multi_stock_relative_value_comparison)

    mcp.prompt(
        name="pairs_trading_screen",
        title="Pairs Trading Relative-Value Screen",
        description="Statistical pairs-trading diagnostic combining correlation, mean-reversion oscillators, and earnings catalyst risk.",
    )(pairs_trading_screen)

    mcp.prompt(
        name="portfolio_tail_risk_audit",
        title="Portfolio Tail-Risk & Rebalance Audit",
        description="Quantitative portfolio VaR/CVaR audit with stateless what-if hedging rebalance simulation.",
    )(portfolio_tail_risk_audit)

    @mcp.completion()
    async def handle_completion(ref, argument, _context) -> Completion | None:
        prefix = (argument.value or "").upper()
        if isinstance(ref, PromptReference):
            if argument.name in ("period", "lookback_period"):
                options = ["5D", "1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y"]
                return Completion(values=[o for o in options if o.startswith(prefix)])
            if argument.name == "benchmark":
                options = ["SPY", "QQQ", "IWM", "DIA", "TLT"]
                return Completion(values=[o for o in options if o.startswith(prefix)])
        if isinstance(ref, ResourceTemplateReference) and argument.name == "symbol":
            options = ["AAPL", "AMD", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "SPY"]
            return Completion(values=[o for o in options if o.startswith(prefix)])
        return Completion(values=[])
