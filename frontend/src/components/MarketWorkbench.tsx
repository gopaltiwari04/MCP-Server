"use client";

import { useEffect, useId, useState } from "react";
import { Search, CandlestickChart, Activity, GitCompareArrows, AlertCircle } from "lucide-react";
import { executeMcpTool } from "@/lib/api";
import type {
  CompareInstrumentsData,
  HistoricalPricesData,
  OHLCVBar,
  PersonaId,
  QuoteData,
  TechnicalIndicatorsData,
} from "@/lib/types";

const QUICK_SYMBOLS = ["NVDA", "AMD", "AAPL", "MSFT", "GOOGL", "AVGO", "TSM", "SPY", "AZN.L"];

function formatMarketCap(cap: number | null | undefined): string {
  if (!cap) return "—";
  if (cap >= 1e12) return `$${(cap / 1e12).toFixed(2)}T`;
  if (cap >= 1e9) return `$${(cap / 1e9).toFixed(1)}B`;
  if (cap >= 1e6) return `$${(cap / 1e6).toFixed(1)}M`;
  return `$${cap.toLocaleString()}`;
}

function correlationCellStyle(val: number): string {
  if (val >= 0.85) return "bg-emerald-500/25 text-emerald-200 border border-emerald-500/30";
  if (val >= 0.55) return "bg-emerald-500/12 text-emerald-300";
  if (val >= 0.2) return "bg-[#151923] text-zinc-300";
  if (val >= -0.2) return "bg-amber-500/12 text-amber-300";
  return "bg-rose-500/20 text-rose-300 border border-rose-500/30";
}

