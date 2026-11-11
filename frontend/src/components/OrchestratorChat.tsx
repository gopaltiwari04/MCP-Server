"use client";

import { useState } from "react";
import { Send, Terminal, ChevronDown, ChevronRight, CheckCircle2, AlertTriangle, Sparkles } from "lucide-react";
import { sendChatPrompt } from "@/lib/api";
import type { ChatResponse, PersonaId } from "@/lib/types";

interface MessageItem {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}

const PRESET_PROMPTS = [
  "Compare NVDA vs AMD over 1M",
  "Generate institutional tearsheet for NVDA",
  "Audit portfolio tail risk and simulate rebalance",
  "Compare NVDA vs AZN.L over 3M cross-exchange",
];

export function OrchestratorChat({ persona }: { persona: PersonaId }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTrace, setExpandedTrace] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<MessageItem[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "Ready. Prompts are routed through the FastAPI AI Orchestrator, which delegates your scoped JWT over Streamable HTTP to `market-intelligence-mcp`. Select a preset workflow or type any market/portfolio question.",
    },
  ]);

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
      setError(err instanceof Error ? err.message : "Failed to run orchestrated MCP query");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
      <div className="xl:col-span-2 flex flex-col bg-slate-900/70 border border-slate-800 rounded-xl overflow-hidden min-h-[620px]">
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-emerald-400" />
            <h2 className="text-sm font-semibold text-slate-100">AI Quantitative Orchestrator</h2>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            Active Persona: <strong className="text-emerald-300">{persona}</strong>
          </span>
        </div>

        {/* Preset prompt pills */}
        <div className="px-4 py-2.5 border-b border-slate-800/70 flex flex-wrap gap-2 bg-slate-950/40">
          {PRESET_PROMPTS.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => submitPrompt(preset)}
              disabled={loading}
              className="text-xs px-2.5 py-1 rounded-md bg-slate-800/80 hover:bg-slate-700/80 text-slate-200 border border-slate-700/80 transition-colors disabled:opacity-50"
            >
              {preset}
            </button>
          ))}
        </div>

        {/* Message stream */}
        <div className="flex-1 p-4 space-y-4 overflow-y-auto max-h-[520px]">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`rounded-xl p-4 border ${
                m.role === "user"
                  ? "bg-emerald-950/30 border-emerald-800/40 ml-8"
                  : "bg-slate-950/70 border-slate-800 mr-4"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400">
                  {m.role === "user" ? `Analyst (${persona})` : "Orchestrator Output"}
                </span>
                {m.response && (
                  <span className="text-[11px] font-mono text-emerald-400">
                    {m.response.tool_traces.length} MCP tool calls ({m.response.mode})
                  </span>
                )}
              </div>
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-200">
                {m.text}
              </pre>

              {/* Provenance Footer */}
              {m.response && m.response.provenance.length > 0 && (
                <div className="mt-3 pt-3 border-t border-slate-800/80">
                  <div className="text-[11px] font-mono text-slate-400 mb-1.5">
                    Data Provenance Citations:
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {m.response.provenance.map((p, idx) => (
                      <span
                        key={`${p.tool}-${idx}`}
                        className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300"
                      >
                        {p.tool} &bull; {p.status} &bull; {p.cache_hit ? "HIT" : "MISS"} &bull;{" "}
                        {p.data_timestamp}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="text-xs font-mono text-emerald-400 animate-pulse px-2">
              Executing delegated MCP Streamable HTTP tool pipeline...
            </div>
          )}
          {error && (
            <div className="text-xs text-rose-300 bg-rose-950/40 border border-rose-800/60 rounded-lg p-3">
              {error}
            </div>
          )}
        </div>

        {/* Input box */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submitPrompt(input);
          }}
          className="p-3 border-t border-slate-800 bg-slate-900/90 flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about equities (NVDA, AMD, AAPL), comparisons, technicals, or portfolio risk..."
            className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-semibold text-sm flex items-center gap-1.5 disabled:opacity-50 transition-colors"
          >
            <Send className="h-4 w-4" />
            Run
          </button>
        </form>
      </div>

      {/* Right Rail: Live MCP Tool Execution Trace */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 flex flex-col max-h-[680px] overflow-y-auto">
        <div className="flex items-center gap-2 pb-3 border-b border-slate-800 mb-3">
          <Terminal className="h-4 w-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-slate-100">Live MCP Tool Traces</h3>
        </div>
        {messages
          .filter((m) => m.response)
          .slice(-1)
          .flatMap((m) => m.response?.tool_traces ?? [])
          .map((trace, i) => {
            const key = `${trace.tool_name}-${i}`;
            const open = !!expandedTrace[key];
            return (
              <div
                key={key}
                className="mb-2.5 bg-slate-950/80 border border-slate-800 rounded-lg p-3 text-xs"
              >
                <button
                  type="button"
                  onClick={() => setExpandedTrace((prev) => ({ ...prev, [key]: !open }))}
                  className="w-full flex items-center justify-between text-left"
                >
                  <div className="flex items-center gap-2">
                    {trace.is_error ? (
                      <AlertTriangle className="h-3.5 w-3.5 text-rose-400 shrink-0" />
                    ) : (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                    )}
                    <span className="font-mono font-semibold text-slate-100">{trace.tool_name}</span>
                  </div>
                  <div className="flex items-center gap-2 text-slate-400 font-mono">
                    <span>{trace.elapsed_ms}ms</span>
                    {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  </div>
                </button>
                <div className="mt-1.5 flex flex-wrap gap-2 text-[11px] font-mono text-slate-400">
                  <span>status: {trace.envelope?.status ?? "ERR"}</span>
                  <span>cache: {trace.envelope?.metadata?.cache_hit ? "HIT" : "MISS"}</span>
                  {trace.progress_updates.length > 0 && (
                    <span className="text-emerald-400">
                      progress: {trace.progress_updates.length} events
                    </span>
                  )}
                </div>
                {open && (
                  <pre className="mt-2 p-2 rounded bg-slate-900 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-60">
                    {JSON.stringify({ arguments: trace.arguments, envelope: trace.envelope }, null, 2)}
                  </pre>
                )}
              </div>
            );
          })}
        {messages.every((m) => !m.response) && (
          <p className="text-xs text-slate-500">
            Run any query to inspect the delegated MCP JSON-RPC tool calls, progress notifications, and
            ResponseEnvelope provenance here.
          </p>
        )}
      </div>
    </div>
  );
}
