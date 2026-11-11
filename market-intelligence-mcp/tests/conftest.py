"""Shared pytest fixtures: FakeClock, test JWTs, mocked FastAPI backend (respx), and ASGI lifespan."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
import respx
from mcp import Client
from starlette.types import ASGIApp

from app.auth.context import (
    RequestSecurityContext,
    reset_security_context,
    set_security_context,
)
from app.config.settings import Settings
from app.server import create_mcp_server


class FakeClock:
    """Deterministic monotonic clock for testing TTL caches, circuit breakers, and rate limits."""

    def __init__(self, initial: float = 1000.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


INTERNAL_JWT_SECRET = "test-internal-jwt-secret-32-bytes-minimum!!"
OAUTH_JWT_SECRET = "test-oauth-jwt-secret-32-bytes-minimum!!!!!"
INTERNAL_API_KEY = "test-gateway-internal-key"
BACKEND_API_KEY = "test-backend-internal-key"


def make_test_settings(**overrides: Any) -> Settings:
    """Create isolated Settings for unit, integration, and security tests."""
    defaults: dict[str, Any] = {
        "env": "test",
        "log_level": "INFO",
        "log_format": "json",
        "backend_base_url": "http://backend.test",
        "backend_internal_api_key": BACKEND_API_KEY,
        "backend_max_retries": 2,
        "internal_api_key": INTERNAL_API_KEY,
        "internal_jwt_issuer": "https://orchestrator.internal",
        "internal_jwt_audience": "market-intelligence-mcp",
        "internal_jwt_algorithm": "HS256",
        "internal_jwt_secret": INTERNAL_JWT_SECRET,
        "oauth_enabled": True,
        "oauth_resource_server_url": "https://mcp.example.com/mcp",
        "oauth_issuer": "https://auth.example.com",
        "oauth_audience": "https://mcp.example.com/mcp",
        "oauth_algorithms": ["HS256"],
        "oauth_public_key": OAUTH_JWT_SECRET,
        "circuit_breaker_failure_threshold": 5,
        "circuit_breaker_recovery_timeout_seconds": 15.0,
        "rate_limit_requests": 100,
        "rate_limit_window_seconds": 60,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_internal_jwt(
    user_id: str = "user_alice",
    scopes: list[str] | str = ("market:read", "portfolio:read", "portfolio:write", "simulation:execute", "research:write"),
    *,
    exp_offset_seconds: int = 600,
    issuer: str = "https://orchestrator.internal",
    audience: str = "market-intelligence-mcp",
    secret: str = INTERNAL_JWT_SECRET,
    client_id: str = "orchestrator-web",
) -> str:
    """Mint a signed HS256 delegated user JWT for Flow A tests."""
    now = int(datetime.now(UTC).timestamp())
    scope_str = scopes if isinstance(scopes, str) else " ".join(scopes)
    payload = {
        "sub": user_id,
        "azp": client_id,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + exp_offset_seconds,
        "scope": scope_str,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def make_oauth_jwt(
    user_id: str = "user_ext_bob",
    scopes: list[str] | str = ("market:read",),
    *,
    exp_offset_seconds: int = 600,
    issuer: str = "https://auth.example.com",
    audience: str = "https://mcp.example.com/mcp",
    secret: str = OAUTH_JWT_SECRET,
    client_id: str = "cursor-ide",
) -> str:
    """Mint a signed HS256 OAuth 2.1 Bearer JWT for Flow B tests."""
    now = int(datetime.now(UTC).timestamp())
    scope_str = scopes if isinstance(scopes, str) else " ".join(scopes)
    payload = {
        "sub": user_id,
        "client_id": client_id,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + exp_offset_seconds,
        "scope": scope_str,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@asynccontextmanager
async def enter_asgi_lifespan(app: ASGIApp) -> AsyncIterator[None]:
    """Drive Starlette/MCP ASGI lifespan startup and shutdown in-process."""
    startup_complete = asyncio.Event()
    shutdown_complete = asyncio.Event()
    receive_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    await receive_queue.put({"type": "lifespan.startup"})

    async def receive() -> dict[str, Any]:
        return await receive_queue.get()

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "lifespan.startup.complete":
            startup_complete.set()
        elif message["type"] == "lifespan.startup.failed":
            startup_complete.set()
            raise RuntimeError(message.get("message", "ASGI lifespan startup failed"))
        elif message["type"] == "lifespan.shutdown.complete":
            shutdown_complete.set()

    task = asyncio.create_task(app({"type": "lifespan"}, receive, send))
    await asyncio.wait_for(startup_complete.wait(), timeout=5.0)
    try:
        yield
    finally:
        await receive_queue.put({"type": "lifespan.shutdown"})
        await asyncio.wait_for(shutdown_complete.wait(), timeout=5.0)
        await task


def iso_now(offset_seconds: int = 0) -> str:
    return (datetime.now(UTC) + timedelta(seconds=offset_seconds)).isoformat().replace("+00:00", "Z")


def register_standard_backend_mocks(mock: respx.MockRouter) -> None:
    """Register deterministic FastAPI mock responses for all 15 tools + /health."""
    fresh_ts = iso_now(-2)

    mock.get("/health").mock(
        return_value=httpx.Response(200, json={"status": "healthy", "service": "market-fastapi"})
    )

    mock.get("/api/v1/market/instruments/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "source": "polygon-ref",
                "data_timestamp": fresh_ts,
                "total_matches": 2,
                "instruments": [
                    {
                        "symbol": "NVDA",
                        "name": "NVIDIA Corporation",
                        "asset_type": "EQUITY",
                        "primary_exchange": "NASDAQ",
                        "currency": "USD",
                        "isin": "US67066G1040",
                        "figi": "BBG000BBJQV0",
                        "is_active": True,
                        "country": "US",
                    },
                    {
                        "symbol": "AMD",
                        "name": "Advanced Micro Devices, Inc.",
                        "asset_type": "EQUITY",
                        "primary_exchange": "NASDAQ",
                        "currency": "USD",
                        "isin": "US0079031078",
                        "figi": "BBG000BBQCY0",
                        "is_active": True,
                        "country": "US",
                    },
                ],
            },
        )
    )

    mock.get("/api/v1/market/exchanges/NASDAQ/schedule").mock(
        return_value=httpx.Response(
            200,
            json={
                "source": "exchange-cal",
                "data_timestamp": fresh_ts,
                "exchange": "NASDAQ",
                "exchange_name": "Nasdaq Global Select Market",
                "timezone": "America/New_York",
                "market_state": "OPEN",
                "regular_open_local": "09:30",
                "regular_close_local": "16:00",
                "is_trading_day": True,
                "upcoming_holidays": [
                    {"holiday_date": "2026-11-26", "name": "Thanksgiving Day", "status": "CLOSED"}
                ],
            },
        )
    )

    def _quote_handler(request: httpx.Request) -> httpx.Response:
        sym = request.url.path.rsplit("/", 1)[-1]
        if sym == "INVALIDXYZ":
            return httpx.Response(
                404,
                json={"detail": {"code": "UNSUPPORTED_SYMBOL", "message": f"Unsupported symbol {sym}"}},
            )
        prices = {"NVDA": 148.50, "AMD": 156.20, "SPY": 592.10, "AAPL": 229.40}
        price = prices.get(sym, 100.0)
        return httpx.Response(
            200,
            json={
                "source": "polygon-quotes",
                "data_timestamp": fresh_ts,
                "symbol": sym,
                "last_price": price,
                "bid": round(price - 0.02, 2),
                "ask": round(price + 0.02, 2),
                "open": round(price - 1.1, 2),
                "high": round(price + 1.8, 2),
                "low": round(price - 1.5, 2),
                "previous_close": round(price - 2.0, 2),
                "change": 2.0,
                "change_pct": round((2.0 / (price - 2.0)) * 100, 2),
                "volume": 42_500_000,
                "avg_volume_30d": 38_000_000,
                "market_cap": 3_620_000_000_000.0 if sym == "NVDA" else 252_000_000_000.0,
                "currency": "USD",
                "exchange": "NASDAQ",
                "is_delayed": False,
                "delay_minutes": 0,
                "quote_timestamp": fresh_ts,
            },
        )

    mock.get(
        path__regex=r"^/api/v1/market/quotes/(?!OLDQ$|LIMIT$)[A-Z0-9.\-^=]+$",
        name="quotes",
    ).mock(side_effect=_quote_handler)

    def _history_handler(request: httpx.Request) -> httpx.Response:
        sym = request.url.path.rsplit("/", 1)[-1]
        base = 130.0 if sym == "NVDA" else 145.0
        bars = []
        start_dt = datetime(2026, 10, 12, 20, 0, tzinfo=UTC)
        for i in range(20):
            dt = start_dt + timedelta(days=i)
            if dt.weekday() >= 5:
                continue
            c = round(base + i * (0.9 if sym == "NVDA" else 0.55), 2)
            bars.append(
                {
                    "timestamp": dt.isoformat().replace("+00:00", "Z"),
                    "open": round(c - 0.8, 2),
                    "high": round(c + 1.2, 2),
                    "low": round(c - 1.1, 2),
                    "close": c,
                    "adjusted_close": c,
                    "volume": 1_000_000 + i * 50_000,
                }
            )
        return httpx.Response(
            200,
            json={
                "source": "polygon-agg",
                "data_timestamp": fresh_ts,
                "currency": "USD",
                "bars": bars,
            },
        )

    mock.get(path__regex=r"^/api/v1/market/history/[A-Z0-9.\-^=]+$", name="history").mock(side_effect=_history_handler)

    def _profile_handler(request: httpx.Request) -> httpx.Response:
        sym = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "source": "sec-edgar-ref",
                "data_timestamp": fresh_ts,
                "symbol": sym,
                "legal_name": "NVIDIA Corporation" if sym == "NVDA" else f"{sym} Corp.",
                "sector": "Information Technology",
                "industry": "Semiconductors",
                "gics_sector_code": "45",
                "headquarters": "Santa Clara, CA",
                "country": "US",
                "ceo": "Jensen Huang" if sym == "NVDA" else "Lisa Su",
                "employees": 29600,
                "fiscal_year_end": "January",
                "website": "https://www.nvidia.com",
                "description": "Accelerated computing and AI semiconductor leader.",
                "primary_exchange": "NASDAQ",
                "currency": "USD",
            },
        )

    mock.get(path__regex=r"^/api/v1/fundamentals/profile/[A-Z0-9.\-^=]+$", name="profile").mock(side_effect=_profile_handler)

    def _metrics_handler(request: httpx.Request) -> httpx.Response:
        sym = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "source": "fundamentals-db",
                "data_timestamp": fresh_ts,
                "currency": "USD",
                "periods": [
                    {
                        "fiscal_period": "TTM",
                        "period_end_date": "2026-09-30",
                        "valuation": {
                            "pe_ratio": 48.2 if sym == "NVDA" else 39.4,
                            "forward_pe": 34.1 if sym == "NVDA" else 28.6,
                            "peg_ratio": 1.15,
                            "pb_ratio": 42.0,
                            "ps_ratio": 28.4,
                            "ev_to_ebitda": 41.5 if sym == "NVDA" else 29.8,
                            "ev_to_revenue": 27.9,
                            "free_cash_flow_yield": 0.021,
                        },
                        "profitability": {
                            "gross_margin": 0.745,
                            "operating_margin": 0.612,
                            "net_margin": 0.531,
                            "roe": 0.91,
                            "roa": 0.48,
                            "roic": 0.67,
                        },
                        "liquidity_leverage": {
                            "current_ratio": 3.5,
                            "quick_ratio": 2.9,
                            "debt_to_equity": 0.19,
                            "net_debt_to_ebitda": -0.45,
                            "interest_coverage": 85.0,
                        },
                        "per_share_growth": {
                            "eps_diluted": 2.85,
                            "revenue_per_share": 4.92,
                            "book_value_per_share": 3.12,
                            "revenue_growth_yoy": 0.94,
                            "eps_growth_yoy": 1.12,
                        },
                    }
                ],
            },
        )

    mock.get(path__regex=r"^/api/v1/fundamentals/metrics/[A-Z0-9.\-^=]+$", name="metrics").mock(side_effect=_metrics_handler)

    mock.get(path__regex=r"^/api/v1/fundamentals/earnings/[A-Z0-9.\-^=]+$", name="earnings").mock(
        return_value=httpx.Response(
            200,
            json={
                "source": "earnings-consensus",
                "data_timestamp": fresh_ts,
                "currency": "USD",
                "next_earnings_date": "2026-11-19",
                "quarters": [
                    {
                        "fiscal_quarter": "Q3 FY2027",
                        "report_date": "2026-08-28",
                        "eps_consensus": 0.74,
                        "eps_actual": 0.81,
                        "eps_surprise_pct": 9.46,
                        "revenue_consensus": 32_500_000_000.0,
                        "revenue_actual": 35_080_000_000.0,
                        "revenue_surprise_pct": 7.94,
                    }
                ],
            },
        )
    )

    def _returns_handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content)
        sym = body["symbol"]
        return httpx.Response(
            200,
            json={
                "source": "quant-engine",
                "data_timestamp": fresh_ts,
                "currency": "USD",
                "observations_count": 21,
                "cumulative_return_pct": 12.45 if sym == "NVDA" else 7.82,
                "log_return": 0.1173 if sym == "NVDA" else 0.0753,
                "annualized_return_cagr_pct": 212.4 if sym == "NVDA" else 118.2,
                "annualized_volatility_pct": 38.4 if sym == "NVDA" else 42.1,
                "max_drawdown_pct": -5.12 if sym == "NVDA" else -7.45,
                "sharpe_ratio": 2.41 if sym == "NVDA" else 1.68,
                "alpha": 0.18 if sym == "NVDA" else 0.09,
                "beta": 1.62 if sym == "NVDA" else 1.48,
                "active_return_pct": 8.95 if sym == "NVDA" else 4.32,
            },
        )

    mock.post("/api/v1/analytics/returns").mock(side_effect=_returns_handler)

    def _indicators_handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content)
        sym = body["symbol"]
        price = 148.5 if sym == "NVDA" else 156.2
        return httpx.Response(
            200,
            json={
                "source": "quant-indicators",
                "data_timestamp": fresh_ts,
                "currency": "USD",
                "latest_price": price,
                "overall_regime": "BULLISH_MOMENTUM",
                "snapshots": [
                    {"indicator": "RSI_14", "latest": {"rsi": 62.4}, "regime_signal": "NEUTRAL"},
                    {
                        "indicator": "MACD",
                        "latest": {"macd": 2.45, "signal": 1.82, "histogram": 0.63},
                        "regime_signal": "BULLISH",
                    },
                    {"indicator": "SMA_50", "latest": {"value": price - 8.2}},
                ],
                "tail_series": [
                    {"timestamp": fresh_ts, "values": {"RSI_14": 62.4, "MACD": 2.45}},
                ],
            },
        )

    mock.post("/api/v1/analytics/indicators").mock(side_effect=_indicators_handler)

    mock.post("/api/v1/analytics/compare").mock(
        return_value=httpx.Response(
            200,
            json={
                "source": "quant-compare",
                "data_timestamp": fresh_ts,
                "currency": "USD",
                "aligned_start_date": "2026-10-12",
                "aligned_end_date": "2026-11-11",
                "aligned_observations": 22,
                "dropped_dates_by_symbol": {"NVDA": [], "AMD": []},
                "comparison_table": [
                    {
                        "symbol": "NVDA",
                        "cumulative_return_pct": 12.45,
                        "annualized_volatility_pct": 38.4,
                        "sharpe_ratio": 2.41,
                        "max_drawdown_pct": -5.12,
                        "pe_ratio": 48.2,
                        "ev_to_ebitda": 41.5,
                        "market_cap": 3_620_000_000_000.0,
                    },
                    {
                        "symbol": "AMD",
                        "cumulative_return_pct": 7.82,
                        "annualized_volatility_pct": 42.1,
                        "sharpe_ratio": 1.68,
                        "max_drawdown_pct": -7.45,
                        "pe_ratio": 39.4,
                        "ev_to_ebitda": 29.8,
                        "market_cap": 252_000_000_000.0,
                    },
                ],
                "correlation_matrix": {
                    "NVDA": {"NVDA": 1.0, "AMD": 0.78},
                    "AMD": {"NVDA": 0.78, "AMD": 1.0},
                },
            },
        )
    )

    def _portfolio_analysis_handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        token = auth.replace("Bearer ", "")
        decoded = jwt.decode(token, options={"verify_signature": False}) if token else {}
        sub = decoded.get("sub", "unknown")
        nav = 1_250_000.0 if sub == "user_alice" else 420_000.0
        return httpx.Response(
            200,
            json={
                "source": "portfolio-risk-engine",
                "data_timestamp": fresh_ts,
                "portfolio_name": f"{sub} Core Equity",
                "base_currency": "USD",
                "nav": nav,
                "cash_balance": nav * 0.08,
                "cash_weight_pct": 8.0,
                "portfolio_beta": 1.18,
                "annualized_volatility_pct": 19.4,
                "sharpe_ratio": 1.52,
                "sortino_ratio": 2.04,
                "historical_var_pct": -2.15,
                "parametric_var_pct": -2.02,
                "expected_shortfall_cvar_pct": -3.11,
                "historical_var_amount": round(nav * -0.0215, 2),
                "expected_shortfall_cvar_amount": round(nav * -0.0311, 2),
                "positions": [
                    {
                        "symbol": "NVDA",
                        "name": "NVIDIA Corporation",
                        "asset_class": "EQUITY",
                        "sector": "Information Technology",
                        "quantity": 1500,
                        "market_price": 148.50,
                        "market_value": 222_750.0,
                        "weight_pct": 17.82,
                        "unrealized_pnl": 48_000.0,
                        "unrealized_pnl_pct": 27.47,
                    }
                ],
                "sector_allocation": [
                    {"category": "Information Technology", "weight_pct": 54.0, "market_value": nav * 0.54},
                    {"category": "Cash", "weight_pct": 8.0, "market_value": nav * 0.08},
                ],
                "asset_class_allocation": [
                    {"category": "EQUITY", "weight_pct": 92.0, "market_value": nav * 0.92},
                    {"category": "CASH", "weight_pct": 8.0, "market_value": nav * 0.08},
                ],
                "top_concentration_contributors": [
                    {"symbol": "NVDA", "weight_pct": 17.82, "risk_contribution_pct": 28.4},
                ],
            },
        )

    mock.get(path__regex=r"^/api/v1/portfolios/[A-Za-z0-9._\-]+/analysis$", name="portfolio_analysis").mock(
        side_effect=_portfolio_analysis_handler
    )

    mock.post(path__regex=r"^/api/v1/portfolios/[A-Za-z0-9._\-]+/simulate$", name="portfolio_simulate").mock(
        return_value=httpx.Response(
            200,
            json={
                "source": "portfolio-simulator",
                "data_timestamp": fresh_ts,
                "base_currency": "USD",
                "estimated_cash_impact": -125_000.0,
                "beta_shift": 0.14,
                "var_delta_pct": -0.42,
                "pre_trade": {
                    "cash_balance": 100_000.0,
                    "cash_weight_pct": 8.0,
                    "portfolio_beta": 1.18,
                    "annualized_volatility_pct": 19.4,
                    "var_95_pct": -2.15,
                    "cvar_95_pct": -3.11,
                    "sector_weights_pct": {"Information Technology": 54.0},
                    "position_weights_pct": {"NVDA": 17.82},
                },
                "post_trade": {
                    "cash_balance": -25_000.0,
                    "cash_weight_pct": -2.0,
                    "portfolio_beta": 1.32,
                    "annualized_volatility_pct": 22.1,
                    "var_95_pct": -2.57,
                    "cvar_95_pct": -3.72,
                    "sector_weights_pct": {"Information Technology": 64.0},
                    "position_weights_pct": {"NVDA": 27.82},
                },
                "constraint_violations": [],
            },
        )
    )

    mock.post(path__regex=r"^/api/v1/watchlists/[A-Za-z0-9._\-]+/items$", name="watchlists").mock(
        return_value=httpx.Response(
            200,
            json={
                "source": "watchlists-svc",
                "data_timestamp": fresh_ts,
                "symbols": ["NVDA", "AMD", "MSFT"],
                "updated_at": fresh_ts,
            },
        )
    )

    mock.post("/api/v1/alerts").mock(
        return_value=httpx.Response(
            201,
            json={
                "source": "alerts-svc",
                "data_timestamp": fresh_ts,
                "alert_id": "alrt_9001",
                "status": "ACTIVE",
                "created_at": fresh_ts,
            },
        )
    )

    mock.post("/api/v1/research/memos").mock(
        return_value=httpx.Response(
            201,
            json={
                "source": "research-notes-svc",
                "data_timestamp": fresh_ts,
                "memo_id": "memo_7001",
                "created_at": fresh_ts,
            },
        )
    )


@pytest.fixture
def test_settings() -> Settings:
    return make_test_settings()


@pytest.fixture
def respx_backend() -> respx.MockRouter:
    with respx.mock(base_url="http://backend.test", assert_all_called=False) as mock:
        register_standard_backend_mocks(mock)
        yield mock


@pytest.fixture
def bind_full_security_context():
    """Bind an authenticated full-scope RequestSecurityContext for direct/in-proc tests."""
    token_jwt = make_internal_jwt(
        user_id="user_alice",
        scopes=["market:read", "portfolio:read", "portfolio:write", "simulation:execute", "research:write"],
    )
    sec_ctx = RequestSecurityContext(
        user_id="user_alice",
        client_id="orchestrator-web",
        auth_mode="INTERNAL_DELEGATED",
        scopes=frozenset(
            ["market:read", "portfolio:read", "portfolio:write", "simulation:execute", "research:write"]
        ),
        delegated_jwt=token_jwt,
        internal_api_key_verified=True,
        issuer="https://orchestrator.internal",
        audience="market-intelligence-mcp",
        token_expires_at=int(datetime.now(UTC).timestamp()) + 600,
        request_id="req-test-001",
    )
    tok = set_security_context(sec_ctx)
    try:
        yield sec_ctx
    finally:
        reset_security_context(tok)


@pytest.fixture
def mcp_server(test_settings: Settings, respx_backend: respx.MockRouter, bind_full_security_context):
    """MCPServer instance backed by respx FastAPI mocks and full-scope test identity."""
    return create_mcp_server(test_settings)
