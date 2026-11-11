"""Domain exception hierarchy and MCP CallToolResult / ToolError formatters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

from app.schemas.common import (
    CalendarType,
    DataMetadata,
    EnvelopeStatus,
    ErrorCode,
    ErrorDetail,
    ResponseEnvelope,
)


class MarketIntelligenceError(Exception):
    """Base domain exception mapped deterministically to ResponseEnvelope errors."""

    code: ErrorCode = ErrorCode.UPSTREAM_PROVIDER_ERROR
    status: EnvelopeStatus = EnvelopeStatus.UPSTREAM_PROVIDER_ERROR
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        status: EnvelopeStatus | None = None,
        retryable: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        if retryable is not None:
            self.retryable = retryable
        self.details: dict[str, Any] = details or {}

    def to_tool_error(self) -> ToolError:
        """Convert to an SDK ToolError with canonical error code prefix."""
        return ToolError(f"{self.code.value}: {self.message}")


class NoDataAvailableError(MarketIntelligenceError):
    code = ErrorCode.NO_DATA_AVAILABLE
    status = EnvelopeStatus.NO_DATA_AVAILABLE
    retryable = False


class StaleDataError(MarketIntelligenceError):
    code = ErrorCode.STALE_DATA
    status = EnvelopeStatus.STALE_DATA
    retryable = True


class UnsupportedSymbolError(MarketIntelligenceError):
    code = ErrorCode.UNSUPPORTED_SYMBOL
    status = EnvelopeStatus.UNSUPPORTED_SYMBOL
    retryable = False


class InvalidParametersError(MarketIntelligenceError):
    code = ErrorCode.INVALID_PARAMETERS
    status = EnvelopeStatus.INVALID_PARAMETERS
    retryable = False


class PermissionDeniedError(MarketIntelligenceError):
    code = ErrorCode.PERMISSION_DENIED
    status = EnvelopeStatus.PERMISSION_DENIED
    retryable = False


class RateLimitedError(MarketIntelligenceError):
    code = ErrorCode.RATE_LIMITED
    status = EnvelopeStatus.RATE_LIMITED
    retryable = True


class UpstreamProviderError(MarketIntelligenceError):
    code = ErrorCode.UPSTREAM_PROVIDER_ERROR
    status = EnvelopeStatus.UPSTREAM_PROVIDER_ERROR
    retryable = True


class CircuitOpenError(UpstreamProviderError):
    code = ErrorCode.UPSTREAM_CIRCUIT_OPEN
    status = EnvelopeStatus.UPSTREAM_PROVIDER_ERROR
    retryable = True


def build_error_envelope(
    exc: Exception,
    *,
    tool_name: str = "market-intelligence-mcp",
    request_id: str | None = None,
    source: str = "market-intelligence-mcp",
) -> ResponseEnvelope[None]:
    """Build a sanitized ResponseEnvelope from any exception."""
    now = datetime.now(UTC)
    corr_id = request_id or "req-unknown"

    if isinstance(exc, MarketIntelligenceError):
        status = exc.status
        error_detail = ErrorDetail(
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details,
        )
        warnings = [f"{exc.code.value}: {exc.message}"]
    else:
        # Never leak raw internal exception text / URLs / tracebacks across the MCP boundary
        status = EnvelopeStatus.UPSTREAM_PROVIDER_ERROR
        error_detail = ErrorDetail(
            code=ErrorCode.UPSTREAM_PROVIDER_ERROR,
            message=f"Internal error while executing '{tool_name}'. Check server logs with request_id='{corr_id}'.",
            retryable=True,
            details={"tool_name": tool_name},
        )
        warnings = [error_detail.message]

    metadata = DataMetadata(
        source=source,
        data_timestamp=now,
        fetched_at=now,
        is_stale=False,
        staleness_threshold_seconds=0,
        currency=None,
        units=None,
        calendar_type=CalendarType.TRADING_DAYS,
        cache_hit=False,
        request_id=corr_id,
    )
    return ResponseEnvelope[None](
        status=status,
        data=None,
        metadata=metadata,
        warnings=warnings,
        error=error_detail,
    )


def format_tool_error_result(
    exc: Exception,
    *,
    tool_name: str,
    request_id: str | None = None,
) -> CallToolResult:
    """Format a domain or unexpected error into a deterministic MCP CallToolResult(is_error=True)."""
    envelope = build_error_envelope(exc, tool_name=tool_name, request_id=request_id)
    payload_json = envelope.model_dump_json(by_alias=True)
    payload_dict = envelope.model_dump(mode="json", by_alias=True)
    return CallToolResult(
        content=[TextContent(type="text", text=payload_json)],
        structured_content=payload_dict,
        is_error=True,
    )
