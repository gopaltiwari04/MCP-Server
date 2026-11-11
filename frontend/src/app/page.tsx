"use client";

import { useCallback, useEffect, useState } from "react";
import { Bot, LineChart, Briefcase, TerminalSquare } from "lucide-react";
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

  const tabs: Array<{ id: TabId; label: string; icon: React.ReactNode }> = [
    { id: "chat", label: "AI Analyst", icon: <Bot className="h-4 w-4" /> },
    { id: "market", label: "Market & Compare", icon: <LineChart className="h-4 w-4" /> },
    { id: "portfolio", label: "Portfolio & Risk", icon: <Briefcase className="h-4 w-4" /> },
    { id: "protocol", label: "MCP Inspector", icon: <TerminalSquare className="h-4 w-4" /> },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      <TopHeader
        personas={personas}
        activePersona={persona}
        onPersonaChange={setPersona}
        health={health}
        onRefreshHealth={refreshHealth}
      />

      <main className="flex-1 max-w-[1440px] w-full mx-auto px-4 sm:px-6 py-5 space-y-5">
        <nav className="flex flex-wrap gap-2 border-b border-slate-800/80 pb-3">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium border transition-colors ${
                tab === t.id
                  ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-300"
                  : "bg-slate-900/70 border-slate-800 text-slate-300 hover:border-slate-700"
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </nav>

        {tab === "chat" && <OrchestratorChat persona={persona} />}
        {tab === "market" && <MarketWorkbench persona={persona} />}
        {tab === "portfolio" && <PortfolioPanel persona={persona} />}
        {tab === "protocol" && <ProtocolExplorer persona={persona} />}
      </main>
    </div>
  );
}
