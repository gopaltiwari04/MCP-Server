"""FastAPI Internal Market Intelligence Backend application."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config import get_backend_settings
from app.market_store import InMemoryMarketBackendStore
from app.security import GatewayCaller, require_scope, verify_gateway_caller, verify_health_key

store = InMemoryMarketBackendStore()

app = FastAPI(
    title="FastAPI Internal Market Intelligence Backend",
    version="1.0.0",
    description="Domain API & quantitative store sitting behind market-intelligence-mcp.",
)

api_router = APIRouter(prefix="/api/v1")


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


@app.get("/health")
async def health(_: None = Depends(verify_health_key)) -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": "market-intelligence-backend",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


@api_router.get("/market/instruments/search")
async def search_instruments_route(
    q: str = Query(..., min_length=1, max_length=50),
    asset_type: str = Query("ALL"),
    exchange: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    return store.search_instruments(q=q, asset_type=asset_type, exchange=exchange, limit=limit)


@api_router.get("/market/exchanges/{exchange}/schedule")
async def exchange_schedule_route(
    exchange: str,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    res = store.get_exchange_schedule(exchange, start_date, end_date)
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": f"Unknown exchange {exchange}"})
    return res


@api_router.get("/market/quotes/{symbol}")
async def market_quote_route(
    symbol: str,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    res = store.get_quote(symbol)
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": f"Unsupported symbol {symbol}"})
    return res


@api_router.get("/market/history/{symbol}")
async def historical_prices_route(
    symbol: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    interval: str = Query("1d"),
    adjusted: bool = Query(True),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    if start_date > end_date:
        raise HTTPException(status_code=422, detail={"code": "INVALID_PARAMETERS", "message": "start_date > end_date"})
    res = store.get_history(symbol, start_date, end_date, interval, adjusted)
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": f"Unsupported symbol {symbol}"})
    return res


@api_router.get("/fundamentals/profile/{symbol}")
async def company_profile_route(
    symbol: str,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    res = store.get_company_profile(symbol)
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": f"Unsupported symbol {symbol}"})
    return res


@api_router.get("/fundamentals/metrics/{symbol}")
async def financial_metrics_route(
    symbol: str,
    period: Literal["TTM", "ANNUAL", "QUARTERLY"] = Query("TTM"),
    limit: int = Query(4, ge=1, le=20),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    res = store.get_financial_metrics(symbol, period, limit)
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": f"No metrics for {symbol}"})
    return res


@api_router.get("/fundamentals/earnings/{symbol}")
async def earnings_history_route(
    symbol: str,
    quarters: int = Query(8, ge=1, le=24),
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    res = store.get_earnings_history(symbol, quarters)
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": f"No earnings for {symbol}"})
    return res


@api_router.post("/analytics/returns")
async def calculate_returns_route(
    body: ReturnsRequest,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    res = store.calculate_returns(
        body.symbol,
        body.benchmark_symbol,
        body.start_date,
        body.end_date,
        body.calendar_basis,
        body.risk_free_rate,
    )
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": f"Unsupported symbol in returns"})
    return res


@api_router.post("/analytics/indicators")
async def calculate_indicators_route(
    body: IndicatorsRequest,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    res = store.calculate_indicators(
        body.symbol,
        body.indicators,
        body.interval,
        body.lookback_bars,
        body.tail_values,
    )
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": f"Unsupported symbol {body.symbol}"})
    return res


@api_router.post("/analytics/compare")
async def compare_instruments_route(
    body: CompareRequest,
    _caller: GatewayCaller = Depends(require_scope("market:read")),
) -> dict[str, Any]:
    res = store.compare_instruments(body.symbols, body.start_date, body.end_date)
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": "One or more unsupported symbols"})
    return res


@api_router.get("/portfolios/{portfolio_id}/analysis")
async def analyse_portfolio_route(
    portfolio_id: str,
    caller: GatewayCaller = Depends(require_scope("portfolio:read")),
) -> dict[str, Any]:
    res = store.analyse_portfolio(caller.user_id, portfolio_id)
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": f"Portfolio {portfolio_id} not found for user"})
    return res


@api_router.post("/portfolios/{portfolio_id}/simulate")
async def simulate_rebalance_route(
    portfolio_id: str,
    body: RebalanceSimulateRequest,
    caller: GatewayCaller = Depends(require_scope("simulation:execute")),
) -> dict[str, Any]:
    try:
        res = store.simulate_rebalance(
            caller.user_id,
            portfolio_id,
            [t.model_dump() for t in body.proposed_trades],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "UNSUPPORTED_SYMBOL", "message": str(exc)}) from exc
    if res is None:
        raise HTTPException(status_code=404, detail={"code": "NO_DATA_AVAILABLE", "message": f"Portfolio {portfolio_id} not found for user"})
    return res


@api_router.post("/watchlists/{watchlist_id}/items")
async def manage_watchlist_route(
    watchlist_id: str,
    body: WatchlistMutationRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    caller: GatewayCaller = Depends(verify_gateway_caller),
) -> dict[str, Any]:
    if body.action == "LIST":
        if not ({"portfolio:read", "portfolio:write"} & caller.scopes):
            raise HTTPException(status_code=403, detail={"code": "PERMISSION_DENIED", "message": "Missing portfolio:read"})
    elif "portfolio:write" not in caller.scopes:
        raise HTTPException(status_code=403, detail={"code": "PERMISSION_DENIED", "message": "Missing portfolio:write"})

    return store.mutate_watchlist(
        user_id=caller.user_id,
        watchlist_id=watchlist_id,
        action=body.action,
        symbols=[s.upper() for s in body.symbols],
        idempotency_key=idempotency_key,
    )


@api_router.post("/alerts", status_code=status.HTTP_201_CREATED)
async def create_price_alert_route(
    body: PriceAlertCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    caller: GatewayCaller = Depends(require_scope("portfolio:write")),
) -> dict[str, Any]:
    return store.create_alert(
        user_id=caller.user_id,
        symbol=body.symbol.upper(),
        condition=body.condition,
        threshold_value=body.threshold_value,
        note=body.note,
        idempotency_key=idempotency_key,
    )


@api_router.post("/research/memos", status_code=status.HTTP_201_CREATED)
async def save_research_memo_route(
    body: ResearchMemoCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    caller: GatewayCaller = Depends(require_scope("research:write")),
) -> dict[str, Any]:
    return store.save_memo(
        user_id=caller.user_id,
        title=body.title,
        symbols=[s.upper() for s in body.symbols],
        thesis_markdown=body.thesis_markdown,
        sentiment=body.sentiment,
        cited_data_timestamps=body.cited_data_timestamps,
        idempotency_key=idempotency_key,
    )


app.include_router(api_router)


if __name__ == "__main__":
    cfg = get_backend_settings()
    uvicorn.run(app, host=cfg.host, port=cfg.port)
