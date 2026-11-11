"""Instrument discovery, exchange trading schedule, and company profile tools."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from app.auth.permissions import require_scopes
from app.schemas.common import CalendarType, Pagination, ResponseEnvelope
from app.schemas.instruments import (
    CompanyProfileData,
    ExchangeScheduleData,
    InstrumentItem,
    SearchInstrumentsData,
)
from app.tools.helpers import (
    build_envelope,
    emit_protocol_log,
    get_runtime,
    mcp_tool_boundary,
    parse_utc_datetime,
)
from app.utils.errors import InvalidParametersError, NoDataAvailableError
from app.utils.formatting import build_tool_result, format_markdown_table
from app.utils.validators import (
    normalize_symbol,
    validate_date_range,
    validate_exchange_code,
    validate_search_query,
)


@mcp_tool_boundary("search_instruments")
@require_scopes("market:read")
async def search_instruments(
    query: str,
    asset_type: Literal["ALL", "EQUITY", "ETF", "INDEX", "CRYPTO", "FX"] = "ALL",
    exchange: str | None = None,
    limit: int = 10,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[SearchInstrumentsData]]:
    """Search tradable financial instruments by ticker prefix, company name, ISIN, or FIGI.

    When to call:
    - Use first when the user mentions a company name (e.g., "Nvidia", "Taiwan Semiconductor") or
      ambiguous ticker and you need the exact normalized symbol, primary exchange, or currency.
    - Not needed if the exact normalized ticker is already verified.

    Parameter rules:
    - `query`: 1 to 50 non-whitespace characters.
    - `asset_type`: One of `ALL`, `EQUITY`, `ETF`, `INDEX`, `CRYPTO`, `FX` (default `ALL`).
    - `exchange`: Optional exchange MIC/code (e.g., `NASDAQ`, `NYSE`, `LSE`).
    - `limit`: Integer between 1 and 50 (default 10).

    Calendar behavior:
    - Metadata reflects `TRADING_DAYS` for primary listing schedules; results are cached for 300s.

    Output guarantees:
    - Returns a standardized `ResponseEnvelope[SearchInstrumentsData]` with `status`, `metadata`
      provenance, `warnings`, and matching instruments with ISIN/FIGI when available.
    """
    cleaned_query, validated_limit = validate_search_query(query, limit)
    cleaned_exchange = validate_exchange_code(exchange) if exchange is not None else None

    runtime = get_runtime(ctx)
    await emit_protocol_log(ctx, "info", f"Searching instruments for query={cleaned_query!r}")

    resp = await runtime.backend_client.request(
        "GET",
        "/api/v1/market/instruments/search",
        params={
            "q": cleaned_query,
            "asset_type": asset_type,
            "exchange": cleaned_exchange,
            "limit": validated_limit,
        },
        tenant_scope="PUBLIC",
        ttl_seconds=runtime.settings.ttl_search_seconds,
    )

    raw = resp.data
    raw_items = raw.get("instruments", raw.get("items", []))
    instruments = [InstrumentItem.model_validate(item) for item in raw_items][:validated_limit]
    total_matches = int(raw.get("total_matches", len(instruments)))

    payload = SearchInstrumentsData(
        query=cleaned_query,
        asset_type_filter=asset_type,
        exchange_filter=cleaned_exchange,
        total_matches=total_matches,
        instruments=instruments,
    )
    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))

    envelope = build_envelope(
        data=payload,
        source=str(raw.get("source", "fastapi-market-reference")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_schedule_seconds,
        currency=None,
        units="instruments",
        calendar_type=CalendarType.TRADING_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        no_data=(len(instruments) == 0),
        warnings=list(raw.get("warnings", [])),
        pagination=Pagination(
            limit=validated_limit,
            offset=0,
            total_count=total_matches,
            has_more=total_matches > len(instruments),
        ),
    )
    md = format_markdown_table(
        ["Symbol", "Name", "Type", "Exchange", "Currency", "Active"],
        [
            [i.symbol, i.name, i.asset_type, i.primary_exchange, i.currency, i.is_active]
            for i in instruments
        ],
    )
    return build_tool_result(envelope, md or f"No instruments matched {cleaned_query!r}.")


@mcp_tool_boundary("get_exchange_schedule")
@require_scopes("market:read")
async def get_exchange_schedule(
    exchange: str,
    start_date: date | None = None,
    end_date: date | None = None,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[ExchangeScheduleData]]:
    """Retrieve exchange trading session hours, current market state, and holiday calendar.

    When to call:
    - Call before interpreting intraday price freshness, market-open status, or cross-exchange
      date alignment across international venues (e.g., NYSE vs LSE vs TSE).

    Parameter rules:
    - `exchange`: 2-16 character exchange code or MIC (e.g., `NYSE`, `NASDAQ`, `XNAS`, `LSE`).
    - `start_date` / `end_date`: Optional date window (`start_date <= end_date`) for holiday lookup.

    Calendar behavior:
    - Uses `CALENDAR_DAYS` for holiday schedules and reports session hours in both local exchange
      timezone and UTC.

    Output guarantees:
    - Returns `ResponseEnvelope[ExchangeScheduleData]` with `market_state` (`OPEN`, `CLOSED`,
      `PRE_MARKET`, `AFTER_HOURS`), local/UTC session hours, and upcoming holidays.
    """
    cleaned_exchange = validate_exchange_code(exchange)
    if (start_date is None) != (end_date is None):
        raise InvalidParametersError("Provide both start_date and end_date, or omit both.")
    if start_date is not None and end_date is not None:
        validate_date_range(start_date, end_date, allow_future_end=True)

    runtime = get_runtime(ctx)
    await emit_protocol_log(ctx, "info", f"Fetching exchange schedule for {cleaned_exchange}")

    resp = await runtime.backend_client.request(
        "GET",
        f"/api/v1/market/exchanges/{cleaned_exchange}/schedule",
        params={
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        tenant_scope="PUBLIC",
        ttl_seconds=runtime.settings.ttl_schedule_seconds,
    )

    raw = resp.data
    schedule = ExchangeScheduleData.model_validate(raw)
    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))

    envelope = build_envelope(
        data=schedule,
        source=str(raw.get("source", "fastapi-exchange-calendar")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_schedule_seconds,
        currency=None,
        units="session_schedule",
        calendar_type=CalendarType.CALENDAR_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        warnings=list(raw.get("warnings", [])),
    )
    md = (
        f"### {schedule.exchange} ({schedule.exchange_name})\n"
        f"- **State:** `{schedule.market_state}` | **Trading Day:** `{schedule.is_trading_day}`\n"
        f"- **Hours ({schedule.timezone}):** {schedule.regular_open_local} – {schedule.regular_close_local}\n"
        f"- **Upcoming Holidays:** {len(schedule.upcoming_holidays)}"
    )
    return build_tool_result(envelope, md)


@mcp_tool_boundary("get_company_profile")
@require_scopes("market:read")
async def get_company_profile(
    symbol: str,
    ctx: Context | None = None,
) -> Annotated[CallToolResult, ResponseEnvelope[CompanyProfileData]]:
    """Fetch canonical corporate profile, GICS sector/industry classification, and listing metadata.

    When to call:
    - Call during single-name equity research, tearsheet generation, or sector attribution.

    Parameter rules:
    - `symbol`: Ticker symbol normalized automatically (1-16 chars matching `[A-Z0-9.-^=]`).

    Calendar behavior:
    - Reference fundamentals cached for 86,400s; `CALENDAR_DAYS` provenance.

    Output guarantees:
    - Returns `ResponseEnvelope[CompanyProfileData]` with legal name, GICS sector/industry,
      headquarters, CEO, headcount, fiscal year end, and listing currency.
    """
    norm_symbol = normalize_symbol(symbol)
    runtime = get_runtime(ctx)
    await emit_protocol_log(ctx, "info", f"Fetching company profile for {norm_symbol}")

    resp = await runtime.backend_client.request(
        "GET",
        f"/api/v1/fundamentals/profile/{norm_symbol}",
        tenant_scope="PUBLIC",
        ttl_seconds=runtime.settings.ttl_profile_seconds,
    )
    raw = resp.data
    if not raw or not raw.get("legal_name"):
        raise NoDataAvailableError(f"No company profile data available for {norm_symbol}.")

    profile = CompanyProfileData.model_validate(raw)
    data_ts = parse_utc_datetime(raw.get("data_timestamp"), default=datetime.now(UTC))

    envelope = build_envelope(
        data=profile,
        source=str(raw.get("source", "fastapi-fundamentals")),
        data_timestamp=data_ts,
        staleness_threshold_seconds=runtime.settings.stale_fundamentals_seconds,
        currency=profile.currency,
        units="company_profile",
        calendar_type=CalendarType.CALENDAR_DAYS,
        cache_hit=resp.cache_hit,
        backend_is_stale=bool(raw.get("is_stale", False)),
        warnings=list(raw.get("warnings", [])),
    )
    md = (
        f"### {profile.legal_name} (`{profile.symbol}`)\n"
        f"- **Sector / Industry:** {profile.sector or '—'} / {profile.industry or '—'}\n"
        f"- **Exchange / Currency:** {profile.primary_exchange} ({profile.currency})\n"
        f"- **CEO:** {profile.ceo or '—'} | **Employees:** {profile.employees or '—'}"
    )
    return build_tool_result(envelope, md)


def register_discovery_tools(mcp: MCPServer) -> None:
    """Register discovery and reference-data tools onto the MCPServer."""
    read_annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
    mcp.add_tool(search_instruments, annotations=read_annotations)
    mcp.add_tool(get_exchange_schedule, annotations=read_annotations)
    mcp.add_tool(get_company_profile, annotations=read_annotations)
