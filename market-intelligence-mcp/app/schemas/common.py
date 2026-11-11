"""Standardized response envelope, provenance metadata, pagination, and error models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_serializer

T = TypeVar("T")


class EnvelopeStatus(str, Enum):
    """Canonical high-level status codes for every MCP tool response."""

    OK = "OK"
    STALE_DATA = "STALE_DATA"
    NO_DATA_AVAILABLE = "NO_DATA_AVAILABLE"
    UNSUPPORTED_SYMBOL = "UNSUPPORTED_SYMBOL"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_PROVIDER_ERROR = "UPSTREAM_PROVIDER_ERROR"


class ErrorCode(str, Enum):
    """Granular domain error codes distinguishing failure modes explicitly."""

    NO_DATA_AVAILABLE = "NO_DATA_AVAILABLE"
    STALE_DATA = "STALE_DATA"
    UNSUPPORTED_SYMBOL = "UNSUPPORTED_SYMBOL"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    UPSTREAM_PROVIDER_ERROR = "UPSTREAM_PROVIDER_ERROR"
    UPSTREAM_CIRCUIT_OPEN = "UPSTREAM_CIRCUIT_OPEN"


class CalendarType(str, Enum):
    """Day-count convention used to compute or index market time windows."""

    TRADING_DAYS = "TRADING_DAYS"
    CALENDAR_DAYS = "CALENDAR_DAYS"


def _format_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.isoformat().replace("+00:00", "Z")


class DataMetadata(BaseModel):
    """Mandatory provenance & SLA metadata attached to every tool response."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Originating backend service or upstream market data vendor.")
    data_timestamp: datetime = Field(..., description="Timestamp of underlying market data in ISO-8601 UTC.")
    fetched_at: datetime = Field(..., description="Timestamp when MCP gateway produced this response in UTC.")
    is_stale: bool = Field(False, description="True if data_timestamp violates freshness SLA.")
    staleness_threshold_seconds: int = Field(..., ge=0, description="Freshness SLA threshold in seconds.")
    currency: str | None = Field(None, description="ISO-4217 currency code if applicable (e.g., USD).")
    units: str | None = Field(None, description="Unit specification (e.g., price_per_share, pct, ratio, shares).")
    calendar_type: CalendarType = Field(
        CalendarType.TRADING_DAYS,
        description="Calendar convention governing date alignment and annualization.",
    )
    cache_hit: bool = Field(False, description="Whether this payload was served from gateway TTL cache.")
    request_id: str = Field(..., description="End-to-end distributed correlation ID.")

    @field_serializer("data_timestamp", "fetched_at")
    def _serialize_dt(self, dt: datetime) -> str:
        return _format_utc_iso(dt)


class ErrorDetail(BaseModel):
    """Structured error payload for deterministic failure handling."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class Pagination(BaseModel):
    """Pagination metadata for collection endpoints."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(..., ge=1)
    offset: int = Field(0, ge=0)
    total_count: int | None = Field(None, ge=0)
    next_cursor: str | None = None
    has_more: bool = False


class ResponseEnvelope(BaseModel, Generic[T]):
    """Unified envelope wrapping all Market Intelligence MCP tool responses."""

    model_config = ConfigDict(extra="forbid")

    status: EnvelopeStatus
    data: T | None = None
    metadata: DataMetadata
    warnings: list[str] = Field(default_factory=list)
    error: ErrorDetail | None = None
    pagination: Pagination | None = None
