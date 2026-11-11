# Backend Route Audit & FastAPI Contract Specification

## Workspace Audit Findings

No FastAPI backend source files were mounted in the workspace (`c:\Users\tewar\MCP Server`). Accordingly, this document defines the complete **Route Mapping Matrix** and the **complete FastAPI Internal Router Implementation Specification** required to back all 15 MCP tools and `/health` readiness checks.

---

## Route Mapping Matrix

| MCP Capability | Scope Required | Target FastAPI Endpoint | Cache TTL | Tenant Isolation |
| --- | --- | --- | --- | --- |
| `search_instruments` | `market:read` | `GET /api/v1/market/instruments/search` | `300s` | `PUBLIC` |
| `get_exchange_schedule` | `market:read` | `GET /api/v1/market/exchanges/{exchange}/schedule` | `3600s` | `PUBLIC` |
| `get_market_quote` | `market:read` | `GET /api/v1/market/quotes/{symbol}` | `5s` | `PUBLIC` |
| `get_historical_prices` | `market:read` | `GET /api/v1/market/history/{symbol}` | `60s` (`1m`–`1h`) / `3600s` (`1d`+) | `PUBLIC` |
| `get_company_profile` | `market:read` | `GET /api/v1/fundamentals/profile/{symbol}` | `86400s` | `PUBLIC` |
| `get_financial_metrics` | `market:read` | `GET /api/v1/fundamentals/metrics/{symbol}` | `3600s` | `PUBLIC` |
| `get_earnings_history` | `market:read` | `GET /api/v1/fundamentals/earnings/{symbol}` | `3600s` | `PUBLIC` |
| `calculate_returns` | `market:read` | `POST /api/v1/analytics/returns` | `60s` | `PUBLIC` |
| `calculate_technical_indicators` | `market:read` | `POST /api/v1/analytics/indicators` | `60s` | `PUBLIC` |
| `compare_instruments` | `market:read` | `POST /api/v1/analytics/compare` | `60s` | `PUBLIC` |
| `analyse_portfolio` | `portfolio:read` | `GET /api/v1/portfolios/{portfolio_id}/analysis` | `15s` | `sec_ctx.user_id` |
| `simulate_portfolio_rebalance` | `simulation:execute` | `POST /api/v1/portfolios/{portfolio_id}/simulate` | `0s` | `sec_ctx.user_id` |
| `manage_watchlist` | `portfolio:read` / `portfolio:write` | `POST /api/v1/watchlists/{watchlist_id}/items` | `15s` (`LIST`) / `0s` (`ADD`/`REMOVE`) | `sec_ctx.user_id` |
| `create_price_alert` | `portfolio:write` | `POST /api/v1/alerts` | `0s` | `sec_ctx.user_id` |
| `save_research_memo` | `research:write` | `POST /api/v1/research/memos` | `0s` | `sec_ctx.user_id` |
| Readiness Probe | Internal API key | `GET /health` | `0s` | Internal |

---

## Complete FastAPI Internal Router Implementation Specification

