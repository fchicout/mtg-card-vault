"""Structured JSON logging with redaction (FR-OPS-02).

Redaction runs on every record before it is formatted, so no handler can leak a secret.
Tokens, e-mail addresses and image data never reach the log output.
"""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from mtgvault.correlation import current_correlation_id

REDACTED = "[REDACTED]"

_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Z0-9._~+/=-]{6,}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Image payloads: data URIs, or any long unbroken base64-looking run.
_DATA_URI = re.compile(r"data:[\w.+-]+/[\w.+-]+;base64,[A-Za-z0-9+/=]+")
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")
_SECRET_KEY = re.compile(
    r"(?i)(password|passwd|secret|token|authorization|api[_-]?key|cookie|e-?mail)"
)

_PATTERNS = (_DATA_URI, _JWT, _BEARER, _EMAIL, _BASE64_BLOB)

# Attributes every LogRecord has; anything else was passed through ``extra=``.
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


def redact(value: Any) -> Any:
    """Return ``value`` with secrets removed; containers are cleaned recursively."""
    if isinstance(value, bytes | bytearray | memoryview):
        return f"[{REDACTED} {len(value)} bytes]"
    if isinstance(value, str):
        for pattern in _PATTERNS:
            value = pattern.sub(REDACTED, value)
        return value
    if isinstance(value, dict):
        return {
            key: REDACTED if isinstance(key, str) and _SECRET_KEY.search(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [redact(item) for item in value]
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        for key in set(vars(record)) - _STANDARD:
            setattr(
                record, key, REDACTED if _SECRET_KEY.search(key) else redact(getattr(record, key))
            )
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": current_correlation_id(),
        }
        for key in set(vars(record)) - _STANDARD - {"correlation_id"}:
            entry[key] = getattr(record, key)
        if record.exc_info:
            # The exception text can carry secrets (connection strings), so it is redacted too.
            entry["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Route all logging, including uvicorn's, through one redacting JSON handler on stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
