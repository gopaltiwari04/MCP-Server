"use client";

import { Activity, ShieldCheck, ShieldAlert, Cpu, RefreshCw } from "lucide-react";
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
  const current = personas.find((p) => p.id === activePersona);
  const gatewayOk = health?.mcp_gateway?.reachable ?? false;
  const cbState = health?.mcp_gateway?.details?.circuit_breaker?.state ?? "UNKNOWN";
  const cacheStats = health?.mcp_gateway?.details?.cache;

  return (
    <header className="border-b border-slate-800/80 bg-[#0b101b]/95 backdrop-blur sticky top-0 z-30">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-3 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Cpu className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-semibold tracking-tight text-slate-100">
                Market Intelligence MCP Terminal
              </h1>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                MCP v2 / Streamable HTTP
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Next.js &rarr; FastAPI Orchestrator &rarr; Zero-Trust MCP Gateway &rarr; Market Backend
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Health & Resilience Pills */}
          <div className="flex items-center gap-2 text-xs bg-slate-900/90 border border-slate-800 rounded-lg px-3 py-1.5">
            <Activity className={`h-3.5 w-3.5 ${gatewayOk ? "text-emerald-400" : "text-rose-400"}`} />
            <span className="text-slate-400">Gateway:</span>
            <span className={`font-mono font-medium ${gatewayOk ? "text-emerald-400" : "text-rose-400"}`}>
              {gatewayOk ? "READY" : "OFFLINE"}
            </span>
            <span className="text-slate-700">|</span>
            <span className="text-slate-400">CB:</span>
            <span
              className={`font-mono font-medium ${
                cbState === "CLOSED"
                  ? "text-emerald-400"
                  : cbState === "HALF_OPEN"
                  ? "text-amber-400"
                  : "text-rose-400"
              }`}
            >
              {cbState}
            </span>
            {cacheStats && (
              <>
                <span className="text-slate-700">|</span>
                <span className="text-slate-400 font-mono">
                  Cache {cacheStats.hits}H/{cacheStats.misses}M ({cacheStats.coalesced_hits}SF)
                </span>
              </>
            )}
            <button
              type="button"
              onClick={onRefreshHealth}
              title="Refresh gateway health"
              className="ml-1 text-slate-400 hover:text-slate-200 transition-colors"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Zero-Trust Identity Switcher */}
          <div className="flex items-center gap-2 bg-slate-900/90 border border-slate-800 rounded-lg px-2.5 py-1.5">
            {activePersona === "alice" ? (
              <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
            ) : (
              <ShieldAlert className="h-4 w-4 text-amber-400 shrink-0" />
            )}
            <label htmlFor="persona-select" className="text-xs text-slate-400">
              Identity:
            </label>
            <select
              id="persona-select"
              value={activePersona}
              onChange={(e) => onPersonaChange(e.target.value as PersonaId)}
              className="bg-slate-950 border border-slate-700 text-xs text-slate-100 rounded px-2 py-1 focus:outline-none focus:border-emerald-500"
            >
              {personas.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
            {current && (
              <div className="hidden xl:flex items-center gap-1 ml-1">
                {current.scopes.map((sc) => (
                  <span
                    key={sc}
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/90 text-emerald-300 border border-slate-700/70"
                  >
                    {sc}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
