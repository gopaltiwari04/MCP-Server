"use client";

import { useCallback, useEffect, useState } from "react";
import { Bot, LineChart, Briefcase, TerminalSquare, Lock, ShieldCheck } from "lucide-react";
import { fetchHealth, fetchPersonas } from "@/lib/api";
import type { HealthResponse, Persona, PersonaId } from "@/lib/types";
import { TopHeader } from "@/components/TopHeader";
import { OrchestratorChat } from "@/components/OrchestratorChat";
import { MarketWorkbench } from "@/components/MarketWorkbench";
import { PortfolioPanel } from "@/components/PortfolioPanel";
import { ProtocolExplorer } from "@/components/ProtocolExplorer";

type TabId = "chat" | "market" | "portfolio" | "protocol";

const FALLBACK_PERSONAS: Persona[] = [
  {
    id: "alice",
    user_id: "user_alice",
    display_name: "Alice (Portfolio Manager)",
    role_title: "Full Access",
    scopes: ["market:read", "portfolio:read", "portfolio:write", "simulation:execute", "research:write"],
  },
  {
    id: "bob",
    user_id: "user_bob",
    display_name: "Bob (Read-Only Analyst)",
    role_title: "market:read only",
    scopes: ["market:read"],
  },
];

export default function HomePage() {
  const [tab, setTab] = useState<TabId>("chat");
  const [persona, setPersona] = useState<PersonaId>("alice");
  const [personas, setPersonas] = useState<Persona[]>(FALLBACK_PERSONAS);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const refreshHealth = useCallback(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    fetchPersonas()
      .then(setPersonas)
      .catch(() => setPersonas(FALLBACK_PERSONAS));
    refreshHealth();
  }, [refreshHealth]);

  const activeProfile = personas.find((p) => p.id === persona) ?? FALLBACK_PERSONAS[0];

  const tabs: Array<{ id: TabId; label: string; sub: string; icon: React.ReactNode }> = [
    { id: "chat", label: "AI Analyst", sub: "Orchestrator & traces", icon: <Bot className="h-4 w-4" /> },
    { id: "market", label: "Market & Compare", sub: "OHLCV, regime & corr", icon: <LineChart className="h-4 w-4" /> },
    { id: "portfolio", label: "Portfolio & Risk", sub: "VaR, CVaR & rebalance", icon: <Briefcase className="h-4 w-4" /> },
    { id: "protocol", label: "MCP Inspector", sub: "15 tools · 4 URIs · prompts", icon: <TerminalSquare className="h-4 w-4" /> },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-[#08090c] terminal-grid-bg">
      <TopHeader
        personas={personas}
        activePersona={persona}
        onPersonaChange={setPersona}
        health={health}
        onRefreshHealth={refreshHealth}
      />

      <div className="flex-1 max-w-[1600px] w-full mx-auto flex flex-col lg:flex-row">
        {/* Desktop Navigation Rail */}
        <aside className="hidden lg:flex w-60 shrink-0 flex-col justify-between border-r border-[#1e222d] bg-[#0a0c10]/90 p-3">
          <div className="space-y-4">
            <div className="px-2 pt-1">
              <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                Workspaces
              </div>
            </div>
            <nav className="space-y-1">
              {tabs.map((t) => {
                const active = tab === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTab(t.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded text-left border-l-2 transition-colors ${
                      active
                        ? "border-amber-400 bg-[#141720] text-zinc-100"
                        : "border-transparent text-zinc-400 hover:bg-[#10131b] hover:text-zinc-200"
                    }`}
                  >
                    <span className={active ? "text-amber-400" : "text-zinc-500"}>{t.icon}</span>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold leading-tight">{t.label}</div>
                      <div className="text-[10.5px] font-mono text-zinc-500 truncate mt-0.5">{t.sub}</div>
                    </div>
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Active Security Context Panel */}
          <div className="border border-[#1f2431] bg-[#0e1016] rounded p-3 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                ContextVar Session
              </span>
              {persona === "alice" ? (
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              ) : (
                <Lock className="h-3.5 w-3.5 text-amber-400" />
              )}
            </div>
            <div className="space-y-0.5">
              <div className="text-xs font-mono font-semibold text-zinc-200">{activeProfile.user_id}</div>
              <div className="text-[10.5px] text-zinc-500 leading-snug">{activeProfile.role_title}</div>
            </div>
            <div className="pt-1 border-t border-[#1c202c]">
              <div className="text-[10px] font-mono text-zinc-500 mb-1.5">DELEGATED JWT SCOPES</div>
              <div className="flex flex-wrap gap-1">
                {activeProfile.scopes.map((sc) => (
                  <span
                    key={sc}
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#141824] border border-[#242a3a] text-zinc-300"
                  >
                    {sc}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </aside>

        {/* Mobile Tab Strip */}
        <div className="lg:hidden border-b border-[#1e222d] bg-[#0a0c10] px-4 py-2 flex gap-1.5 overflow-x-auto">
          {tabs.map((t) => {
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap border transition-colors ${
                  active
                    ? "bg-[#151822] border-amber-500/60 text-amber-300"
                    : "bg-[#0e1016] border-[#1f2431] text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {t.icon}
                {t.label}
              </button>
            );
          })}
        </div>

        {/* Main Workspace Surface */}
        <main className="flex-1 min-w-0 p-4 lg:p-6">
          {tab === "chat" && <OrchestratorChat persona={persona} />}
          {tab === "market" && <MarketWorkbench persona={persona} />}
          {tab === "portfolio" && <PortfolioPanel persona={persona} onSwitchPersona={setPersona} />}
          {tab === "protocol" && <ProtocolExplorer persona={persona} />}
        </main>
      </div>
    </div>
  );
}
