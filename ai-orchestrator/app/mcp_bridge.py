"""Delegated JWT minting and zero-trust MCP Streamable HTTP client bridge."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import httpx2
import jwt
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client

from app.config import OrchestratorSettings


@dataclass(frozen=True, slots=True)
class UserPersona:
    id: str
    user_id: str
    display_name: str
    role_title: str
    scopes: list[str]
    client_id: str = "nextjs-market-terminal"


PERSONAS: dict[str, UserPersona] = {
    "alice": UserPersona(
        id="alice",
        user_id="user_alice",
        display_name="Alice (Portfolio Manager)",
        role_title="Institutional PM — Full Read/Write & Simulation Scopes",
        scopes=[
            "market:read",
            "portfolio:read",
            "portfolio:write",
            "simulation:execute",
            "research:write",
        ],
    ),
    "bob": UserPersona(
        id="bob",
        user_id="user_bob",
        display_name="Bob (External Read-Only Analyst)",
        role_title="Market Research Analyst — market:read Scope Only",
        scopes=["market:read"],
    ),
}


def resolve_persona(persona_id: str) -> UserPersona:
    key = persona_id.strip().lower()
    if key not in PERSONAS:
        raise ValueError(f"Unknown persona {persona_id!r}. Choose from {list(PERSONAS)}.")
    return PERSONAS[key]


def mint_delegated_jwt(persona: UserPersona, settings: OrchestratorSettings) -> str:
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "sub": persona.user_id,
        "azp": persona.client_id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + 900,
        "scope": " ".join(persona.scopes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")


class MCPGatewayBridge:
    """Zero-trust MCP Streamable HTTP client delegating caller identity per request."""

    def __init__(self, settings: OrchestratorSettings) -> None:
        self.settings = settings

    def _auth_headers(self, persona: UserPersona, request_id: str | None = None) -> tuple[dict[str, str], str]:
        corr_id = request_id or f"orch-{uuid.uuid4().hex[:12]}"
        token = mint_delegated_jwt(persona, self.settings)
        headers = {
            "X-Internal-API-Key": self.settings.internal_api_key.get_secret_value(),
            "Authorization": f"Bearer {token}",
            "X-Request-ID": corr_id,
        }
        return headers, corr_id

    async def gateway_health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(self.settings.mcp_health_url)
                return {
                    "reachable": resp.status_code == 200,
                    "status_code": resp.status_code,
                    "details": resp.json() if resp.content else {},
                }
        except Exception as exc:
            return {"reachable": False, "status_code": 503, "details": {"error": type(exc).__name__}}

    async def list_catalog(self, persona: UserPersona, request_id: str | None = None) -> dict[str, Any]:
        headers, corr_id = self._auth_headers(persona, request_id)
        async with httpx2.AsyncClient(headers=headers, timeout=15.0) as http_client:
            transport = streamable_http_client(self.settings.mcp_url, http_client=http_client)
            async with Client(transport) as client:
                tools_res = await client.list_tools()
                resources_res = await client.list_resources()
                templates_res = await client.list_resource_templates()
                prompts_res = await client.list_prompts()

        return {
            "request_id": corr_id,
            "persona": persona.id,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools_res.tools
            ],
            "resources": [
                {
                    "uri": str(r.uri),
                    "name": r.name,
                    "title": r.title,
                    "description": r.description,
                    "mime_type": r.mime_type,
                }
                for r in resources_res.resources
            ],
            "resource_templates": [
                {
                    "uri_template": rt.uri_template,
                    "name": rt.name,
                    "title": rt.title,
                    "description": rt.description,
                    "mime_type": rt.mime_type,
                }
                for rt in templates_res.resource_templates
            ],
            "prompts": [
                {
                    "name": p.name,
                    "title": p.title,
                    "description": p.description,
                    "arguments": [
                        {"name": a.name, "description": a.description, "required": a.required}
                        for a in (p.arguments or [])
                    ],
                }
                for p in prompts_res.prompts
            ],
        }

    async def call_tool(
        self,
        persona: UserPersona,
        tool_name: str,
        arguments: dict[str, Any],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        headers, corr_id = self._auth_headers(persona, request_id)
        progress_updates: list[dict[str, Any]] = []

        async def _on_progress(progress: float, total: float | None, message: str | None) -> None:
            progress_updates.append({"progress": progress, "total": total, "message": message})

        t0 = time.perf_counter()
        async with httpx2.AsyncClient(headers=headers, timeout=20.0) as http_client:
            transport = streamable_http_client(self.settings.mcp_url, http_client=http_client)
            async with Client(transport) as client:
                result = await client.call_tool(tool_name, arguments, progress_callback=_on_progress)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        envelope: dict[str, Any] | None = None
        markdown: str | None = None
        if result.content:
            first_text = getattr(result.content[0], "text", None)
            if first_text:
                try:
                    envelope = json.loads(first_text)
                except ValueError:
                    markdown = first_text
            if len(result.content) > 1:
                markdown = getattr(result.content[1], "text", None)

        if envelope is None and result.structured_content:
            envelope = result.structured_content

        return {
            "tool_name": tool_name,
            "arguments": arguments,
            "is_error": bool(result.is_error),
            "elapsed_ms": elapsed_ms,
            "request_id": corr_id,
            "progress_updates": progress_updates,
            "envelope": envelope,
            "markdown": markdown,
        }

    async def read_resource(
        self,
        persona: UserPersona,
        uri: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        headers, corr_id = self._auth_headers(persona, request_id)
        async with httpx2.AsyncClient(headers=headers, timeout=15.0) as http_client:
            transport = streamable_http_client(self.settings.mcp_url, http_client=http_client)
            async with Client(transport) as client:
                try:
                    res = await client.read_resource(uri)
                except MCPError as exc:
                    return {
                        "uri": uri,
                        "is_error": True,
                        "error_message": exc.message,
                        "request_id": corr_id,
                    }

        contents = [
            {
                "uri": str(c.uri),
                "mime_type": c.mime_type,
                "text": getattr(c, "text", None),
            }
            for c in res.contents
        ]
        return {"uri": uri, "is_error": False, "contents": contents, "request_id": corr_id}

    async def get_prompt(
        self,
        persona: UserPersona,
        name: str,
        arguments: dict[str, str],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        headers, corr_id = self._auth_headers(persona, request_id)
        async with httpx2.AsyncClient(headers=headers, timeout=15.0) as http_client:
            transport = streamable_http_client(self.settings.mcp_url, http_client=http_client)
            async with Client(transport) as client:
                res = await client.get_prompt(name, arguments)

        messages = [
            {"role": m.role, "text": getattr(m.content, "text", "")}
            for m in res.messages
        ]
        return {
            "name": name,
            "description": res.description,
            "messages": messages,
            "request_id": corr_id,
        }
