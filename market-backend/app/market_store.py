"""Deterministic quantitative market data, analytics, and user-scoped workspace store."""

from __future__ import annotations

import math
import statistics
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class InstrumentSeed:
    symbol: str
    name: str
    asset_type: str
    exchange: str
    currency: str
    base_price: float
    drift: float
    vol: float
    beta: float
    market_cap: float
    pe_ratio: float | None
    forward_pe: float | None
    ev_to_ebitda: float | None
    gross_margin: float | None
    operating_margin: float | None
    roe: float | None
    roic: float | None
    rev_growth: float | None
    eps_growth: float | None
    sector: str
    industry: str
    ceo: str
    employees: int
    isin: str
    figi: str
    description: str


_INSTRUMENTS: dict[str, InstrumentSeed] = {
    "NVDA": InstrumentSeed(
        symbol="NVDA",
        name="NVIDIA Corporation",
        asset_type="EQUITY",
        exchange="NASDAQ",
        currency="USD",
        base_price=148.50,
        drift=0.0014,
        vol=0.024,
        beta=1.65,
        market_cap=3_640_000_000_000.0,
        pe_ratio=48.2,
        forward_pe=34.1,
        ev_to_ebitda=41.5,
        gross_margin=0.745,
        operating_margin=0.612,
        roe=0.91,
        roic=0.67,
        rev_growth=0.94,
        eps_growth=1.12,
        sector="Information Technology",
        industry="Semiconductors",
        ceo="Jensen Huang",
        employees=29600,
        isin="US67066G1040",
        figi="BBG000BBJQV0",
        description="Accelerated computing GPUs, CUDA software platform, and AI data-center networking.",
    ),
    "AMD": InstrumentSeed(
        symbol="AMD",
        name="Advanced Micro Devices, Inc.",
        asset_type="EQUITY",
        exchange="NASDAQ",
        currency="USD",
        base_price=156.20,
        drift=0.0009,
        vol=0.026,
        beta=1.52,
        market_cap=252_800_000_000.0,
        pe_ratio=39.4,
        forward_pe=28.6,
        ev_to_ebitda=29.8,
        gross_margin=0.518,
        operating_margin=0.214,
        roe=0.145,
        roic=0.118,
        rev_growth=0.18,
        eps_growth=0.31,
        sector="Information Technology",
        industry="Semiconductors",
        ceo="Lisa Su",
        employees=26000,
        isin="US0079031078",
        figi="BBG000BBQCY0",
        description="High-performance CPUs, Instinct data-center GPUs, and adaptive FPGA silicon.",
    ),
    "AAPL": InstrumentSeed(
        symbol="AAPL",
        name="Apple Inc.",
        asset_type="EQUITY",
        exchange="NASDAQ",
        currency="USD",
        base_price=229.40,
        drift=0.0006,
        vol=0.015,
        beta=1.18,
        market_cap=3_480_000_000_000.0,
        pe_ratio=33.8,
        forward_pe=29.5,
        ev_to_ebitda=25.2,
        gross_margin=0.462,
        operating_margin=0.315,
        roe=1.42,
        roic=0.54,
        rev_growth=0.06,
        eps_growth=0.11,
        sector="Information Technology",
        industry="Consumer Hardware & Ecosystem",
        ceo="Tim Cook",
        employees=161000,
        isin="US0378331005",
        figi="BBG000B9XRY4",
        description="Consumer devices, Apple Silicon, and high-margin recurring services ecosystem.",
    ),
    "MSFT": InstrumentSeed(
        symbol="MSFT",
        name="Microsoft Corporation",
        asset_type="EQUITY",
        exchange="NASDAQ",
        currency="USD",
        base_price=424.80,
        drift=0.0007,
        vol=0.016,
        beta=1.08,
        market_cap=3_160_000_000_000.0,
        pe_ratio=34.5,
        forward_pe=30.1,
        ev_to_ebitda=23.9,
        gross_margin=0.698,
        operating_margin=0.446,
        roe=0.371,
        roic=0.284,
        rev_growth=0.15,
        eps_growth=0.18,
        sector="Information Technology",
        industry="Enterprise Cloud & Software",
        ceo="Satya Nadella",
        employees=228000,
        isin="US5949181045",
        figi="BBG000BPH459",
        description="Azure cloud infrastructure, enterprise productivity suites, and Copilot AI platform.",
    ),
    "GOOGL": InstrumentSeed(
        symbol="GOOGL",
        name="Alphabet Inc.",
        asset_type="EQUITY",
        exchange="NASDAQ",
        currency="USD",
        base_price=182.10,
        drift=0.0007,
        vol=0.018,
        beta=1.12,
        market_cap=2_240_000_000_000.0,
        pe_ratio=23.4,
        forward_pe=20.2,
        ev_to_ebitda=16.5,
        gross_margin=0.582,
        operating_margin=0.321,
        roe=0.312,
        roic=0.258,
        rev_growth=0.14,
        eps_growth=0.27,
        sector="Communication Services",
        industry="Interactive Media & Cloud",
        ceo="Sundar Pichai",
        employees=181000,
        isin="US02079K3059",
        figi="BBG009S39JX6",
        description="Search, YouTube, Google Cloud Platform, TPUs, and Gemini foundation models.",
    ),
    "AVGO": InstrumentSeed(
        symbol="AVGO",
        name="Broadcom Inc.",
        asset_type="EQUITY",
        exchange="NASDAQ",
        currency="USD",
        base_price=178.90,
        drift=0.0010,
        vol=0.021,
        beta=1.34,
        market_cap=835_000_000_000.0,
        pe_ratio=36.2,
        forward_pe=27.8,
        ev_to_ebitda=26.4,
        gross_margin=0.751,
        operating_margin=0.452,
        roe=0.39,
        roic=0.22,
        rev_growth=0.44,
        eps_growth=0.28,
        sector="Information Technology",
        industry="Semiconductors & Infrastructure Software",
        ceo="Hock Tan",
        employees=37000,
        isin="US11135F1012",
        figi="BBG00KHY53D2",
        description="Custom AI XPUs, Ethernet switching silicon, and VMware enterprise virtualization.",
    ),
    "TSM": InstrumentSeed(
        symbol="TSM",
        name="Taiwan Semiconductor Manufacturing Co.",
        asset_type="EQUITY",
        exchange="NYSE",
        currency="USD",
        base_price=194.30,
        drift=0.0010,
        vol=0.020,
        beta=1.28,
        market_cap=1_005_000_000_000.0,
        pe_ratio=28.9,
        forward_pe=22.4,
        ev_to_ebitda=15.8,
        gross_margin=0.556,
        operating_margin=0.448,
        roe=0.295,
        roic=0.241,
        rev_growth=0.36,
        eps_growth=0.41,
        sector="Information Technology",
        industry="Semiconductor Foundry",
        ceo="C.C. Wei",
        employees=76000,
        isin="US8740391003",
        figi="BBG000BD2Y94",
        description="Leading-edge N3/N2 semiconductor foundry and CoWoS advanced packaging.",
    ),
    "SPY": InstrumentSeed(
        symbol="SPY",
        name="SPDR S&P 500 ETF Trust",
        asset_type="ETF",
        exchange="ARCA",
        currency="USD",
        base_price=592.10,
        drift=0.0004,
        vol=0.009,
        beta=1.0,
        market_cap=615_000_000_000.0,
        pe_ratio=24.1,
        forward_pe=21.2,
        ev_to_ebitda=None,
        gross_margin=None,
        operating_margin=None,
        roe=None,
        roic=None,
        rev_growth=None,
        eps_growth=None,
        sector="Broad Market ETF",
        industry="Large-Cap US Equity Index",
        ceo="State Street Global Advisors",
        employees=0,
        isin="US78462F1030",
        figi="BBG000BDTBL9",
        description="Exchange-traded fund tracking the S&P 500 Index.",
    ),
    "QQQ": InstrumentSeed(
        symbol="QQQ",
        name="Invesco QQQ Trust",
        asset_type="ETF",
        exchange="NASDAQ",
        currency="USD",
        base_price=508.40,
        drift=0.0005,
        vol=0.012,
        beta=1.18,
        market_cap=305_000_000_000.0,
        pe_ratio=31.0,
        forward_pe=26.5,
        ev_to_ebitda=None,
        gross_margin=None,
        operating_margin=None,
        roe=None,
        roic=None,
        rev_growth=None,
        eps_growth=None,
        sector="Broad Market ETF",
        industry="Nasdaq-100 Index",
        ceo="Invesco Capital Management",
        employees=0,
        isin="US46090E1038",
        figi="BBG000BSWKH7",
        description="Exchange-traded fund tracking the Nasdaq-100 Index.",
    ),
    "AZN.L": InstrumentSeed(
        symbol="AZN.L",
        name="AstraZeneca PLC",
        asset_type="EQUITY",
        exchange="LSE",
        currency="GBP",
        base_price=112.40,
        drift=0.0004,
        vol=0.013,
        beta=0.72,
        market_cap=174_000_000_000.0,
        pe_ratio=24.8,
        forward_pe=17.9,
        ev_to_ebitda=14.6,
        gross_margin=0.818,
        operating_margin=0.256,
        roe=0.184,
        roic=0.132,
        rev_growth=0.19,
        eps_growth=0.22,
        sector="Health Care",
        industry="Pharmaceuticals",
        ceo="Pascal Soriot",
        employees=89900,
        isin="GB0009895292",
        figi="BBG000C28K29",
        description="Global biopharmaceutical oncology, cardiovascular, and rare-disease leader.",
    ),
}

