"""FR-OPS-02: JSON logs with a correlation id, and no tokens, e-mails or image data."""

import io
import json
import logging

import pytest

from mtgvault.correlation import reset_correlation_id, set_correlation_id
from mtgvault.logging_setup import REDACTED, JsonFormatter, RedactingFilter, redact

# Assembled at run time so no token-shaped literal sits in the repository (secret scanners).
JWT = ".".join(
    ["eyJ" + "hbGciOiJSUzI1NiJ9", "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0", "c2lnbmF0dXJlLXZhbHVl"]
)
EMAIL = "collector@example.org"
IMAGE = "A" * 400


@pytest.fixture
def stream() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def logger(stream: io.StringIO) -> logging.Logger:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    log = logging.getLogger("test.redaction")
    log.handlers[:] = [handler]
    log.setLevel(logging.DEBUG)
    log.propagate = False
    return log


def test_output_is_one_json_object_per_line_with_the_correlation_id(
    logger: logging.Logger, stream: io.StringIO
) -> None:
    token = set_correlation_id("req-42")
    try:
        logger.info("hello %s", "world", extra={"status": 200})
    finally:
        reset_correlation_id(token)
    entry = json.loads(stream.getvalue())
    assert entry["message"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["correlation_id"] == "req-42"
    assert entry["status"] == 200
    assert entry["timestamp"].endswith("+00:00")


def test_seeded_secrets_never_reach_the_output(logger: logging.Logger, stream: io.StringIO) -> None:
    logger.info(
        "auth failed for %s with Bearer abcdef123456 and %s",
        EMAIL,
        JWT,
        extra={
            "authorization": f"Bearer {JWT}",
            "user_email": EMAIL,
            "upload": b"\xff\xd8\xff" + b"\x00" * 100,
            "payload": f"data:image/jpeg;base64,{IMAGE}",
            "nested": {"password": "hunter2", "note": f"mail {EMAIL}", "items": [IMAGE]},
        },
    )
    output = stream.getvalue()
    for secret in (EMAIL, JWT, "abcdef123456", "hunter2", IMAGE, "\\xff"):
        assert secret not in output
    assert REDACTED in output


def test_exception_text_is_redacted(logger: logging.Logger, stream: io.StringIO) -> None:
    try:
        raise RuntimeError(f"cannot reach db for {EMAIL}")
    except RuntimeError:
        logger.exception("failed")
    entry = json.loads(stream.getvalue())
    assert EMAIL not in entry["exception"]
    assert "RuntimeError" in entry["exception"]


def test_ordinary_values_are_untouched() -> None:
    assert redact("plain text 42") == "plain text 42"
    assert redact({"count": 3, "name": "Black Lotus"}) == {"count": 3, "name": "Black Lotus"}
    assert redact(7) == 7
