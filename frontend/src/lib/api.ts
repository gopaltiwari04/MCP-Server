import type {
  ChatResponse,
  HealthResponse,
  McpCatalog,
  Persona,
  PersonaId,
  ToolTrace,
} from "./types";

const BASE = "/api/orchestrator";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${body.slice(0, 300)}`);
  }
  return (await resp.json()) as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>(`${BASE}/health`);
}

export function fetchPersonas(): Promise<Persona[]> {
  return requestJson<Persona[]>(`${BASE}/personas`);
}

export function fetchMcpCatalog(persona: PersonaId): Promise<McpCatalog> {
  return requestJson<McpCatalog>(`${BASE}/mcp/catalog?persona=${encodeURIComponent(persona)}`);
}

export function executeMcpTool<T = Record<string, unknown>>(
  persona: PersonaId,
  toolName: string,
  args: Record<string, unknown>
): Promise<ToolTrace<T>> {
  return requestJson<ToolTrace<T>>(`${BASE}/mcp/tools/${encodeURIComponent(toolName)}`, {
    method: "POST",
    body: JSON.stringify({ persona, arguments: args }),
  });
}

export function readMcpResource(
  persona: PersonaId,
  uri: string
): Promise<{
  uri: string;
  is_error: boolean;
  error_message?: string;
  contents?: Array<{ uri: string; mime_type: string | null; text: string | null }>;
  request_id: string;
}> {
  return requestJson(
    `${BASE}/mcp/resources/read?persona=${encodeURIComponent(persona)}&uri=${encodeURIComponent(uri)}`
  );
}

export function renderMcpPrompt(
  persona: PersonaId,
  promptName: string,
  args: Record<string, string>
): Promise<{
  name: string;
  description: string | null;
  messages: Array<{ role: string; text: string }>;
  request_id: string;
}> {
  return requestJson(`${BASE}/mcp/prompts/${encodeURIComponent(promptName)}`, {
    method: "POST",
    body: JSON.stringify({ persona, arguments: args }),
  });
}

export function sendChatPrompt(persona: PersonaId, prompt: string): Promise<ChatResponse> {
  return requestJson<ChatResponse>(`${BASE}/chat`, {
    method: "POST",
    body: JSON.stringify({ persona, prompt }),
  });
}
