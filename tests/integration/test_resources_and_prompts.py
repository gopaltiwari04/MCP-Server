"""Integration tests for MCP static/dynamic resources, prompts, completions, and subscriptions."""

import asyncio
import json

import pytest
from mcp import Client
from mcp.types import PromptReference

from app.server import create_mcp_server


@pytest.mark.asyncio
async def test_resources_templates_and_prompts_discovery_and_execution(mcp_server) -> None:
    async with Client(mcp_server) as mcp_client:
        await _run_resources_and_prompts(mcp_client)


async def _run_resources_and_prompts(mcp_client: Client) -> None:
    res_list = await mcp_client.list_resources()
    uris = {str(r.uri) for r in res_list.resources}
    assert {"market://system/capabilities", "market://system/glossary"}.issubset(uris)

    tpl_list = await mcp_client.list_resource_templates()
    tpl_uris = {t.uri_template for t in tpl_list.resource_templates}
    assert {
        "market://instrument/{symbol}/snapshot",
        "portfolio://user/{portfolio_id}/summary",
    }.issubset(tpl_uris)

    # Read static resources
    cap_res = await mcp_client.read_resource("market://system/capabilities")
    cap_json = json.loads(cap_res.contents[0].text)
    assert cap_json["max_historical_bars_per_call"] == 500
    assert "RSI_14" in cap_json["supported_technical_indicators"]

    glossary_res = await mcp_client.read_resource("market://system/glossary")
    glossary_json = json.loads(glossary_res.contents[0].text)
    assert "SharpeRatio" in glossary_json and "ExpectedShortfallCVaR" in glossary_json

    # Read dynamic template resources
    snap_res = await mcp_client.read_resource("market://instrument/nvda/snapshot")
    assert "NVIDIA Corporation" in snap_res.contents[0].text
    assert "148.5" in snap_res.contents[0].text

    port_res = await mcp_client.read_resource("portfolio://user/port_123/summary")
    assert "user_alice" in port_res.contents[0].text
    assert "1250000" in port_res.contents[0].text

    # Prompts & completions
    prompt_list = await mcp_client.list_prompts()
    prompt_names = {p.name for p in prompt_list.prompts}
    assert {
        "institutional_equity_tearsheet",
        "multi_stock_relative_value_comparison",
        "pairs_trading_screen",
        "portfolio_tail_risk_audit",
    }.issubset(prompt_names)

    rendered = await mcp_client.get_prompt(
        "institutional_equity_tearsheet",
        {"symbol": "nvda", "benchmark": "qqq"},
    )
    prompt_text = rendered.messages[0].content.text
    assert "NVDA" in prompt_text and "QQQ" in prompt_text
    assert "Data Provenance Footer" in prompt_text

    comp = await mcp_client.complete(
        PromptReference(type="ref/prompt", name="institutional_equity_tearsheet"),
        {"name": "benchmark", "value": "SP"},
    )
    assert "SPY" in comp.completion.values


@pytest.mark.asyncio
async def test_resource_subscription_notifications_on_watchlist_mutation(
    test_settings,
    respx_backend,
    bind_full_security_context,
) -> None:
    """Verify subscriptions/listen stream receives ResourceUpdated when manage_watchlist mutates state."""
    from mcp import Client
    from mcp.client.subscriptions import ResourceUpdated

    server = create_mcp_server(test_settings)
    received_uris: list[str] = []

    async with Client(server) as client:
        async with client.listen(resource_subscriptions=["portfolio://user/default/summary"]) as sub:
            assert sub.honored.resource_subscriptions == ["portfolio://user/default/summary"]

            async def consume() -> None:
                async for event in sub:
                    if isinstance(event, ResourceUpdated):
                        received_uris.append(event.uri)
                        break

            consumer = asyncio.create_task(consume())
            await client.call_tool(
                "manage_watchlist",
                {"action": "ADD", "watchlist_name": "Default", "symbols": ["NVDA"]},
            )
            await asyncio.wait_for(consumer, timeout=3.0)

    assert received_uris == ["portfolio://user/default/summary"]
