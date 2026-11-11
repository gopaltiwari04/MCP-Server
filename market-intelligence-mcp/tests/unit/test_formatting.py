"""Unit tests for context-window compaction, Markdown/JSON dual formatting, and error envelopes."""

import json
from datetime import UTC, datetime

from app.schemas.common import CalendarType, EnvelopeStatus, ErrorCode
from app.tools.helpers import build_envelope
from app.utils.errors import (
    CircuitOpenError,
    InvalidParametersError,
    NoDataAvailableError,
    PermissionDeniedError,
    RateLimitedError,
    UnsupportedSymbolError,
    UpstreamProviderError,
    format_tool_error_result,
)
from app.utils.formatting import build_tool_result, compact_series_for_context, format_markdown_table


def test_format_markdown_table_escaping() -> None:
    md = format_markdown_table(["Symbol", "Note"], [["NVDA", "AI | GPU"], ["AMD", None]])
    assert "| NVDA | AI \\| GPU |" in md
    assert "| AMD | — |" in md


def test_compact_series_for_context() -> None:
    items = list(range(200))
    compacted, did_compact = compact_series_for_context(items, max_items=50, head=10, tail=20)
    assert did_compact is True
    assert len(compacted) == 30
    assert compacted[:10] == list(range(10))
    assert compacted[-20:] == list(range(180, 200))

    full, did_not = compact_series_for_context(list(range(10)), max_items=50)
    assert did_not is False
    assert len(full) == 10


def test_build_tool_result_dual_format() -> None:
    env = build_envelope(
        data={"symbol": "NVDA", "price": 148.5},
        source="unit-test",
        data_timestamp=datetime.now(UTC),
        staleness_threshold_seconds=60,
        currency="USD",
        units="price_per_share",
        calendar_type=CalendarType.TRADING_DAYS,
    )
    res = build_tool_result(env, "### NVDA")
    assert res.is_error is False
    assert len(res.content) == 2
    parsed = json.loads(res.content[0].text)
    assert parsed["status"] == "OK"
    assert parsed["metadata"]["currency"] == "USD"
    assert res.content[1].text == "### NVDA"
    assert res.structured_content["data"]["symbol"] == "NVDA"


def test_error_mapping_for_all_domain_error_codes() -> None:
    cases = [
        (NoDataAvailableError("missing"), ErrorCode.NO_DATA_AVAILABLE, EnvelopeStatus.NO_DATA_AVAILABLE),
        (UnsupportedSymbolError("bad sym"), ErrorCode.UNSUPPORTED_SYMBOL, EnvelopeStatus.UNSUPPORTED_SYMBOL),
        (InvalidParametersError("bad arg"), ErrorCode.INVALID_PARAMETERS, EnvelopeStatus.INVALID_PARAMETERS),
        (PermissionDeniedError("forbidden"), ErrorCode.PERMISSION_DENIED, EnvelopeStatus.PERMISSION_DENIED),
        (RateLimitedError("too many"), ErrorCode.RATE_LIMITED, EnvelopeStatus.RATE_LIMITED),
        (UpstreamProviderError("503"), ErrorCode.UPSTREAM_PROVIDER_ERROR, EnvelopeStatus.UPSTREAM_PROVIDER_ERROR),
        (CircuitOpenError("open"), ErrorCode.UPSTREAM_CIRCUIT_OPEN, EnvelopeStatus.UPSTREAM_PROVIDER_ERROR),
    ]
    for exc, expected_code, expected_status in cases:
        res = format_tool_error_result(exc, tool_name="test_tool", request_id="req-99")
        assert res.is_error is True
        body = json.loads(res.content[0].text)
        assert body["status"] == expected_status.value
        assert body["error"]["code"] == expected_code.value
        assert body["metadata"]["request_id"] == "req-99"

    # Unexpected runtime error must NOT leak raw secret/exception text
    unexpected = RuntimeError("postgres://secret_password@db/prod crashed")
    res_unexpected = format_tool_error_result(unexpected, tool_name="test_tool", request_id="req-100")
    assert res_unexpected.is_error is True
    assert "secret_password" not in res_unexpected.content[0].text
