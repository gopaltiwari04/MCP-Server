"use client";

import { useEffect, useState } from "react";
import { Boxes, FileCode2, MessageSquareCode, Play, Search } from "lucide-react";
import { executeMcpTool, fetchMcpCatalog, readMcpResource, renderMcpPrompt } from "@/lib/api";
import type { McpCatalog, PersonaId, ToolTrace } from "@/lib/types";
import { MarkdownView } from "@/components/MarkdownView";

const DEFAULT_TOOL_ARGS: Record<string, Record<string, unknown>> = {
  search_instruments: { query: "NVIDIA", limit: 5 },
  get_exchange_schedule: { exchange: "NASDAQ" },
  get_company_profile: { symbol: "NVDA" },
  get_market_quote: { symbol: "NVDA" },
  get_historical_prices: { symbol: "NVDA", interval: "1d", include_summary_stats: true },
  get_financial_metrics: { symbol: "NVDA", period: "TTM", limit: 2 },
  get_earnings_history: { symbol: "NVDA", quarters: 4 },
  calculate_returns: { symbol: "NVDA", benchmark_symbol: "SPY", period: "1M" },
  calculate_technical_indicators: { symbol: "NVDA", indicators: ["RSI_14", "MACD", "SMA_50"] },
  compare_instruments: { symbols: ["NVDA", "AMD", "AVGO"], period: "1M" },
  analyse_portfolio: { portfolio_id: "port_123", benchmark_symbol: "SPY", confidence_level: 0.95 },
  simulate_portfolio_rebalance: {
    portfolio_id: "port_123",
    proposed_trades: [{ symbol: "NVDA", side: "BUY", weight_delta_pct: 5 }],
  },
  manage_watchlist: { action: "LIST", watchlist_name: "Default" },
  create_price_alert: { symbol: "NVDA", condition: "CROSSES_ABOVE", threshold_value: 200 },
  save_research_memo: {
    title: "NVDA Compute Demand Note",
    symbols: ["NVDA"],
    thesis_markdown: "Data center demand remains structurally elevated with expanding margins.",
    sentiment: "BULLISH",
    cited_data_timestamps: [new Date().toISOString()],
  },
};

const DEFAULT_PROMPT_ARGS: Record<string, Record<string, string>> = {
  institutional_equity_tearsheet: { symbol: "NVDA", benchmark: "SPY" },
  multi_stock_relative_value_comparison: { symbols_csv: "NVDA,AMD", period: "1M" },
  pairs_trading_screen: { symbol_a: "NVDA", symbol_b: "AMD", lookback_period: "6M" },
  portfolio_tail_risk_audit: { portfolio_id: "port_123" },
};

