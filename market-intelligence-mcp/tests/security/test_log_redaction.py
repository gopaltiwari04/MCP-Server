"""Security tests verifying secret, API key, and JWT redaction in structlog JSON & tracebacks."""

import io
import json

from app.config.logging import REDACTED, configure_logging, get_logger
from tests.conftest import INTERNAL_API_KEY, make_internal_jwt, make_test_settings


def test_log_redaction_scrubs_secrets_headers_and_exception_tracebacks() -> None:
    stream = io.StringIO()
    settings = make_test_settings(log_format="json", log_level="DEBUG")
    configure_logging(settings, stream=stream)
    log = get_logger("security.audit")

    secret_jwt = make_internal_jwt(user_id="user_alice")
    assert secret_jwt.startswith("eyJ")

    # 1. Structured event dict with sensitive keys & embedded bearer string
    log.info(
        "Outbound request failed",
        authorization=f"Bearer {secret_jwt}",
        x_internal_api_key=INTERNAL_API_KEY,
        nested={"delegated_jwt": secret_jwt, "api_key": "super-secret-value"},
        safe_field="NVDA",
    )

    # 2. Exception traceback containing an inline JWT & Bearer token
    try:
        raise RuntimeError(
            f"Upstream rejected Authorization: Bearer {secret_jwt} and x-internal-api-key={INTERNAL_API_KEY}"
        )
    except RuntimeError:
        log.exception("Exception during authenticated request")

    output = stream.getvalue()
    assert secret_jwt not in output
    assert INTERNAL_API_KEY not in output
    assert "super-secret-value" not in output
    assert REDACTED in output
    assert "NVDA" in output

    lines = [json.loads(line) for line in output.strip().splitlines()]
    assert len(lines) == 2
    assert lines[0]["authorization"] == REDACTED
    assert lines[0]["x_internal_api_key"] == REDACTED
    assert lines[0]["nested"]["delegated_jwt"] == REDACTED
    assert lines[0]["nested"]["api_key"] == REDACTED
    assert REDACTED in lines[1]["exception"]
