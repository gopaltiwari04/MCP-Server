"use client";

import { useEffect, useState } from "react";
import {
  ShieldAlert,
  PieChart,
  SlidersHorizontal,
  BookmarkPlus,
  BellPlus,
  RefreshCw,
  ArrowRight,
  Lock,
} from "lucide-react";
import { executeMcpTool } from "@/lib/api";
import type {
  PersonaId,
  PortfolioAnalysisData,
  RebalanceSimulationData,
} from "@/lib/types";

const SECTOR_COLORS = [
  "bg-amber-400",
  "bg-sky-400",
  "bg-emerald-400",
  "bg-indigo-400",
  "bg-rose-400",
  "bg-zinc-400",
];

export function PortfolioPanel({
  persona,
  onSwitchPersona,
}: {
  persona: PersonaId;
  onSwitchPersona?: (p: PersonaId) => void;
}) {
  const [analysis, setAnalysis] = useState<PortfolioAnalysisData | null>(null);
  const [cacheHit, setCacheHit] = useState(false);
  const [permError, setPermError] = useState<string | null>(null);

  const [tradeSymbol, setTradeSymbol] = useState("NVDA");
  const [tradeSide, setTradeSide] = useState<"BUY" | "SELL">("BUY");
  const [tradeWeightDelta, setTradeWeightDelta] = useState(10);
  const [simulation, setSimulation] = useState<RebalanceSimulationData | null>(null);
  const [simError, setSimError] = useState<string | null>(null);

  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [wlSymbol, setWlSymbol] = useState("TSM");
  const [alertCondition, setAlertCondition] = useState<"CROSSES_ABOVE" | "CROSSES_BELOW">("CROSSES_ABOVE");
  const [alertThreshold, setAlertThreshold] = useState(200);
  const [actionFeedback, setActionFeedback] = useState<{ ok: boolean; msg: string } | null>(null);

  async function loadPortfolio() {
    setPermError(null);
    setSimulation(null);
    const res = await executeMcpTool<PortfolioAnalysisData>(persona, "analyse_portfolio", {
      portfolio_id: "port_123",
      benchmark_symbol: "SPY",
      confidence_level: 0.95,
    });
    if (res.is_error || !res.envelope?.data) {
      setAnalysis(null);
      setPermError(
        `${res.envelope?.error?.code ?? "ERROR"}: ${res.envelope?.error?.message ?? "Access denied"}`
      );
    } else {
      setAnalysis(res.envelope.data);
      setCacheHit(res.envelope.metadata.cache_hit);
    }

    const wlRes = await executeMcpTool<{ symbols: string[] }>(persona, "manage_watchlist", {
      action: "LIST",
      watchlist_name: "Default",
    });
    if (!wlRes.is_error && wlRes.envelope?.data) {
      setWatchlist(wlRes.envelope.data.symbols);
    } else {
      setWatchlist([]);
    }
  }

  async function runSimulation() {
    setSimError(null);
    const res = await executeMcpTool<RebalanceSimulationData>(persona, "simulate_portfolio_rebalance", {
      portfolio_id: "port_123",
      proposed_trades: [{ symbol: tradeSymbol, side: tradeSide, weight_delta_pct: tradeWeightDelta }],
      benchmark_symbol: "SPY",
    });
    if (res.is_error || !res.envelope?.data) {
      setSimulation(null);
      setSimError(
        `${res.envelope?.error?.code ?? "ERROR"}: ${res.envelope?.error?.message ?? "Simulation failed"}`
      );
    } else {
      setSimulation(res.envelope.data);
    }
  }

  async function mutateWatchlist(action: "ADD" | "REMOVE", sym: string) {
    setActionFeedback(null);
    const clean = sym.trim().toUpperCase();
    if (!clean) return;
    const res = await executeMcpTool<{ symbols: string[] }>(persona, "manage_watchlist", {
      action,
      watchlist_name: "Default",
      symbols: [clean],
    });
    if (res.is_error || !res.envelope?.data) {
      setActionFeedback({
        ok: false,
        msg: `${res.envelope?.error?.code ?? "ERROR"}: ${res.envelope?.error?.message ?? "Action rejected"}`,
      });
    } else {
      setWatchlist(res.envelope.data.symbols);
      setActionFeedback({ ok: true, msg: `Watchlist ${action} ${clean} committed & cache invalidated.` });
    }
  }

  async function createQuickAlert() {
    setActionFeedback(null);
    const res = await executeMcpTool<{ alert_id: string }>(persona, "create_price_alert", {
      symbol: tradeSymbol,
      condition: alertCondition,
      threshold_value: alertThreshold,
      note: "Configured via QuantMCP Terminal",
    });
    if (res.is_error || !res.envelope?.data) {
      setActionFeedback({
        ok: false,
        msg: `${res.envelope?.error?.code ?? "ERROR"}: ${res.envelope?.error?.message ?? "Alert rejected"}`,
      });
    } else {
      setActionFeedback({
        ok: true,
        msg: `Alert ${res.envelope.data.alert_id}: ${tradeSymbol} ${alertCondition} ${alertThreshold}`,
      });
    }
  }

  useEffect(() => {
    void loadPortfolio();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona]);

  if (permError) {
    return (
      <div className="border border-amber-500/40 bg-[#0e1015] rounded-md p-6 max-w-2xl space-y-4">
        <div className="flex items-start gap-3">
          <div className="h-9 w-9 rounded bg-amber-500/15 border border-amber-500/40 flex items-center justify-center text-amber-400 shrink-0">
            <Lock className="h-4 w-4" />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-mono uppercase tracking-wider text-amber-400">
              Zero-Trust Scope Gate // Fail-Closed
            </div>
            <h2 className="text-base font-semibold text-zinc-100">
              Portfolio &amp; Simulation Access Restricted for Principal `{persona}`
            </h2>
          </div>
        </div>

        <div className="bg-[#080a0e] border border-[#232836] rounded p-3 font-mono text-xs text-rose-300">
          {permError}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px] font-mono">
          <div className="bg-[#090b0f] border border-[#1d222e] rounded p-3">
            <div className="text-zinc-500">REQUIRED SCOPES</div>
            <div className="text-zinc-200 mt-1">portfolio:read · simulation:execute</div>
          </div>
          <div className="bg-[#090b0f] border border-[#1d222e] rounded p-3">
            <div className="text-zinc-500">ACTIVE CALLER SCOPES</div>
            <div className="text-amber-300 mt-1">market:read</div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <span className="text-xs text-zinc-400 flex items-center gap-1.5">
            <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
            JWT scopes are extracted solely from server-verified `ContextVar`, never tool parameters.
          </span>
          {onSwitchPersona && (
            <button
              type="button"
              onClick={() => onSwitchPersona("alice")}
              className="px-3.5 py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-[#08090c] text-xs font-mono font-semibold uppercase"
            >
              Switch to Alice (PM)
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {analysis && (
        <>
          {/* Header & KPI Strip */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-zinc-100">{analysis.portfolio_name}</h2>
                <span className="text-[10.5px] font-mono px-2 py-0.5 rounded bg-[#141720] border border-[#252a38] text-amber-300">
                  {analysis.portfolio_id}
                </span>
                <span className="text-[10.5px] font-mono px-2 py-0.5 rounded bg-[#0d0f14] border border-[#1e222d] text-zinc-400">
                  {cacheHit ? "USER CACHE HIT (15s TTL)" : "LIVE COMPUTATION"}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void loadPortfolio()}
              className="inline-flex items-center gap-1.5 text-[11px] font-mono px-3 py-1.5 rounded bg-[#11141c] hover:bg-[#181c26] text-zinc-200 border border-[#242936]"
            >
              <RefreshCw className="h-3 w-3" />
              Re-query Portfolio
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 tabular-nums">
            {[
              ["Total NAV", `$${analysis.nav.toLocaleString()}`, "text-zinc-100"],
              [
                "Cash Balance",
                `$${analysis.cash_balance.toLocaleString()} (${analysis.cash_weight_pct}%)`,
                "text-zinc-200",
              ],
              ["Portfolio Beta", String(analysis.portfolio_beta ?? "—"), "text-amber-300"],
              [
                "Sharpe / Sortino",
                `${analysis.sharpe_ratio ?? "—"} / ${analysis.sortino_ratio ?? "—"}`,
                "text-emerald-400",
              ],
              ["95% Hist VaR", `${analysis.historical_var_pct}%`, "text-rose-400"],
              ["95% CVaR (ES)", `${analysis.expected_shortfall_cvar_pct}%`, "text-rose-400"],
            ].map(([lbl, val, colorCls]) => (
              <div key={lbl} className="border border-[#1e222d] bg-[#0d0f14] rounded-md p-3">
                <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500">{lbl}</div>
                <div className={`text-sm font-mono font-bold mt-1 ${colorCls}`}>{val}</div>
              </div>
            ))}
          </div>

          {/* Sector Allocation + Concentration Monitor */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            <div className="lg:col-span-7 border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-[#191d27] pb-2">
                <div className="flex items-center gap-2">
                  <PieChart className="h-3.5 w-3.5 text-amber-400" />
                  <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                    Sector Allocation
                  </h3>
                </div>
                <span className="text-[10.5px] font-mono text-zinc-500">{analysis.base_currency} NAV Basis</span>
              </div>

              {/* Stacked Horizontal Bar */}
              <div className="h-3 w-full rounded bg-[#141720] overflow-hidden flex">
                {analysis.sector_allocation.map((sec, idx) => (
                  <div
                    key={sec.category}
                    className={`${SECTOR_COLORS[idx % SECTOR_COLORS.length]} border-r border-[#08090c]`}
                    style={{ width: `${Math.max(2, sec.weight_pct)}%` }}
                    title={`${sec.category}: ${sec.weight_pct.toFixed(1)}%`}
                  />
                ))}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono tabular-nums">
                {analysis.sector_allocation.map((sec, idx) => (
                  <div
                    key={sec.category}
                    className="flex items-center justify-between px-2.5 py-1.5 rounded bg-[#090b0f] border border-[#1a1e29]"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className={`h-2 w-2 rounded-sm shrink-0 ${
                          SECTOR_COLORS[idx % SECTOR_COLORS.length]
                        }`}
                      />
                      <span className="font-sans text-zinc-300 truncate">{sec.category}</span>
                    </div>
                    <div className="text-zinc-200 shrink-0 ml-2">
                      {sec.weight_pct.toFixed(1)}%{" "}
                      <span className="text-zinc-500">(${Math.round(sec.market_value).toLocaleString()})</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Single-Position Concentration vs 25% Policy Limit */}
            <div className="lg:col-span-5 border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-[#191d27] pb-2">
                <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                  Concentration Risk Monitor
                </h3>
                <span className="text-[10px] font-mono text-amber-300">MAX CAP 25.0%</span>
              </div>

              <div className="space-y-2.5 tabular-nums">
                {analysis.top_concentration_contributors.map((item) => {
                  const overCap = item.weight_pct > 25;
                  return (
                    <div key={item.symbol} className="space-y-1 text-xs font-mono">
                      <div className="flex justify-between">
                        <span className="font-semibold text-zinc-200">{item.symbol}</span>
                        <span className={overCap ? "text-rose-400 font-semibold" : "text-zinc-300"}>
                          {item.weight_pct.toFixed(2)}%
                          {overCap ? " [BREACH]" : ""}
                        </span>
                      </div>
                      <div className="h-2 bg-[#141720] rounded relative overflow-hidden">
                        {/* 25% policy line (scaled to 50% chart max) */}
                        <div
                          className="absolute top-0 bottom-0 w-px bg-amber-400/70 z-10"
                          style={{ left: "50%" }}
                          title="25% Concentration Ceiling"
                        />
                        <div
                          className={`h-full rounded ${overCap ? "bg-rose-500" : "bg-amber-400/80"}`}
                          style={{ width: `${Math.min(100, item.weight_pct * 2)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Holdings & P&L Attribution Table */}
          <div className="border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 overflow-x-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                Holdings &amp; P&amp;L Attribution
              </h3>
              <span className="text-[11px] font-mono text-zinc-500">
                {analysis.positions.length} Active Positions
              </span>
            </div>
            <table className="w-full text-xs text-left tabular-nums border-collapse">
              <thead className="text-[10.5px] font-mono uppercase text-zinc-400 border-b border-[#222736] bg-[#11141c]">
                <tr>
                  <th className="py-2 px-3">Symbol</th>
                  <th className="py-2 px-3">Sector</th>
                  <th className="py-2 px-3 text-right">Qty</th>
                  <th className="py-2 px-3 text-right">Last Price</th>
                  <th className="py-2 px-3 text-right">Market Value</th>
                  <th className="py-2 px-3 text-right">Weight</th>
                  <th className="py-2 px-3 text-right">Unrealized P&amp;L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#181c26] font-mono">
                {analysis.positions.map((pos) => (
                  <tr key={pos.symbol} className="hover:bg-[#141824] transition-colors">
                    <td className="py-2 px-3 font-bold text-amber-300">{pos.symbol}</td>
                    <td className="py-2 px-3 font-sans text-zinc-300">{pos.sector}</td>
                    <td className="py-2 px-3 text-right text-zinc-300">{pos.quantity}</td>
                    <td className="py-2 px-3 text-right text-zinc-300">${pos.market_price.toFixed(2)}</td>
                    <td className="py-2 px-3 text-right text-zinc-100">
                      ${pos.market_value.toLocaleString()}
                    </td>
                    <td className="py-2 px-3 text-right text-zinc-200">{pos.weight_pct.toFixed(2)}%</td>
                    <td
                      className={`py-2 px-3 text-right ${
                        (pos.unrealized_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      ${pos.unrealized_pnl?.toLocaleString()} ({pos.unrealized_pnl_pct?.toFixed(2)}%)
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Simulator + Controlled Writes */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <div className="lg:col-span-7 border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-3.5">
          <div className="flex items-center justify-between border-b border-[#191d27] pb-2.5">
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="h-3.5 w-3.5 text-amber-400" />
              <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                Stateless What-If Rebalance Simulator
              </h3>
            </div>
            <span className="text-[10px] font-mono text-zinc-500">SCOPE: simulation:execute</span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={tradeSide}
              onChange={(e) => setTradeSide(e.target.value as "BUY" | "SELL")}
              className="bg-[#090b0f] border border-[#242936] rounded px-2.5 py-1.5 text-xs font-mono text-zinc-100"
            >
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
            <input
              type="text"
              value={tradeSymbol}
              onChange={(e) => setTradeSymbol(e.target.value.toUpperCase())}
              className="bg-[#090b0f] border border-[#242936] rounded px-2.5 py-1.5 text-xs font-mono text-zinc-100 w-24 uppercase"
            />
            <input
              type="number"
              min={1}
              max={50}
              value={tradeWeightDelta}
              onChange={(e) => setTradeWeightDelta(Number(e.target.value))}
              className="bg-[#090b0f] border border-[#242936] rounded px-2.5 py-1.5 text-xs font-mono text-zinc-100 w-20"
            />
            <span className="text-xs font-mono text-zinc-500">% weight</span>
            <button
              type="button"
              onClick={() => void runSimulation()}
              className="px-3.5 py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-[#08090c] text-xs font-mono font-semibold uppercase"
            >
              Simulate Trade
            </button>
          </div>

          {simError && <p className="text-xs font-mono text-rose-400">{simError}</p>}

          {simulation && (
            <div className="space-y-3">
              {/* Pre vs Post Delta Table */}
              <div className="grid grid-cols-3 gap-2 bg-[#090b0f] border border-[#1a1e29] rounded p-3 text-[11px] font-mono tabular-nums">
                <div>
                  <div className="text-zinc-500 text-[10px]">CASH IMPACT</div>
                  <div
                    className={`font-semibold mt-0.5 ${
                      simulation.estimated_cash_impact >= 0 ? "text-emerald-400" : "text-amber-300"
                    }`}
                  >
                    ${simulation.estimated_cash_impact.toLocaleString()}
                  </div>
                </div>
                <div>
                  <div className="text-zinc-500 text-[10px]">BETA SHIFT</div>
                  <div className="text-zinc-200 mt-0.5 inline-flex items-center gap-1">
                    {simulation.pre_trade.portfolio_beta}
                    <ArrowRight className="h-3 w-3 text-zinc-500" />
                    <strong className="text-amber-300">{simulation.post_trade.portfolio_beta}</strong>
                  </div>
                </div>
                <div>
                  <div className="text-zinc-500 text-[10px]">95% VAR DELTA</div>
                  <div className="text-zinc-200 mt-0.5 inline-flex items-center gap-1">
                    {simulation.pre_trade.var_95_pct}%
                    <ArrowRight className="h-3 w-3 text-zinc-500" />
                    <strong className="text-rose-300">{simulation.post_trade.var_95_pct}%</strong>
                  </div>
                </div>
              </div>

              {/* Post-Trade Weights */}
              <div className="bg-[#090b0f] border border-[#1a1e29] rounded p-3 space-y-1.5">
                <div className="text-[10px] font-mono uppercase text-zinc-500">
                  Projected Post-Trade Allocation
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px] font-mono tabular-nums">
                  {Object.entries(simulation.post_trade.position_weights_pct).map(([sym, wt]) => (
                    <div
                      key={sym}
                      className={`flex justify-between px-2 py-1 rounded border ${
                        wt > 25
                          ? "bg-rose-950/30 border-rose-500/40 text-rose-300"
                          : "bg-[#11141c] border-[#1f2431] text-zinc-300"
                      }`}
                    >
                      <span>{sym}</span>
                      <span>{wt.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>

              {simulation.constraint_violations.map((v, idx) => (
                <div
                  key={`${v.rule_code}-${idx}`}
                  className="p-2.5 rounded bg-rose-950/35 border border-rose-700/60 text-xs font-mono text-rose-300"
                >
                  [{v.severity}] {v.rule_code}: {v.message}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Controlled Writes: Watchlist & Custom Alert */}
        <div className="lg:col-span-5 border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-4">
          <div className="flex items-center justify-between border-b border-[#191d27] pb-2.5">
            <div className="flex items-center gap-2">
              <BookmarkPlus className="h-3.5 w-3.5 text-amber-400" />
              <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                Controlled Workspace Actions
              </h3>
            </div>
            <span className="text-[10px] font-mono text-zinc-500">SCOPE: portfolio:write</span>
          </div>

          {/* Watchlist Mutation */}
          <div className="space-y-2">
            <div className="text-[10px] font-mono uppercase text-zinc-500">Default Watchlist</div>
            <div className="flex gap-2">
              <input
                type="text"
                value={wlSymbol}
                onChange={(e) => setWlSymbol(e.target.value.toUpperCase())}
                className="bg-[#090b0f] border border-[#242936] rounded px-2.5 py-1.5 text-xs font-mono text-zinc-100 w-28 uppercase"
              />
              <button
                type="button"
                onClick={() => void mutateWatchlist("ADD", wlSymbol)}
                className="px-3 py-1.5 rounded bg-[#161a24] hover:bg-[#1f2433] border border-[#2d3344] text-amber-300 text-xs font-mono font-semibold"
              >
                + Add Symbol
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {watchlist.map((sym) => (
                <span
                  key={sym}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#090b0f] border border-[#202532] text-xs font-mono text-zinc-200"
                >
                  {sym}
                  <button
                    type="button"
                    onClick={() => void mutateWatchlist("REMOVE", sym)}
                    className="text-zinc-500 hover:text-rose-400"
                    title={`Remove ${sym}`}
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
          </div>

          {/* Custom Price Alert */}
          <div className="pt-3 border-t border-[#191d27] space-y-2">
            <div className="text-[10px] font-mono uppercase text-zinc-500">Price Alert Trigger</div>
            <div className="flex flex-wrap gap-2">
              <select
                value={alertCondition}
                onChange={(e) => setAlertCondition(e.target.value as typeof alertCondition)}
                className="bg-[#090b0f] border border-[#242936] rounded px-2 py-1.5 text-xs font-mono text-zinc-100"
              >
                <option value="CROSSES_ABOVE">ABOVE</option>
                <option value="CROSSES_BELOW">BELOW</option>
              </select>
              <input
                type="number"
                min={1}
                step="0.5"
                value={alertThreshold}
                onChange={(e) => setAlertThreshold(Number(e.target.value))}
                className="bg-[#090b0f] border border-[#242936] rounded px-2.5 py-1.5 text-xs font-mono text-zinc-100 w-24"
              />
              <button
                type="button"
                onClick={() => void createQuickAlert()}
                className="inline-flex items-center gap-1.5 text-xs font-mono px-3 py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-[#08090c] font-semibold"
              >
                <BellPlus className="h-3.5 w-3.5" />
                Set {tradeSymbol} Alert
              </button>
            </div>
          </div>

          {actionFeedback && (
            <div
              className={`text-xs font-mono p-2.5 rounded border ${
                actionFeedback.ok
                  ? "bg-emerald-950/25 border-emerald-500/30 text-emerald-300"
                  : "bg-rose-950/30 border-rose-500/40 text-rose-300"
              }`}
            >
              {actionFeedback.msg}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
