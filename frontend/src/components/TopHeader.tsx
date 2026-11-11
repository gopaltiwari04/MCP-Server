"use client";

import { RefreshCw, ShieldCheck, ShieldAlert } from "lucide-react";
import type { HealthResponse, Persona, PersonaId } from "@/lib/types";

interface TopHeaderProps {
  personas: Persona[];
  activePersona: PersonaId;
  onPersonaChange: (id: PersonaId) => void;
  health: HealthResponse | null;
  onRefreshHealth: () => void;
}

export function TopHeader({
  personas,
  activePersona,
  onPersonaChange,
  health,
  onRefreshHealth,
}: TopHeaderProps) {
  const gatewayOk = health?.mcp_gateway?.reachable ?? false;
  const cbState = health?.mcp_gateway?.details?.circuit_breaker?.state ?? "UNKNOWN";
  const cacheStats = health?.mcp_gateway?.details?.cache;
  const totalLookups = (cacheStats?.hits ?? 0) + (cacheStats?.misses ?? 0);
  const hitRatePct = totalLookups > 0 ? Math.round(((cacheStats?.hits ?? 0) / totalLookups) * 100) : null;
  const llmLabel = health?.llm_mode === "openai" ? "OPENAI TOOL LOOP" : "DETERMINISTIC MCP";

  return (
    <header className="border-b border-[#1e222d] bg-[#0b0d12]/95 backdrop-blur sticky top-0 z-30">
      <div className="max-w-[1600px] mx-auto px-4 lg:px-6 h-14 flex items-center justify-between gap-4">
        {/* Left Brand */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-8 w-8 rounded bg-amber-500/15 border border-amber-500/40 flex items-center justify-center font-mono text-xs font-bold tracking-tighter text-amber-400 shrink-0">
            QM
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold tracking-tight text-zinc-100 truncate">
                QuantMCP Terminal
              </span>
              <span className="hidden sm:inline-block text-[10px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded bg-[#141720] text-zinc-400 border border-[#252a38]">
                MCP v2 &bull; Streamable HTTP
              </span>
            </div>
            <p className="hidden md:block text-[11px] font-mono text-zinc-500 truncate">
              Next.js &rarr; Orchestrator &rarr; Zero-Trust MCP Gateway &rarr; Market API
            </p>
          </div>
        </div>

        {/* Right Telemetry & Identity */}
        <div className="flex items-center gap-2.5 shrink-0">
          {/* Telemetry Cluster */}
          <div className="hidden md:flex items-center gap-2.5 text-[11px] font-mono bg-[#10131b] border border-[#1f2431] rounded px-3 py-1.5 tabular-nums">
            <span className="inline-flex items-center gap-1.5">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  gatewayOk ? "bg-emerald-400 shadow-[0_0_8px_#34d399]" : "bg-rose-500"
                }`}
              />
              <span className="text-zinc-500">GW</span>
              <span className={gatewayOk ? "text-emerald-400 font-medium" : "text-rose-400 font-medium"}>
                {gatewayOk ? "READY" : "DOWN"}
              </span>
            </span>

            <span className="text-[#262b38]">|</span>

            <span>
              <span className="text-zinc-500 mr-1">CB</span>
              <span
                className={
                  cbState === "CLOSED"
                    ? "text-zinc-200 font-medium"
                    : cbState === "HALF_OPEN"
                    ? "text-amber-400 font-medium"
                    : "text-rose-400 font-medium"
                }
              >
                {cbState}
              </span>
            </span>

            {cacheStats && (
              <>
                <span className="text-[#262b38]">|</span>
                <span className="text-zinc-400">
                  CACHE{" "}
                  <span className="text-zinc-200">
                    {hitRatePct !== null ? `${hitRatePct}%` : "—"}
                  </span>{" "}
                  <span className="text-zinc-500">
                    ({cacheStats.hits}H/{cacheStats.misses}M/{cacheStats.coalesced_hits}SF)
                  </span>
                </span>
              </>
            )}

            <span className="hidden xl:inline text-[#262b38]">|</span>
            <span className="hidden xl:inline text-amber-300/90">{llmLabel}</span>

            <button
              type="button"
              onClick={onRefreshHealth}
              title="Refresh gateway telemetry"
              className="ml-0.5 p-0.5 text-zinc-500 hover:text-zinc-200 transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
            </button>
          </div>

          {/* Identity Selector */}
          <div className="flex items-center gap-2 bg-[#10131b] border border-[#1f2431] rounded px-2.5 py-1">
            {activePersona === "alice" ? (
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
            ) : (
              <ShieldAlert className="h-3.5 w-3.5 text-amber-400 shrink-0" />
            )}
            <label htmlFor="persona-select" className="hidden sm:inline text-[11px] font-mono text-zinc-500">
              PRINCIPAL
            </label>
            <select
              id="persona-select"
              value={activePersona}
              onChange={(e) => onPersonaChange(e.target.value as PersonaId)}
              className="bg-[#0b0d12] border border-[#282e3d] text-xs font-medium text-zinc-100 rounded px-2 py-1 focus:outline-none focus:border-amber-500"
            >
              {personas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </header>
  );
}
