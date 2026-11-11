"""Market quotes and historical OHLCV bar schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MarketQuoteData(BaseModel):
    """Normalized level-1 market quote payload."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    last_price: float
    bid: float | None = None
    ask: float | None = None
    spread_bps: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    volume: int | None = Field(None, ge=0)
    avg_volume_30d: int | None = Field(None, ge=0)
    market_cap: float | None = Field(None, ge=0)
    currency: str
    exchange: str
    is_delayed: bool = False
    delay_minutes: int = Field(0, ge=0)
    quote_timestamp: datetime


class OHLCVBar(BaseModel):
    """Single OHLCV price bar."""

    model_config = ConfigDict(extra="ignore")

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = Field(..., ge=0)
    adjusted_close: float | None = None
    vwap: float | None = None


class HistoricalSummaryStats(BaseModel):
    """Deterministic descriptive summary over returned OHLCV bars."""

    model_config = ConfigDict(extra="forbid")

    period_high: float
    period_low: float
    vwap: float | None = None
    mean_close: float
    std_close: float = Field(..., ge=0)
    total_volume: float = Field(..., ge=0)
    trading_days_count: int = Field(..., ge=1)


class HistoricalPricesData(BaseModel):
    """Payload returned by `get_historical_prices`."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    interval: Literal["1m", "5m", "15m", "1h", "1d", "1wk", "1mo"]
    start_date: date
    end_date: date
    adjusted: bool
    currency: str
    bars_count: int = Field(..., ge=0)
    was_compacted: bool = False
    summary_stats: HistoricalSummaryStats | None = None
    bars: list[OHLCVBar] = Field(default_factory=list)
