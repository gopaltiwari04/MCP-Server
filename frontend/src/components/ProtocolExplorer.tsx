"use client";

import { useEffect, useState } from "react";
import { Boxes, FileCode2, MessageSquareCode } from "lucide-react";
import { fetchMcpCatalog, readMcpResource, renderMcpPrompt } from "@/lib/api";
import type { McpCatalog, PersonaId } from "@/lib/types";

export function ProtocolExplorer({ persona }: { persona: PersonaId }) {
  const [catalog, setCatalog] = useState<McpCatalog | null>(null);
  const [resourceUri, setResourceUri] = useState("market://system/capabilities");
  const [resourceOutput, setResourceOutput] = useState<string>("");
  const [promptOutput, setPromptOutput] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    fetchMcpCatalog(persona)
      .then(setCatalog)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed loading MCP catalog"));
  }, [persona]);

  async function handleReadResource(uri: string) {
    setResourceUri(uri);
    const res = await readMcpResource(persona, uri);
    if (res.is_error) {
      setResourceOutput(`ERROR: ${res.error_message}`);
    } else {
      setResourceOutput(res.contents?.[0]?.text ?? "");
    }
  }

  async function handleRenderPrompt(name: string, args: Record<string, string>) {
    const res = await renderMcpPrompt(persona, name, args);
    setPromptOutput(res.messages.map((m) => `[${m.role}]\n${m.text}`).join("\n\n"));
  }

  return (
    <div className="space-y-5">
      {error && (
        <div className="text-xs text-rose-300 bg-rose-950/40 border border-rose-800 rounded-lg p-3">
          {error}
        </div>
      )}

      {catalog && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Discovered Tools */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 max-h-[560px] overflow-y-auto">
            <div className="flex items-center gap-2 pb-2.5 border-b border-slate-800 mb-3">
              <Boxes className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-slate-100">
                Registered Tools ({catalog.tools.length})
              </h3>
            </div>
            <div className="space-y-2">
              {catalog.tools.map((t) => (
                <div key={t.name} className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5">
                  <div className="font-mono text-xs font-semibold text-emerald-300">{t.name}</div>
                  <div className="text-[11px] text-slate-400 mt-1 line-clamp-2">{t.description}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Resources & Templates */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2 pb-2.5 border-b border-slate-800">
              <FileCode2 className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-slate-100">MCP Resources &amp; Templates</h3>
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
                  className={`text-[11px] font-mono px-2 py-1 rounded border ${
                    resourceUri === uri
                      ? "bg-emerald-500/20 border-emerald-500 text-emerald-300"
                      : "bg-slate-950 border-slate-800 text-slate-300"
                  }`}
                >
                  {uri}
                </button>
              ))}
            </div>
            <pre className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-[11px] font-mono text-slate-300 overflow-auto max-h-[390px] whitespace-pre-wrap">
              {resourceOutput || "Click a resource URI above to inspect live MCP resource contents."}
            </pre>
          </div>

          {/* Prompts */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2 pb-2.5 border-b border-slate-800">
              <MessageSquareCode className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-slate-100">
                Institutional Prompts ({catalog.prompts.length})
              </h3>
            </div>
            <div className="space-y-1.5">
              {catalog.prompts.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => {
                    const defaultArgs: Record<string, string> =
                      p.name === "institutional_equity_tearsheet"
                        ? { symbol: "NVDA", benchmark: "SPY" }
                        : p.name === "multi_stock_relative_value_comparison"
                        ? { symbols_csv: "NVDA,AMD", period: "1M" }
                        : p.name === "pairs_trading_screen"
                        ? { symbol_a: "NVDA", symbol_b: "AMD", lookback_period: "6M" }
                        : { portfolio_id: "port_123" };
                    void handleRenderPrompt(p.name, defaultArgs);
                  }}
                  className="w-full text-left bg-slate-950/70 hover:bg-slate-800 border border-slate-800 rounded-lg p-2.5"
                >
                  <div className="font-mono text-xs font-semibold text-emerald-300">{p.name}</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">{p.description}</div>
                </button>
              ))}
            </div>
            <pre className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-[11px] font-mono text-slate-300 overflow-auto max-h-[240px] whitespace-pre-wrap">
              {promptOutput || "Click any prompt above to render its institutional MCP workflow."}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
