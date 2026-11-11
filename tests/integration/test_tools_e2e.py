"""End-to-end integration tests for all 15 MCP tools, provenance metadata, and error paths."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from mcp import Client

from app.schemas.common import EnvelopeStatus


def _assert_provenance(envelope: dict, *, expected_status: str = "OK") -> None:
    assert envelope["status"] == expected_status
    meta = envelope["metadata"]
    for required_field in (
        "source",
        "data_timestamp",
        "fetched_at",
        "is_stale",
        "staleness_threshold_seconds",
        "calendar_type",
        "cache_hit",
        "request_id",
    ):
        assert required_field in meta
    assert meta["data_timestamp"].endswith("Z")
    assert meta["fetched_at"].endswith("Z")
    assert meta["calendar_type"] in ("TRADING_DAYS", "CALENDAR_DAYS")


@pytest.mark.asyncio
async def test_tool_discovery_and_zero_trust_schema_hygiene(mcp_server) -> None:
    async with Client(mcp_server) as mcp_client:
        listing = await mcp_client.list_tools()
    names = {t.name for t in listing.tools}
    expected = {
        "search_instruments",
        "get_exchange_schedule",
        "get_company_profile",
        "get_market_quote",
        "get_historical_prices",
        "get_financial_metrics",
        "get_earnings_history",
        "calculate_returns",
        "calculate_technical_indicators",
        "compare_instruments",
        "analyse_portfolio",
        "simulate_portfolio_rebalance",
        "manage_watchlist",
        "create_price_alert",
        "save_research_memo",
    }
    assert names == expected

    # Critical zero-trust invariant: no LLM-visible auth/identity params
    forbidden_param_names = {"ctx", "context", "user_id", "token", "api_key", "authorization", "jwt"}
    for tool in listing.tools:
        props = set((tool.input_schema or {}).get("properties", {}).keys())
        assert props.isdisjoint(forbidden_param_names), f"Tool {tool.name} leaked forbidden param: {props}"


@pytest.mark.asyncio
async def test_all_15_tools_e2e_happy_paths(mcp_server, respx_backend: respx.MockRouter) -> None:
    async with Client(mcp_server) as mcp_client:
        await _run_all_15_tools(mcp_client, respx_backend)


async def _run_all_15_tools(mcp_client: Client, respx_backend: respx.MockRouter) -> None:
    # 1. search_instruments
    r1 = await mcp_client.call_tool("search_instruments", {"query": "NVDA", "limit": 5})
    assert not r1.is_error
    env1 = json.loads(r1.content[0].text)
    _assert_provenance(env1)
    assert env1["data"]["total_matches"] == 2

    # 2. get_exchange_schedule
    r2 = await mcp_client.call_tool("get_exchange_schedule", {"exchange": "nasdaq"})
    assert not r2.is_error
    env2 = json.loads(r2.content[0].text)
    _assert_provenance(env2)
    assert env2["data"]["market_state"] == "OPEN"

    # 3. get_company_profile
    r3 = await mcp_client.call_tool("get_company_profile", {"symbol": "nvda"})
    assert not r3.is_error
    env3 = json.loads(r3.content[0].text)
    _assert_provenance(env3)
    assert env3["data"]["legal_name"] == "NVIDIA Corporation"

    # 4. get_market_quote + verify outbound zero-trust headers
    r4 = await mcp_client.call_tool("get_market_quote", {"symbol": "nvda"})
    assert not r4.is_error
    env4 = json.loads(r4.content[0].text)
    _assert_provenance(env4)
    assert env4["data"]["last_price"] == 148.50
    assert env4["data"]["spread_bps"] is not None
    last_req = respx_backend.calls[-1].request
    assert last_req.headers["x-internal-api-key"] == "test-backend-internal-key"
    assert last_req.headers["authorization"].startswith("Bearer ")
    assert last_req.headers["x-request-id"] == "req-test-001"
    assert last_req.headers["x-mcp-tool-name"] == "get_market_quote"

    # 5. get_historical_prices (verifies deterministic summary stats & VWAP)
    r5 = await mcp_client.call_tool(
        "get_historical_prices",
        {
            "symbol": "NVDA",
            "start_date": "2026-10-12",
            "end_date": "2026-11-01",
            "interval": "1d",
            "include_summary_stats": True,
        },
    )
    assert not r5.is_error
    env5 = json.loads(r5.content[0].text)
    _assert_provenance(env5)
    assert env5["data"]["bars_count"] > 0
    assert env5["data"]["summary_stats"]["vwap"] is not None
    assert env5["data"]["summary_stats"]["period_high"] >= env5["data"]["summary_stats"]["period_low"]

    # 6. get_financial_metrics
    r6 = await mcp_client.call_tool("get_financial_metrics", {"symbol": "NVDA", "period": "TTM"})
    assert not r6.is_error
    env6 = json.loads(r6.content[0].text)
    _assert_provenance(env6)
    assert env6["data"]["periods"][0]["valuation"]["pe_ratio"] == 48.2

    # 7. get_earnings_history
    r7 = await mcp_client.call_tool("get_earnings_history", {"symbol": "NVDA", "quarters": 4})
    assert not r7.is_error
    env7 = json.loads(r7.content[0].text)
    _assert_provenance(env7)
    assert env7["data"]["quarters"][0]["eps_surprise_pct"] == 9.46

    # 8. calculate_returns
    r8 = await mcp_client.call_tool("calculate_returns", {"symbol": "NVDA", "period": "1M", "benchmark_symbol": "SPY"})
    assert not r8.is_error
    env8 = json.loads(r8.content[0].text)
    _assert_provenance(env8)
    assert env8["data"]["sharpe_ratio"] == 2.41

    # 9. calculate_technical_indicators
    r9 = await mcp_client.call_tool(
        "calculate_technical_indicators",
        {"symbol": "NVDA", "indicators": ["RSI_14", "MACD", "SMA_50"], "interval": "1d"},
    )
    assert not r9.is_error
    env9 = json.loads(r9.content[0].text)
    _assert_provenance(env9)
    sma_snap = next(s for s in env9["data"]["snapshots"] if s["indicator"] == "SMA_50")
    assert sma_snap["regime_signal"] == "PRICE_ABOVE_MA"

    # 10. compare_instruments with progress notifications
    progress_events: list[tuple[float, float | None, str | None]] = []

    async def on_progress(progress: float, total: float | None, message: str | None) -> None:
        progress_events.append((progress, total, message))

    r10 = await mcp_client.call_tool(
        "compare_instruments",
        {"symbols": ["NVDA", "AMD"], "period": "1M"},
        progress_callback=on_progress,
    )
    assert not r10.is_error
    env10 = json.loads(r10.content[0].text)
    _assert_provenance(env10)
    assert env10["data"]["correlation_matrix"]["NVDA"]["AMD"] == 0.78
    assert len(progress_events) >= 2

    # 11. analyse_portfolio
    r11 = await mcp_client.call_tool("analyse_portfolio", {"portfolio_id": "port_123"})
    assert not r11.is_error
    env11 = json.loads(r11.content[0].text)
    _assert_provenance(env11)
    assert env11["data"]["nav"] == 1_250_000.0
    assert env11["data"]["historical_var_pct"] == -2.15

    # 12. simulate_portfolio_rebalance (detects negative cash & >25% concentration violations)
    r12 = await mcp_client.call_tool(
        "simulate_portfolio_rebalance",
        {
            "portfolio_id": "port_123",
            "proposed_trades": [{"symbol": "NVDA", "side": "BUY", "weight_delta_pct": 10.0}],
        },
    )
    assert not r12.is_error
    env12 = json.loads(r12.content[0].text)
    _assert_provenance(env12)
    rule_codes = {v["rule_code"] for v in env12["data"]["constraint_violations"]}
    assert {"NEGATIVE_CASH", "SINGLE_STOCK_CONCENTRATION"}.issubset(rule_codes)

    # 13. manage_watchlist
    r13 = await mcp_client.call_tool(
        "manage_watchlist",
        {"action": "ADD", "watchlist_name": "AI Leaders", "symbols": ["NVDA", "AMD"]},
    )
    assert not r13.is_error
    env13 = json.loads(r13.content[0].text)
    _assert_provenance(env13)
    assert "NVDA" in env13["data"]["symbols"]

    # 14. create_price_alert
    r14 = await mcp_client.call_tool(
        "create_price_alert",
        {"symbol": "NVDA", "condition": "CROSSES_ABOVE", "threshold_value": 155.0, "note": "Breakout"},
    )
    assert not r14.is_error
    env14 = json.loads(r14.content[0].text)
    _assert_provenance(env14)
    assert env14["data"]["alert_id"] == "alrt_9001"

    # 15. save_research_memo
    r15 = await mcp_client.call_tool(
        "save_research_memo",
        {
            "title": "NVDA vs AMD Compute Capex Thesis",
            "symbols": ["NVDA", "AMD"],
            "thesis_markdown": "NVIDIA maintains software moat and ROIC leadership.",
            "sentiment": "BULLISH",
            "cited_data_timestamps": [env4["metadata"]["data_timestamp"]],
        },
    )
    assert not r15.is_error
    env15 = json.loads(r15.content[0].text)
    _assert_provenance(env15)
    assert env15["data"]["memo_id"] == "memo_7001"


@pytest.mark.asyncio
async def test_stale_data_and_error_classification(mcp_server, respx_backend: respx.MockRouter) -> None:
    async with Client(mcp_server) as mcp_client:
        await _run_stale_and_errors(mcp_client, respx_backend)


async def _run_stale_and_errors(mcp_client: Client, respx_backend: respx.MockRouter) -> None:
    # STALE_DATA on old quote timestamp (> 60s SLA)
    stale_ts = (datetime.now(UTC) - timedelta(seconds=300)).isoformat().replace("+00:00", "Z")
    respx_backend.get("/api/v1/market/quotes/OLDQ").mock(
        return_value=httpx.Response(
            200,
            json={
                "source": "delayed-feed",
                "data_timestamp": stale_ts,
                "symbol": "OLDQ",
                "last_price": 42.0,
                "currency": "USD",
                "exchange": "NYSE",
                "is_delayed": True,
                "delay_minutes": 15,
                "quote_timestamp": stale_ts,
            },
        )
    )
    res_stale = await mcp_client.call_tool("get_market_quote", {"symbol": "OLDQ"})
    assert not res_stale.is_error
    env_stale = json.loads(res_stale.content[0].text)
    assert env_stale["status"] == EnvelopeStatus.STALE_DATA.value
    assert env_stale["metadata"]["is_stale"] is True
    assert any("STALE_DATA" in w for w in env_stale["warnings"])

    # UNSUPPORTED_SYMBOL
    res_unsup = await mcp_client.call_tool("get_market_quote", {"symbol": "INVALIDXYZ"})
    assert res_unsup.is_error
    env_unsup = json.loads(res_unsup.content[0].text)
    assert env_unsup["error"]["code"] == "UNSUPPORTED_SYMBOL"

    # RATE_LIMITED from backend 429
    respx_backend.get("/api/v1/market/quotes/LIMIT").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "12"}, json={"message": "Quota exceeded"})
    )
    res_rate = await mcp_client.call_tool("get_market_quote", {"symbol": "LIMIT"})
    assert res_rate.is_error
    env_rate = json.loads(res_rate.content[0].text)
    assert env_rate["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_watchlist_read_cache_invalidation_and_derived_fallbacks(
    test_settings,
    bind_full_security_context,
) -> None:
    """Verify LIST caching + ADD invalidation, MACD crossover detection, and auto valuation enrichment."""
    from app.server import create_mcp_server
    from tests.conftest import iso_now

    ts1 = iso_now(-120)
    ts2 = iso_now(-60)
    ts3 = iso_now(-10)

    with respx.mock(base_url="http://backend.test") as mock:
        wl_calls = 0

        def _wl_handler(request: httpx.Request) -> httpx.Response:
            nonlocal wl_calls
            wl_calls += 1
            body = json.loads(request.content)
            syms = ["NVDA"] if body["action"] == "LIST" and wl_calls == 1 else ["NVDA", "AMD"]
            return httpx.Response(200, json={"source": "wl", "data_timestamp": ts3, "symbols": syms})

        mock.post("/api/v1/watchlists/default/items").mock(side_effect=_wl_handler)
        mock.post("/api/v1/analytics/indicators").mock(
            return_value=httpx.Response(
                200,
                json={
                    "source": "quant-ind",
                    "data_timestamp": ts3,
                    "latest_price": 150.0,
                    "snapshots": [
                        {"indicator": "SMA_200", "latest": {"value": 120.0}},
                        {"indicator": "MACD", "latest": {"macd": 1.2, "signal": 0.8}},
                    ],
                    "tail_series": [
                        {"timestamp": ts1, "values": {"MACD": 0.4, "MACD_SIGNAL": 0.6}},
                        {"timestamp": ts2, "values": {"MACD": 0.9, "MACD_SIGNAL": 0.7}},
                        {"timestamp": ts3, "values": {"MACD": 1.2, "MACD_SIGNAL": 0.8}},
                    ],
                },
            )
        )
        mock.post("/api/v1/analytics/compare").mock(
            return_value=httpx.Response(
                200,
                json={
                    "source": "quant-cmp",
                    "data_timestamp": ts3,
                    "comparison_table": [
                        {"symbol": "NVDA", "cumulative_return_pct": 10.0, "sharpe_ratio": 2.0},
                        {"symbol": "AMD", "cumulative_return_pct": 5.0, "sharpe_ratio": 1.2},
                    ],
                },
            )
        )
        mock.get("/api/v1/fundamentals/metrics/NVDA").mock(
            return_value=httpx.Response(
                200,
                json={"periods": [{"fiscal_period": "TTM", "valuation": {"pe_ratio": 45.0, "ev_to_ebitda": 38.0}}]},
            )
        )
        mock.get("/api/v1/fundamentals/metrics/AMD").mock(
            return_value=httpx.Response(
                200,
                json={"periods": [{"fiscal_period": "TTM", "valuation": {"pe_ratio": 36.0, "ev_to_ebitda": 27.5}}]},
            )
        )

        server = create_mcp_server(test_settings)
        async with Client(server) as client:
            # 1st LIST -> miss, 2nd LIST -> cache hit, ADD -> invalidates, 3rd LIST -> miss with updated data
            l1 = json.loads((await client.call_tool("manage_watchlist", {"action": "LIST"})).content[0].text)
            l2 = json.loads((await client.call_tool("manage_watchlist", {"action": "LIST"})).content[0].text)
            assert l1["metadata"]["cache_hit"] is False and l1["data"]["symbols"] == ["NVDA"]
            assert l2["metadata"]["cache_hit"] is True

            await client.call_tool("manage_watchlist", {"action": "ADD", "symbols": ["AMD"]})
            l3 = json.loads((await client.call_tool("manage_watchlist", {"action": "LIST"})).content[0].text)
            assert l3["metadata"]["cache_hit"] is False and l3["data"]["symbols"] == ["NVDA", "AMD"]

            # SMA_200 regime + MACD crossover timestamp detection
            ind = json.loads(
                (
                    await client.call_tool(
                        "calculate_technical_indicators",
                        {"symbol": "NVDA", "indicators": ["SMA_200", "MACD"]},
                    )
                ).content[0].text
            )
            snaps = {s["indicator"]: s for s in ind["data"]["snapshots"]}
            assert snaps["SMA_200"]["regime_signal"] == "PRICE_ABOVE_200SMA"
            assert snaps["MACD"]["regime_signal"] == "BULLISH"
            assert snaps["MACD"]["crossover_timestamp"] is not None

            # Auto-enrichment of missing valuation multiples in compare_instruments
            cmp_env = json.loads(
                (
                    await client.call_tool(
                        "compare_instruments",
                        {"symbols": ["NVDA", "AMD"], "metrics": ["RETURNS", "VALUATION"]},
                    )
                ).content[0].text
            )
            rows = {r["symbol"]: r for r in cmp_env["data"]["comparison_table"]}
            assert rows["NVDA"]["pe_ratio"] == 45.0
            assert rows["AMD"]["ev_to_ebitda"] == 27.5