function QuantitativePriceChart({
  bars,
  vwap,
  currency,
  chartMode,
}: {
  bars: OHLCVBar[];
  vwap: number | null;
  currency: string;
  chartMode: "area" | "candles";
}) {
  const gradId = useId().replace(/:/g, "");
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (!bars.length) return null;

  const width = 760;
  const height = 270;
  const padLeft = 14;
  const padRight = 64;
  const padTop = 18;
  const priceHeight = 166;
  const volTop = padTop + priceHeight + 14;
  const volHeight = 46;
  const chartW = width - padLeft - padRight;

  const highs = bars.map((b) => b.high);
  const lows = bars.map((b) => b.low);
  let minP = Math.min(...lows, vwap ?? Infinity);
  let maxP = Math.max(...highs, vwap ?? -Infinity);
  const rawSpan = maxP - minP || 1;
  minP -= rawSpan * 0.05;
  maxP += rawSpan * 0.05;
  const span = maxP - minP;

  const maxVol = Math.max(1, ...bars.map((b) => b.volume));

  const xFor = (idx: number) =>
    padLeft + ((idx + 0.5) / bars.length) * chartW;
  const yFor = (price: number) =>
    padTop + priceHeight - ((price - minP) / span) * priceHeight;

  const isUpOverall = bars[bars.length - 1].close >= bars[0].close;
  const lineColor = isUpOverall ? "#10b981" : "#f43f5e";

  const linePoints = bars
    .map((b, i) => `${xFor(i).toFixed(1)},${yFor(b.close).toFixed(1)}`)
    .join(" ");

  const areaPath =
    `M ${xFor(0).toFixed(1)},${yFor(bars[0].close).toFixed(1)} ` +
    bars
      .slice(1)
      .map((b, i) => `L ${xFor(i + 1).toFixed(1)},${yFor(b.close).toFixed(1)}`)
      .join(" ") +
    ` L ${xFor(bars.length - 1).toFixed(1)},${padTop + priceHeight} L ${xFor(0).toFixed(1)},${
      padTop + priceHeight
    } Z`;

  const gridLevels = [0, 0.33, 0.67, 1].map((pct) => {
    const val = minP + span * pct;
    return { val, y: yFor(val) };
  });

  const activeBar = hoverIdx !== null ? bars[hoverIdx] : bars[bars.length - 1];
  const barWidth = Math.max(2.5, Math.min(11, (chartW / bars.length) * 0.62));
  const vwapY = vwap !== null ? yFor(vwap) : null;

  return (
    <div className="space-y-2">
      {/* Interactive Bar Readout HUD */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 rounded bg-[#090b0f] border border-[#1b1f2a] text-[11px] font-mono tabular-nums">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-zinc-400">{activeBar.timestamp.slice(0, 10)}</span>
          <span>
            O <strong className="text-zinc-200">{activeBar.open.toFixed(2)}</strong>
          </span>
          <span>
            H <strong className="text-zinc-200">{activeBar.high.toFixed(2)}</strong>
          </span>
          <span>
            L <strong className="text-zinc-200">{activeBar.low.toFixed(2)}</strong>
          </span>
          <span>
            C{" "}
            <strong
              className={
                activeBar.close >= activeBar.open ? "text-emerald-400" : "text-rose-400"
              }
            >
              {activeBar.close.toFixed(2)}
            </strong>
          </span>
          <span>
            Vol <strong className="text-zinc-300">{(activeBar.volume / 1e6).toFixed(2)}M</strong>
          </span>
        </div>
        {vwap !== null && (
          <div className="flex items-center gap-2 text-amber-300">
            <span className="inline-block w-3 border-t border-dashed border-amber-400" />
            <span>VWAP {vwap.toFixed(2)} {currency}</span>
          </div>
        )}
      </div>

      {/* SVG Canvas */}
      <div className="relative bg-[#080a0e] border border-[#1d222e] rounded overflow-hidden">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-64 select-none cursor-crosshair"
          onMouseLeave={() => setHoverIdx(null)}
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const relX = ((e.clientX - rect.left) / rect.width) * width;
            const ratio = (relX - padLeft) / chartW;
            const idx = Math.max(0, Math.min(bars.length - 1, Math.floor(ratio * bars.length)));
            setHoverIdx(idx);
          }}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={lineColor} stopOpacity="0.28" />
              <stop offset="100%" stopColor={lineColor} stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Horizontal Grid + Right Price Scale */}
          {gridLevels.map((g, i) => (
            <g key={`grid-${i}`}>
              <line
                x1={padLeft}
                x2={width - padRight}
                y1={g.y}
                y2={g.y}
                stroke="#181c26"
                strokeDasharray="2 3"
              />
              <text
                x={width - padRight + 8}
                y={g.y + 3.5}
                fill="#71717a"
                fontSize="10"
                fontFamily="monospace"
              >
                {g.val.toFixed(2)}
              </text>
            </g>
          ))}

          {/* VWAP Reference Line */}
          {vwapY !== null && vwapY >= padTop && vwapY <= padTop + priceHeight && (
            <line
              x1={padLeft}
              x2={width - padRight}
              y1={vwapY}
              y2={vwapY}
              stroke="#f59e0b"
              strokeWidth="1.2"
              strokeDasharray="5 4"
              opacity="0.85"
            />
          )}

          {/* Price Series */}
          {chartMode === "area" ? (
            <>
              <path d={areaPath} fill={`url(#${gradId})`} />
              <polyline fill="none" stroke={lineColor} strokeWidth="2" points={linePoints} />
            </>
          ) : (
            bars.map((b, i) => {
              const cx = xFor(i);
              const isUp = b.close >= b.open;
              const col = isUp ? "#10b981" : "#f43f5e";
              const yHigh = yFor(b.high);
              const yLow = yFor(b.low);
              const yOpen = yFor(b.open);
              const yClose = yFor(b.close);
              const bodyTop = Math.min(yOpen, yClose);
              const bodyH = Math.max(1.5, Math.abs(yClose - yOpen));
              return (
                <g key={`candle-${i}`}>
                  <line x1={cx} x2={cx} y1={yHigh} y2={yLow} stroke={col} strokeWidth="1.2" />
                  <rect
                    x={cx - barWidth / 2}
                    y={bodyTop}
                    width={barWidth}
                    height={bodyH}
                    fill={col}
                    rx="0.5"
                  />
                </g>
              );
            })
          )}

          {/* Volume Divider + Histogram */}
          <line
            x1={padLeft}
            x2={width - padRight}
            y1={volTop - 4}
            y2={volTop - 4}
            stroke="#171b24"
          />
          {bars.map((b, i) => {
            const cx = xFor(i);
            const h = (b.volume / maxVol) * volHeight;
            const isUp = b.close >= b.open;
            return (
              <rect
                key={`vol-${i}`}
                x={cx - barWidth / 2}
                y={volTop + volHeight - h}
                width={barWidth}
                height={h}
                fill={isUp ? "#10b981" : "#f43f5e"}
                opacity={hoverIdx === i ? "0.75" : "0.28"}
              />
            );
          })}

          {/* Interactive Crosshair */}
          {hoverIdx !== null && (
            <g>
              <line
                x1={xFor(hoverIdx)}
                x2={xFor(hoverIdx)}
                y1={padTop}
                y2={volTop + volHeight}
                stroke="#f59e0b"
                strokeWidth="1"
                strokeDasharray="3 3"
                opacity="0.7"
              />
              <circle
                cx={xFor(hoverIdx)}
                cy={yFor(bars[hoverIdx].close)}
                r="3.5"
                fill="#f59e0b"
                stroke="#08090c"
                strokeWidth="1.5"
              />
            </g>
          )}

          {/* X-Axis Dates */}
          {[0, Math.floor(bars.length / 2), bars.length - 1].map((idx) => (
            <text
              key={`dt-${idx}`}
              x={xFor(idx)}
              y={height - 6}
              textAnchor={idx === 0 ? "start" : idx === bars.length - 1 ? "end" : "middle"}
              fill="#71717a"
              fontSize="10"
              fontFamily="monospace"
            >
              {bars[idx].timestamp.slice(0, 10)}
            </text>
          ))}
        </svg>
      </div>
    </div>
  );
}

