"use client";

import { useEffect, useState } from "react";
import { Search, TrendingUp, BarChart3, GitCompareArrows } from "lucide-react";
import { executeMcpTool } from "@/lib/api";
import type {
  CompareInstrumentsData,
  HistoricalPricesData,
  PersonaId,
  QuoteData,
  TechnicalIndicatorsData,
} from "@/lib/types";

const QUICK_SYMBOLS = ["NVDA", "AMD", "AAPL", "MSFT", "GOOGL", "AVGO", "TSM", "SPY", "AZN.L"];

function PriceSparkChart({ bars }: { bars: HistoricalPricesData["bars"] }) {
  if (!bars.length) return null;
  const closes = bars.map((b) => b.close);
  const minP = Math.min(...closes);
  const maxP = Math.max(...closes);
  const span = maxP - minP || 1;
  const width = 680;
  const height = 180;
  const pad = 16;

  const points = bars
    .map((b, i) => {
      const x = pad + (i / Math.max(1, bars.length - 1)) * (width - pad * 2);
      const y = height - pad - ((b.close - minP) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const isUp = closes[closes.length - 1] >= closes[0];
  const stroke = isUp ? "#34d399" : "#fb7185";

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-44 bg-slate-950/60 rounded-lg border border-slate-800/80">
      <polyline fill="none" stroke={stroke} strokeWidth="2.5" points={points} />
    </svg>
  );
}

export function MarketWorkbench({ persona }: { persona: PersonaId }) {
  const [symbol, setSymbol] = useState("NVDA");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ symbol: string; name: string; primary_exchange: string }>>([]);

  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [quoteMeta, setQuoteMeta] = useState<{ cache_hit: boolean; ts: string; source: string } | null>(null);
  const [history, setHistory] = useState<HistoricalPricesData | null>(null);
  const [technicals, setTechnicals] = useState<TechnicalIndicatorsData | null>(null);

  const [compareInput, setCompareInput] = useState("NVDA, AMD, AVGO");
  const [comparePeriod, setComparePeriod] = useState<"5D" | "1M" | "3M" | "6M" | "1Y">("1M");
  const [comparison, setComparison] = useState<CompareInstrumentsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadSymbol(target: string) {
    setLoading(true);
    setError(null);
    const end = new Date();
    const start = new Date(end.getTime() - 42 * 86400_000);
    const fmt = (d: Date) => d.toISOString().slice(0, 10);

    try {
      const [qRes, hRes, tRes] = await Promise.all([
        executeMcpTool<QuoteData>(persona, "get_market_quote", { symbol: target }),
        executeMcpTool<HistoricalPricesData>(persona, "get_historical_prices", {
          symbol: target,
          start_date: fmt(start),
          end_date: fmt(end),
          interval: "1d",
          include_summary_stats: true,
        }),
        executeMcpTool<TechnicalIndicatorsData>(persona, "calculate_technical_indicators", {
          symbol: target,
          indicators: ["RSI_14", "MACD", "SMA_50", "SMA_200", "BOLLINGER_BANDS"],
          interval: "1d",
        }),
      ]);

      if (qRes.is_error || !qRes.envelope?.data) {
        setError(qRes.envelope?.error?.message ?? `Failed loading quote for ${target}`);
      } else {
        setQuote(qRes.envelope.data);
        setQuoteMeta({
          cache_hit: qRes.envelope.metadata.cache_hit,
          ts: qRes.envelope.metadata.data_timestamp,
          source: qRes.envelope.metadata.source,
        });
      }
      if (!hRes.is_error && hRes.envelope?.data) setHistory(hRes.envelope.data);
      if (!tRes.is_error && tRes.envelope?.data) setTechnicals(tRes.envelope.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed loading market data");
    } finally {
      setLoading(false);
    }
  }

  async function runComparison() {
    const syms = compareInput
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (syms.length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const res = await executeMcpTool<CompareInstrumentsData>(persona, "compare_instruments", {
        symbols: syms,
        period: comparePeriod,
      });
      if (res.is_error || !res.envelope?.data) {
        setError(res.envelope?.error?.message ?? "Comparison failed");
      } else {
        setComparison(res.envelope.data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison error");
    } finally {
      setLoading(false);
    }
  }

  async function runSearch(q: string) {
    setSearchQuery(q);
    if (!q.trim()) {
      setSearchResults([]);
      return;
    }
    const res = await executeMcpTool<{ instruments: Array<{ symbol: string; name: string; primary_exchange: string }> }>(
      persona,
      "search_instruments",
      { query: q.trim(), limit: 6 }
    );
    if (!res.is_error && res.envelope?.data) {
      setSearchResults(res.envelope.data.instruments);
    }
  }

  useEffect(() => {
    void loadSymbol(symbol);
    void runComparison();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona]);

  return (
    <div className="space-y-6">
      {/* Search + Quick Symbol Bar */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="h-4 w-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => void runSearch(e.target.value)}
            placeholder="Search ticker, name, ISIN (e.g., Nvidia, Semiconductor, AZN)..."
            className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-emerald-500"
          />
          {searchResults.length > 0 && (
            <div className="absolute left-0 right-0 mt-1 bg-slate-950 border border-slate-700 rounded-lg shadow-xl z-20 overflow-hidden">
              {searchResults.map((item) => (
                <button
                  key={item.symbol}
                  type="button"
                  onClick={() => {
                    setSymbol(item.symbol);
                    setSearchResults([]);
                    setSearchQuery("");
                    void loadSymbol(item.symbol);
                  }}
                  className="w-full px-3 py-2 text-left text-xs hover:bg-slate-800 flex justify-between items-center"
                >
                  <span>
                    <strong className="font-mono text-emerald-400">{item.symbol}</strong> — {item.name}
                  </span>
                  <span className="font-mono text-slate-500">{item.primary_exchange}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-1.5">
          {QUICK_SYMBOLS.map((sym) => (
            <button
              key={sym}
              type="button"
              onClick={() => {
                setSymbol(sym);
                void loadSymbol(sym);
              }}
              className={`px-2.5 py-1 rounded text-xs font-mono border transition-colors ${
                symbol === sym
                  ? "bg-emerald-500/20 border-emerald-500 text-emerald-300"
                  : "bg-slate-950 border-slate-800 text-slate-300 hover:border-slate-600"
              }`}
            >
              {sym}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="text-xs text-rose-300 bg-rose-950/40 border border-rose-800/60 rounded-lg p-3">
          {error}
        </div>
      )}

      {/* Quote + OHLCV Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-emerald-400" />
                <h2 className="text-lg font-bold font-mono text-slate-100">{quote?.symbol ?? symbol}</h2>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                  {quote?.exchange ?? "—"}
                </span>
                {quoteMeta && (
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-400">
                    {quoteMeta.cache_hit ? "CACHE HIT" : "FRESH"} &bull; {quoteMeta.source}
                  </span>
                )}
              </div>
              {quote && (
                <div className="mt-1 flex items-baseline gap-3 tabular-nums">
                  <span className="text-2xl font-bold font-mono text-white">
                    {quote.last_price.toLocaleString(undefined, { minimumFractionDigits: 2 })} {quote.currency}
                  </span>
                  <span
                    className={`text-sm font-mono font-medium ${
                      (quote.change_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {(quote.change ?? 0) >= 0 ? "+" : ""}
                    {quote.change?.toFixed(2)} ({quote.change_pct?.toFixed(2)}%)
                  </span>
                  <span className="text-xs font-mono text-slate-400">
                    Spread: {quote.spread_bps ?? "—"} bps
                  </span>
                </div>
              )}
            </div>
            {loading && <span className="text-xs font-mono text-emerald-400">Refreshing...</span>}
          </div>

          {history && <PriceSparkChart bars={history.bars} />}

          {history?.summary_stats && (
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 text-xs tabular-nums">
              {[
                ["Period High", history.summary_stats.period_high.toFixed(2)],
                ["Period Low", history.summary_stats.period_low.toFixed(2)],
                ["VWAP", history.summary_stats.vwap?.toFixed(2) ?? "—"],
                ["Mean Close", history.summary_stats.mean_close.toFixed(2)],
                ["Trading Days", String(history.summary_stats.trading_days_count)],
              ].map(([label, val]) => (
                <div key={label} className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5">
                  <div className="text-slate-400 text-[11px]">{label}</div>
                  <div className="font-mono font-semibold text-slate-100 mt-0.5">{val}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Technical Indicators Panel */}
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-slate-100">Technical Regime</h3>
            </div>
            {technicals?.overall_regime && (
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                {technicals.overall_regime}
              </span>
            )}
          </div>
          <div className="space-y-2.5">
            {technicals?.snapshots.map((snap) => (
              <div key={snap.indicator} className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-semibold text-slate-200">{snap.indicator}</span>
                  {snap.regime_signal && (
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                        snap.regime_signal.includes("BULL") || snap.regime_signal.includes("ABOVE")
                          ? "bg-emerald-500/15 text-emerald-300"
                          : snap.regime_signal.includes("OVERBOUGHT") || snap.regime_signal.includes("BEAR")
                          ? "bg-rose-500/15 text-rose-300"
                          : "bg-slate-800 text-slate-300"
                      }`}
                    >
                      {snap.regime_signal}
                    </span>
                  )}
                </div>
                <div className="mt-1 font-mono text-[11px] text-slate-400">
                  {Object.entries(snap.latest)
                    .map(([k, v]) => `${k}: ${v ?? "—"}`)
                    .join(" | ")}
                </div>
                {snap.crossover_timestamp && (
                  <div className="mt-1 text-[10px] font-mono text-amber-300">
                    Crossover: {snap.crossover_timestamp}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Multi-Asset Comparison & Correlation Matrix */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <GitCompareArrows className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-slate-100">
              Multi-Asset Alignment &amp; Correlation Matrix (`compare_instruments`)
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={compareInput}
              onChange={(e) => setCompareInput(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-xs font-mono text-slate-100 w-48"
            />
            <select
              value={comparePeriod}
              onChange={(e) => setComparePeriod(e.target.value as typeof comparePeriod)}
              className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono text-slate-100"
            >
              {["5D", "1M", "3M", "6M", "1Y"].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void runComparison()}
              className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-semibold"
            >
              Compare
            </button>
          </div>
        </div>

        {comparison && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 overflow-x-auto">
              <table className="w-full text-xs text-left tabular-nums">
                <thead className="text-[11px] uppercase text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-2 pr-3">Symbol</th>
                    <th className="py-2 pr-3">Cum Return</th>
                    <th className="py-2 pr-3">Ann Vol</th>
                    <th className="py-2 pr-3">Sharpe</th>
                    <th className="py-2 pr-3">Max DD</th>
                    <th className="py-2 pr-3">P/E</th>
                    <th className="py-2">EV/EBITDA</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70 font-mono">
                  {comparison.comparison_table.map((row) => (
                    <tr key={row.symbol}>
                      <td className="py-2 pr-3 font-bold text-emerald-300">{row.symbol}</td>
                      <td
                        className={`py-2 pr-3 ${
                          (row.cumulative_return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {row.cumulative_return_pct?.toFixed(2)}%
                      </td>
                      <td className="py-2 pr-3 text-slate-300">{row.annualized_volatility_pct?.toFixed(2)}%</td>
                      <td className="py-2 pr-3 text-slate-200">{row.sharpe_ratio?.toFixed(2)}</td>
                      <td className="py-2 pr-3 text-rose-400">{row.max_drawdown_pct?.toFixed(2)}%</td>
                      <td className="py-2 pr-3 text-slate-300">{row.pe_ratio?.toFixed(1) ?? "—"}</td>
                      <td className="py-2 text-slate-300">{row.ev_to_ebitda?.toFixed(1) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-2 text-[11px] font-mono text-slate-400">
                Aligned Window: {comparison.aligned_start_date} &rarr; {comparison.aligned_end_date} (
                {comparison.aligned_observations} common trading days)
              </div>
            </div>

            <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
              <div className="text-[11px] font-mono text-slate-400 mb-2">Pairwise Return Correlation</div>
              <table className="w-full text-[11px] font-mono text-center tabular-nums">
                <thead>
                  <tr>
                    <th className="p-1"></th>
                    {comparison.symbols.map((s) => (
                      <th key={s} className="p-1 text-slate-300">
                        {s}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {comparison.symbols.map((rowSym) => (
                    <tr key={rowSym}>
                      <td className="p-1 text-left font-semibold text-slate-300">{rowSym}</td>
                      {comparison.symbols.map((colSym) => {
                        const val = comparison.correlation_matrix?.[rowSym]?.[colSym] ?? 0;
                        return (
                          <td
                            key={colSym}
                            className={`p-1 rounded ${
                              val >= 0.75
                                ? "bg-emerald-500/20 text-emerald-300"
                                : val <= 0.2
                                ? "bg-amber-500/15 text-amber-300"
                                : "text-slate-300"
                            }`}
                          >
                            {val.toFixed(2)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
