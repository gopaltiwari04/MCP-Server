"""Unit tests for ticker normalization, date bounds, bar limits, and trade validators."""

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.portfolio import ProposedTrade
from app.utils.errors import InvalidParametersError
from app.utils.validators import (
    count_trading_days_approx,
    normalize_symbol,
    normalize_symbols,
    resolve_period_dates,
    slugify_watchlist_id,
    validate_date_range,
    validate_exchange_code,
    validate_history_bar_limit,
    validate_identifier,
    validate_search_query,
)


def test_normalize_symbol_valid_cases() -> None:
    assert normalize_symbol("  nvda ") == "NVDA"
    assert normalize_symbol("brk.b") == "BRK.B"
    assert normalize_symbol("^GSPC") == "^GSPC"
    assert normalize_symbol("EURUSD=X") == "EURUSD=X"
    assert normalize_symbol("BTC-USD") == "BTC-USD"


@pytest.mark.parametrize("bad", ["", "   ", "AAPL;DROP", "../etc", "TOO_LONG_TICKER_12345", "A B", "NVDA$"])
def test_normalize_symbol_rejects_invalid(bad: str) -> None:
    with pytest.raises(InvalidParametersError):
        normalize_symbol(bad)


def test_normalize_symbols_dedup_and_bounds() -> None:
    assert normalize_symbols(["nvda", "NVDA", "amd"], min_count=2, max_count=5) == ["NVDA", "AMD"]
    with pytest.raises(InvalidParametersError):
        normalize_symbols(["NVDA"], min_count=2, max_count=5)
    with pytest.raises(InvalidParametersError):
        normalize_symbols(["A", "B", "C"], min_count=1, max_count=2)


def test_validate_search_query_bounds() -> None:
    assert validate_search_query("  nvidia ", 10) == ("nvidia", 10)
    with pytest.raises(InvalidParametersError):
        validate_search_query("   ", 10)
    with pytest.raises(InvalidParametersError):
        validate_search_query("a" * 51, 10)
    with pytest.raises(InvalidParametersError):
        validate_search_query("nvda", 0)
    with pytest.raises(InvalidParametersError):
        validate_search_query("nvda", 51)


def test_validate_date_range_inversions_and_future() -> None:
    today = datetime.now(UTC).date()
    d1 = today - timedelta(days=10)
    d2 = today - timedelta(days=2)
    assert validate_date_range(d1, d2) == (d1, d2)

    with pytest.raises(InvalidParametersError):
        validate_date_range(d2, d1)

    future = today + timedelta(days=10)
    with pytest.raises(InvalidParametersError):
        validate_date_range(future, future + timedelta(days=2))


def test_validate_history_bar_limit() -> None:
    d_start = date(2026, 1, 5)
    # 30 days of 1d bars (~22 bars) -> passes
    assert validate_history_bar_limit(d_start, date(2026, 2, 4), "1d", max_bars=500) <= 500
    # 1m bars over 10 trading days = ~3900 bars -> must fail deterministically
    with pytest.raises(InvalidParametersError) as exc_info:
        validate_history_bar_limit(date(2026, 1, 5), date(2026, 1, 19), "1m", max_bars=500)
    assert "exceeding the 500-bar" in exc_info.value.message


def test_count_trading_days_weekend_only() -> None:
    # 2026-11-07 is Saturday, 2026-11-08 is Sunday
    assert count_trading_days_approx(date(2026, 11, 7), date(2026, 11, 8)) == 0
    # Mon-Fri week = 5 trading days
    assert count_trading_days_approx(date(2026, 11, 2), date(2026, 11, 6)) == 5


def test_resolve_period_dates_trading_vs_calendar() -> None:
    ref = date(2026, 11, 11)
    s_tr, e_tr = resolve_period_dates("1M", calendar_basis="TRADING_DAYS", reference_date=ref)
    s_cal, e_cal = resolve_period_dates("1M", calendar_basis="CALENDAR_DAYS", reference_date=ref)
    assert e_tr == ref and e_cal == ref
    assert s_cal == ref - timedelta(days=30)
    assert count_trading_days_approx(s_tr, ref) >= 21

    with pytest.raises(InvalidParametersError):
        resolve_period_dates("CUSTOM", start_date=date(2026, 1, 1), end_date=None)


def test_identifiers_and_proposed_trade_validation() -> None:
    assert validate_exchange_code(" nasdaq ") == "NASDAQ"
    assert validate_identifier("port_123", name="portfolio_id") == "port_123"
    assert slugify_watchlist_id("AI Semiconductors") == "ai-semiconductors"

    with pytest.raises(InvalidParametersError):
        validate_identifier("../secret", name="portfolio_id")

    trade = ProposedTrade(symbol="NVDA", side="BUY", weight_delta_pct=5.0)
    assert trade.weight_delta_pct == 5.0

    with pytest.raises(ValidationError):
        ProposedTrade(symbol="NVDA", side="BUY")  # neither sizing specified
    with pytest.raises(ValidationError):
        ProposedTrade(symbol="NVDA", side="BUY", weight_delta_pct=5.0, share_delta=10.0)  # both specified
