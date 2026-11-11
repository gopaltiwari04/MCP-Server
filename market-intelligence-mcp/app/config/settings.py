"""Application configuration backed by Pydantic BaseSettings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Market Intelligence MCP Server."""

    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Service Identity & Runtime
    env: Literal["development", "staging", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    server_name: str = "market-intelligence-mcp"
    server_version: str = "1.0.0"

    # Streamable HTTP & Transport Security
    streamable_http_path: str = "/mcp"
    json_response: bool = False
    stateless_http: bool = False
    enable_dns_rebinding_protection: bool = True
    allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            "127.0.0.1",
            "127.0.0.1:*",
            "localhost",
            "localhost:*",
            "[::1]",
            "[::1]:*",
            "testserver",
            "testserver:*",
        ]
    )
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1",
            "http://127.0.0.1:*",
            "http://localhost",
            "http://localhost:*",
            "http://[::1]",
            "http://[::1]:*",
            "http://testserver",
        ]
    )
    max_request_body_size: int = 4 * 1024 * 1024

    # Upstream FastAPI Backend
    backend_base_url: str = "http://localhost:8000"
    backend_internal_api_key: SecretStr = SecretStr("dev-backend-internal-key")
    backend_connect_timeout_seconds: float = Field(default=3.0, gt=0)
    backend_read_timeout_seconds: float = Field(default=15.0, gt=0)
    backend_write_timeout_seconds: float = Field(default=5.0, gt=0)
    backend_pool_timeout_seconds: float = Field(default=5.0, gt=0)
    backend_max_connections: int = Field(default=100, ge=1)
    backend_max_keepalive_connections: int = Field(default=20, ge=0)
    backend_keepalive_expiry_seconds: float = Field(default=30.0, gt=0)
    backend_max_retries: int = Field(default=2, ge=0, le=5)

    # Zero-Trust Authentication - Flow A (Internal Service + Delegated User JWT)
    internal_api_key: SecretStr = SecretStr("dev-gateway-internal-key")
    internal_jwt_issuer: str = "https://orchestrator.internal"
    internal_jwt_audience: str = "market-intelligence-mcp"
    internal_jwt_algorithm: str = "HS256"
    internal_jwt_secret: SecretStr = SecretStr("dev-internal-jwt-secret-must-be-at-least-32-bytes")
    internal_jwt_public_key: SecretStr | None = None

    # Zero-Trust Authentication - Flow B (External OAuth 2.1 Resource Server)
    oauth_enabled: bool = True
    oauth_resource_server_url: str = "https://mcp.example.com/mcp"
    oauth_issuer: str = "https://auth.example.com"
    oauth_audience: str = "https://mcp.example.com/mcp"
    oauth_algorithms: list[str] = Field(default_factory=lambda: ["RS256", "HS256"])
    oauth_jwks_url: str | None = None
    oauth_public_key: SecretStr | None = None
    oauth_supported_scopes: list[str] = Field(
        default_factory=lambda: [
            "market:read",
            "portfolio:read",
            "portfolio:write",
            "simulation:execute",
            "research:write",
        ]
    )
    jwt_leeway_seconds: int = Field(default=10, ge=0, le=300)

    # Stdio Local Principal (only used in --transport stdio mode, NEVER in HTTP mode)
    stdio_user_id: str = "local-stdio-analyst"
    stdio_client_id: str = "mcp-stdio-client"
    stdio_scopes: list[str] = Field(
        default_factory=lambda: [
            "market:read",
            "portfolio:read",
            "portfolio:write",
            "simulation:execute",
            "research:write",
        ]
    )

    # Resilience: Circuit Breaker, Cache & Rate Limiter
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_recovery_timeout_seconds: float = Field(default=15.0, gt=0)
    cache_max_size: int = Field(default=4096, ge=64)
    rate_limit_requests: int = Field(default=120, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    # Endpoint Cache TTLs (seconds)
    ttl_search_seconds: int = 300
    ttl_schedule_seconds: int = 3600
    ttl_quote_seconds: int = 5
    ttl_history_intraday_seconds: int = 60
    ttl_history_daily_seconds: int = 3600
    ttl_profile_seconds: int = 86400
    ttl_metrics_seconds: int = 3600
    ttl_earnings_seconds: int = 3600
    ttl_analytics_seconds: int = 60
    ttl_portfolio_analysis_seconds: int = 15

    # Data Staleness SLA Thresholds (seconds)
    stale_quote_seconds: int = 60
    stale_history_intraday_seconds: int = 900
    stale_history_daily_seconds: int = 345600
    stale_fundamentals_seconds: int = 604800
    stale_portfolio_seconds: int = 120
    stale_schedule_seconds: int = 86400

    # Quantitative Guardrails
    max_historical_bars: int = 500
    default_risk_free_rate: float = 0.045
    max_single_position_concentration_pct: float = 25.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    return Settings()
