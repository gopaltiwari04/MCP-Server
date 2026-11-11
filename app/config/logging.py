"""Structured logging with automatic secret, header, and JWT redaction."""

from __future__ import annotations

import logging
import re
import sys
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.config.settings import Settings

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_MARKERS = (
    "authorization",
    "x-internal-api-key",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "delegated_jwt",
    "id_token",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "private_key",
    "cookie",
    "set-cookie",
    "jwt",
    "bearer",
    "credential",
)

_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b")
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*")
_API_KEY_KV_PATTERN = re.compile(
    r"(?i)(x-internal-api-key|authorization|api_key|token|secret|password)\s*[:=]\s*(['\"]?)[^\s,'\";\)]+\2"
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().strip()
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _scrub_string(value: str) -> str:
    scrubbed = _JWT_PATTERN.sub(REDACTED, value)
    scrubbed = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", scrubbed)
    scrubbed = _API_KEY_KV_PATTERN.sub(lambda m: f"{m.group(1)}={REDACTED}", scrubbed)
    return scrubbed


def _scrub_value(value: Any, *, key_hint: str | None = None) -> Any:
    if key_hint is not None and _is_sensitive_key(key_hint):
        if value is None:
            return None
        return REDACTED
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, bytes):
        return _scrub_string(value.decode("utf-8", errors="replace"))
    if isinstance(value, dict):
        return {k: _scrub_value(v, key_hint=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return [_scrub_value(item) for item in value]
    return value


def redact_sensitive_data(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that redacts secrets, headers, and JWTs from logs & tracebacks."""
    return {k: _scrub_value(v, key_hint=str(k)) for k, v in event_dict.items()}


def configure_logging(settings: Settings | None = None, *, stream: Any = None) -> None:
    """Configure structlog and stdlib logging with JSON/console output on stderr."""
    log_level_name = settings.log_level if settings else "INFO"
    log_format = settings.log_format if settings else "json"
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)
    target_stream = stream if stream is not None else sys.stderr

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive_data,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(target_stream)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Keep noisy HTTP/ASGI third-party loggers aligned without dropping warnings
    for lib_logger in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(lib_logger).setLevel(max(log_level, logging.INFO))


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