export function ProtocolExplorer({ persona }: { persona: PersonaId }) {
  const [catalog, setCatalog] = useState<McpCatalog | null>(null);
  const [toolFilter, setToolFilter] = useState("");
  const [selectedToolName, setSelectedToolName] = useState<string>("get_market_quote");
  const [toolArgsJson, setToolArgsJson] = useState<string>(
    JSON.stringify(DEFAULT_TOOL_ARGS.get_market_quote, null, 2)
  );
  const [toolRunning, setToolRunning] = useState(false);
  const [toolResult, setToolResult] = useState<ToolTrace | null>(null);
  const [toolRunErr, setToolRunErr] = useState<string | null>(null);

  const [resourceUri, setResourceUri] = useState("market://system/capabilities");
  const [resourceMime, setResourceMime] = useState<string>("application/json");
  const [resourceOutput, setResourceOutput] = useState<string>("");
  const [resourceMode, setResourceMode] = useState<"rendered" | "raw">("rendered");

  const [selectedPromptName, setSelectedPromptName] = useState<string>("institutional_equity_tearsheet");
  const [promptArgs, setPromptArgs] = useState<Record<string, string>>(
    DEFAULT_PROMPT_ARGS.institutional_equity_tearsheet
  );
  const [promptOutput, setPromptOutput] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    fetchMcpCatalog(persona)
      .then((cat) => {
        setCatalog(cat);
        if (cat.tools.length > 0 && !cat.tools.some((t) => t.name === selectedToolName)) {
          selectTool(cat.tools[0].name);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed loading MCP catalog"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona]);

  function selectTool(name: string) {
    setSelectedToolName(name);
    setToolArgsJson(JSON.stringify(DEFAULT_TOOL_ARGS[name] ?? {}, null, 2));
    setToolResult(null);
    setToolRunErr(null);
  }

  async function runSelectedTool() {
    setToolRunErr(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(toolArgsJson) as Record<string, unknown>;
    } catch {
      setToolRunErr("Invalid JSON syntax in tool arguments.");
      return;
    }
    setToolRunning(true);
    try {
      const res = await executeMcpTool(persona, selectedToolName, parsed);
      setToolResult(res);
    } catch (e) {
      setToolRunErr(e instanceof Error ? e.message : "RPC execution error");
    } finally {
      setToolRunning(false);
    }
  }

  async function handleReadResource(uri: string) {
    setResourceUri(uri);
    const res = await readMcpResource(persona, uri);
    if (res.is_error) {
      setResourceMime("text/plain");
      setResourceOutput(`ERROR: ${res.error_message}`);
    } else {
      const mime = res.contents?.[0]?.mime_type ?? "text/plain";
      const raw = res.contents?.[0]?.text ?? "";
      setResourceMime(mime);
      if (mime.includes("json")) {
        try {
          setResourceOutput(JSON.stringify(JSON.parse(raw), null, 2));
          return;
        } catch {
          // fallback raw
        }
      }
      setResourceOutput(raw);
    }
  }

  async function handleRenderPrompt() {
    const res = await renderMcpPrompt(persona, selectedPromptName, promptArgs);
    setPromptOutput(res.messages.map((m) => `#### Message Role: \`${m.role}\`\n\n${m.text}`).join("\n\n"));
  }

  const filteredTools =
    catalog?.tools.filter(
      (t) =>
        t.name.toLowerCase().includes(toolFilter.toLowerCase()) ||
        t.description.toLowerCase().includes(toolFilter.toLowerCase())
    ) ?? [];

  const activeTool = catalog?.tools.find((t) => t.name === selectedToolName);
  const schemaProps =
    (activeTool?.input_schema?.properties as Record<string, { type?: string; description?: string }> | undefined) ??
    {};
  const requiredProps = new Set<string>(
    ((activeTool?.input_schema?.required as string[] | undefined) ?? [])
  );

  const activePrompt = catalog?.prompts.find((p) => p.name === selectedPromptName);

  return (
    <div className="space-y-5">
      {error && (
        <div className="text-xs font-mono text-rose-300 bg-rose-950/30 border border-rose-800 rounded p-3">
          {error}
        </div>
      )}

      {catalog && (
        <>
          {/* Interactive Tools Workbench */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Tool List */}
            <div className="lg:col-span-5 border border-[#1e222d] bg-[#0d0f14] rounded-md flex flex-col max-h-[540px] overflow-hidden">
              <div className="px-4 py-2.5 border-b border-[#191d27] bg-[#11141c] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Boxes className="h-3.5 w-3.5 text-amber-400" />
                  <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                    MCP Tools ({catalog.tools.length})
                  </h3>
                </div>
                <span className="text-[10px] font-mono text-zinc-500">CLICK TO INSPECT &amp; RUN</span>
              </div>
              <div className="p-2.5 border-b border-[#191d27] bg-[#0a0c10]">
                <div className="relative">
                  <Search className="h-3.5 w-3.5 text-zinc-500 absolute left-2.5 top-2" />
                  <input
                    type="text"
                    value={toolFilter}
                    onChange={(e) => setToolFilter(e.target.value)}
                    placeholder="Filter tools..."
                    className="w-full bg-[#090b0f] border border-[#242936] rounded pl-8 pr-2.5 py-1 text-xs font-mono text-zinc-100"
                  />
                </div>
              </div>
              <div className="p-2.5 space-y-1.5 overflow-y-auto flex-1">
                {filteredTools.map((t) => {
                  const selected = t.name === selectedToolName;
                  return (
                    <button
                      key={t.name}
                      type="button"
                      onClick={() => selectTool(t.name)}
                      className={`w-full text-left rounded p-2.5 border transition-colors ${
                        selected
                          ? "bg-[#151822] border-amber-500/60"
                          : "bg-[#090b0f] border-[#1a1e29] hover:border-[#2c3345]"
                      }`}
                    >
                      <div className="font-mono text-xs font-semibold text-amber-300">{t.name}</div>
                      <div className="text-[11px] text-zinc-400 mt-0.5 line-clamp-2">{t.description}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Live Schema + Executor */}
            <div className="lg:col-span-7 border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-3 flex flex-col max-h-[540px] overflow-y-auto">
              {activeTool && (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#191d27] pb-2.5">
                    <div>
                      <div className="font-mono text-sm font-bold text-amber-300">{activeTool.name}</div>
                      <p className="text-xs text-zinc-400 mt-0.5">{activeTool.description}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void runSelectedTool()}
                      disabled={toolRunning}
                      className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-[#08090c] text-xs font-mono font-semibold uppercase disabled:opacity-50 shrink-0"
                    >
                      <Play className="h-3 w-3" />
                      {toolRunning ? "Calling..." : "tools/call"}
                    </button>
                  </div>

                  {/* Schema Parameters */}
                  {Object.keys(schemaProps).length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(schemaProps).map(([propName, meta]) => (
                        <span
                          key={propName}
                          title={meta.description ?? ""}
                          className="text-[10.5px] font-mono px-2 py-0.5 rounded bg-[#090b0f] border border-[#1e2330] text-zinc-300"
                        >
                          <span className="text-zinc-100">{propName}</span>
                          {requiredProps.has(propName) && <span className="text-rose-400">*</span>}
                          {meta.type && <span className="text-zinc-500">:{meta.type}</span>}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Arguments Editor */}
                  <div className="space-y-1">
                    <label className="block text-[10px] font-mono uppercase tracking-wider text-zinc-500">
                      JSON Arguments (Never includes auth tokens or user_id)
                    </label>
                    <textarea
                      value={toolArgsJson}
                      onChange={(e) => setToolArgsJson(e.target.value)}
                      rows={4}
                      className="w-full bg-[#07090d] border border-[#242936] rounded p-2.5 text-xs font-mono text-zinc-200 focus:outline-none focus:border-amber-500"
                    />
                  </div>

                  {toolRunErr && (
                    <div className="text-xs font-mono text-rose-300 bg-rose-950/30 border border-rose-800 rounded p-2.5">
                      {toolRunErr}
                    </div>
                  )}

                  {toolResult && (
                    <div className="space-y-1.5">
                      <div className="flex flex-wrap items-center justify-between text-[11px] font-mono text-zinc-400">
                        <span>
                          STATUS:{" "}
                          <strong className={toolResult.is_error ? "text-rose-400" : "text-emerald-400"}>
                            {toolResult.envelope?.status ?? "ERR"}
                          </strong>{" "}
                          &bull; {toolResult.elapsed_ms}ms &bull;{" "}
                          {toolResult.envelope?.metadata?.cache_hit ? "HIT" : "MISS"}
                        </span>
                        <span className="text-zinc-500">{toolResult.request_id}</span>
                      </div>
                      <pre className="bg-[#06070a] border border-[#1d222e] rounded p-3 text-[11px] font-mono text-zinc-300 overflow-auto max-h-56">
                        {JSON.stringify(toolResult.envelope, null, 2)}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Bottom Split: Resources & Workflow Prompts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Resources */}
            <div className="border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-[#191d27] pb-2.5">
                <div className="flex items-center gap-2">
                  <FileCode2 className="h-3.5 w-3.5 text-amber-400" />
                  <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                    MCP Resources &amp; URI Templates
                  </h3>
                </div>
                {resourceOutput && resourceMime.includes("markdown") && (
                  <button
                    type="button"
                    onClick={() => setResourceMode((m) => (m === "rendered" ? "raw" : "rendered"))}
                    className="text-[10.5px] font-mono px-2 py-0.5 rounded bg-[#141720] border border-[#242936] text-zinc-300"
                  >
                    {resourceMode === "rendered" ? "View Raw" : "Render Markdown"}
                  </button>
                )}
              </div>

              <div className="flex flex-wrap gap-1.5">
                {[
                  "market://system/capabilities",
                  "market://system/glossary",
                  "market://instrument/NVDA/snapshot",
                  "portfolio://user/port_123/summary",
                ].map((uri) => (
                  <button
                    key={uri}
                    type="button"
                    onClick={() => void handleReadResource(uri)}
                    className={`text-[10.5px] font-mono px-2 py-1 rounded border transition-colors ${
                      resourceUri === uri
                        ? "bg-amber-500/15 border-amber-500/60 text-amber-300"
                        : "bg-[#090b0f] border-[#1f2431] text-zinc-300 hover:border-[#32394b]"
                    }`}
                  >
                    {uri}
                  </button>
                ))}
              </div>

              <div className="flex gap-2">
                <input
                  type="text"
                  value={resourceUri}
                  onChange={(e) => setResourceUri(e.target.value)}
                  className="flex-1 bg-[#090b0f] border border-[#242936] rounded px-2.5 py-1.5 text-xs font-mono text-zinc-100"
                />
                <button
                  type="button"
                  onClick={() => void handleReadResource(resourceUri)}
                  className="px-3 py-1.5 rounded bg-[#161a24] hover:bg-[#1f2433] border border-[#2d3344] text-amber-300 text-xs font-mono font-semibold"
                >
                  resources/read
                </button>
              </div>

              <div className="bg-[#07090d] border border-[#1a1e29] rounded p-3 overflow-auto max-h-80">
                {!resourceOutput ? (
                  <p className="text-xs font-mono text-zinc-500">
                    Select a resource URI or enter a dynamic template (`market://instrument/MSFT/snapshot`) to
                    inspect live server payloads.
                  </p>
                ) : resourceMime.includes("markdown") && resourceMode === "rendered" ? (
                  <MarkdownView content={resourceOutput} />
                ) : (
                  <pre className="text-[11px] font-mono text-zinc-300 whitespace-pre-wrap">{resourceOutput}</pre>
                )}
              </div>
            </div>

            {/* Institutional Prompts Studio */}
            <div className="border border-[#1e222d] bg-[#0d0f14] rounded-md p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-[#191d27] pb-2.5">
                <div className="flex items-center gap-2">
                  <MessageSquareCode className="h-3.5 w-3.5 text-amber-400" />
                  <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
                    Institutional Prompts ({catalog.prompts.length})
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => void handleRenderPrompt()}
                  className="px-3 py-1 rounded bg-amber-500 hover:bg-amber-400 text-[#08090c] text-[11px] font-mono font-semibold uppercase"
                >
                  prompts/get
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                {catalog.prompts.map((p) => {
                  const selected = p.name === selectedPromptName;
                  return (
                    <button
                      key={p.name}
                      type="button"
                      onClick={() => {
                        setSelectedPromptName(p.name);
                        setPromptArgs(DEFAULT_PROMPT_ARGS[p.name] ?? {});
                        setPromptOutput("");
                      }}
                      className={`text-left rounded p-2 border transition-colors ${
                        selected
                          ? "bg-[#151822] border-amber-500/60"
                          : "bg-[#090b0f] border-[#1a1e29] hover:border-[#2c3345]"
                      }`}
                    >
                      <div className="font-mono text-[11px] font-semibold text-amber-300 truncate">{p.name}</div>
                      <div className="text-[10.5px] text-zinc-400 line-clamp-1 mt-0.5">{p.description}</div>
                    </button>
                  );
                })}
              </div>

              {activePrompt && activePrompt.arguments.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {activePrompt.arguments.map((arg) => (
                    <div key={arg.name}>
                      <label className="block text-[10px] font-mono text-zinc-400 mb-0.5">
                        {arg.name}
                        {arg.required && <span className="text-rose-400">*</span>}
                      </label>
                      <input
                        type="text"
                        value={promptArgs[arg.name] ?? ""}
                        onChange={(e) =>
                          setPromptArgs((prev) => ({ ...prev, [arg.name]: e.target.value }))
                        }
                        className="w-full bg-[#090b0f] border border-[#242936] rounded px-2 py-1 text-xs font-mono text-zinc-100"
                      />
                    </div>
                  ))}
                </div>
              )}

              <div className="bg-[#07090d] border border-[#1a1e29] rounded p-3 overflow-auto max-h-64">
                {!promptOutput ? (
                  <p className="text-xs font-mono text-zinc-500">
                    Customize arguments above and click `prompts/get` to render the institutional prompt template.
                  </p>
                ) : (
                  <MarkdownView content={promptOutput} />
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
