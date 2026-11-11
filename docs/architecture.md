# Architecture & Security Model

## High-Level Topology

```text
+-----------------------+       HTTPS / Streamable HTTP        +---------------------------+
| External AI Clients   | -----------------------------------> | Reverse Proxy (Caddy/     |
| (Claude, Cursor,      |       OAuth 2.1 Bearer JWT           | Nginx: no SSE buffering)  |
|  MCP Inspector)       |                                      +-------------+-------------+
+-----------------------+                                                    |
                                                                             v  edge_net
+-----------------------+       Internal HTTP +                +---------------------------+
| In-Product AI         |       X-Internal-API-Key +           | market-intelligence-mcp   |
| Orchestrator          | ----> Delegated User JWT ----------> | (ASGI Auth Middleware ->  |
+-----------------------+                                      |  ContextVar -> MCPServer  |
                                                               |  -> SingleFlightCache ->  |
                                                               |  CircuitBreaker -> HTTPX) |
                                                               +-------------+-------------+
                                                                             |
                                                                             v  internal_net
                                                               +---------------------------+
                                                               | FastAPI Market Backend    |
                                                               | (PostgreSQL / Market Data)|
                                                               +---------------------------+
```

## Zero-Trust Identity Propagation

1. **No LLM-Visible Identity Arguments:** None of the 15 `@mcp.tool()` signatures accept `user_id`, `api_key`, or `token` arguments, eliminating prompt-injection identity spoofing.
2. **ASGI Authentication Middleware (`app/auth/middleware.py`):**
   - Inspects `X-Internal-API-Key` (via constant-time `secrets.compare_digest`) + `Authorization: Bearer <delegated_jwt>`, **or** validates external OAuth 2.1 Bearer JWTs (`iss`, `aud`, `exp`, `sub`, `scope`/`scp`, signature via JWKS or configured key).
   - Populates an immutable `RequestSecurityContext` inside `contextvars.ContextVar` and sets Starlette's `scope["user"]` so `StreamableHTTPSessionManager` binds every `Mcp-Session-Id` to the originating principal.
   - Enforces per-principal sliding-window rate limits (`429 RATE_LIMITED`).
3. **Outbound Propagation (`app/clients/backend_client.py`):**
   - Extracts `RequestSecurityContext` and current MCP tool name from `ContextVar`s and injects `X-Internal-API-Key`, `Authorization: Bearer <jwt>`, `X-Request-ID`, and `X-MCP-Tool-Name` on every outbound FastAPI call.

## Resilience, Single-Flight Caching & Multi-Tenancy

- **Tenant-Isolated Cache Keys (`app/clients/cache.py`):** Keys are SHA-256 digests of `(tenant_scope, method, endpoint, canonical_params, canonical_body)`. Public market endpoints use `tenant_scope="PUBLIC"`, while `portfolio:*` and `research:*` endpoints strictly use `tenant_scope=sec_ctx.user_id`.
- **Single-Flight Coalescing:** Concurrent identical misses await a shared `asyncio.Future` (wrapped in `asyncio.shield` so one caller's cancellation does not abort peers).
- **Circuit Breaker (`app/clients/circuit_breaker.py`):** Trips `CLOSED -> OPEN` after 5 consecutive upstream 5xx/transport failures for a 15-second cooldown (`UPSTREAM_CIRCUIT_OPEN`), then allows a single probe in `HALF_OPEN`. HTTP 4xx errors do not trip the breaker.
- **Bounded Retries:** Up to 2 retries with full jitter (`uniform(0, min(2.0, 0.2 * 2^attempt))`) strictly for `ConnectError`, `ReadTimeout`, `PoolTimeout`, and HTTP `502/503/504`.
