"""Domain and application error hierarchy (FR-API-02).

Framework-free on purpose: the HTTP layer maps these to RFC 9457 problem documents
(``api/errors.py``), so business code never knows about status codes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldError:
    """One offending input field, reported back to the caller."""

    field: str
    message: str


class DomainError(Exception):
    """Base class of every error the application raises on purpose."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFound(DomainError):
    """The requested resource does not exist, or is not visible to the caller."""


class ValidationFailed(DomainError):
    """Input is well-formed but violates a business rule."""

    def __init__(self, detail: str, errors: tuple[FieldError, ...] = ()) -> None:
        super().__init__(detail)
        self.errors = errors


class Conflict(DomainError):
    """The request conflicts with the current state of the resource."""


class UpstreamUnavailable(DomainError):
    """A dependency (for example Scryfall) is down, slow or misbehaving."""


class RateLimited(DomainError):
    """The caller, or an upstream, asked us to slow down."""

    def __init__(self, detail: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(detail)
        self.retry_after_seconds = retry_after_seconds


class Unauthenticated(DomainError):
    """No valid credentials. The detail is generic on purpose (reasons are logged, not returned)."""

    def __init__(self, detail: str, *, invalid_token: bool = False) -> None:
        super().__init__(detail)
        self.invalid_token = invalid_token


class Forbidden(DomainError):
    """The caller is authenticated but not allowed to do this."""


class PayloadTooLarge(DomainError):
    """The request body is larger than this endpoint accepts (413)."""


class UnsupportedMediaType(DomainError):
    """The body is not one of the accepted file types (415)."""
