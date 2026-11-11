"""Instrument discovery, exchange schedule, and company profile schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InstrumentItem(BaseModel):
    """Normalized instrument search result."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    name: str
    asset_type: Literal["EQUITY", "ETF", "INDEX", "CRYPTO", "FX", "OTHER"]
    primary_exchange: str
    currency: str
    isin: str | None = None
    figi: str | None = None
    is_active: bool = True
    country: str | None = None


class SearchInstrumentsData(BaseModel):
    """Payload returned by `search_instruments`."""

    model_config = ConfigDict(extra="forbid")

    query: str
    asset_type_filter: str
    exchange_filter: str | None = None
    total_matches: int = Field(..., ge=0)
    instruments: list[InstrumentItem]


class ExchangeHoliday(BaseModel):
    """Exchange holiday entry."""

    model_config = ConfigDict(extra="ignore")

    holiday_date: date
    name: str
    status: Literal["CLOSED", "EARLY_CLOSE"] = "CLOSED"
    close_time_local: str | None = None


class ExchangeScheduleData(BaseModel):
    """Payload returned by `get_exchange_schedule`."""

    model_config = ConfigDict(extra="ignore")

    exchange: str
    exchange_name: str
    timezone: str
    market_state: Literal["OPEN", "CLOSED", "PRE_MARKET", "AFTER_HOURS"]
    regular_open_local: str
    regular_close_local: str
    regular_open_utc: datetime | None = None
    regular_close_utc: datetime | None = None
    is_trading_day: bool
    upcoming_holidays: list[ExchangeHoliday] = Field(default_factory=list)


class CompanyProfileData(BaseModel):
    """Payload returned by `get_company_profile`."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    legal_name: str
    sector: str | None = None
    industry: str | None = None
    gics_sector_code: str | None = None
    gics_industry_code: str | None = None
    headquarters: str | None = None
    country: str | None = None
    ceo: str | None = None
    employees: int | None = Field(None, ge=0)
    fiscal_year_end: str | None = None
    website: str | None = None
    description: str | None = None
    primary_exchange: str
    currency: str
    isin: str | None = None
    figi: str | None = None
    ipo_date: date | None = None