```python
from __future__ import annotations

import secrets
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Security Dependency: Constant-Time Key Verification + Delegated JWT Auth
# ---------------------------------------------------------------------------

class GatewayCaller(BaseModel):
    user_id: str
    scopes: frozenset[str]
    request_id: str | None = None
    mcp_tool_name: str | None = None


def verify_internal_gateway_caller(
    request: Request,
    x_internal_api_key: str = Header(..., alias="X-Internal-API-Key"),
    authorization: str = Header(..., alias="Authorization"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_mcp_tool_name: str | None = Header(default=None, alias="X-MCP-Tool-Name"),
) -> GatewayCaller:
    cfg = request.app.state.settings
    if not secrets.compare_digest(x_internal_api_key, cfg.backend_internal_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "PERMISSION_DENIED", "message": "Invalid internal gateway API key."},
        )

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "PERMISSION_DENIED", "message": "Missing Bearer JWT."},
        )
    token = authorization[7:].strip()
    try:
        claims = jwt.decode(
            token,
            key=cfg.jwt_verification_key,
            algorithms=cfg.jwt_algorithms,
            audience=cfg.jwt_allowed_audiences,
            options={"require": ["sub", "exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "PERMISSION_DENIED", "message": f"Invalid delegated JWT: {type(exc).__name__}"},
        ) from exc

    raw_scope = claims.get("scope", "")
    scopes = frozenset(raw_scope.split() if isinstance(raw_scope, str) else [str(s) for s in raw_scope])
    return GatewayCaller(
        user_id=str(claims["sub"]),
        scopes=scopes,
        request_id=x_request_id,
        mcp_tool_name=x_mcp_tool_name,
    )


def require_scope(required: str):
    def _dep(caller: GatewayCaller = Depends(verify_internal_gateway_caller)) -> GatewayCaller:
        if required not in caller.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": f"Missing required scope: {required}"},
            )
        return caller

    return _dep


# ---------------------------------------------------------------------------
# Request / Service Contracts
# ---------------------------------------------------------------------------

class ReturnsRequest(BaseModel):
    symbol: str
    benchmark_symbol: str = "SPY"
    period: str
    start_date: date
    end_date: date
    calendar_basis: Literal["TRADING_DAYS", "CALENDAR_DAYS"] = "TRADING_DAYS"
    risk_free_rate: float = 0.045


class IndicatorsRequest(BaseModel):
    symbol: str
    indicators: list[str]
    interval: Literal["1h", "1d", "1wk"] = "1d"
    lookback_bars: int = Field(100, ge=20, le=500)
    tail_values: int = Field(10, ge=1, le=50)


class CompareRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=2, max_length=10)
    period: str
    start_date: date
    end_date: date
    metrics: list[str]
    risk_free_rate: float = 0.045


class ProposedTradeRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    weight_delta_pct: float | None = None
    share_delta: float | None = None


class RebalanceSimulateRequest(BaseModel):
    benchmark_symbol: str = "SPY"
    proposed_trades: list[ProposedTradeRequest] = Field(..., min_length=1, max_length=25)


class WatchlistMutationRequest(BaseModel):
    action: Literal["LIST", "ADD", "REMOVE"]
    watchlist_name: str = "Default"
    symbols: list[str] = Field(default_factory=list)


class PriceAlertCreateRequest(BaseModel):
    symbol: str
    condition: Literal["CROSSES_ABOVE", "CROSSES_BELOW", "PCT_CHANGE_1D_EXCEEDS"]
    threshold_value: float = Field(..., gt=0)
    note: str | None = Field(default=None, max_length=280)


class ResearchMemoCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=160)
    symbols: list[str] = Field(..., min_length=1, max_length=15)
    thesis_markdown: str = Field(..., min_length=10, max_length=32000)
    sentiment: Literal["BULLISH", "NEUTRAL", "BEARISH"]
    cited_data_timestamps: list[str] = Field(..., min_length=1)


class MarketBackendServices(Protocol):
    async def search_instruments(self, q: str, asset_type: str, exchange: str | None, limit: int) -> dict[str, Any]: ...
    async def get_exchange_schedule(self, exchange: str, start_date: date | None, end_date: date | None) -> dict[str, Any]: ...
    async def get_quote(self, symbol: str) -> dict[str, Any] | None: ...
    async def get_history(self, symbol: str, start_date: date, end_date: date, interval: str, adjusted: bool) -> dict[str, Any] | None: ...
    async def get_company_profile(self, symbol: str) -> dict[str, Any] | None: ...
    async def get_financial_metrics(self, symbol: str, period: str, limit: int) -> dict[str, Any] | None: ...
    async def get_earnings_history(self, symbol: str, quarters: int) -> dict[str, Any] | None: ...
    async def calculate_returns(self, body: ReturnsRequest) -> dict[str, Any]: ...
    async def calculate_indicators(self, body: IndicatorsRequest) -> dict[str, Any]: ...
    async def compare_instruments(self, body: CompareRequest) -> dict[str, Any]: ...
    async def analyse_portfolio(self, user_id: str, portfolio_id: str, benchmark_symbol: str, confidence_level: float, lookback_days: int) -> dict[str, Any] | None: ...
    async def simulate_rebalance(self, user_id: str, portfolio_id: str, body: RebalanceSimulateRequest) -> dict[str, Any] | None: ...
    async def mutate_watchlist(self, user_id: str, watchlist_id: str, body: WatchlistMutationRequest, idempotency_key: str | None) -> dict[str, Any]: ...
    async def create_alert(self, user_id: str, body: PriceAlertCreateRequest, idempotency_key: str | None) -> dict[str, Any]: ...
    async def save_memo(self, user_id: str, body: ResearchMemoCreateRequest, idempotency_key: str | None) -> dict[str, Any]: ...


def get_services(request: Request) -> MarketBackendServices:
    return request.app.state.services


# ---------------------------------------------------------------------------
# Router Handlers (All 15 Endpoints + Health)
# ---------------------------------------------------------------------------

health_router = APIRouter()
router = APIRouter(prefix="/api/v1")


@health_router.get("/health")
async def internal_health(request: Request) -> dict[str, Any]:
    db_ok = await request.app.state.db_ping()
    if not db_ok:
        raise HTTPException(status_code=503, detail={"status": "unhealthy"})
    return {"status": "healthy", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/market/instruments/search")
async def search_instruments_route(
    q: str = Query(..., min_length=1, max_length=50),
    asset_type: str = Query("ALL"),
    exchange: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    return await svc.search_instruments(q=q, asset_type=asset_type, exchange=exchange, limit=limit)


@router.get("/market/exchanges/{exchange}/schedule")
async def exchange_schedule_route(
    exchange: str,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    result = await svc.get_exchange_schedule(exchange=exchange.upper(), start_date=start_date, end_date=end_date)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": f"Unknown exchange {exchange}"})
    return result


@router.get("/market/quotes/{symbol}")
async def market_quote_route(
    symbol: str,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    quote = await svc.get_quote(symbol.upper())
    if quote is None:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": f"Unsupported symbol {symbol}"})
    return quote


@router.get("/market/history/{symbol}")
async def historical_prices_route(
    symbol: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    interval: str = Query("1d"),
    adjusted: bool = Query(True),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    if start_date > end_date:
        raise HTTPException(status_code=422, detail={"code": "INVALID_PARAMETERS", "message": "start_date > end_date"})
    history = await svc.get_history(symbol.upper(), start_date, end_date, interval, adjusted)
    if history is None:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": f"Unsupported symbol {symbol}"})
    return history


@router.get("/fundamentals/profile/{symbol}")
async def company_profile_route(
    symbol: str,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    profile = await svc.get_company_profile(symbol.upper())
    if profile is None:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": f"No profile for {symbol}"})
    return profile


@router.get("/fundamentals/metrics/{symbol}")
async def financial_metrics_route(
    symbol: str,
    period: Literal["TTM", "ANNUAL", "QUARTERLY"] = Query("TTM"),
    limit: int = Query(4, ge=1, le=20),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    metrics = await svc.get_financial_metrics(symbol.upper(), period, limit)
    if metrics is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": f"No metrics for {symbol}"})
    return metrics


@router.get("/fundamentals/earnings/{symbol}")
async def earnings_history_route(
    symbol: str,
    quarters: int = Query(8, ge=1, le=24),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    earnings = await svc.get_earnings_history(symbol.upper(), quarters)
    if earnings is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": f"No earnings for {symbol}"})
    return earnings


@router.post("/analytics/returns")
async def calculate_returns_route(
    body: ReturnsRequest,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    return await svc.calculate_returns(body)


@router.post("/analytics/indicators")
async def calculate_indicators_route(
    body: IndicatorsRequest,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    return await svc.calculate_indicators(body)


@router.post("/analytics/compare")
async def compare_instruments_route(
    body: CompareRequest,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    return await svc.compare_instruments(body)


@router.get("/portfolios/{portfolio_id}/analysis")
async def analyse_portfolio_route(
    portfolio_id: str,
    benchmark_symbol: str = Query("SPY"),
    confidence_level: float = Query(0.95, gt=0.5, lt=1.0),
    lookback_days: int = Query(252, ge=20, le=1260),
    caller: GatewayCaller = Depends(require_scope("portfolio:read")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    analysis = await svc.analyse_portfolio(
        user_id=caller.user_id,
        portfolio_id=portfolio_id,
        benchmark_symbol=benchmark_symbol.upper(),
        confidence_level=confidence_level,
        lookback_days=lookback_days,
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": "Portfolio not found"})
    return analysis


@router.post("/portfolios/{portfolio_id}/simulate")
async def simulate_rebalance_route(
    portfolio_id: str,
    body: RebalanceSimulateRequest,
    caller: GatewayCaller = Depends(require_scope("simulation:execute")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    sim = await svc.simulate_rebalance(user_id=caller.user_id, portfolio_id=portfolio_id, body=body)
    if sim is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": "Portfolio not found"})
    return sim


@router.post("/watchlists/{watchlist_id}/items")
async def manage_watchlist_route(
    watchlist_id: str,
    body: WatchlistMutationRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    caller: GatewayCaller = Depends(verify_internal_gateway_caller),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    if body.action == "LIST":
        if not ({"portfolio:read", "portfolio:write"} & caller.scopes):
            raise HTTPException(status_code=403, detail={"code": "PERMISSION_DENIED", "message": "Missing portfolio:read"})
    elif "portfolio:write" not in caller.scopes:
        raise HTTPException(status_code=403, detail={"code": "PERMISSION_DENIED", "message": "Missing portfolio:write"})

    return await svc.mutate_watchlist(
        user_id=caller.user_id,
        watchlist_id=watchlist_id,
        body=body,
        idempotency_key=idempotency_key,
    )


@router.post("/alerts", status_code=status.HTTP_201_CREATED)
async def create_price_alert_route(
    body: PriceAlertCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    caller: GatewayCaller = Depends(require_scope("portfolio:write")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    return await svc.create_alert(user_id=caller.user_id, body=body, idempotency_key=idempotency_key)


@router.post("/research/memos", status_code=status.HTTP_201_CREATED)
async def save_research_memo_route(
    body: ResearchMemoCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    caller: GatewayCaller = Depends(require_scope("research:write")),
    svc: MarketBackendServices = Depends(get_services),
) -> dict[str, Any]:
    return await svc.save_memo(user_id=caller.user_id, body=body, idempotency_key=idempotency_key)
```

### Error Envelope Alignment

When FastAPI returns error responses (`400`/`404`/`422`/`429`/`5xx`), returning JSON `{"detail": {"code": "UNSUPPORTED_SYMBOL", "message": "..."}}` allows `BackendClient._handle_response` to classify `UNSUPPORTED_SYMBOL` vs `NO_DATA_AVAILABLE` deterministically on HTTP `404`.
