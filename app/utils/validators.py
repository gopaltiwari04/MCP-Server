"""Deterministic input validators for tickers, date bounds, intervals, and identifiers."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from app.utils.errors import InvalidParametersError

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,16}$")
_EXCHANGE_RE = re.compile(r"^[A-Z0-9._\-]{2,16}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")
_WATCHLIST_NAME_RE = re.compile(r"^[A-Za-z0-9._\- ]{1,64}$")

_INTERVAL_TRADING_BARS_PER_DAY: dict[str, float] = {
    "1m": 390.0,
    "5m": 78.0,
    "15m": 26.0,
    "1h": 6.5,
    "1d": 1.0,
    "1wk": 0.2,
    "1mo": 1.0 / 21.0,
}

_TRADING_PERIOD_DAYS: dict[str, int] = {
    "1D": 1,
    "5D": 5,
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
    "3Y": 756,
    "5Y": 1260,
}

_CALENDAR_PERIOD_DAYS: dict[str, int] = {
    "1D": 1,
    "5D": 5,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
    "3Y": 1095,
    "5Y": 1825,
}


def normalize_symbol(symbol: str) -> str:
    """Normalize and validate an asset ticker symbol against strict whitelist rules."""
    if not isinstance(symbol, str):
        raise InvalidParametersError("Ticker symbol must be a string.")
    cleaned = symbol.strip().upper()
    if not cleaned or not _SYMBOL_RE.fullmatch(cleaned) or ".." in cleaned:
        raise InvalidParametersError(
            f"Invalid ticker symbol {symbol!r}. Expected 1-16 uppercase characters matching [A-Z0-9.-^=].",
            details={"symbol": symbol},
        )
    return cleaned


def normalize_symbols(
    symbols: Sequence[str],
    *,
    min_count: int = 1,
    max_count: int = 10,
) -> list[str]:
    """Normalize, deduplicate (order-preserving), and validate symbol list bounds."""
    if not isinstance(symbols, Sequence) or isinstance(symbols, str | bytes):
        raise InvalidParametersError("symbols must be a list of ticker strings.")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = normalize_symbol(raw)
        if sym not in seen:
            seen.add(sym)
            normalized.append(sym)
    if len(normalized) < min_count or len(normalized) > max_count:
        raise InvalidParametersError(
            f"Expected between {min_count} and {max_count} unique valid symbols; got {len(normalized)}.",
            details={"count": len(normalized), "min_count": min_count, "max_count": max_count},
        )
    return normalized


def validate_search_query(query: str, limit: int) -> tuple[str, int]:
    """Validate instrument search query text and result limit."""
    cleaned = query.strip()
    if len(cleaned) < 1 or len(cleaned) > 50:
        raise InvalidParametersError(
            "Search query length must be between 1 and 50 non-whitespace characters.",
            details={"query_length": len(cleaned)},
        )
    if limit < 1 or limit > 50:
        raise InvalidParametersError(
            f"Limit must be between 1 and 50; got {limit}.",
            details={"limit": limit},
        )
    return cleaned, limit


def validate_exchange_code(exchange: str) -> str:
    """Normalize and validate an exchange MIC or code (e.g., NASDAQ, NYSE, LSE)."""
    cleaned = exchange.strip().upper()
    if not _EXCHANGE_RE.fullmatch(cleaned) or ".." in cleaned:
        raise InvalidParametersError(
            f"Invalid exchange code {exchange!r}. Expected 2-16 characters matching [A-Z0-9._-].",
            details={"exchange": exchange},
        )
    return cleaned


def validate_identifier(value: str, name: str = "id") -> str:
    """Validate opaque identifiers such as portfolio_id against path traversal."""
    cleaned = value.strip()
    if not cleaned or ".." in cleaned or "/" in cleaned or "\\" in cleaned or not _IDENTIFIER_RE.fullmatch(cleaned):
        raise InvalidParametersError(
            f"Invalid {name} {value!r}. Expected 1-64 safe identifier characters [A-Za-z0-9._-].",
            details={name: value},
        )
    return cleaned


def slugify_watchlist_id(watchlist_name: str) -> str:
    """Validate a human watchlist name and produce a safe URL path slug."""
    cleaned = watchlist_name.strip()
    if not cleaned or ".." in cleaned or not _WATCHLIST_NAME_RE.fullmatch(cleaned):
        raise InvalidParametersError(
            f"Invalid watchlist_name {watchlist_name!r}. Expected 1-64 characters [A-Za-z0-9._- ]."
        )
    slug = re.sub(r"\s+", "-", cleaned.lower())
    return slug


def validate_date_range(
    start_date: date,
    end_date: date,
    *,
    max_span_days: int | None = None,
    allow_future_end: bool = True,
) -> tuple[date, date]:
    """Enforce chronological ordering and optional span bounds."""
    if start_date > end_date:
        raise InvalidParametersError(
            f"start_date ({start_date.isoformat()}) must be on or before end_date ({end_date.isoformat()}).",
            details={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        )
    today_utc = datetime.now(UTC).date()
    if start_date > today_utc + timedelta(days=1):
        raise InvalidParametersError(
            f"start_date ({start_date.isoformat()}) cannot be in the future.",
            details={"start_date": start_date.isoformat()},
        )
    if not allow_future_end and end_date > today_utc + timedelta(days=1):
        raise InvalidParametersError(
            f"end_date ({end_date.isoformat()}) cannot be in the future.",
            details={"end_date": end_date.isoformat()},
        )
    if max_span_days is not None:
        span = (end_date - start_date).days
        if span > max_span_days:
            raise InvalidParametersError(
                f"Date span of {span} days exceeds maximum allowed {max_span_days} days.",
                details={"span_days": span, "max_span_days": max_span_days},
            )
    return start_date, end_date


def count_trading_days_approx(start_date: date, end_date: date) -> int:
    """Count weekday sessions (Mon-Fri) in [start_date, end_date] inclusive."""
    if start_date > end_date:
        return 0
    total_days = (end_date - start_date).days + 1
    full_weeks, remainder = divmod(total_days, 7)
    trading_days = full_weeks * 5
    start_weekday = start_date.weekday()
    for offset in range(remainder):
        if (start_weekday + offset) % 7 < 5:
            trading_days += 1
    return trading_days


def estimate_bar_count(start_date: date, end_date: date, interval: str) -> int:
    """Estimate maximum number of OHLCV bars over [start_date, end_date] for an interval."""
    rate = _INTERVAL_TRADING_BARS_PER_DAY.get(interval)
    if rate is None:
        raise InvalidParametersError(f"Unsupported historical interval {interval!r}.")
    trading_days = max(1, count_trading_days_approx(start_date, end_date))
    return max(1, math.ceil(trading_days * rate))


def validate_history_bar_limit(
    start_date: date,
    end_date: date,
    interval: str,
    max_bars: int = 500,
) -> int:
    """Guard against context-overflowing historical bar queries (>500 bars)."""
    estimated = estimate_bar_count(start_date, end_date, interval)
    if estimated > max_bars:
        raise InvalidParametersError(
            f"Requested range ({start_date.isoformat()} to {end_date.isoformat()}) at interval "
            f"'{interval}' is estimated at ~{estimated} bars, exceeding the {max_bars}-bar per-call limit. "
            "Use a coarser interval (e.g., '1d' or '1wk') or split into narrower date windows.",
            details={
                "estimated_bars": estimated,
                "max_bars": max_bars,
                "interval": interval,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
    return estimated


def resolve_period_dates(
    period: str,
    start_date: date | None = None,
    end_date: date | None = None,
    calendar_basis: Literal["TRADING_DAYS", "CALENDAR_DAYS"] = "TRADING_DAYS",
    reference_date: date | None = None,
) -> tuple[date, date]:
    """Resolve standardized period codes ('1D'..'5Y', 'YTD', 'CUSTOM') into concrete dates."""
    ref = reference_date or datetime.now(UTC).date()

    if period == "CUSTOM":
        if start_date is None or end_date is None:
            raise InvalidParametersError(
                "Both start_date and end_date are required when period='CUSTOM'."
            )
        return validate_date_range(start_date, end_date)

    resolved_end = end_date or ref
    if period == "YTD":
        resolved_start = date(resolved_end.year, 1, 1)
        return validate_date_range(resolved_start, resolved_end)

    if calendar_basis == "TRADING_DAYS":
        trading_days = _TRADING_PERIOD_DAYS.get(period)
        if trading_days is None:
            raise InvalidParametersError(f"Unsupported period {period!r}.")
        # Walk backward exactly `trading_days` Mon-Fri sessions
        cursor = resolved_end
        remaining = trading_days
        while remaining > 0:
            cursor -= timedelta(days=1)
            if cursor.weekday() < 5:
                remaining -= 1
        resolved_start = cursor
    else:
        cal_days = _CALENDAR_PERIOD_DAYS.get(period)
        if cal_days is None:
            raise InvalidParametersError(f"Unsupported period {period!r}.")
        resolved_start = resolved_end - timedelta(days=cal_days)

    return validate_date_range(resolved_start, resolved_end)
