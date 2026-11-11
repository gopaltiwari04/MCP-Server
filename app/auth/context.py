"""ContextVar-backed immutable request security context for zero-trust propagation."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal

from app.utils.errors import PermissionDeniedError


@dataclass(frozen=True, slots=True)
class RequestSecurityContext:
    """Immutable authenticated caller identity stored per request in a ContextVar."""

    user_id: str
    client_id: str
    auth_mode: Literal["INTERNAL_DELEGATED", "OAUTH2_BEARER", "STDIO_LOCAL"]
    scopes: frozenset[str]
    delegated_jwt: str | None
    internal_api_key_verified: bool
    issuer: str | None
    audience: str | None
    token_expires_at: int | None
    request_id: str
    session_id: str | None = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def has_all_scopes(self, required: tuple[str, ...] | list[str] | frozenset[str]) -> bool:
        return all(scope in self.scopes for scope in required)

    def __repr__(self) -> str:
        return (
            f"RequestSecurityContext(user_id={self.user_id!r}, client_id={self.client_id!r}, "
            f"auth_mode={self.auth_mode!r}, scopes={sorted(self.scopes)!r}, "
            f"delegated_jwt='[REDACTED]', request_id={self.request_id!r})"
        )


_security_context_var: ContextVar[RequestSecurityContext | None] = ContextVar(
    "market_mcp_security_context",
    default=None,
)

_current_tool_name_var: ContextVar[str] = ContextVar(
    "market_mcp_current_tool_name",
    default="mcp-gateway",
)


def get_security_context() -> RequestSecurityContext | None:
    """Return the active RequestSecurityContext or None if unauthenticated."""
    return _security_context_var.get()


def require_security_context() -> RequestSecurityContext:
    """Return the active RequestSecurityContext or raise PermissionDeniedError."""
    ctx = _security_context_var.get()
    if ctx is None:
        raise PermissionDeniedError(
            "Authentication required: no active RequestSecurityContext found in execution context."
        )
    return ctx


def set_security_context(ctx: RequestSecurityContext) -> Token[RequestSecurityContext | None]:
    """Bind RequestSecurityContext to the current async execution context."""
    return _security_context_var.set(ctx)


def reset_security_context(token: Token[RequestSecurityContext | None]) -> None:
    """Restore previous RequestSecurityContext after request completion."""
    _security_context_var.reset(token)


def get_current_tool_name() -> str:
    """Return the active MCP tool or resource identifier for outbound header tracing."""
    return _current_tool_name_var.get()


def set_current_tool_name(name: str) -> Token[str]:
    """Bind current MCP tool or resource name for outbound BackendClient headers."""
    return _current_tool_name_var.set(name)


def reset_current_tool_name(token: Token[str]) -> None:
    """Restore previous MCP tool or resource name."""
    _current_tool_name_var.reset(token)
