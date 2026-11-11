"use client";

import { useState } from "react";
import {
  Send,
  Terminal,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  RotateCcw,
  Clock,
  Layers,
} from "lucide-react";
import { sendChatPrompt } from "@/lib/api";
import type { ChatResponse, PersonaId } from "@/lib/types";
import { MarkdownView } from "@/components/MarkdownView";

interface MessageItem {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}

const PRESET_PROMPTS = [
  { label: "NVDA vs AMD · 1M", prompt: "Compare NVDA vs AMD over 1M" },
  { label: "NVDA Equity Tearsheet", prompt: "Generate institutional tearsheet for NVDA" },
  { label: "Portfolio Tail Risk + Rebalance", prompt: "Audit portfolio tail risk and simulate rebalance" },
  { label: "Cross-Exchange US/UK · 3M", prompt: "Compare NVDA vs AZN.L over 3M cross-exchange" },
];

const INITIAL_MESSAGE: MessageItem = {
  id: "welcome",
  role: "assistant",
  text: "Ready. Queries route through the **FastAPI AI Orchestrator**, which mints a scoped delegated JWT per principal and invokes `market-intelligence-mcp` over **Streamable HTTP**. Select a benchmark workflow above or enter an equity, comparison, or portfolio risk prompt below.",
};

export function OrchestratorChat({ persona }: { persona: PersonaId }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTrace, setExpandedTrace] = useState<Record<string, boolean>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([INITIAL_MESSAGE]);

  async function submitPrompt(promptText: string) {
    const trimmed = promptText.trim();
    if (!trimmed || loading) return;
    setError(null);
    const userMsg: MessageItem = { id: `u-${Date.now()}`, role: "user", text: trimmed };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    try {
      const res = await sendChatPrompt(persona, trimmed);
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: res.assistant_markdown,
          response: res,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to execute orchestrated MCP query");
    } finally {
      setLoading(false);
    }
  }

  function handleCopy(key: string, payload: unknown) {
    void navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1500);
  }

  const latestTraces =
    messages
      .filter((m) => m.response)
      .slice(-1)[0]?.response?.tool_traces ?? [];

  const totalTraceMs = latestTraces.reduce((acc, t) => acc + t.elapsed_ms, 0);
  const maxTraceMs = Math.max(1, ...latestTraces.map((t) => t.elapsed_ms));
  const cacheHitCount = latestTraces.filter((t) => t.envelope?.metadata?.cache_hit).length;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-start">
      {/* Left 8 Cols: Research Brief & Prompt Stream */}
      <div className="xl:col-span-8 flex flex-col border border-[#1e222d] bg-[#0d0f14] rounded-md overflow-hidden min-h-[660px]">
        {/* Toolbar */}
        <div className="px-4 py-2.5 border-b border-[#1e222d] bg-[#11141c] flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-amber-400" />
            <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
              Quantitative Research Desk
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-mono text-zinc-400">
              DELEGATED AS <strong className="text-amber-300 uppercase">{persona}</strong>
            </span>
            {messages.length > 1 && (
              <button
                type="button"
                onClick={() => {
                  setMessages([INITIAL_MESSAGE]);
                  setExpandedTrace({});
                  setError(null);
                }}
                className="inline-flex items-center gap-1 text-[11px] font-mono text-zinc-400 hover:text-zinc-100 px-2 py-1 rounded border border-[#242936] bg-[#0b0d12] transition-colors"
              >
                <RotateCcw className="h-3 w-3" />
                Reset
              </button>
            )}
          </div>
        </div>

        {/* Preset Query Strip */}
        <div className="px-4 py-2 border-b border-[#191d27] bg-[#0a0c10] flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mr-1">
            Workflows:
          </span>
          {PRESET_PROMPTS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => submitPrompt(preset.prompt)}
              disabled={loading}
              className="text-[11px] font-mono px-2.5 py-1 rounded bg-[#121620] hover:bg-[#191f2d] text-zinc-300 hover:text-amber-300 border border-[#242936] hover:border-amber-500/40 transition-colors disabled:opacity-50"
            >
              {preset.label}
            </button>
          ))}
        </div>

        {/* Stream */}
        <div className="flex-1 p-4 space-y-4 overflow-y-auto max-h-[540px]">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`rounded-md border ${
                m.role === "user"
                  ? "bg-[#12151e] border-[#282e3d] ml-6 sm:ml-12"
                  : "bg-[#090b0f] border-[#1c202b]"
              }`}
            >
              {/* Entry Header */}
              <div className="px-4 py-2 border-b border-[#181c26] flex flex-wrap items-center justify-between gap-2 bg-[#0e1118]/60">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded ${
                      m.role === "user"
                        ? "bg-amber-500/15 text-amber-300 border border-amber-500/30"
                        : "bg-[#151a26] text-zinc-300 border border-[#252b3b]"
                    }`}
                  >
                    {m.role === "user" ? `PRINCIPAL // ${persona.toUpperCase()}` : "RESEARCH BRIEF"}
                  </span>
                </div>
                {m.response && (
                  <div className="flex items-center gap-2 text-[11px] font-mono text-zinc-400 tabular-nums">
                    <span className="text-emerald-400">{m.response.tool_traces.length} calls</span>
                    <span className="text-zinc-600">&bull;</span>
                    <span>{m.response.mode}</span>
                  </div>
                )}
              </div>

              {/* Rendered Body */}
              <div className="px-4 py-3">
                {m.role === "user" ? (
                  <p className="text-sm font-medium text-zinc-100">{m.text}</p>
                ) : (
                  <MarkdownView content={m.text} />
                )}
              </div>

              {/* Provenance Footer */}
              {m.response && m.response.provenance.length > 0 && (
                <div className="px-4 py-2.5 border-t border-[#171b24] bg-[#0b0d12]">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-1.5">
                    Verified Data Provenance ({m.response.provenance.length})
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {m.response.provenance.map((p, idx) => {
                      const isOk = p.status === "OK";
                      const shortTs = p.data_timestamp.slice(11, 19) || p.data_timestamp;
                      return (
                        <span
                          key={`${p.tool}-${idx}`}
                          title={`Source: ${p.source} | Request ID: ${p.request_id} | Timestamp: ${p.data_timestamp}`}
                          className="inline-flex items-center gap-1.5 text-[10.5px] font-mono px-2 py-0.5 rounded bg-[#12151e] border border-[#222736] text-zinc-300 tabular-nums"
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              isOk ? "bg-emerald-400" : "bg-rose-400"
                            }`}
                          />
                          <span className="text-zinc-200">{p.tool}</span>
                          <span className="text-zinc-500">{p.cache_hit ? "HIT" : "LIVE"}</span>
                          <span className="text-zinc-500">{shortTs}Z</span>
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="border border-amber-500/30 bg-amber-500/5 rounded px-4 py-3 flex items-center gap-3 text-xs font-mono text-amber-300">
              <span className="h-2 w-2 rounded-full bg-amber-400 animate-ping" />
              Delegating scoped JWT over Streamable HTTP and executing MCP tool DAG...
            </div>
          )}

          {error && (
            <div className="text-xs font-mono text-rose-300 bg-rose-950/30 border border-rose-800/60 rounded p-3">
              {error}
            </div>
          )}
        </div>

        {/* Composer */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submitPrompt(input);
          }}
          className="p-3 border-t border-[#1e222d] bg-[#0b0d12] flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Command: Compare NVDA vs AVGO over 3M, Generate tearsheet for MSFT, Audit portfolio tail risk..."
            className="flex-1 bg-[#12151e] border border-[#252a38] rounded px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-amber-500"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-4 py-2 rounded bg-amber-500 hover:bg-amber-400 text-[#08090c] font-semibold text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 disabled:opacity-40 transition-colors"
          >
            <Send className="h-3.5 w-3.5" />
            Execute
          </button>
        </form>
      </div>

      {/* Right 4 Cols: MCP Latency Waterfall & Envelope Inspector */}
      <div className="xl:col-span-4 border border-[#1e222d] bg-[#0d0f14] rounded-md flex flex-col max-h-[710px] overflow-hidden">
        <div className="px-4 py-2.5 border-b border-[#1e222d] bg-[#11141c] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="h-3.5 w-3.5 text-amber-400" />
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-zinc-200">
              MCP Call Waterfall
            </h3>
          </div>
          {latestTraces.length > 0 && (
            <span className="text-[11px] font-mono text-zinc-400 tabular-nums">
              {totalTraceMs}ms &bull; {cacheHitCount}/{latestTraces.length} cached
            </span>
          )}
        </div>

        {/* Summary KPI Strip */}
        {latestTraces.length > 0 && (
          <div className="grid grid-cols-3 border-b border-[#191d27] bg-[#0a0c10] text-[11px] font-mono tabular-nums divide-x divide-[#191d27]">
            <div className="px-3 py-2">
              <div className="text-[10px] text-zinc-500 flex items-center gap-1">
                <Layers className="h-3 w-3" /> CALLS
              </div>
              <div className="text-zinc-100 font-semibold mt-0.5">{latestTraces.length}</div>
            </div>
            <div className="px-3 py-2">
              <div className="text-[10px] text-zinc-500 flex items-center gap-1">
                <Clock className="h-3 w-3" /> SUM MS
              </div>
              <div className="text-zinc-100 font-semibold mt-0.5">{totalTraceMs.toFixed(0)}ms</div>
            </div>
            <div className="px-3 py-2">
              <div className="text-[10px] text-zinc-500">CACHE HIT</div>
              <div className="text-emerald-400 font-semibold mt-0.5">
                {Math.round((cacheHitCount / latestTraces.length) * 100)}%
              </div>
            </div>
          </div>
        )}

        <div className="p-3 space-y-2.5 overflow-y-auto flex-1">
          {latestTraces.length === 0 ? (
            <div className="p-4 text-xs text-zinc-500 font-mono leading-relaxed border border-dashed border-[#222736] rounded bg-[#090b0f]">
              Execute a query to inspect per-tool RPC latency bars, progress events, tenant cache status, and
              raw `ResponseEnvelope` payloads.
            </div>
          ) : (
            latestTraces.map((trace, i) => {
              const key = `${trace.tool_name}-${i}`;
              const open = !!expandedTrace[key];
              const widthPct = Math.max(6, Math.min(100, (trace.elapsed_ms / maxTraceMs) * 100));
              const isCached = trace.envelope?.metadata?.cache_hit ?? false;
              const statusLabel = trace.envelope?.status ?? (trace.is_error ? "ERROR" : "OK");

              return (
                <div
                  key={key}
                  className="bg-[#090b0f] border border-[#1e2330] rounded p-2.5 text-xs"
                >
                  <button
                    type="button"
                    onClick={() => setExpandedTrace((prev) => ({ ...prev, [key]: !open }))}
                    className="w-full text-left"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {trace.is_error ? (
                          <AlertTriangle className="h-3.5 w-3.5 text-rose-400 shrink-0" />
                        ) : (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                        )}
                        <span className="font-mono font-semibold text-zinc-100 truncate">
                          {trace.tool_name}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 font-mono text-[11px] text-zinc-400 shrink-0 tabular-nums">
                        <span>{trace.elapsed_ms}ms</span>
                        {open ? (
                          <ChevronDown className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5" />
                        )}
                      </div>
                    </div>

                    {/* Latency Waterfall Bar */}
                    <div className="mt-2 h-1.5 w-full bg-[#151822] rounded-sm overflow-hidden">
                      <div
                        className={`h-full rounded-sm ${
                          trace.is_error
                            ? "bg-rose-500"
                            : isCached
                            ? "bg-emerald-500"
                            : "bg-amber-400"
                        }`}
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                  </button>

                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
                    <span
                      className={`px-1.5 py-0.5 rounded border ${
                        trace.is_error
                          ? "bg-rose-500/10 border-rose-500/30 text-rose-300"
                          : "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                      }`}
                    >
                      {statusLabel}
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-[#141720] border border-[#232836] text-zinc-400">
                      {isCached ? "CACHE HIT" : "BACKEND CALL"}
                    </span>
                    {trace.progress_updates.length > 0 && (
                      <span className="px-1.5 py-0.5 rounded bg-sky-500/10 border border-sky-500/30 text-sky-300">
                        {trace.progress_updates.length} progress events
                      </span>
                    )}
                  </div>

                  {open && (
                    <div className="mt-2.5 pt-2 border-t border-[#181c26]">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] font-mono text-zinc-500">
                          REQ {trace.request_id}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            handleCopy(key, { arguments: trace.arguments, envelope: trace.envelope })
                          }
                          className="inline-flex items-center gap-1 text-[10px] font-mono text-zinc-400 hover:text-amber-300"
                        >
                          {copiedKey === key ? (
                            <>
                              <Check className="h-3 w-3 text-emerald-400" /> Copied
                            </>
                          ) : (
                            <>
                              <Copy className="h-3 w-3" /> Copy JSON
                            </>
                          )}
                        </button>
                      </div>
                      <pre className="p-2 rounded bg-[#06070a] border border-[#1a1f2b] text-[10.5px] font-mono text-zinc-300 overflow-x-auto max-h-60">
                        {JSON.stringify(
                          { arguments: trace.arguments, envelope: trace.envelope },
                          null,
                          2
                        )}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
