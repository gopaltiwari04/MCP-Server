"use client";

import { useEffect, useState } from "react";
import { ShieldAlert, PieChart, SlidersHorizontal, BookmarkPlus, BellPlus } from "lucide-react";
import { executeMcpTool } from "@/lib/api";
import type {
  PersonaId,
  PortfolioAnalysisData,
  RebalanceSimulationData,
} from "@/lib/types";

export function PortfolioPanel({ persona }: { persona: PersonaId }) {
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
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

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
    const res = await executeMcpTool<{ symbols: string[] }>(persona, "manage_watchlist", {
      action,
      watchlist_name: "Default",
      symbols: [sym],
    });
    if (res.is_error || !res.envelope?.data) {
      setActionFeedback(
        `${res.envelope?.error?.code ?? "ERROR"}: ${res.envelope?.error?.message ?? "Action rejected"}`
      );
    } else {
      setWatchlist(res.envelope.data.symbols);
      setActionFeedback(`Watchlist ${action} ${sym} succeeded.`);
    }
  }

  async function createQuickAlert() {
    setActionFeedback(null);
    const res = await executeMcpTool<{ alert_id: string }>(persona, "create_price_alert", {
      symbol: tradeSymbol,
      condition: "CROSSES_ABOVE",
      threshold_value: 200,
      note: "Triggered from Next.js Terminal",
    });
    if (res.is_error || !res.envelope?.data) {
      setActionFeedback(
        `${res.envelope?.error?.code ?? "ERROR"}: ${res.envelope?.error?.message ?? "Alert rejected"}`
      );
    } else {
      setActionFeedback(`Created alert ${res.envelope.data.alert_id} for ${tradeSymbol} > 200.`);
    }
  }

  useEffect(() => {
    void loadPortfolio();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona]);

  if (permError) {
    return (
      <div className="bg-amber-950/30 border border-amber-700/60 rounded-xl p-6 space-y-2">
        <div className="flex items-center gap-2 text-amber-300 font-semibold">
          <ShieldAlert className="h-5 w-5" />
          Zero-Trust Scope Enforcement Triggered
        </div>
        <p className="text-sm font-mono text-amber-200">{permError}</p>
        <p className="text-xs text-slate-300">
          Switch the Identity dropdown in the header back to <strong>Alice (Portfolio Manager)</strong> to
          inspect tenant-isolated portfolio holdings, VaR/CVaR risk metrics, and stateless rebalance
          simulations.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top KPI Cards */}
      {analysis && (
        <>
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-100">{analysis.portfolio_name}</h2>
              <p className="text-xs font-mono text-slate-400">
                ID: {analysis.portfolio_id} &bull; Cache: {cacheHit ? "HIT (user-scoped)" : "MISS"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadPortfolio()}
              className="text-xs px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
            >
              Re-query Portfolio
            </button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-6 gap-3 tabular-nums">
            {[
              ["Total NAV", `$${analysis.nav.toLocaleString()}`],
              ["Cash Balance", `$${analysis.cash_balance.toLocaleString()} (${analysis.cash_weight_pct}%)`],
              ["Portfolio Beta", String(analysis.portfolio_beta ?? "—")],
              ["Sharpe / Sortino", `${analysis.sharpe_ratio ?? "—"} / ${analysis.sortino_ratio ?? "—"}`],
              ["95% Hist VaR", `${analysis.historical_var_pct}%`],
              ["95% CVaR", `${analysis.expected_shortfall_cvar_pct}%`],
            ].map(([lbl, val]) => (
              <div key={lbl} className="bg-slate-900/70 border border-slate-800 rounded-xl p-3">
                <div className="text-[11px] text-slate-400">{lbl}</div>
                <div className="text-sm font-mono font-bold text-slate-100 mt-1">{val}</div>
              </div>
            ))}
          </div>

          {/* Holdings Table */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 overflow-x-auto">
            <div className="flex items-center gap-2 mb-3">
              <PieChart className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-slate-100">Holdings &amp; P&amp;L Attribution</h3>
            </div>
            <table className="w-full text-xs text-left tabular-nums">
              <thead className="text-[11px] uppercase text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2 pr-3">Symbol</th>
                  <th className="py-2 pr-3">Sector</th>
                  <th className="py-2 pr-3">Qty</th>
                  <th className="py-2 pr-3">Price</th>
                  <th className="py-2 pr-3">Market Value</th>
                  <th className="py-2 pr-3">Weight</th>
                  <th className="py-2">Unrealized P&amp;L</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70 font-mono">
                {analysis.positions.map((pos) => (
                  <tr key={pos.symbol}>
                    <td className="py-2 pr-3 font-bold text-emerald-300">{pos.symbol}</td>
                    <td className="py-2 pr-3 font-sans text-slate-300">{pos.sector}</td>
                    <td className="py-2 pr-3 text-slate-300">{pos.quantity}</td>
                    <td className="py-2 pr-3 text-slate-300">${pos.market_price.toFixed(2)}</td>
                    <td className="py-2 pr-3 text-slate-100">${pos.market_value.toLocaleString()}</td>
                    <td className="py-2 pr-3 text-slate-200">{pos.weight_pct.toFixed(2)}%</td>
                    <td
                      className={`py-2 ${
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

      {/* Simulator + Watchlist / Alert Controlled Writes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-slate-100">
              Stateless What-If Rebalance Simulator
            </h3>
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              value={tradeSide}
              onChange={(e) => setTradeSide(e.target.value as "BUY" | "SELL")}
              className="bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono"
            >
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
            <input
              type="text"
              value={tradeSymbol}
              onChange={(e) => setTradeSymbol(e.target.value.toUpperCase())}
              className="bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono w-24"
            />
            <input
              type="number"
              min={1}
              max={50}
              value={tradeWeightDelta}
              onChange={(e) => setTradeWeightDelta(Number(e.target.value))}
              className="bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono w-24"
            />
            <span className="self-center text-xs text-slate-400">% weight</span>
            <button
              type="button"
              onClick={() => void runSimulation()}
              className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-semibold"
            >
              Simulate Trade
            </button>
          </div>

          {simError && <p className="text-xs font-mono text-rose-400">{simError}</p>}

          {simulation && (
            <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3 space-y-2 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-slate-400">Cash Impact:</span>
                <span className={simulation.estimated_cash_impact >= 0 ? "text-emerald-400" : "text-amber-300"}>
                  ${simulation.estimated_cash_impact.toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Beta Shift:</span>
                <span>
                  {simulation.pre_trade.portfolio_beta} &rarr; {simulation.post_trade.portfolio_beta} (
                  {simulation.beta_shift})
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">VaR 95% Delta:</span>
                <span>
                  {simulation.pre_trade.var_95_pct}% &rarr; {simulation.post_trade.var_95_pct}% (
                  {simulation.var_delta_pct}%)
                </span>
              </div>
              {simulation.constraint_violations.map((v, idx) => (
                <div
                  key={`${v.rule_code}-${idx}`}
                  className="p-2 rounded bg-rose-950/50 border border-rose-700/60 text-rose-300"
                >
                  [{v.severity}] {v.rule_code}: {v.message}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Controlled Writes: Watchlist & Alert */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BookmarkPlus className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-slate-100">Watchlist &amp; Alert Actions</h3>
            </div>
            <button
              type="button"
              onClick={() => void createQuickAlert()}
              className="flex items-center gap-1 text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200"
            >
              <BellPlus className="h-3.5 w-3.5" />
              Alert {tradeSymbol} &gt; 200
            </button>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={wlSymbol}
              onChange={(e) => setWlSymbol(e.target.value.toUpperCase())}
              className="bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs font-mono w-28"
            />
            <button
              type="button"
              onClick={() => void mutateWatchlist("ADD", wlSymbol)}
              className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-semibold"
            >
              Add to Watchlist
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {watchlist.map((sym) => (
              <span
                key={sym}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200"
              >
                {sym}
                <button
                  type="button"
                  onClick={() => void mutateWatchlist("REMOVE", sym)}
                  className="text-slate-500 hover:text-rose-400"
                  title={`Remove ${sym}`}
                >
                  &times;
                </button>
              </span>
            ))}
          </div>
          {actionFeedback && <div className="text-xs font-mono text-emerald-300">{actionFeedback}</div>}
        </div>
      </div>
    </div>
  );
}
