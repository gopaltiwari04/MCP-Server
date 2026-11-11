"""Shared runtime container, metadata builders, protocol logging, and error boundaries."""

import functools
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar

from mcp.server.mcpserver import Context
from mcp.types import CallToolResult
from pydantic import ValidationError

from app.auth.context import (
    get_security_context,
    reset_current_tool_name,
    set_current_tool_name,
)
from app.clients.backend_client import BackendClient
from app.clients.cache import TieredTTLCache
from app.clients.circuit_breaker import CircuitBreaker
from app.config.logging import get_logger
from app.config.settings import Settings
from app.schemas.common import (
    CalendarType,
    DataMetadata,
    EnvelopeStatus,
    Pagination,
    ResponseEnvelope,
)
from app.utils.errors import (
    InvalidParametersError,
    MarketIntelligenceError,
    format_tool_error_result,
)

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")


@dataclass(slots=True)
class ServerRuntime:
    """Lifespan-owned dependencies injected into MCP tool & resource handlers."""

    settings: Settings
    cache: TieredTTLCache
    circuit_breaker: CircuitBreaker
    backend_client: BackendClient
    rate_limiter: Any = None


_FALLBACK_RUNTIME: ServerRuntime | None = None


def set_fallback_runtime(runtime: ServerRuntime | None) -> None:
    """Register fallback runtime for direct Python invocations outside ASGI lifespan."""
    global _FALLBACK_RUNTIME
    _FALLBACK_RUNTIME = runtime


def get_runtime(ctx: Context | None = None) -> ServerRuntime:
    """Extract ServerRuntime from MCP RequestContext lifespan_context or registered fallback."""
    if ctx is not None:
        try:
            lifespan_ctx = ctx.request_context.lifespan_context
            if isinstance(lifespan_ctx, ServerRuntime):
                return lifespan_ctx
        except ValueError:
            pass
    if _FALLBACK_RUNTIME is not None:
        return _FALLBACK_RUNTIME
    raise RuntimeError("ServerRuntime is not initialized; ensure server lifespan has started.")


def parse_utc_datetime(raw: Any, default: datetime | None = None) -> datetime:
    """Parse an ISO-8601 string or datetime into a timezone-aware UTC datetime."""
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return default or datetime.now(UTC)
    else:
        return default or datetime.now(UTC)

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def build_envelope(
    *,
    data: T | None,
    source: str,
    data_timestamp: datetime,
    staleness_threshold_seconds: int,
    currency: str | None = None,
    units: str | None = None,
    calendar_type: CalendarType = CalendarType.TRADING_DAYS,
    cache_hit: bool = False,
    backend_is_stale: bool = False,
    enforce_staleness: bool = True,
    no_data: bool = False,
    warnings: list[str] | None = None,
    pagination: Pagination | None = None,
) -> ResponseEnvelope[T]:
    """Construct a standardized ResponseEnvelope with deterministic SLA staleness detection."""
    fetched_at = datetime.now(UTC)
    ts_utc = parse_utc_datetime(data_timestamp, default=fetched_at)
    age_seconds = (fetched_at - ts_utc).total_seconds()
    is_stale = bool(backend_is_stale) or (
        enforce_staleness and staleness_threshold_seconds > 0 and age_seconds > staleness_threshold_seconds
    )

    out_warnings = list(warnings or [])
    if no_data:
        status = EnvelopeStatus.NO_DATA_AVAILABLE
        if not out_warnings:
            out_warnings.append("NO_DATA_AVAILABLE: Backend returned zero matching records.")
    elif is_stale:
        status = EnvelopeStatus.STALE_DATA
        out_warnings.append(
            f"STALE_DATA: Data timestamp {ts_utc.isoformat()} is {int(age_seconds)}s old "
            f"(SLA threshold: {staleness_threshold_seconds}s)."
        )
    else:
        status = EnvelopeStatus.OK

    sec_ctx = get_security_context()
    request_id = sec_ctx.request_id if sec_ctx is not None else "req-local"

    metadata = DataMetadata(
        source=source,
        data_timestamp=ts_utc,
        fetched_at=fetched_at,
        is_stale=is_stale,
        staleness_threshold_seconds=staleness_threshold_seconds,
        currency=currency,
        units=units,
        calendar_type=calendar_type,
        cache_hit=cache_hit,
        request_id=request_id,
    )
    return ResponseEnvelope[T](
        status=status,
        data=data,
        metadata=metadata,
        warnings=out_warnings,
        pagination=pagination,
    )


async def emit_protocol_log(
    ctx: Context | None,
    level: Literal["debug", "info", "warning", "error"],
    message: str,
    *,
    logger_name: str = "market-intelligence-mcp",
) -> None:
    """Send an MCP protocol log notification safely when inside an active MCP request."""
    if ctx is None:
        return
    try:
        # Context.log raises ValueError outside an active request or if session is detached
        await ctx.log(level, message, logger_name=logger_name)
    except Exception:
        pass


async def emit_progress(
    ctx: Context | None,
    progress: float,
    total: float | None = None,
    message: str | None = None,
) -> None:
    """Emit an MCP progress notification safely when inside an active MCP request."""
    if ctx is None:
        return
    try:
        await ctx.report_progress(progress, total, message)
    except Exception:
        pass


def mcp_tool_boundary(tool_name: str) -> Callable[[F], F]:
    """Bind X-MCP-Tool-Name ContextVar and format domain/unexpected errors uniformly."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> CallToolResult:
            sec_ctx = get_security_context()
            request_id = sec_ctx.request_id if sec_ctx is not None else None
            tool_token = set_current_tool_name(tool_name)
            try:
                return await fn(*args, **kwargs)
            except MarketIntelligenceError as exc:
                logger.warning(
                    "Tool failed with domain error",
                    tool_name=tool_name,
                    error_code=exc.code.value,
                    message=exc.message,
                )
                return format_tool_error_result(exc, tool_name=tool_name, request_id=request_id)
            except ValidationError as exc:
                err = InvalidParametersError(
                    f"Parameter validation failed for '{tool_name}': {exc.errors()[0].get('msg', 'invalid input')}",
                    details={"validation_errors": exc.errors()},
                )
                return format_tool_error_result(err, tool_name=tool_name, request_id=request_id)
            except Exception as exc:
                logger.exception(
                    "Unexpected exception in MCP tool",
                    tool_name=tool_name,
                    error_type=type(exc).__name__,
                )
                return format_tool_error_result(exc, tool_name=tool_name, request_id=request_id)
            finally:
                reset_current_tool_name(tool_token)

        wrapper.__annotations__ = dict(fn.__annotations__)
        wrapper.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
