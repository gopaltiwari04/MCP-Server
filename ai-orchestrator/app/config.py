"""Settings for the FastAPI AI Orchestrator."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORCH_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = "127.0.0.1"
    port: int = 8001
    mcp_url: str = "http://127.0.0.1:8080/mcp"
    mcp_health_url: str = "http://127.0.0.1:8080/health/ready"

    internal_api_key: SecretStr = SecretStr("dev-gateway-internal-key")
    jwt_secret: SecretStr = SecretStr("dev-internal-jwt-secret-must-be-at-least-32-bytes")
    jwt_issuer: str = "https://orchestrator.internal"
    jwt_audience: str = "market-intelligence-mcp"

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Optional external OpenAI-compatible LLM (falls back to deterministic MCP planner if unset)
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"


@lru_cache(maxsize=1)
def get_orchestrator_settings() -> OrchestratorSettings:
    return OrchestratorSettings()
