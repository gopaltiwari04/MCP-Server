"""Live 3-tier end-to-end test: ai-orchestrator -> market-intelligence-mcp -> market-backend."""

import asyncio
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise TimeoutError(f"Service did not become ready at {url}")


def test_live_orchestrator_mcp_backend_pipeline() -> None:
    asyncio.run(_run_live_pipeline())


async def _run_live_pipeline() -> None:
    root = Path(__file__).resolve().parents[2]
    p_backend = _free_port()
    p_mcp = _free_port()
    p_orch = _free_port()

    backend_py = str(root / "market-backend" / ".venv" / "Scripts" / "python.exe")
    mcp_py = str(root / "market-intelligence-mcp" / ".venv" / "Scripts" / "python.exe")
    orch_py = str(root / "ai-orchestrator" / ".venv" / "Scripts" / "python.exe")

    proc_env = os.environ.copy()
    backend_proc = subprocess.Popen(
        [backend_py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(p_backend)],
        cwd=str(root / "market-backend"),
        env={**proc_env, "BACKEND_HOST": "127.0.0.1", "BACKEND_PORT": str(p_backend)},
    )
    mcp_proc = subprocess.Popen(
        [mcp_py, "-m", "app.main", "--transport", "streamable-http", "--host", "127.0.0.1", "--port", str(p_mcp)],
        cwd=str(root / "market-intelligence-mcp"),
        env={
            **proc_env,
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": str(p_mcp),
            "MCP_BACKEND_BASE_URL": f"http://127.0.0.1:{p_backend}",
        },
    )
    orch_proc = subprocess.Popen(
        [orch_py, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(p_orch)],
        cwd=str(root / "ai-orchestrator"),
        env={
            **proc_env,
            "ORCH_HOST": "127.0.0.1",
            "ORCH_PORT": str(p_orch),
            "ORCH_MCP_URL": f"http://127.0.0.1:{p_mcp}/mcp",
            "ORCH_MCP_HEALTH_URL": f"http://127.0.0.1:{p_mcp}/health/ready",
        },
    )

    try:
        _wait_ready(f"http://127.0.0.1:{p_mcp}/health/ready")
        _wait_ready(f"http://127.0.0.1:{p_orch}/api/v1/health")

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{p_orch}", timeout=20.0) as client:
            health = (await client.get("/api/v1/health")).json()
            assert health["mcp_gateway"]["reachable"] is True
            assert health["mcp_gateway"]["details"]["circuit_breaker"]["state"] == "CLOSED"

            catalog = (await client.get("/api/v1/mcp/catalog", params={"persona": "alice"})).json()
            assert len(catalog["tools"]) == 15

            # Alice compares NVDA vs AMD over 1M
            cmp_res = (
                await client.post(
                    "/api/v1/chat",
                    json={"persona": "alice", "prompt": "Compare NVDA vs AMD over 1M"},
                )
            ).json()
            assert len(cmp_res["tool_traces"]) >= 3
            assert cmp_res["tool_traces"][0]["envelope"]["status"] == "OK"

            # Alice runs portfolio tail-risk audit -> succeeds
            alice_port = (
                await client.post(
                    "/api/v1/chat",
                    json={"persona": "alice", "prompt": "Audit portfolio tail risk"},
                )
            ).json()
            assert alice_port["tool_traces"][0]["is_error"] is False
            assert "Alice Institutional" in alice_port["assistant_markdown"]

            # Bob (market:read only) runs portfolio tail-risk audit -> PERMISSION_DENIED
            bob_port = (
                await client.post(
                    "/api/v1/chat",
                    json={"persona": "bob", "prompt": "Audit portfolio tail risk"},
                )
            ).json()
            assert bob_port["tool_traces"][0]["is_error"] is True
            assert bob_port["tool_traces"][0]["envelope"]["error"]["code"] == "PERMISSION_DENIED"
    finally:
        for proc in (orch_proc, mcp_proc, backend_proc):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
