"""Zero-trust identity propagation, ASGI auth middleware, and scope enforcement."""

from app.auth.context import (
    RequestSecurityContext,
    get_current_tool_name,
    get_security_context,
    require_security_context,
    reset_current_tool_name,
    reset_security_context,
    set_current_tool_name,
    set_security_context,
)
from app.auth.identity import (
    AuthenticationError,
    VerifiedTokenClaims,
    build_protected_resource_metadata,
    verify_delegated_jwt,
    verify_oauth_jwt,
)
from app.auth.middleware import SlidingWindowRateLimiter, ZeroTrustAuthMiddleware
from app.auth.permissions import assert_any_scope, assert_scopes, require_scopes

__all__ = [
    "AuthenticationError",
    "RequestSecurityContext",
    "SlidingWindowRateLimiter",
    "VerifiedTokenClaims",
    "ZeroTrustAuthMiddleware",
    "assert_any_scope",
    "assert_scopes",
    "build_protected_resource_metadata",
    "get_current_tool_name",
    "get_security_context",
    "require_scopes",
    "require_security_context",
    "reset_current_tool_name",
    "reset_security_context",
    "set_current_tool_name",
    "set_security_context",
    "verify_delegated_jwt",
    "verify_oauth_jwt",
]
