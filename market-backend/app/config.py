"""Settings for the internal FastAPI Market Intelligence Backend."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BACKEND_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    host: str = "127.0.0.1"
    port: int = 8000
    internal_api_key: SecretStr = SecretStr("dev-backend-internal-key")
    jwt_secret: SecretStr = SecretStr("dev-internal-jwt-secret-must-be-at-least-32-bytes")
    oauth_public_key: SecretStr | None = None
    jwt_algorithms: list[str] = ["HS256", "RS256"]
    jwt_allowed_issuers: list[str] = ["https://orchestrator.internal", "https://auth.example.com"]
    jwt_allowed_audiences: list[str] = ["market-intelligence-mcp", "https://mcp.example.com/mcp"]


@lru_cache(maxsize=1)
def get_backend_settings() -> BackendSettings:
    return BackendSettings()
