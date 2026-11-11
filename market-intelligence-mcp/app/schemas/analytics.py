"""Quantitative return attribution, technical indicators, and comparison schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReturnsData(BaseModel):
    """Payload returned by `calculate_returns`."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    benchmark_symbol: str
    period: str
    start_date: date
    end_date: date
    calendar_basis: Literal["TRADING_DAYS", "CALENDAR_DAYS"]
    observations_count: int = Field(..., ge=0)
    cumulative_return_pct: float
    log_return: float
    annualized_return_cagr_pct: float
    annualized_volatility_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    risk_free_rate_used: float
    alpha: float | None = None
    beta: float | None = None
    active_return_pct: float | None = None


class IndicatorPoint(BaseModel):
    """Single timestamped indicator observation."""

    model_config = ConfigDict(extra="ignore")

    timestamp: datetime
    values: dict[str, float | None]


class IndicatorSnapshot(BaseModel):
    """Latest value and deterministic regime signal for a technical indicator."""

    model_config = ConfigDict(extra="ignore")

    indicator: str
    latest: dict[str, float | None]
    regime_signal: str | None = None
    crossover_timestamp: datetime | None = None


class TechnicalIndicatorsData(BaseModel):
    """Payload returned by `calculate_technical_indicators`."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    interval: Literal["1h", "1d", "1wk"]
    lookback_bars: int
    tail_values_count: int
    latest_price: float | None = None
    overall_regime: str | None = None
    snapshots: list[IndicatorSnapshot] = Field(default_factory=list)
    tail_series: list[IndicatorPoint] = Field(default_factory=list)


class InstrumentComparisonRow(BaseModel):
    """Per-symbol side-by-side comparison metrics."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    cumulative_return_pct: float | None = None
    annualized_volatility_pct: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown_pct: float | None = None
    pe_ratio: float | None = None
    ev_to_ebitda: float | None = None
    market_cap: float | None = None
    extra_metrics: dict[str, Any] = Field(default_factory=dict)


class InstrumentRankings(BaseModel):
    """Ordered symbol rankings per requested metric (best to worst)."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    ordered_symbols: list[str]


class CompareInstrumentsData(BaseModel):
    """Payload returned by `compare_instruments`."""

    model_config = ConfigDict(extra="ignore")

    symbols: list[str]
    period: str
    aligned_start_date: date | None = None
    aligned_end_date: date | None = None
    aligned_observations: int = Field(0, ge=0)
    dropped_dates_by_symbol: dict[str, list[str]] = Field(default_factory=dict)
    comparison_table: list[InstrumentComparisonRow] = Field(default_factory=list)
    correlation_matrix: dict[str, dict[str, float]] = Field(default_factory=dict)
    rankings: list[InstrumentRankings] = Field(default_factory=list)
