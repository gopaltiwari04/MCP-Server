# Market Intelligence MCP Server (`market-intelligence-mcp`)

A production-grade, standalone **Model Context Protocol (MCP)** gateway built in Python 3.12 with the official `mcp` SDK (`2.3.0`) and Pydantic v2. It exposes 15 quantitative market, fundamental, portfolio risk, and controlled workspace tools alongside dynamic resources and institutional workflow prompts—sitting strictly in front of the FastAPI Market Intelligence Backend with zero direct database access.

## Key Capabilities

- **Zero-Trust Identity Propagation:** ASGI authentication middleware supporting dual flows:
  - *Internal Service-to-Service + Delegated User JWT* (`X-Internal-API-Key` verified with `secrets.compare_digest` + `Authorization: Bearer <delegated_jwt>`).
  - *External OAuth 2.1 Resource Server* (JWKS/key JWT validation + RFC 9728 `/.well-known/oauth-protected-resource` discovery).
  - Binds an immutable `RequestSecurityContext` into a `contextvars.ContextVar` and propagates `X-Internal-API-Key`, `Authorization`, `X-Request-ID`, and `X-MCP-Tool-Name` to FastAPI without ever exposing tokens or `user_id` parameters to the LLM.
- **Resilience & Concurrency:**
  - Pooled `httpx.AsyncClient` managed via ASGI lifespan.
  - Three-state `CircuitBreaker` (`CLOSED` -> `OPEN` -> `HALF_OPEN`) with bounded exponential-backoff + full-jitter retries (`502/503/504`, `ConnectError`, `ReadTimeout`).
  - `SingleFlightCache` coalescing concurrent identical cache misses over a `TieredTTLCache` keyed by tenant-isolated SHA-256 digests (`PUBLIC` vs `user_id`).
- **Full MCP Spec Coverage:**
  - **15 Tools:** Instrument discovery, exchange calendars, quotes, historical OHLCV with deterministic VWAP/summary stats, financial metrics, earnings surprises, return attribution, technical indicators, multi-asset comparisons with progress notifications, portfolio VaR/CVaR analytics, stateless rebalance simulations, and idempotent workspace mutations.
  - **4 Resources & Subscriptions:** Static capability/glossary JSON resources plus dynamic `market://instrument/{symbol}/snapshot` and tenant-isolated `portfolio://user/{portfolio_id}/summary`, supporting both `subscriptions/listen` (2026-07-28) and `resources/subscribe` (2025-11-25).
  - **4 Institutional Prompts + Completions:** `institutional_equity_tearsheet`, `multi_stock_relative_value_comparison`, `pairs_trading_screen`, and `portfolio_tail_risk_audit`.
- **Observability & Probes:** `structlog` JSON logging with recursive secret/JWT/traceback redaction, plus `/health/live` and `/health/ready` probes.

## Quick Start

```bash
# 1. Create virtualenv and install package + dev tools
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"

# 2. Configure environment
cp .env.example .env

# 3. Run Streamable HTTP server
python -m app.main --transport streamable-http --host 0.0.0.0 --port 8080

# 4. Run stdio server (for local MCP Inspector / Claude Desktop debugging)
python -m app.main --transport stdio

# 5. Run full test suite
pytest -v
```

## Documentation

- [Architecture & Security Model](docs/architecture.md)
- [Backend FastAPI Route Audit & Contract](docs/backend-route-contract.md)
- [MCP Tools, Resources & Prompts Reference](docs/tools-reference.md)
- [Client Integration Guide (Internal Orchestrator, Claude, Cursor, MCP Inspector)](docs/client-integration.md)