export function MarketWorkbench({ persona }: { persona: PersonaId }) {
  const [symbol, setSymbol] = useState("NVDA");
  const [chartMode, setChartMode] = useState<"area" | "candles">("candles");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<
    Array<{ symbol: string; name: string; primary_exchange: string }>
  >([]);

  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [quoteMeta, setQuoteMeta] = useState<{ cache_hit: boolean; ts: string; source: string } | null>(
    null
  );
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
    const start = new Date(end.getTime() - 48 * 86400_000);
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
    const res = await executeMcpTool<{
      instruments: Array<{ symbol: string; name: string; primary_exchange: string }>;
    }>(persona, "search_instruments", { query: q.trim(), limit: 6 });
    if (!res.is_error && res.envelope?.data) {
      setSearchResults(res.envelope.data.instruments);
    }
  }

  useEffect(() => {
    void loadSymbol(symbol);
    void runComparison();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona]);

  // Day range marker percentage
  const dayPosPct =
    quote && quote.high !== null && quote.low !== null && quote.high > quote.low
      ? Math.max(0, Math.min(100, ((quote.last_price - quote.low) / (quote.high - quote.low)) * 100))
      : 50;

  // Extract RSI-14 value if available
  const rsiSnap = technicals?.snapshots.find((s) => s.indicator === "RSI_14");
  const rsiVal = rsiSnap ? Object.values(rsiSnap.latest)[0] ?? null : null;

  const droppedEntries = comparison
    ? Object.entries(comparison.dropped_dates_by_symbol).filter(([, dates]) => dates.length > 0)
    : [];

  return (
    <div className="space-y-5">
      {/* Instrument Search & Quick Select Tape */}
      <div className="border border-[#1e222d] bg-[#0d0f14] rounded-md p-3 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="h-3.5 w-3.5 text-zinc-500 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => void runSearch(e.target.value)}
            placeholder="Lookup symbol, entity, ISIN (e.g. NVDA, Taiwan, AZN)..."
            className="w-full bg-[#090b0f] border border-[#242936] rounded pl-9 pr-3 py-1.5 text-xs font-mono text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-amber-500"
          />
          {searchResults.length > 0 && (
            <div className="absolute left-0 right-0 mt-1 bg-[#0b0d12] border border-[#2c3242] rounded shadow-2xl z-20 overflow-hidden">
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
                  className="w-full px-3 py-2 text-left text-xs hover:bg-[#151924] flex justify-between items-center border-b border-[#181c26] last:border-0"
                >
                  <span>
                    <strong className="font-mono text-amber-300">{item.symbol}</strong>{" "}
                    <span className="text-zinc-300">&mdash; {item.name}</span>
                  </span>
                  <span className="font-mono text-[10.5px] text-zinc-500">{item.primary_exchange}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1">
          {QUICK_SYMBOLS.map((sym) => {
            const active = symbol === sym;
            return (
              <button
                key={sym}
                type="button"
                onClick={() => {
                  setSymbol(sym);
                  void loadSymbol(sym);
                }}
                className={`px-2.5 py-1 rounded text-[11px] font-mono border transition-colors ${
                  active
                    ? "bg-amber-500/15 border-amber-500/60 text-amber-300 font-semibold"
                    : "bg-[#090b0f] border-[#1f2431] text-zinc-400 hover:text-zinc-100 hover:border-[#32394b]"
                }`}
              >
                {sym}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="text-xs font-mono text-rose-300 bg-rose-950/30 border border-rose-800/60 rounded p-3 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Primary Terminal Chart + Technical Regime */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        <div className="xl:col-span-8 border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#191d27] pb-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-mono font-bold tracking-tight text-zinc-100">
                  {quote?.symbol ?? symbol}
                </h2>
                <span className="text-[10.5px] font-mono px-1.5 py-0.5 rounded bg-[#151822] border border-[#252b3b] text-zinc-300">
                  {quote?.exchange ?? "—"}
                </span>
                {quoteMeta && (
                  <span className="text-[10.5px] font-mono px-1.5 py-0.5 rounded bg-[#090b0f] border border-[#1f2431] text-zinc-400">
                    {quoteMeta.cache_hit ? "CACHE HIT" : "LIVE"} &bull; {quoteMeta.source}
                  </span>
                )}
              </div>

              {quote && (
                <div className="mt-1.5 flex flex-wrap items-baseline gap-3 tabular-nums">
                  <span className="text-2xl font-mono font-bold text-white">
                    {quote.last_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}{" "}
                    <span className="text-xs font-normal text-zinc-400">{quote.currency}</span>
                  </span>
                  <span
                    className={`text-sm font-mono font-semibold ${
                      (quote.change_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {(quote.change ?? 0) >= 0 ? "+" : ""}
                    {quote.change?.toFixed(2)} ({quote.change_pct?.toFixed(2)}%)
                  </span>
                </div>
              )}
            </div>

            {/* Chart Controls + Microstructure Bid/Ask */}
            <div className="flex flex-col items-end gap-2">
              <div className="flex items-center gap-1 bg-[#090b0f] border border-[#1f2431] rounded p-0.5">
                <button
                  type="button"
                  onClick={() => setChartMode("candles")}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-mono transition-colors ${
                    chartMode === "candles"
                      ? "bg-[#1a1f2b] text-amber-300"
                      : "text-zinc-500 hover:text-zinc-200"
                  }`}
                >
                  <CandlestickChart className="h-3 w-3" /> OHLC
                </button>
                <button
                  type="button"
                  onClick={() => setChartMode("area")}
                  className={`px-2.5 py-1 rounded text-[11px] font-mono transition-colors ${
                    chartMode === "area"
                      ? "bg-[#1a1f2b] text-amber-300"
                      : "text-zinc-500 hover:text-zinc-200"
                  }`}
                >
                  Area
                </button>
              </div>
              {loading && (
                <span className="text-[10.5px] font-mono text-amber-400 animate-pulse">
                  SYNCING MCP SERIES...
                </span>
              )}
            </div>
          </div>

          {/* Quote Microstructure & Day Range */}
          {quote && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px] font-mono tabular-nums">
              <div className="bg-[#090b0f] border border-[#1a1e29] rounded px-3 py-2">
                <div className="text-zinc-500 text-[10px]">BID / ASK (SPREAD)</div>
                <div className="text-zinc-200 mt-0.5">
                  {quote.bid?.toFixed(2) ?? "—"} / {quote.ask?.toFixed(2) ?? "—"}{" "}
                  <span className="text-amber-300">({quote.spread_bps ?? "—"} bps)</span>
                </div>
              </div>
              <div className="bg-[#090b0f] border border-[#1a1e29] rounded px-3 py-2">
                <div className="text-zinc-500 text-[10px]">MARKET CAP</div>
                <div className="text-zinc-200 font-semibold mt-0.5">
                  {formatMarketCap(quote.market_cap)}
                </div>
              </div>
              <div className="col-span-2 bg-[#090b0f] border border-[#1a1e29] rounded px-3 py-2">
                <div className="flex justify-between text-[10px] text-zinc-500">
                  <span>DAY LOW {quote.low?.toFixed(2) ?? "—"}</span>
                  <span>SESSION RANGE</span>
                  <span>HIGH {quote.high?.toFixed(2) ?? "—"}</span>
                </div>
                <div className="mt-1.5 h-1.5 bg-[#171b24] rounded-full relative">
                  <div
                    className="absolute top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full bg-amber-400 border border-[#08090c]"
                    style={{ left: `calc(${dayPosPct}% - 5px)` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Chart */}
          {history && (
            <QuantitativePriceChart
              bars={history.bars}
              vwap={history.summary_stats?.vwap ?? null}
              currency={history.currency}
              chartMode={chartMode}
            />
          )}

          {/* Deterministic Summary Stats */}
          {history?.summary_stats && (
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs tabular-nums">
              {[
                ["Period High", history.summary_stats.period_high.toFixed(2)],
                ["Period Low", history.summary_stats.period_low.toFixed(2)],
                ["VWAP", history.summary_stats.vwap?.toFixed(2) ?? "—"],
                ["Mean Close", history.summary_stats.mean_close.toFixed(2)],
                ["Trading Days", String(history.summary_stats.trading_days_count)],
              ].map(([label, val]) => (
                <div key={label} className="bg-[#090b0f] border border-[#1a1e29] rounded px-3 py-2">
                  <div className="text-zinc-500 text-[10px] font-mono uppercase">{label}</div>
                  <div className="font-mono font-semibold text-zinc-100 mt-0.5">{val}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Technical Regime & RSI Gauge Panel */}
        <div className="xl:col-span-4 border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-[#191d27] pb-2.5">
            <div className="flex items-center gap-2">
              <Activity className="h-3.5 w-3.5 text-amber-400" />
              <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                Technical Regime
              </h3>
            </div>
            {technicals?.overall_regime && (
              <span className="text-[10.5px] font-mono px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                {technicals.overall_regime}
              </span>
            )}
          </div>

          {/* RSI-14 Gauge */}
          {typeof rsiVal === "number" && (
            <div className="bg-[#090b0f] border border-[#1a1e29] rounded p-3 space-y-1.5">
              <div className="flex items-center justify-between text-[11px] font-mono tabular-nums">
                <span className="text-zinc-400">RSI (14) MOMENTUM</span>
                <span
                  className={
                    rsiVal >= 70
                      ? "text-rose-400 font-semibold"
                      : rsiVal <= 30
                      ? "text-emerald-400 font-semibold"
                      : "text-zinc-100 font-semibold"
                  }
                >
                  {rsiVal.toFixed(1)}
                </span>
              </div>
              <div className="h-2 rounded-full bg-[#161a24] relative overflow-hidden flex">
                <div className="w-[30%] bg-emerald-500/25 border-r border-[#242a3a]" />
                <div className="w-[40%] bg-zinc-700/20 border-r border-[#242a3a]" />
                <div className="w-[30%] bg-rose-500/25" />
                <div
                  className="absolute top-0 bottom-0 w-1.5 bg-amber-400 rounded"
                  style={{ left: `calc(${Math.max(2, Math.min(98, rsiVal))}% - 3px)` }}
                />
              </div>
              <div className="flex justify-between text-[9.5px] font-mono text-zinc-500">
                <span>0 OVERSOLD</span>
                <span>30 / 70 NEUTRAL</span>
                <span>OVERBOUGHT 100</span>
              </div>
            </div>
          )}

          {/* Indicator Snapshots */}
          <div className="space-y-2">
            {technicals?.snapshots.map((snap) => (
              <div
                key={snap.indicator}
                className="bg-[#090b0f] border border-[#1a1e29] rounded p-2.5 text-xs"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono font-semibold text-zinc-200">{snap.indicator}</span>
                  {snap.regime_signal && (
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                        snap.regime_signal.includes("BULL") || snap.regime_signal.includes("ABOVE")
                          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                          : snap.regime_signal.includes("OVERBOUGHT") || snap.regime_signal.includes("BEAR")
                          ? "bg-rose-500/10 border-rose-500/30 text-rose-300"
                          : "bg-[#151822] border-[#252a38] text-zinc-300"
                      }`}
                    >
                      {snap.regime_signal}
                    </span>
                  )}
                </div>
                <div className="mt-1 font-mono text-[11px] text-zinc-400 tabular-nums">
                  {Object.entries(snap.latest)
                    .map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(2) : v ?? "—"}`)
                    .join("  |  ")}
                </div>
                {snap.crossover_timestamp && (
                  <div className="mt-1 text-[10px] font-mono text-amber-300">
                    Crossover @ {snap.crossover_timestamp.slice(0, 10)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Multi-Asset Comparison & Correlation Heatmap */}
      <div className="border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#191d27] pb-3">
          <div className="flex items-center gap-2">
            <GitCompareArrows className="h-4 w-4 text-amber-400" />
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
              Cross-Asset Alignment &amp; Correlation Matrix (`compare_instruments`)
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={compareInput}
              onChange={(e) => setCompareInput(e.target.value)}
              className="bg-[#090b0f] border border-[#242936] rounded px-2.5 py-1 text-xs font-mono text-zinc-100 w-52 focus:outline-none focus:border-amber-500"
            />
            <select
              value={comparePeriod}
              onChange={(e) => setComparePeriod(e.target.value as typeof comparePeriod)}
              className="bg-[#090b0f] border border-[#242936] rounded px-2 py-1 text-xs font-mono text-zinc-100"
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
              className="px-3 py-1 rounded bg-amber-500 hover:bg-amber-400 text-[#08090c] text-xs font-mono font-semibold uppercase"
            >
              Compare
            </button>
          </div>
        </div>

        {comparison && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            <div className="lg:col-span-7 space-y-3 overflow-x-auto">
              <table className="w-full text-xs text-left tabular-nums border-collapse">
                <thead className="text-[10.5px] font-mono uppercase text-zinc-400 border-b border-[#222736] bg-[#11141c]">
                  <tr>
                    <th className="py-2 px-3">Symbol</th>
                    <th className="py-2 px-3 text-right">Return</th>
                    <th className="py-2 px-3 text-right">Ann Vol</th>
                    <th className="py-2 px-3 text-right">Sharpe</th>
                    <th className="py-2 px-3 text-right">Max DD</th>
                    <th className="py-2 px-3 text-right">P/E</th>
                    <th className="py-2 px-3 text-right">EV/EBITDA</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#181c26] font-mono">
                  {comparison.comparison_table.map((row) => (
                    <tr
                      key={row.symbol}
                      onClick={() => {
                        setSymbol(row.symbol);
                        void loadSymbol(row.symbol);
                      }}
                      title={`Load ${row.symbol} chart`}
                      className="hover:bg-[#141824] cursor-pointer transition-colors"
                    >
                      <td className="py-2 px-3 font-bold text-amber-300">{row.symbol}</td>
                      <td
                        className={`py-2 px-3 text-right ${
                          (row.cumulative_return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {row.cumulative_return_pct !== null
                          ? `${row.cumulative_return_pct >= 0 ? "+" : ""}${row.cumulative_return_pct.toFixed(2)}%`
                          : "—"}
                      </td>
                      <td className="py-2 px-3 text-right text-zinc-300">
                        {row.annualized_volatility_pct?.toFixed(2)}%
                      </td>
                      <td className="py-2 px-3 text-right text-zinc-100">
                        {row.sharpe_ratio?.toFixed(2)}
                      </td>
                      <td className="py-2 px-3 text-right text-rose-400">
                        {row.max_drawdown_pct?.toFixed(2)}%
                      </td>
                      <td className="py-2 px-3 text-right text-zinc-300">
                        {row.pe_ratio?.toFixed(1) ?? "—"}
                      </td>
                      <td className="py-2 px-3 text-right text-zinc-300">
                        {row.ev_to_ebitda?.toFixed(1) ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono text-zinc-400">
                <span>
                  Aligned Window: {comparison.aligned_start_date} &rarr; {comparison.aligned_end_date} (
                  {comparison.aligned_observations} common trading days)
                </span>
                {droppedEntries.length > 0 && (
                  <span className="text-amber-300">
                    Dropped non-overlapping dates:{" "}
                    {droppedEntries.map(([s, d]) => `${s}(${d.length})`).join(", ")}
                  </span>
                )}
              </div>

              {comparison.rankings.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {comparison.rankings.map((r) => (
                    <span
                      key={r.metric}
                      className="text-[10.5px] font-mono px-2 py-1 rounded bg-[#090b0f] border border-[#1d222e] text-zinc-300"
                    >
                      <span className="text-zinc-500">{r.metric}:</span>{" "}
                      {r.ordered_symbols.join(" > ")}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Pairwise Correlation Heatmap */}
            <div className="lg:col-span-5 bg-[#090b0f] border border-[#1a1e29] rounded p-3">
              <div className="text-[10.5px] font-mono uppercase tracking-wider text-zinc-400 mb-2.5">
                Pairwise Return Correlation (&rho;)
              </div>
              <table className="w-full text-[11px] font-mono text-center tabular-nums border-separate border-spacing-1">
                <thead>
                  <tr>
                    <th className="p-1"></th>
                    {comparison.symbols.map((s) => (
                      <th key={s} className="p-1 text-zinc-400 font-semibold">
                        {s}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {comparison.symbols.map((rowSym) => (
                    <tr key={rowSym}>
                      <td className="p-1 text-left font-semibold text-zinc-300">{rowSym}</td>
                      {comparison.symbols.map((colSym) => {
                        const val = comparison.correlation_matrix?.[rowSym]?.[colSym] ?? 0;
                        return (
                          <td key={colSym} className={`p-1.5 rounded ${correlationCellStyle(val)}`}>
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
