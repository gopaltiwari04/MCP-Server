"""Portfolio risk analytics, what-if simulation, and workspace mutation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortfolioHolding(BaseModel):
    """Single portfolio position with weight and P&L attribution."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    name: str | None = None
    asset_class: str = "EQUITY"
    sector: str | None = None
    quantity: float
    market_price: float
    market_value: float
    weight_pct: float
    cost_basis: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None


class AllocationSlice(BaseModel):
    """Allocation breakdown entry."""

    model_config = ConfigDict(extra="ignore")

    category: str
    weight_pct: float
    market_value: float


class ConcentrationContributor(BaseModel):
    """Top risk / weight concentration contributor."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    weight_pct: float
    risk_contribution_pct: float | None = None


class PortfolioAnalysisData(BaseModel):
    """Payload returned by `analyse_portfolio`."""

    model_config = ConfigDict(extra="ignore")

    portfolio_id: str
    portfolio_name: str | None = None
    base_currency: str = "USD"
    benchmark_symbol: str = "SPY"
    confidence_level: float = Field(0.95, gt=0.5, lt=1.0)
    lookback_days: int = Field(252, ge=20)
    nav: float
    cash_balance: float
    cash_weight_pct: float
    portfolio_beta: float | None = None
    annualized_volatility_pct: float | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    historical_var_pct: float | None = None
    parametric_var_pct: float | None = None
    expected_shortfall_cvar_pct: float | None = None
    historical_var_amount: float | None = None
    expected_shortfall_cvar_amount: float | None = None
    positions: list[PortfolioHolding] = Field(default_factory=list)
    sector_allocation: list[AllocationSlice] = Field(default_factory=list)
    asset_class_allocation: list[AllocationSlice] = Field(default_factory=list)
    top_concentration_contributors: list[ConcentrationContributor] = Field(default_factory=list)


class ProposedTrade(BaseModel):
    """Single hypothetical trade order for stateless rebalance simulation."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1, max_length=16)
    side: Literal["BUY", "SELL"]
    weight_delta_pct: float | None = Field(
        None,
        gt=0,
        le=100.0,
        description="Target percentage-point weight delta (e.g., 5.0 means +5% BUY or -5% SELL).",
    )
    share_delta: float | None = Field(
        None,
        gt=0,
        description="Positive share count to buy or sell.",
    )

    @model_validator(mode="after")
    def _validate_sizing_present(self) -> ProposedTrade:
        if self.weight_delta_pct is None and self.share_delta is None:
            raise ValueError("Each ProposedTrade must specify either 'weight_delta_pct' or 'share_delta'.")
        if self.weight_delta_pct is not None and self.share_delta is not None:
            raise ValueError("Specify only one of 'weight_delta_pct' or 'share_delta', not both.")
        return self


class PortfolioSnapshotMetrics(BaseModel):
    """Pre-trade or post-trade summary risk snapshot."""

    model_config = ConfigDict(extra="ignore")

    cash_balance: float
    cash_weight_pct: float
    portfolio_beta: float | None = None
    annualized_volatility_pct: float | None = None
    var_95_pct: float | None = None
    cvar_95_pct: float | None = None
    sector_weights_pct: dict[str, float] = Field(default_factory=dict)
    position_weights_pct: dict[str, float] = Field(default_factory=dict)


class ConstraintViolation(BaseModel):
    """Policy or risk guardrail breach identified during rebalance simulation."""

    model_config = ConfigDict(extra="ignore")

    rule_code: str
    severity: Literal["WARNING", "BREACH"]
    message: str
    symbol: str | None = None
    observed_value: float | None = None
    limit_value: float | None = None


class RebalanceSimulationData(BaseModel):
    """Payload returned by `simulate_portfolio_rebalance`."""

    model_config = ConfigDict(extra="ignore")

    portfolio_id: str
    benchmark_symbol: str
    is_stateless_simulation: bool = True
    estimated_cash_impact: float
    beta_shift: float | None = None
    var_delta_pct: float | None = None
    pre_trade: PortfolioSnapshotMetrics
    post_trade: PortfolioSnapshotMetrics
    constraint_violations: list[ConstraintViolation] = Field(default_factory=list)


class WatchlistData(BaseModel):
    """Payload returned by `manage_watchlist`."""

    model_config = ConfigDict(extra="ignore")

    watchlist_id: str
    watchlist_name: str
    action: Literal["LIST", "ADD", "REMOVE"]
    symbols: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class PriceAlertData(BaseModel):
    """Payload returned by `create_price_alert`."""

    model_config = ConfigDict(extra="ignore")

    alert_id: str
    symbol: str
    condition: Literal["CROSSES_ABOVE", "CROSSES_BELOW", "PCT_CHANGE_1D_EXCEEDS"]
    threshold_value: float
    note: str | None = None
    status: Literal["ACTIVE", "TRIGGERED", "DISABLED"] = "ACTIVE"
    created_at: datetime | None = None


class ResearchMemoData(BaseModel):
    """Payload returned by `save_research_memo`."""

    model_config = ConfigDict(extra="ignore")

    memo_id: str
    title: str
    symbols: list[str]
    sentiment: Literal["BULLISH", "NEUTRAL", "BEARISH"]
    cited_data_timestamps: list[str]
    created_at: datetime | None = None
