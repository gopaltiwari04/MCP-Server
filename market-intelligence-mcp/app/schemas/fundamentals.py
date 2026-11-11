"""Fundamental financial metrics, ratios, and earnings surprise schemas."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ValuationMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_to_ebitda: float | None = None
    ev_to_revenue: float | None = None
    free_cash_flow_yield: float | None = None


class ProfitabilityMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None


class LiquidityLeverageMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    current_ratio: float | None = None
    quick_ratio: float | None = None
    debt_to_equity: float | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None


class PerShareGrowthMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    eps_diluted: float | None = None
    revenue_per_share: float | None = None
    book_value_per_share: float | None = None
    revenue_growth_yoy: float | None = None
    eps_growth_yoy: float | None = None


class FinancialMetricsPeriod(BaseModel):
    """Structured financial metrics for one reporting period."""

    model_config = ConfigDict(extra="ignore")

    fiscal_period: str
    period_end_date: date | None = None
    valuation: ValuationMetrics = Field(default_factory=ValuationMetrics)
    profitability: ProfitabilityMetrics = Field(default_factory=ProfitabilityMetrics)
    liquidity_leverage: LiquidityLeverageMetrics = Field(default_factory=LiquidityLeverageMetrics)
    per_share_growth: PerShareGrowthMetrics = Field(default_factory=PerShareGrowthMetrics)


class FinancialMetricsData(BaseModel):
    """Payload returned by `get_financial_metrics`."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    period_type: Literal["TTM", "ANNUAL", "QUARTERLY"]
    currency: str
    periods: list[FinancialMetricsPeriod] = Field(default_factory=list)


class EarningsQuarter(BaseModel):
    """Single historical quarterly earnings print."""

    model_config = ConfigDict(extra="ignore")

    fiscal_quarter: str
    report_date: date
    eps_consensus: float | None = None
    eps_actual: float | None = None
    eps_surprise_pct: float | None = None
    revenue_consensus: float | None = None
    revenue_actual: float | None = None
    revenue_surprise_pct: float | None = None


class EarningsHistoryData(BaseModel):
    """Payload returned by `get_earnings_history`."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    currency: str
    next_earnings_date: date | None = None
    quarters_returned: int = Field(..., ge=0)
    quarters: list[EarningsQuarter] = Field(default_factory=list)
