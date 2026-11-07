"""Per-request correlation id, shared by logs and error documents (FR-OPS-02, FR-API-02)."""

import re
import uuid
from contextvars import ContextVar

_CORRELATION_ID: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Accept only boring ids from the client, so a header can never inject log lines or markup.
_ACCEPTABLE = re.compile(r"[A-Za-z0-9._-]{1,128}")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def accept_or_generate(incoming: str | None) -> str:
    """Use the caller's ``X-Request-ID`` when it is safe, otherwise generate one."""
    if incoming is not None and _ACCEPTABLE.fullmatch(incoming):
        return incoming
    return new_correlation_id()


def set_correlation_id(value: str) -> object:
    return _CORRELATION_ID.set(value)


def reset_correlation_id(token: object) -> None:
    _CORRELATION_ID.reset(token)  # type: ignore[arg-type]


def current_correlation_id() -> str | None:
    return _CORRELATION_ID.get()
