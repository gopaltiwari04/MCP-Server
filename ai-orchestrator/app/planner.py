"""AI Orchestrator planner: optional OpenAI tool loop + deterministic MCP workflow engine."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import OrchestratorSettings
from app.mcp_bridge import MCPGatewayBridge, UserPersona

_KNOWN_TICKERS = ("NVDA", "AMD", "AAPL", "MSFT", "GOOGL", "AVGO", "TSM", "SPY", "QQQ", "AZN.L")
_PERIOD_TOKENS = ("5D", "1M", "3M", "6M", "YTD", "1Y", "3Y")


def _extract_tickers(prompt: str) -> list[str]:
    upper = prompt.upper()
    found = [t for t in _KNOWN_TICKERS if re.search(rf"(?<![A-Z0-9.]){re.escape(t)}(?![A-Z0-9.])", upper)]
    if not found:
        # Fallback regex for any uppercase ticker symbols user might type
        candidates = re.findall(r"\b[A-Z]{2,5}(?:\.[A-Z]{1,2})?\b", prompt)
        ignore = {"MCP", "API", "VAR", "CVAR", "RSI", "MACD", "SMA", "EMA", "USD", "TTM", "ETF", "YTD", "BUY", "SELL"}
        found = [c for c in candidates if c not in ignore]
    return list(dict.fromkeys(found))[:6]


def _extract_period(prompt: str) -> str:
    upper = prompt.upper()
    for p in _PERIOD_TOKENS:
        if re.search(rf"\b{p}\b", upper):
            return p
    if "30 DAY" in upper or "MONTH" in upper:
        return "1M"
    if "YEAR" in upper:
        return "1Y"
    return "1M"


def _collect_citations(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations = []
    for t in traces:
        env = t.get("envelope") or {}
        meta = env.get("metadata") or {}
        if meta:
            citations.append(
                {
                    "tool": t["tool_name"],
                    "status": env.get("status"),
                    "source": meta.get("source"),
                    "data_timestamp": meta.get("data_timestamp"),
                    "cache_hit": meta.get("cache_hit"),
                    "is_stale": meta.get("is_stale"),
                    "request_id": meta.get("request_id"),
                }
            )
    return citations


async def _run_openai_agent(
    *,
    prompt: str,
    persona: UserPersona,
    bridge: MCPGatewayBridge,
    settings: OrchestratorSettings,
    request_id: str,
) -> dict[str, Any]:
    assert settings.openai_api_key is not None
    catalog = await bridge.list_catalog(persona, request_id=request_id)
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": (t["description"] or "")[:1000],
                "parameters": t["input_schema"],
            },
        }
        for t in catalog["tools"]
    ]
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are an institutional quantitative analyst. Always use the provided MCP tools for "
                "prices, fundamentals, indicators, comparisons, and portfolio analytics. Never invent numbers. "
                "Cite exact data_timestamp and request_id values in a Data Provenance Footer."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    traces: list[dict[str, Any]] = []
    headers = {"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"}
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=45.0) as client:
        for _ in range(6):
            resp = await client.post(
                url,
                headers=headers,
                json={"model": settings.openai_model, "messages": messages, "tools": openai_tools},
            )
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            messages.append(msg)
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return {
                    "mode": "llm_agent",
                    "model": settings.openai_model,
                    "assistant_markdown": msg.get("content") or "",
                    "tool_traces": traces,
                    "provenance": _collect_citations(traces),
                }
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"] or "{}")
                trace = await bridge.call_tool(persona, fn_name, fn_args, request_id=request_id)
                traces.append(trace)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(trace["envelope"] or {"markdown": trace["markdown"]}),
                    }
                )

    return {
        "mode": "llm_agent",
        "model": settings.openai_model,
        "assistant_markdown": "Reached maximum tool-calling iterations.",
        "tool_traces": traces,
        "provenance": _collect_citations(traces),
    }


async def run_orchestrated_chat(
    *,
    prompt: str,
    persona: UserPersona,
    bridge: MCPGatewayBridge,
    settings: OrchestratorSettings,
    request_id: str,
) -> dict[str, Any]:
    if settings.openai_api_key and settings.openai_api_key.get_secret_value().strip():
        return await _run_openai_agent(
            prompt=prompt,
            persona=persona,
            bridge=bridge,
            settings=settings,
            request_id=request_id,
        )

    lower = prompt.lower()
    tickers = _extract_tickers(prompt)
    period = _extract_period(prompt)
    traces: list[dict[str, Any]] = []

    # Intent 1: Portfolio tail risk audit / rebalance simulation
    if any(k in lower for k in ("portfolio", "var", "cvar", "rebalance", "tail risk", "concentration")):
        port_trace = await bridge.call_tool(
            persona,
            "analyse_portfolio",
            {"portfolio_id": "port_123", "benchmark_symbol": "SPY", "confidence_level": 0.95},
            request_id=request_id,
        )
        traces.append(port_trace)
        if port_trace["is_error"]:
            err = (port_trace.get("envelope") or {}).get("error") or {}
            return {
                "mode": "deterministic_mcp_planner",
                "assistant_markdown": (
                    f"### Access Denied (`{err.get('code', 'ERROR')}`)\n\n"
                    f"Active persona **{persona.display_name}** lacks required permissions: `{err.get('message')}`."
                ),
                "tool_traces": traces,
                "provenance": _collect_citations(traces),
            }

        sim_sym = tickers[0] if tickers else "NVDA"
        sim_trace = await bridge.call_tool(
            persona,
            "simulate_portfolio_rebalance",
            {
                "portfolio_id": "port_123",
                "proposed_trades": [{"symbol": sim_sym, "side": "BUY", "weight_delta_pct": 6.0}],
                "benchmark_symbol": "SPY",
            },
            request_id=request_id,
        )
        traces.append(sim_trace)
        p_data = port_trace["envelope"]["data"]
        s_data = (sim_trace.get("envelope") or {}).get("data") or {}
        md = (
            f"### Institutional Portfolio Audit (`port_123`) — {p_data.get('portfolio_name')}\n\n"
            f"- **NAV:** ${p_data['nav']:,.2f} | **Cash:** ${p_data['cash_balance']:,.2f} ({p_data['cash_weight_pct']:.2f}%)\n"
            f"- **Beta:** {p_data['portfolio_beta']} | **Ann. Vol:** {p_data['annualized_volatility_pct']}% | "
            f"**Sharpe:** {p_data['sharpe_ratio']}\n"
            f"- **95% Historical VaR:** {p_data['historical_var_pct']}% (${p_data['historical_var_amount']:,.2f}) | "
            f"**95% CVaR:** {p_data['expected_shortfall_cvar_pct']}%\n\n"
            f"{port_trace.get('markdown') or ''}\n\n"
            f"#### What-If Simulation (+6% `{sim_sym}`)\n"
            f"- **Cash Impact:** ${s_data.get('estimated_cash_impact', 0):+,.2f} | "
            f"**Beta Shift:** {s_data.get('beta_shift')} | **VaR Delta:** {s_data.get('var_delta_pct')}%\n"
            f"- **Violations Flagged:** {len(s_data.get('constraint_violations', []))}"
        )
        return {
            "mode": "deterministic_mcp_planner",
            "assistant_markdown": md,
            "tool_traces": traces,
            "provenance": _collect_citations(traces),
        }

    # Intent 2: Multi-stock comparison (2+ tickers or "compare" / "vs")
    if len(tickers) >= 2 or "compare" in lower or " vs " in lower:
        pair = tickers[:5] if len(tickers) >= 2 else ["NVDA", "AMD"]
        end_d = datetime.now(UTC).date()
        start_d = end_d - timedelta(days=35)
        tasks = [
            bridge.call_tool(persona, "compare_instruments", {"symbols": pair, "period": period}, request_id=request_id),
            *(
                bridge.call_tool(
                    persona,
                    "calculate_technical_indicators",
                    {"symbol": s, "indicators": ["RSI_14", "MACD", "SMA_50"]},
                    request_id=request_id,
                )
                for s in pair[:2]
            ),
            bridge.call_tool(
                persona,
                "get_historical_prices",
                {
                    "symbol": pair[0],
                    "start_date": start_d.isoformat(),
                    "end_date": end_d.isoformat(),
                    "interval": "1d",
                },
                request_id=request_id,
            ),
        ]
        traces = list(await asyncio.gather(*tasks))
        cmp_trace = traces[0]
        cmp_data = (cmp_trace.get("envelope") or {}).get("data") or {}
        corr = cmp_data.get("correlation_matrix") or {}
        rankings = cmp_data.get("rankings") or []
        rank_lines = "\n".join(
            f"- **{r['metric']} Ranking:** {' > '.join(r['ordered_symbols'])}" for r in rankings
        )
        corr_val = corr.get(pair[0], {}).get(pair[1]) if len(pair) >= 2 else None
        md = (
            f"### Multi-Asset Quantitative Comparison: `{' vs '.join(pair)}` ({period})\n\n"
            f"{cmp_trace.get('markdown') or ''}\n\n"
            f"{rank_lines}\n"
            + (f"- **Pairwise Return Correlation ({pair[0]}/{pair[1]}):** `{corr_val}`\n" if corr_val is not None else "")
        )
        return {
            "mode": "deterministic_mcp_planner",
            "assistant_markdown": md,
            "tool_traces": traces,
            "provenance": _collect_citations(traces),
        }

    # Intent 3: Single-stock institutional tearsheet / quote / technicals / earnings
    sym = tickers[0] if tickers else "NVDA"
    calls = [
        bridge.call_tool(persona, "get_company_profile", {"symbol": sym}, request_id=request_id),
        bridge.call_tool(persona, "get_market_quote", {"symbol": sym}, request_id=request_id),
        bridge.call_tool(persona, "get_financial_metrics", {"symbol": sym, "period": "TTM", "limit": 2}, request_id=request_id),
        bridge.call_tool(persona, "calculate_returns", {"symbol": sym, "period": period, "benchmark_symbol": "SPY"}, request_id=request_id),
        bridge.call_tool(
            persona,
            "calculate_technical_indicators",
            {"symbol": sym, "indicators": ["RSI_14", "MACD", "SMA_50", "SMA_200"]},
            request_id=request_id,
        ),
    ]
    traces = list(await asyncio.gather(*calls))
    q_data = (traces[1].get("envelope") or {}).get("data")
    if traces[1]["is_error"] or not q_data:
        err = (traces[1].get("envelope") or {}).get("error") or {}
        return {
            "mode": "deterministic_mcp_planner",
            "assistant_markdown": f"### Error Querying `{sym}` (`{err.get('code', 'ERROR')}`)\n\n{err.get('message')}",
            "tool_traces": traces,
            "provenance": _collect_citations(traces),
        }

    p_data = traces[0]["envelope"]["data"]
    r_data = traces[3]["envelope"]["data"]
    md = (
        f"### Equity Tearsheet: {p_data['legal_name']} (`{sym}`) — {period}\n\n"
        f"- **Sector / Industry:** {p_data.get('sector')} / {p_data.get('industry')}\n"
        f"- **Last Price:** {q_data['last_price']:,.2f} {q_data['currency']} ({q_data.get('change_pct', 0):+.2f}%)\n"
        f"- **Period Return / Sharpe vs SPY:** `{r_data['cumulative_return_pct']:+.2f}%` | "
        f"Sharpe `{r_data['sharpe_ratio']}` | Beta `{r_data.get('beta')}` | Max DD `{r_data['max_drawdown_pct']:.2f}%`\n\n"
        f"#### Valuation & Profitability\n{traces[2].get('markdown') or ''}\n\n"
        f"#### Technical Regime\n{traces[4].get('markdown') or ''}"
    )
    return {
        "mode": "deterministic_mcp_planner",
        "assistant_markdown": md,
        "tool_traces": traces,
        "provenance": _collect_citations(traces),
    }
