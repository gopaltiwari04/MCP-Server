# MCP Tools, Resources & Prompts Reference

Every tool returns a dual-formatted `CallToolResult` whose `structured_content` and first JSON `TextContent` block strictly conform to `ResponseEnvelope[T]`, paired with a compact Markdown summary block.

## Standardized `ResponseEnvelope` Contract

- `status`: `OK` | `STALE_DATA` | `NO_DATA_AVAILABLE` | `UNSUPPORTED_SYMBOL` | `INVALID_PARAMETERS` | `PERMISSION_DENIED` | `RATE_LIMITED` | `UPSTREAM_PROVIDER_ERROR`
- `metadata`: `source`, `data_timestamp` (ISO-8601 UTC), `fetched_at` (ISO-8601 UTC), `is_stale`, `staleness_threshold_seconds`, `currency`, `units`, `calendar_type` (`TRADING_DAYS` | `CALENDAR_DAYS`), `cache_hit`, `request_id`
- `warnings`: List of non-fatal caveats (e.g., `STALE_DATA`, delayed quote notice, dropped cross-exchange holiday dates)
- `error`: Populated deterministically on failures with `code`, `message`, `retryable`, and sanitized `details`

## Tools Matrix (15 Tools)

| Tool | Required Scope | Cache TTL | Purpose |
| --- | --- | --- | --- |
| `search_instruments` | `market:read` | 300s | Search equities, ETFs, indices, crypto, FX by query/ISIN/FIGI |
| `get_exchange_schedule` | `market:read` | 3600s | Market state (`OPEN`/`CLOSED`/extended), hours, holidays |
| `get_company_profile` | `market:read` | 86400s | GICS sector/industry, CEO, headcount, listing metadata |
| `get_market_quote` | `market:read` | 5s | Level-1 quote, bid/ask spread (bps), volume, market cap |
| `get_historical_prices` | `market:read` | 60s / 3600s | OHLCV bars (max 500/call) + deterministic VWAP & summary stats |
| `get_financial_metrics` | `market:read` | 3600s | Valuation, profitability, leverage/liquidity, per-share growth |
| `get_earnings_history` | `market:read` | 3600s | EPS/revenue consensus vs. actuals, surprises, next earnings date |
| `calculate_returns` | `market:read` | 60s | Cumulative/log return, CAGR, volatility, drawdown, Sharpe, alpha, beta |
| `calculate_technical_indicators` | `market:read` | 60s | SMA/EMA/RSI/MACD/Bollinger/ATR/VWAP/OBV snapshots & regime signals |
| `compare_instruments` | `market:read` | 60s | Multi-asset (2-10) aligned comparison, correlation matrix, rankings |
| `analyse_portfolio` | `portfolio:read` | 15s (User) | NAV, P&L, sector weights, beta, Sharpe/Sortino, VaR/CVaR, top 3 concentration |
| `simulate_portfolio_rebalance` | `simulation:execute` | 0s | Stateless pre/post-trade risk simulation & concentration/cash guardrails |
| `manage_watchlist` | `portfolio:read`/`write` | 15s (`LIST`) / 0s (`ADD`/`REMOVE`) | Idempotent watchlist list/add/remove with cache invalidation & notifications |
| `create_price_alert` | `portfolio:write` | 0s | Create user-scoped price / 1D move alert rule |
| `save_research_memo` | `research:write` | 0s | Persist grounded AI research memo with cited `data_timestamp`s |

## Resources

- `market://system/capabilities` (`application/json`) — Supported exchanges, intervals, indicators, SLAs, and rate limits.
- `market://system/glossary` (`application/json`) — Exact financial formulas used by the platform.
- `market://instrument/{symbol}/snapshot` (`text/markdown`) — Concurrent composite profile + quote + TTM metrics (`market:read`).
- `portfolio://user/{portfolio_id}/summary` (`text/markdown`) — Tenant-isolated portfolio holdings & risk snapshot (`portfolio:read`).

## Prompts

- `institutional_equity_tearsheet(symbol, benchmark="SPY")`
- `multi_stock_relative_value_comparison(symbols_csv, period="1M")`
- `pairs_trading_screen(symbol_a, symbol_b, lookback_period="6M")`
- `portfolio_tail_risk_audit(portfolio_id)`
