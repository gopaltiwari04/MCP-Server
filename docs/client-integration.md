# Client Integration Guide

## 1. In-Product FastAPI AI Orchestrator (Streamable HTTP + Delegated Auth)

The AI Orchestrator authenticates to the MCP gateway using its service key and the end user's verified delegated JWT:

```python
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

headers = {
    "X-Internal-API-Key": INTERNAL_GATEWAY_KEY,
    "Authorization": f"Bearer {user_delegated_jwt}",
    "X-Request-ID": trace_request_id,
}

async with httpx2.AsyncClient(headers=headers) as http_client:
    async with streamable_http_client(
        "https://mcp.internal:8080/mcp",
        http_client=http_client,
    ) as (read_stream, write_stream):
        # Use ClientSession or Client(transport)
        ...
```

## 2. Claude Desktop / Cursor (External OAuth 2.1 over HTTPS Reverse Proxy)

Discover protected resource metadata at:
`GET https://mcp.example.com/.well-known/oauth-protected-resource`

Example `claude_desktop_config.json` (remote HTTP via OAuth bearer or local stdio):

```json
{
  "mcpServers": {
    "market-intelligence": {
      "command": "python",
      "args": ["-m", "app.main", "--transport", "stdio"],
      "cwd": "/path/to/market-intelligence-mcp",
      "env": {
        "MCP_BACKEND_BASE_URL": "http://localhost:8000",
        "MCP_BACKEND_INTERNAL_API_KEY": "your-backend-key"
      }
    }
  }
}
```

For remote Cursor / OpenAI / Claude HTTP clients:

```json
{
  "mcpServers": {
    "market-intelligence-remote": {
      "url": "https://mcp.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${MARKET_MCP_OAUTH_TOKEN}"
      }
    }
  }
}
```

## 3. Local Debugging with MCP Inspector

### Option A: Streamable HTTP Mode

```bash
# Terminal 1: Start gateway
python -m app.main --transport streamable-http --host 127.0.0.1 --port 8080

# Terminal 2: Launch MCP Inspector (configure Authorization + X-Internal-API-Key headers in UI)
npx @modelcontextprotocol/inspector http://127.0.0.1:8080/mcp
```

### Option B: Stdio Mode

```bash
npx @modelcontextprotocol/inspector python -m app.main --transport stdio
```