_EXCHANGES: dict[str, dict[str, Any]] = {
    "NASDAQ": {
        "exchange": "NASDAQ",
        "exchange_name": "Nasdaq Global Select Market",
        "timezone": "America/New_York",
        "regular_open_local": "09:30",
        "regular_close_local": "16:00",
        "holidays": [("2026-11-26", "Thanksgiving Day"), ("2026-12-25", "Christmas Day")],
    },
    "NYSE": {
        "exchange": "NYSE",
        "exchange_name": "New York Stock Exchange",
        "timezone": "America/New_York",
        "regular_open_local": "09:30",
        "regular_close_local": "16:00",
        "holidays": [("2026-11-26", "Thanksgiving Day"), ("2026-12-25", "Christmas Day")],
    },
    "ARCA": {
        "exchange": "ARCA",
        "exchange_name": "NYSE Arca",
        "timezone": "America/New_York",
        "regular_open_local": "09:30",
        "regular_close_local": "16:00",
        "holidays": [("2026-11-26", "Thanksgiving Day"), ("2026-12-25", "Christmas Day")],
    },
    "LSE": {
        "exchange": "LSE",
        "exchange_name": "London Stock Exchange",
        "timezone": "Europe/London",
        "regular_open_local": "08:00",
        "regular_close_local": "16:30",
        "holidays": [("2026-12-25", "Christmas Day"), ("2026-12-28", "Boxing Day Observed")],
    },
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _generate_daily_series(seed: InstrumentSeed, start_date: date, end_date: date) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    # Anchor deterministically backwards from today so ending price aligns smoothly near base_price
    today = datetime.now(UTC).date()
    all_days: list[date] = []
    cursor = min(start_date, today - timedelta(days=400))
    limit_end = max(end_date, today)
    while cursor <= limit_end:
        if cursor.weekday() < 5:
            # Simulate UK vs US calendar nuance for LSE symbols (omit first Monday of May / occasional UK bank holiday)
            if seed.exchange == "LSE" and cursor.month == 5 and cursor.weekday() == 0 and cursor.day <= 7:
                cursor += timedelta(days=1)
                continue
            all_days.append(cursor)
        cursor += timedelta(days=1)

    if not all_days:
        return []

    # Generate deterministic wave + trend series anchored so today's close ~ base_price
    sym_phase = sum(ord(c) for c in seed.symbol) * 0.17
    raw_closes: list[float] = []
    p = seed.base_price * 0.78
    for idx, _d in enumerate(all_days):
        wave = math.sin(idx * 0.27 + sym_phase) * seed.vol + math.cos(idx * 0.11 + sym_phase) * (seed.vol * 0.45)
        p = max(1.0, p * (1.0 + seed.drift + wave * 0.55))
        raw_closes.append(p)

    scale = seed.base_price / raw_closes[-1]
    for idx, d in enumerate(all_days):
        if d < start_date or d > end_date:
            continue
        close_px = round(raw_closes[idx] * scale, 2)
        open_px = round(close_px * (1.0 - math.sin(idx + sym_phase) * 0.006), 2)
        high_px = round(max(open_px, close_px) * (1.0 + 0.008 + abs(math.cos(idx)) * 0.007), 2)
        low_px = round(min(open_px, close_px) * (1.0 - 0.008 - abs(math.sin(idx)) * 0.006), 2)
        vol = int(28_000_000 * (0.75 + abs(math.sin(idx * 0.4 + sym_phase)) * 0.8))
        ts = datetime(d.year, d.month, d.day, 20, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")
        bars.append(
            {
                "timestamp": ts,
                "date": d.isoformat(),
                "open": open_px,
                "high": high_px,
                "low": low_px,
                "close": close_px,
                "adjusted_close": close_px,
                "volume": vol,
            }
        )
    return bars


def _ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    ema_val = statistics.fmean(values[:period])
    out[period - 1] = ema_val
    for i in range(period, len(values)):
        ema_val = values[i] * k + ema_val * (1.0 - k)
        out[i] = ema_val
    return out


def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = statistics.fmean(values[i - period + 1 : i + 1])
    return out


class InMemoryMarketBackendStore:
    """Thread/async-safe reference store powering all 15 FastAPI routes."""

    def __init__(self) -> None:
        self._portfolios: dict[str, dict[str, dict[str, Any]]] = {
            "user_alice": {
                "port_123": {
                    "portfolio_name": "Alice Institutional AI & Quality Core",
                    "base_currency": "USD",
                    "cash_balance": 120_000.0,
                    "holdings": [
                        {"symbol": "NVDA", "quantity": 1800, "cost_basis": 108.0},
                        {"symbol": "MSFT", "quantity": 650, "cost_basis": 365.0},
                        {"symbol": "AAPL", "quantity": 950, "cost_basis": 195.0},
                        {"symbol": "AVGO", "quantity": 800, "cost_basis": 142.0},
                        {"symbol": "GOOGL", "quantity": 900, "cost_basis": 152.0},
                    ],
                }
            },
            "user_bob": {
                "port_123": {
                    "portfolio_name": "Bob Defensive Value Portfolio",
                    "base_currency": "USD",
                    "cash_balance": 85_000.0,
                    "holdings": [
                        {"symbol": "SPY", "quantity": 400, "cost_basis": 520.0},
                        {"symbol": "GOOGL", "quantity": 550, "cost_basis": 160.0},
                    ],
                }
            },
        }
        self._watchlists: dict[str, dict[str, list[str]]] = {
            "user_alice": {"default": ["NVDA", "AMD", "AVGO", "MSFT"]},
            "user_bob": {"default": ["SPY", "AAPL"]},
        }
        self._alerts: dict[str, list[dict[str, Any]]] = {}
        self._memos: dict[str, list[dict[str, Any]]] = {}
        self._idempotency_results: dict[tuple[str, str], dict[str, Any]] = {}

    def search_instruments(
        self, q: str, asset_type: str, exchange: str | None, limit: int
    ) -> dict[str, Any]:
        ql = q.strip().lower()
        matches: list[dict[str, Any]] = []
        for inst in _INSTRUMENTS.values():
            if asset_type != "ALL" and inst.asset_type != asset_type:
                continue
            if exchange and inst.exchange != exchange.upper():
                continue
            haystack = f"{inst.symbol} {inst.name} {inst.isin} {inst.figi} {inst.sector}".lower()
            if ql in haystack:
                matches.append(
                    {
                        "symbol": inst.symbol,
                        "name": inst.name,
                        "asset_type": inst.asset_type,
                        "primary_exchange": inst.exchange,
                        "currency": inst.currency,
                        "isin": inst.isin,
                        "figi": inst.figi,
                        "is_active": True,
                        "country": "GB" if inst.exchange == "LSE" else "US",
                    }
                )
        return {
            "source": "fastapi-market-reference",
            "data_timestamp": _now_iso(),
            "total_matches": len(matches),
            "instruments": matches[:limit],
        }

    def get_exchange_schedule(
        self, exchange: str, start_date: date | None, end_date: date | None
    ) -> dict[str, Any] | None:
        info = _EXCHANGES.get(exchange.upper())
        if not info:
            return None
        today = datetime.now(UTC).date()
        is_weekday = today.weekday() < 5
        holidays = [
            {"holiday_date": hd, "name": nm, "status": "CLOSED"}
            for hd, nm in info["holidays"]
            if (start_date is None or date.fromisoformat(hd) >= start_date)
            and (end_date is None or date.fromisoformat(hd) <= end_date)
        ]
        return {
            "source": "fastapi-exchange-calendar",
            "data_timestamp": _now_iso(),
            "exchange": info["exchange"],
            "exchange_name": info["exchange_name"],
            "timezone": info["timezone"],
            "market_state": "OPEN" if is_weekday else "CLOSED",
            "regular_open_local": info["regular_open_local"],
            "regular_close_local": info["regular_close_local"],
            "is_trading_day": is_weekday,
            "upcoming_holidays": holidays,
        }

    def get_quote(self, symbol: str) -> dict[str, Any] | None:
        inst = _INSTRUMENTS.get(symbol.upper())
        if not inst:
            return None
        end_d = datetime.now(UTC).date()
        bars = _generate_daily_series(inst, end_d - timedelta(days=10), end_d)
        last = bars[-1]["close"] if bars else inst.base_price
        prev = bars[-2]["close"] if len(bars) >= 2 else round(last * 0.99, 2)
        chg = round(last - prev, 2)
        chg_pct = round((chg / prev) * 100.0, 2) if prev else 0.0
        spread = round(max(0.01, last * 0.0003), 2)
        ts = _now_iso()
        return {
            "source": "fastapi-market-quotes",
            "data_timestamp": ts,
            "symbol": inst.symbol,
            "last_price": last,
            "bid": round(last - spread / 2, 2),
            "ask": round(last + spread / 2, 2),
            "open": bars[-1]["open"] if bars else last,
            "high": bars[-1]["high"] if bars else last,
            "low": bars[-1]["low"] if bars else last,
            "previous_close": prev,
            "change": chg,
            "change_pct": chg_pct,
            "volume": bars[-1]["volume"] if bars else 10_000_000,
            "avg_volume_30d": 32_500_000,
            "market_cap": inst.market_cap,
            "currency": inst.currency,
            "exchange": inst.exchange,
            "is_delayed": False,
            "delay_minutes": 0,
            "quote_timestamp": ts,
        }

    def get_history(
        self, symbol: str, start_date: date, end_date: date, interval: str, adjusted: bool
    ) -> dict[str, Any] | None:
        inst = _INSTRUMENTS.get(symbol.upper())
        if not inst:
            return None
        bars = _generate_daily_series(inst, start_date, end_date)
        if interval == "1wk":
            bars = bars[::5]
        elif interval == "1mo":
            bars = bars[::21]
        return {
            "source": "fastapi-market-history",
            "data_timestamp": _now_iso(),
            "currency": inst.currency,
            "adjusted": adjusted,
            "bars": bars,
        }

    def get_company_profile(self, symbol: str) -> dict[str, Any] | None:
        inst = _INSTRUMENTS.get(symbol.upper())
        if not inst:
            return None
        return {
            "source": "fastapi-fundamentals",
            "data_timestamp": _now_iso(),
            "symbol": inst.symbol,
            "legal_name": inst.name,
            "sector": inst.sector,
            "industry": inst.industry,
            "gics_sector_code": "45" if inst.sector == "Information Technology" else "35",
            "headquarters": "London, UK" if inst.exchange == "LSE" else "United States",
            "country": "GB" if inst.exchange == "LSE" else "US",
            "ceo": inst.ceo,
            "employees": inst.employees,
            "fiscal_year_end": "December",
            "website": f"https://www.{inst.symbol.lower().split('.')[0]}.com",
            "description": inst.description,
            "primary_exchange": inst.exchange,
            "currency": inst.currency,
            "isin": inst.isin,
            "figi": inst.figi,
        }

    def get_financial_metrics(self, symbol: str, period: str, limit: int) -> dict[str, Any] | None:
        inst = _INSTRUMENTS.get(symbol.upper())
        if not inst:
            return None
        periods = []
        for idx in range(min(limit, 4)):
            scale = 1.0 - idx * 0.05
            periods.append(
                {
                    "fiscal_period": "TTM" if (period == "TTM" and idx == 0) else f"FY{2026 - idx}",
                    "period_end_date": f"{2026 - idx}-09-30",
                    "valuation": {
                        "pe_ratio": round(inst.pe_ratio * scale, 2) if inst.pe_ratio else None,
                        "forward_pe": round(inst.forward_pe * scale, 2) if inst.forward_pe else None,
                        "peg_ratio": 1.18 if inst.pe_ratio else None,
                        "pb_ratio": 14.2 if inst.pe_ratio else None,
                        "ps_ratio": 12.1 if inst.pe_ratio else None,
                        "ev_to_ebitda": round(inst.ev_to_ebitda * scale, 2) if inst.ev_to_ebitda else None,
                        "ev_to_revenue": 11.4 if inst.ev_to_ebitda else None,
                        "free_cash_flow_yield": 0.028 if inst.pe_ratio else None,
                    },
                    "profitability": {
                        "gross_margin": inst.gross_margin,
                        "operating_margin": inst.operating_margin,
                        "net_margin": round(inst.operating_margin * 0.82, 3) if inst.operating_margin else None,
                        "roe": inst.roe,
                        "roa": round(inst.roe * 0.52, 3) if inst.roe else None,
                        "roic": inst.roic,
                    },
                    "liquidity_leverage": {
                        "current_ratio": 2.45,
                        "quick_ratio": 2.05,
                        "debt_to_equity": 0.28,
                        "net_debt_to_ebitda": -0.22,
                        "interest_coverage": 42.0,
                    },
                    "per_share_growth": {
                        "eps_diluted": 3.45 if inst.pe_ratio else None,
                        "revenue_per_share": 11.20 if inst.pe_ratio else None,
                        "book_value_per_share": 9.85 if inst.pe_ratio else None,
                        "revenue_growth_yoy": inst.rev_growth,
                        "eps_growth_yoy": inst.eps_growth,
                    },
                }
            )
        return {
            "source": "fastapi-fundamentals",
            "data_timestamp": _now_iso(),
            "currency": inst.currency,
            "periods": periods,
        }

    def get_earnings_history(self, symbol: str, quarters: int) -> dict[str, Any] | None:
        inst = _INSTRUMENTS.get(symbol.upper())
        if not inst:
            return None
        base_eps = round(inst.base_price / (inst.pe_ratio or 25.0) / 4.0, 2)
        entries = []
        today = datetime.now(UTC).date()
        for q in range(min(quarters, 8)):
            rep_d = today - timedelta(days=45 + q * 91)
            est = round(base_eps * (1.0 - q * 0.04), 2)
            surprise = round(4.5 + math.sin(q + len(symbol)) * 5.0, 2)
            act = round(est * (1.0 + surprise / 100.0), 2)
            rev_est = round(inst.market_cap * 0.008 * (1.0 - q * 0.03), 0)
            rev_act = round(rev_est * (1.0 + (surprise * 0.6) / 100.0), 0)
            entries.append(
                {
                    "fiscal_quarter": f"Q{4 - (q % 4)} FY{2026 - (q // 4)}",
                    "report_date": rep_d.isoformat(),
                    "eps_consensus": est,
                    "eps_actual": act,
                    "eps_surprise_pct": surprise,
                    "revenue_consensus": rev_est,
                    "revenue_actual": rev_act,
                    "revenue_surprise_pct": round(surprise * 0.6, 2),
                }
            )
        return {
            "source": "fastapi-fundamentals",
            "data_timestamp": _now_iso(),
            "currency": inst.currency,
            "next_earnings_date": (today + timedelta(days=28)).isoformat(),
            "quarters": entries,
        }

    def calculate_returns(
        self,
        symbol: str,
        benchmark_symbol: str,
        start_date: date,
        end_date: date,
        calendar_basis: str,
        risk_free_rate: float,
    ) -> dict[str, Any] | None:
        inst = _INSTRUMENTS.get(symbol.upper())
        bench = _INSTRUMENTS.get(benchmark_symbol.upper())
        if not inst or not bench:
            return None
        bars = _generate_daily_series(inst, start_date, end_date)
        b_bars = _generate_daily_series(bench, start_date, end_date)
        return {
            "source": "fastapi-quant-analytics",
            "data_timestamp": _now_iso(),
            "currency": inst.currency,
            "closes": [b["close"] for b in bars],
            "benchmark_closes": [b["close"] for b in b_bars[: len(bars)]],
            "risk_free_rate_used": risk_free_rate,
            "calendar_basis": calendar_basis,
        }

    def calculate_indicators(
        self,
        symbol: str,
        indicators: list[str],
        interval: str,
        lookback_bars: int,
        tail_values: int,
    ) -> dict[str, Any] | None:
        inst = _INSTRUMENTS.get(symbol.upper())
        if not inst:
            return None
        end_d = datetime.now(UTC).date()
        bars = _generate_daily_series(inst, end_d - timedelta(days=max(320, lookback_bars * 2)), end_d)
        bars = bars[-max(lookback_bars, 220) :]
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        vols = [b["volume"] for b in bars]
        latest_price = closes[-1]

        sma20 = _sma(closes, 20)
        sma50 = _sma(closes, 50)
        sma200 = _sma(closes, min(200, len(closes)))
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        macd_line: list[float | None] = [
            (e12 - e26) if (e12 is not None and e26 is not None) else None
            for e12, e26 in zip(ema12, ema26, strict=True)
        ]
        valid_macd = [m for m in macd_line if m is not None]
        sig_valid = _ema(valid_macd, 9) if len(valid_macd) >= 9 else [None] * len(valid_macd)
        macd_sig: list[float | None] = [None] * (len(macd_line) - len(sig_valid)) + sig_valid

        # Wilder-style RSI_14 over tail
        rsi_series: list[float | None] = [None] * len(closes)
        if len(closes) > 15:
            gains = [max(0.0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
            losses = [max(0.0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
            avg_g = statistics.fmean(gains[:14])
            avg_l = statistics.fmean(losses[:14])
            for i in range(14, len(gains)):
                avg_g = (avg_g * 13 + gains[i]) / 14.0
                avg_l = (avg_l * 13 + losses[i]) / 14.0
                rs = avg_g / avg_l if avg_l > 0 else 100.0
                rsi_series[i + 1] = round(100.0 - (100.0 / (1.0 + rs)), 2)

        snapshots = []
        for ind in indicators:
            if ind == "SMA_20" and sma20[-1] is not None:
                snapshots.append({"indicator": "SMA_20", "latest": {"value": round(sma20[-1], 2)}})
            elif ind == "SMA_50" and sma50[-1] is not None:
                snapshots.append({"indicator": "SMA_50", "latest": {"value": round(sma50[-1], 2)}})
            elif ind == "SMA_200" and sma200[-1] is not None:
                snapshots.append({"indicator": "SMA_200", "latest": {"value": round(sma200[-1], 2)}})
            elif ind == "EMA_12" and ema12[-1] is not None:
                snapshots.append({"indicator": "EMA_12", "latest": {"value": round(ema12[-1], 2)}})
            elif ind == "EMA_26" and ema26[-1] is not None:
                snapshots.append({"indicator": "EMA_26", "latest": {"value": round(ema26[-1], 2)}})
            elif ind == "RSI_14" and rsi_series[-1] is not None:
                snapshots.append({"indicator": "RSI_14", "latest": {"rsi": rsi_series[-1]}})
            elif ind == "MACD" and macd_line[-1] is not None and macd_sig[-1] is not None:
                snapshots.append(
                    {
                        "indicator": "MACD",
                        "latest": {
                            "macd": round(macd_line[-1], 4),
                            "signal": round(macd_sig[-1], 4),
                            "histogram": round(macd_line[-1] - macd_sig[-1], 4),
                        },
                    }
                )
            elif ind == "BOLLINGER_BANDS" and sma20[-1] is not None:
                sd20 = statistics.stdev(closes[-20:])
                snapshots.append(
                    {
                        "indicator": "BOLLINGER_BANDS",
                        "latest": {
                            "upper": round(sma20[-1] + 2 * sd20, 2),
                            "middle": round(sma20[-1], 2),
                            "lower": round(sma20[-1] - 2 * sd20, 2),
                        },
                    }
                )
            elif ind == "ATR_14" and len(bars) >= 15:
                trs = [
                    max(
                        highs[i] - lows[i],
                        abs(highs[i] - closes[i - 1]),
                        abs(lows[i] - closes[i - 1]),
                    )
                    for i in range(-14, 0)
                ]
                snapshots.append({"indicator": "ATR_14", "latest": {"atr": round(statistics.fmean(trs), 2)}})
            elif ind == "VWAP":
                tot_v = sum(vols[-20:])
                vw = sum(((highs[i] + lows[i] + closes[i]) / 3.0) * vols[i] for i in range(-20, 0)) / tot_v
                snapshots.append({"indicator": "VWAP", "latest": {"vwap": round(vw, 2)}})
            elif ind == "OBV":
                obv = 0
                for i in range(1, len(closes)):
                    if closes[i] > closes[i - 1]:
                        obv += vols[i]
                    elif closes[i] < closes[i - 1]:
                        obv -= vols[i]
                snapshots.append({"indicator": "OBV", "latest": {"obv": float(obv)}})

        tail_series = []
        for idx in range(-min(tail_values, len(bars)), 0):
            vals: dict[str, float | None] = {}
            if rsi_series[idx] is not None:
                vals["RSI_14"] = rsi_series[idx]
            if macd_line[idx] is not None:
                vals["MACD"] = round(macd_line[idx], 4)
            if macd_sig[idx] is not None:
                vals["MACD_SIGNAL"] = round(macd_sig[idx], 4)
            if sma50[idx] is not None:
                vals["SMA_50"] = round(sma50[idx], 2)
            tail_series.append({"timestamp": bars[idx]["timestamp"], "values": vals})

        return {
            "source": "fastapi-quant-indicators",
            "data_timestamp": _now_iso(),
            "currency": inst.currency,
            "latest_price": latest_price,
            "overall_regime": "BULLISH" if (sma50[-1] and latest_price >= sma50[-1]) else "NEUTRAL",
            "snapshots": snapshots,
            "tail_series": tail_series,
        }

    def compare_instruments(
        self, symbols: list[str], start_date: date, end_date: date
    ) -> dict[str, Any] | None:
        series_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for sym in symbols:
            inst = _INSTRUMENTS.get(sym.upper())
            if not inst:
                return None
            bars = _generate_daily_series(inst, start_date, end_date)
            series_by_symbol[inst.symbol] = [{"date": b["date"], "close": b["close"]} for b in bars]

        return {
            "source": "fastapi-quant-compare",
            "data_timestamp": _now_iso(),
            "currency": "USD",
            "series_by_symbol": series_by_symbol,
        }

    def analyse_portfolio(self, user_id: str, portfolio_id: str) -> dict[str, Any] | None:
        user_ports = self._portfolios.get(user_id, {})
        port = user_ports.get(portfolio_id)
        if not port:
            return None

        positions = []
        total_eq_mv = 0.0
        sector_totals: dict[str, float] = {}
        weighted_beta = 0.0
        weighted_vol = 0.0

        for h in port["holdings"]:
            inst = _INSTRUMENTS[h["symbol"]]
            quote = self.get_quote(inst.symbol)
            px = quote["last_price"] if quote else inst.base_price
            mv = round(h["quantity"] * px, 2)
            cost = round(h["quantity"] * h["cost_basis"], 2)
            pnl = round(mv - cost, 2)
            pnl_pct = round((pnl / cost) * 100.0, 2) if cost else 0.0
            total_eq_mv += mv
            sector_totals[inst.sector] = sector_totals.get(inst.sector, 0.0) + mv
            positions.append(
                {
                    "symbol": inst.symbol,
                    "name": inst.name,
                    "asset_class": inst.asset_type,
                    "sector": inst.sector,
                    "quantity": h["quantity"],
                    "market_price": px,
                    "market_value": mv,
                    "cost_basis": h["cost_basis"],
                    "unrealized_pnl": pnl,
                    "unrealized_pnl_pct": pnl_pct,
                    "_beta": inst.beta,
                    "_ann_vol": inst.vol * math.sqrt(252) * 100.0,
                }
            )

        cash = float(port["cash_balance"])
        nav = round(total_eq_mv + cash, 2)
        for pos in positions:
            w = round((pos["market_value"] / nav) * 100.0, 2) if nav else 0.0
            pos["weight_pct"] = w
            weighted_beta += (w / 100.0) * pos.pop("_beta")
            weighted_vol += (w / 100.0) * pos.pop("_ann_vol")

        cash_weight = round((cash / nav) * 100.0, 2) if nav else 0.0
        ann_vol = round(weighted_vol * 0.85, 2)
        daily_vol_dec = (ann_vol / 100.0) / math.sqrt(252)
        param_var = round(-1.645 * daily_vol_dec * 100.0, 2)
        hist_var = round(param_var * 1.07, 2)
        cvar = round(param_var * 1.48, 2)

        sector_alloc = [
            {"category": cat, "market_value": round(val, 2), "weight_pct": round((val / nav) * 100.0, 2)}
            for cat, val in sorted(sector_totals.items(), key=lambda x: x[1], reverse=True)
        ]
        if cash > 0:
            sector_alloc.append({"category": "Cash", "market_value": cash, "weight_pct": cash_weight})

        return {
            "source": "fastapi-portfolio-risk",
            "data_timestamp": _now_iso(),
            "portfolio_name": port["portfolio_name"],
            "base_currency": port["base_currency"],
            "nav": nav,
            "cash_balance": cash,
            "cash_weight_pct": cash_weight,
            "portfolio_beta": round(weighted_beta, 3),
            "annualized_volatility_pct": ann_vol,
            "sharpe_ratio": 1.62,
            "sortino_ratio": 2.18,
            "historical_var_pct": hist_var,
            "parametric_var_pct": param_var,
            "expected_shortfall_cvar_pct": cvar,
            "historical_var_amount": round(nav * (hist_var / 100.0), 2),
            "expected_shortfall_cvar_amount": round(nav * (cvar / 100.0), 2),
            "positions": positions,
            "sector_allocation": sector_alloc,
            "asset_class_allocation": [
                {"category": "EQUITY", "market_value": round(total_eq_mv, 2), "weight_pct": round(100.0 - cash_weight, 2)},
                {"category": "CASH", "market_value": cash, "weight_pct": cash_weight},
            ],
        }

    def simulate_rebalance(
        self, user_id: str, portfolio_id: str, proposed_trades: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        current = self.analyse_portfolio(user_id, portfolio_id)
        if not current:
            return None

        nav = current["nav"]
        cash = current["cash_balance"]
        pos_weights: dict[str, float] = {p["symbol"]: p["weight_pct"] for p in current["positions"]}
        pos_sectors: dict[str, str] = {p["symbol"]: p["sector"] for p in current["positions"]}

        pre_snapshot = {
            "cash_balance": cash,
            "cash_weight_pct": current["cash_weight_pct"],
            "portfolio_beta": current["portfolio_beta"],
            "annualized_volatility_pct": current["annualized_volatility_pct"],
            "var_95_pct": current["historical_var_pct"],
            "cvar_95_pct": current["expected_shortfall_cvar_pct"],
            "sector_weights_pct": {s["category"]: s["weight_pct"] for s in current["sector_allocation"]},
            "position_weights_pct": dict(pos_weights),
        }

        cash_delta = 0.0
        post_weights = dict(pos_weights)

        for trade in proposed_trades:
            sym = trade["symbol"].upper()
            inst = _INSTRUMENTS.get(sym)
            if not inst:
                raise ValueError(f"Unsupported symbol {sym}")
            px = self.get_quote(sym)["last_price"]
            if trade.get("weight_delta_pct") is not None:
                delta_w = float(trade["weight_delta_pct"])
                dollar_val = nav * (delta_w / 100.0)
            else:
                dollar_val = float(trade["share_delta"]) * px
                delta_w = (dollar_val / nav) * 100.0 if nav else 0.0

            if trade["side"] == "BUY":
                cash_delta -= dollar_val
                post_weights[sym] = round(post_weights.get(sym, 0.0) + delta_w, 2)
            else:
                cash_delta += dollar_val
                post_weights[sym] = round(max(0.0, post_weights.get(sym, 0.0) - delta_w), 2)
            pos_sectors.setdefault(sym, inst.sector)

        post_cash = round(cash + cash_delta, 2)
        post_cash_w = round((post_cash / nav) * 100.0, 2) if nav else 0.0

        post_beta = 0.0
        post_vol_base = 0.0
        post_sectors: dict[str, float] = {}
        for sym, w in post_weights.items():
            inst = _INSTRUMENTS[sym]
            post_beta += (w / 100.0) * inst.beta
            post_vol_base += (w / 100.0) * (inst.vol * math.sqrt(252) * 100.0)
            sec = pos_sectors.get(sym, inst.sector)
            post_sectors[sec] = round(post_sectors.get(sec, 0.0) + w, 2)

        post_ann_vol = round(post_vol_base * 0.85, 2)
        post_var = round(-1.645 * ((post_ann_vol / 100.0) / math.sqrt(252)) * 100.0 * 1.07, 2)
        post_cvar = round(post_var * 1.38, 2)

        post_snapshot = {
            "cash_balance": post_cash,
            "cash_weight_pct": post_cash_w,
            "portfolio_beta": round(post_beta, 3),
            "annualized_volatility_pct": post_ann_vol,
            "var_95_pct": post_var,
            "cvar_95_pct": post_cvar,
            "sector_weights_pct": post_sectors,
            "position_weights_pct": post_weights,
        }

        return {
            "source": "fastapi-portfolio-simulator",
            "data_timestamp": _now_iso(),
            "base_currency": current["base_currency"],
            "estimated_cash_impact": round(cash_delta, 2),
            "pre_trade": pre_snapshot,
            "post_trade": post_snapshot,
            "constraint_violations": [],
        }

    def mutate_watchlist(
        self,
        user_id: str,
        watchlist_id: str,
        action: str,
        symbols: list[str],
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        if idempotency_key and (user_id, idempotency_key) in self._idempotency_results:
            return self._idempotency_results[(user_id, idempotency_key)]

        user_lists = self._watchlists.setdefault(user_id, {"default": []})
        items = user_lists.setdefault(watchlist_id, [])

        if action == "ADD":
            for sym in symbols:
                if sym not in items:
                    items.append(sym)
        elif action == "REMOVE":
            items[:] = [s for s in items if s not in set(symbols)]

        res = {
            "source": "fastapi-watchlists",
            "data_timestamp": _now_iso(),
            "symbols": list(items),
            "updated_at": _now_iso(),
        }
        if idempotency_key and action in ("ADD", "REMOVE"):
            self._idempotency_results[(user_id, idempotency_key)] = res
        return res

    def create_alert(
        self,
        user_id: str,
        symbol: str,
        condition: str,
        threshold_value: float,
        note: str | None,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        if idempotency_key and (user_id, idempotency_key) in self._idempotency_results:
            return self._idempotency_results[(user_id, idempotency_key)]

        alert = {
            "source": "fastapi-alerts",
            "data_timestamp": _now_iso(),
            "alert_id": f"alrt_{uuid.uuid4().hex[:8]}",
            "symbol": symbol,
            "condition": condition,
            "threshold_value": threshold_value,
            "note": note,
            "status": "ACTIVE",
            "created_at": _now_iso(),
        }
        self._alerts.setdefault(user_id, []).append(alert)
        if idempotency_key:
            self._idempotency_results[(user_id, idempotency_key)] = alert
        return alert

    def save_memo(
        self,
        user_id: str,
        title: str,
        symbols: list[str],
        thesis_markdown: str,
        sentiment: str,
        cited_data_timestamps: list[str],
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        if idempotency_key and (user_id, idempotency_key) in self._idempotency_results:
            return self._idempotency_results[(user_id, idempotency_key)]

        memo = {
            "source": "fastapi-research-notes",
            "data_timestamp": _now_iso(),
            "memo_id": f"memo_{uuid.uuid4().hex[:8]}",
            "title": title,
            "symbols": symbols,
            "thesis_markdown": thesis_markdown,
            "sentiment": sentiment,
            "cited_data_timestamps": cited_data_timestamps,
            "created_at": _now_iso(),
        }
        self._memos.setdefault(user_id, []).append(memo)
        if idempotency_key:
            self._idempotency_results[(user_id, idempotency_key)] = memo
        return memo
