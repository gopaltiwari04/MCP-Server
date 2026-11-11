"""FastAPI AI Orchestrator HTTP endpoints consumed by the Next.js frontend."""

from __future__ import annotations

import uuid
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import get_orchestrator_settings
from app.mcp_bridge import PERSONAS, MCPGatewayBridge, resolve_persona
from app.planner import run_orchestrated_chat

settings = get_orchestrator_settings()
bridge = MCPGatewayBridge(settings)

app = FastAPI(
    title="Market Intelligence AI Orchestrator",
    version="1.0.0",
    description="Orchestrator & Zero-Trust MCP Client sitting between Next.js UI and market-intelligence-mcp.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ToolExecuteRequest(BaseModel):
    persona: str = "alice"
    arguments: dict[str, Any] = Field(default_factory=dict)


class PromptExecuteRequest(BaseModel):
    persona: str = "alice"
    arguments: dict[str, str] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    persona: str = "alice"
    prompt: str = Field(..., min_length=1, max_length=2000)


@app.get("/api/v1/health")
async def health() -> dict[str, Any]:
    mcp_status = await bridge.gateway_health()
    return {
        "orchestrator": "healthy",
        "mcp_gateway": mcp_status,
        "llm_mode": "openai" if (settings.openai_api_key and settings.openai_api_key.get_secret_value().strip()) else "deterministic_mcp_planner",
    }


@app.get("/api/v1/personas")
async def list_personas() -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "user_id": p.user_id,
            "display_name": p.display_name,
            "role_title": p.role_title,
            "scopes": p.scopes,
        }
        for p in PERSONAS.values()
    ]


@app.get("/api/v1/mcp/catalog")
async def get_mcp_catalog(persona: str = Query("alice")) -> dict[str, Any]:
    try:
        resolved = resolve_persona(persona)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await bridge.list_catalog(resolved)


@app.post("/api/v1/mcp/tools/{tool_name}")
async def execute_mcp_tool(tool_name: str, body: ToolExecuteRequest) -> dict[str, Any]:
    try:
        resolved = resolve_persona(body.persona)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await bridge.call_tool(resolved, tool_name, body.arguments)


@app.get("/api/v1/mcp/resources/read")
async def read_mcp_resource(uri: str = Query(...), persona: str = Query("alice")) -> dict[str, Any]:
    try:
        resolved = resolve_persona(persona)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await bridge.read_resource(resolved, uri)


@app.post("/api/v1/mcp/prompts/{prompt_name}")
async def render_mcp_prompt(prompt_name: str, body: PromptExecuteRequest) -> dict[str, Any]:
    try:
        resolved = resolve_persona(body.persona)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await bridge.get_prompt(resolved, prompt_name, body.arguments)


@app.post("/api/v1/chat")
async def chat_endpoint(body: ChatRequest) -> dict[str, Any]:
    try:
        resolved = resolve_persona(body.persona)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    req_id = f"chat-{uuid.uuid4().hex[:12]}"
    return await run_orchestrated_chat(
        prompt=body.prompt,
        persona=resolved,
        bridge=bridge,
        settings=settings,
        request_id=req_id,
    )


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
