"""Security & multi-tenant isolation tests: JWT validation, scopes, cache isolation, rate limits."""

import json

import httpx
import httpx2
import pytest
import respx
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client

from app.auth.middleware import SlidingWindowRateLimiter
from app.main import create_asgi_app
from tests.conftest import (
    INTERNAL_API_KEY,
    FakeClock,
    enter_asgi_lifespan,
    make_internal_jwt,
    make_oauth_jwt,
)


@pytest.mark.asyncio
async def test_unauthenticated_and_invalid_tokens_rejected_with_401(test_settings, respx_backend) -> None:
    app = create_asgi_app(test_settings, configure_logs=False)

    async with enter_asgi_lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as http_client:
            # Public health and RFC 9728 OAuth discovery succeed without auth
            live = await http_client.get("/health/live")
            assert live.status_code == 200
            ready = await http_client.get("/health/ready")
            assert ready.status_code == 200
            meta = await http_client.get("/.well-known/oauth-protected-resource")
            assert meta.status_code == 200
            assert "authorization_servers" in meta.json()

            # Missing credentials -> 401 + WWW-Authenticate
            r_no_auth = await http_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            assert r_no_auth.status_code == 401
            assert "www-authenticate" in r_no_auth.headers

            # Wrong X-Internal-API-Key -> 401
            valid_internal_jwt = make_internal_jwt()
            r_bad_key = await http_client.post(
                "/mcp",
                headers={
                    "X-Internal-API-Key": "wrong-key",
                    "Authorization": f"Bearer {valid_internal_jwt}",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert r_bad_key.status_code == 401

            # Expired OAuth JWT -> 401
            expired_oauth = make_oauth_jwt(exp_offset_seconds=-120)
            r_expired = await http_client.post(
                "/mcp",
                headers={"Authorization": f"Bearer {expired_oauth}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert r_expired.status_code == 401

            # Tampered signature -> 401
            tampered_oauth = make_oauth_jwt(secret="attacker-wrong-signing-secret-32bytes!!")
            r_tampered = await http_client.post(
                "/mcp",
                headers={"Authorization": f"Bearer {tampered_oauth}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert r_tampered.status_code == 401

            # Wrong audience -> 401
            wrong_aud = make_oauth_jwt(audience="https://other-service.example.com")
            r_aud = await http_client.post(
                "/mcp",
                headers={"Authorization": f"Bearer {wrong_aud}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert r_aud.status_code == 401


@pytest.mark.asyncio
async def test_scope_enforcement_denies_market_read_only_user_on_portfolio_and_writes(
    test_settings,
    respx_backend,
) -> None:
    """User with only `market:read` receives deterministic PERMISSION_DENIED on portfolio/write tools."""
    app = create_asgi_app(test_settings, configure_logs=False)
    oauth_token = make_oauth_jwt(user_id="user_readonly", scopes=["market:read"])

    async with enter_asgi_lifespan(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {oauth_token}"},
        ) as http_client:
            transport = streamable_http_client("http://testserver/mcp", http_client=http_client)
            async with Client(transport) as client:
                # market:read succeeds
                ok_res = await client.call_tool("get_market_quote", {"symbol": "NVDA"})
                assert not ok_res.is_error

                # portfolio:read denied
                denied_port = await client.call_tool("analyse_portfolio", {"portfolio_id": "port_123"})
                assert denied_port.is_error
                assert json.loads(denied_port.content[0].text)["error"]["code"] == "PERMISSION_DENIED"

                # simulation:execute denied
                denied_sim = await client.call_tool(
                    "simulate_portfolio_rebalance",
                    {
                        "portfolio_id": "port_123",
                        "proposed_trades": [{"symbol": "NVDA", "side": "BUY", "weight_delta_pct": 5.0}],
                    },
                )
                assert denied_sim.is_error
                assert json.loads(denied_sim.content[0].text)["error"]["code"] == "PERMISSION_DENIED"

                # portfolio:write denied
                denied_wl = await client.call_tool(
                    "manage_watchlist",
                    {"action": "ADD", "watchlist_name": "Default", "symbols": ["NVDA"]},
                )
                assert denied_wl.is_error
                assert json.loads(denied_wl.content[0].text)["error"]["code"] == "PERMISSION_DENIED"

                # portfolio resource denied
                with pytest.raises(MCPError) as exc_info:
                    await client.read_resource("portfolio://user/port_123/summary")
                assert "PERMISSION_DENIED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cross_user_portfolio_cache_isolation(
    test_settings,
    respx_backend: respx.MockRouter,
) -> None:
    """User A's cached analyse_portfolio('port_123') must NEVER be served to User B."""
    app = create_asgi_app(test_settings, configure_logs=False)

    jwt_alice = make_internal_jwt(user_id="user_alice", scopes=["portfolio:read"])
    jwt_bob = make_internal_jwt(user_id="user_bob", scopes=["portfolio:read"])

    async with enter_asgi_lifespan(app):
        # User A calls analyse_portfolio("port_123") twice -> 1st miss (NAV 1,250,000), 2nd hit
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Internal-API-Key": INTERNAL_API_KEY, "Authorization": f"Bearer {jwt_alice}"},
        ) as client_a_http:
            async with Client(streamable_http_client("http://testserver/mcp", http_client=client_a_http)) as client_a:
                res_a1 = await client_a.call_tool("analyse_portfolio", {"portfolio_id": "port_123"})
                env_a1 = json.loads(res_a1.content[0].text)
                assert env_a1["data"]["nav"] == 1_250_000.0
                assert env_a1["metadata"]["cache_hit"] is False

                res_a2 = await client_a.call_tool("analyse_portfolio", {"portfolio_id": "port_123"})
                env_a2 = json.loads(res_a2.content[0].text)
                assert env_a2["metadata"]["cache_hit"] is True

        # User B calls analyse_portfolio("port_123") -> MUST be a cache miss and return Bob's NAV (420,000)
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Internal-API-Key": INTERNAL_API_KEY, "Authorization": f"Bearer {jwt_bob}"},
        ) as client_b_http:
            async with Client(streamable_http_client("http://testserver/mcp", http_client=client_b_http)) as client_b:
                res_b = await client_b.call_tool("analyse_portfolio", {"portfolio_id": "port_123"})
                env_b = json.loads(res_b.content[0].text)
                assert env_b["metadata"]["cache_hit"] is False
                assert env_b["data"]["nav"] == 420_000.0
                assert env_b["data"]["portfolio_name"] == "user_bob Core Equity"


@pytest.mark.asyncio
async def test_rate_limiting_returns_429_and_retry_after(test_settings, respx_backend) -> None:
    clock = FakeClock(1000.0)
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60, clock=clock)
    app = create_asgi_app(test_settings, rate_limiter=limiter, configure_logs=False)
    token = make_oauth_jwt(user_id="user_rate", scopes=["market:read"])

    async with enter_asgi_lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as http_client:
            for _ in range(2):
                r = await http_client.post(
                    "/mcp",
                    headers={"Accept": "application/json, text/event-stream"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                )
                assert r.status_code != 429

            r_limited = await http_client.post(
                "/mcp",
                headers={"Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )
            assert r_limited.status_code == 429
            assert r_limited.json()["error"] == "RATE_LIMITED"
            assert int(r_limited.headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_session_hijacking_with_other_users_mcp_session_id_is_rejected(
    test_settings,
    respx_backend,
) -> None:
    """User B replaying User A's Mcp-Session-Id must be rejected with HTTP 404."""
    app = create_asgi_app(test_settings, configure_logs=False)
    jwt_alice = make_internal_jwt(user_id="user_alice", scopes=["market:read"])
    jwt_bob = make_internal_jwt(user_id="user_bob", scopes=["market:read"])

    async with enter_asgi_lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as http_client:
            # Alice establishes a legacy stateful session
            init_resp = await http_client.post(
                "/mcp",
                headers={
                    "X-Internal-API-Key": INTERNAL_API_KEY,
                    "Authorization": f"Bearer {jwt_alice}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "alice-client", "version": "1.0"},
                    },
                },
            )
            assert init_resp.status_code == 200
            session_id = init_resp.headers.get("mcp-session-id")
            assert session_id

            # Bob attempts to hijack Alice's session ID -> must be rejected
            hijack_resp = await http_client.post(
                "/mcp",
                headers={
                    "X-Internal-API-Key": INTERNAL_API_KEY,
                    "Authorization": f"Bearer {jwt_bob}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                    "Mcp-Session-Id": session_id,
                },
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            )
            assert hijack_resp.status_code == 404


@pytest.mark.asyncio
async def test_asymmetric_rs256_oauth_jwt_verification_and_wrong_key_rejection(respx_backend) -> None:
    """Verify external OAuth 2.1 RS256 asymmetric signature verification end-to-end."""
    from datetime import UTC, datetime

    import jwt as pyjwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from tests.conftest import make_test_settings

    def _gen_rsa_pem_pair() -> tuple[bytes, str]:
        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        pub_pem = priv.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return priv_pem, pub_pem

    good_priv, good_pub = _gen_rsa_pem_pair()
    bad_priv, _ = _gen_rsa_pem_pair()

    rs_settings = make_test_settings(
        oauth_algorithms=["RS256"],
        oauth_public_key=good_pub,
    )
    app = create_asgi_app(rs_settings, configure_logs=False)

    now = int(datetime.now(UTC).timestamp())
    claims = {
        "sub": "user_rs256",
        "client_id": "claude-enterprise",
        "iss": "https://auth.example.com",
        "aud": "https://mcp.example.com/mcp",
        "iat": now,
        "exp": now + 600,
        "scope": "market:read",
    }
    valid_rs_token = pyjwt.encode(claims, good_priv, algorithm="RS256")
    forged_rs_token = pyjwt.encode(claims, bad_priv, algorithm="RS256")

    async with enter_asgi_lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as http_client:
            rejected = await http_client.post(
                "/mcp",
                headers={"Authorization": f"Bearer {forged_rs_token}"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert rejected.status_code == 401

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {valid_rs_token}"},
        ) as mcp_http:
            async with Client(streamable_http_client("http://testserver/mcp", http_client=mcp_http)) as client:
                res = await client.call_tool("get_market_quote", {"symbol": "NVDA"})
                assert not res.is_error
                assert json.loads(res.content[0].text)["data"]["last_price"] == 148.5
