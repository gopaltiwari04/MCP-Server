"""Integration tests for the multi-tool NVDA vs AMD workflow & Streamable HTTP ASGI stack."""

import json
import sys
from pathlib import Path

import httpx
import httpx2
import pytest
import respx
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from app.main import create_asgi_app
from app.tools.comparison import align_and_compute_from_series
from tests.conftest import (
    INTERNAL_API_KEY,
    enter_asgi_lifespan,
    iso_now,
    make_internal_jwt,
)


@pytest.mark.asyncio
async def test_nvda_vs_amd_30d_multi_tool_workflow(mcp_server) -> None:
    """Flagship workflow: history + returns + technicals + comparison with full provenance."""
    async with Client(mcp_server) as mcp_client:
        await _run_nvda_vs_amd_workflow(mcp_client)


async def _run_nvda_vs_amd_workflow(mcp_client: Client) -> None:
    hist_nvda = await mcp_client.call_tool(
        "get_historical_prices",
        {"symbol": "NVDA", "start_date": "2026-10-12", "end_date": "2026-11-11", "interval": "1d"},
    )
    hist_amd = await mcp_client.call_tool(
        "get_historical_prices",
        {"symbol": "AMD", "start_date": "2026-10-12", "end_date": "2026-11-11", "interval": "1d"},
    )
    ret_nvda = await mcp_client.call_tool(
        "calculate_returns",
        {"symbol": "NVDA", "period": "1M", "benchmark_symbol": "SPY"},
    )
    ret_amd = await mcp_client.call_tool(
        "calculate_returns",
        {"symbol": "AMD", "period": "1M", "benchmark_symbol": "SPY"},
    )
    tech_nvda = await mcp_client.call_tool(
        "calculate_technical_indicators",
        {"symbol": "NVDA", "indicators": ["RSI_14", "MACD", "SMA_50"]},
    )
    tech_amd = await mcp_client.call_tool(
        "calculate_technical_indicators",
        {"symbol": "AMD", "indicators": ["RSI_14", "MACD", "SMA_50"]},
    )
    comp = await mcp_client.call_tool(
        "compare_instruments",
        {"symbols": ["NVDA", "AMD"], "period": "1M"},
    )

    for res in (hist_nvda, hist_amd, ret_nvda, ret_amd, tech_nvda, tech_amd, comp):
        assert not res.is_error
        env = json.loads(res.content[0].text)
        assert env["status"] == "OK"
        assert env["metadata"]["source"]
        assert env["metadata"]["data_timestamp"].endswith("Z")
        assert env["metadata"]["fetched_at"].endswith("Z")
        assert env["metadata"]["request_id"] == "req-test-001"

    comp_env = json.loads(comp.content[0].text)
    assert comp_env["data"]["rankings"][0]["ordered_symbols"] == ["NVDA", "AMD"]
    assert comp_env["data"]["correlation_matrix"]["NVDA"]["AMD"] == 0.78


def test_cross_exchange_date_alignment_drops_holiday_mismatches() -> None:
    """Verify common trading-day intersection drops non-overlapping dates explicitly."""
    series = {
        "NVDA": [
            {"date": "2026-11-02", "close": 140.0},
            {"date": "2026-11-03", "close": 142.0},  # US trading day, UK holiday
            {"date": "2026-11-04", "close": 145.0},
            {"date": "2026-11-05", "close": 148.0},
        ],
        "AZN.L": [
            {"date": "2026-11-02", "close": 110.0},
            {"date": "2026-11-04", "close": 112.0},
            {"date": "2026-11-05", "close": 113.0},
            {"date": "2026-11-06", "close": 114.0},  # UK trading day, US omitted
        ],
    }
    start_d, end_d, count, dropped, rows, corr = align_and_compute_from_series(
        symbols=["NVDA", "AZN.L"],
        series_by_symbol=series,
        risk_free_rate=0.045,
    )
    assert str(start_d) == "2026-11-02"
    assert str(end_d) == "2026-11-05"
    assert count == 3
    assert dropped["NVDA"] == ["2026-11-03"]
    assert dropped["AZN.L"] == ["2026-11-06"]
    assert len(rows) == 2
    assert -1.0 <= corr["NVDA"]["AZN.L"] <= 1.0


@pytest.mark.asyncio
async def test_streamable_http_asgi_stack_end_to_end(test_settings, respx_backend: respx.MockRouter) -> None:
    """Drive full Streamable HTTP transport through ZeroTrustAuthMiddleware over ASGI."""
    app = create_asgi_app(test_settings, configure_logs=False)
    jwt_alice = make_internal_jwt(user_id="user_alice", scopes=["market:read", "portfolio:read"])
    headers = {
        "X-Internal-API-Key": INTERNAL_API_KEY,
        "Authorization": f"Bearer {jwt_alice}",
        "X-Request-ID": "req-http-e2e-1",
    }

    async with enter_asgi_lifespan(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
            headers=headers,
        ) as http_client:
            transport = streamable_http_client("http://testserver/mcp", http_client=http_client)
            async with Client(transport) as client:
                tools = await client.list_tools()
                assert len(tools.tools) == 15

                quote_res = await client.call_tool("get_market_quote", {"symbol": "NVDA"})
                assert not quote_res.is_error
                env = json.loads(quote_res.content[0].text)
                assert env["data"]["last_price"] == 148.5
                assert env["metadata"]["request_id"] == "req-http-e2e-1"

                port_res = await client.call_tool("analyse_portfolio", {"portfolio_id": "port_123"})
                assert not port_res.is_error
                port_env = json.loads(port_res.content[0].text)
                assert port_env["data"]["nav"] == 1_250_000.0


@pytest.mark.asyncio
async def test_health_ready_returns_503_when_backend_unhealthy(test_settings) -> None:
    with respx.mock(base_url="http://backend.test") as mock:
        mock.get("/health").mock(return_value=httpx.Response(503, json={"status": "down"}))
        app = create_asgi_app(test_settings, configure_logs=False)

        async with enter_asgi_lifespan(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as http_client:
                live = await http_client.get("/health/live")
                assert live.status_code == 200
                ready = await http_client.get("/health/ready")
                assert ready.status_code == 503
                assert ready.json()["status"] == "degraded"


@pytest.mark.asyncio
async def test_stdio_transport_subprocess_discovery() -> None:
    """Verify `python -m app.main --transport stdio` speaks clean MCP over stdio without stdout logs."""
    repo_root = str(Path(__file__).resolve().parents[2])
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.main", "--transport", "stdio"],
        cwd=repo_root,
    )
    async with Client(params) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 15
        resources = await client.list_resources()
        assert any(str(r.uri) == "market://system/capabilities" for r in resources.resources)
