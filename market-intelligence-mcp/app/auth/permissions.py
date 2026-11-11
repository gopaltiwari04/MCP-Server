"""Scope enforcement helpers and decorators for MCP tools and resources."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from app.auth.context import RequestSecurityContext, require_security_context
from app.utils.errors import PermissionDeniedError

F = TypeVar("F", bound=Callable[..., Any])


def assert_scopes(*required_scopes: str) -> RequestSecurityContext:
    """Assert that the active RequestSecurityContext grants all required scopes."""
    sec_ctx = require_security_context()
    missing = [scope for scope in required_scopes if scope not in sec_ctx.scopes]
    if missing:
        raise PermissionDeniedError(
            f"PERMISSION_DENIED: Caller lacks required scope(s): {', '.join(missing)}.",
            details={
                "required_scopes": list(required_scopes),
                "missing_scopes": missing,
                "user_id": sec_ctx.user_id,
            },
        )
    return sec_ctx


def assert_any_scope(*candidate_scopes: str) -> RequestSecurityContext:
    """Assert that the active RequestSecurityContext grants at least one candidate scope."""
    sec_ctx = require_security_context()
    if not any(scope in sec_ctx.scopes for scope in candidate_scopes):
        raise PermissionDeniedError(
            f"PERMISSION_DENIED: Caller requires one of scopes: {', '.join(candidate_scopes)}.",
            details={
                "required_any_scopes": list(candidate_scopes),
                "user_id": sec_ctx.user_id,
            },
        )
    return sec_ctx


def require_scopes(*required_scopes: str) -> Callable[[F], F]:
    """Decorator enforcing required OAuth/delegated scopes on async tool or resource functions."""

    def decorator(fn: F) -> F:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"@require_scopes can only decorate async functions; got {fn!r}")

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            assert_scopes(*required_scopes)
            return await fn(*args, **kwargs)

        wrapper.__annotations__ = dict(fn.__annotations__)
        wrapper.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
