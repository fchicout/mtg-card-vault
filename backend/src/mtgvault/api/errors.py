"""RFC 9457 ``application/problem+json`` error documents (FR-API-02, ADR-013).

Every error path ends here: domain errors, request validation, HTTP errors and unexpected
exceptions. Each document carries the request's ``correlation_id``; an unexpected exception never
leaks its message or stack trace to the caller (it is logged with the same id).
"""

import logging
from collections.abc import Callable
from http import HTTPStatus

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from mtgvault.correlation import current_correlation_id
from mtgvault.domain.errors import (
    Conflict,
    DomainError,
    Forbidden,
    NotFound,
    PayloadTooLarge,
    RateLimited,
    Unauthenticated,
    UnsupportedMediaType,
    UpstreamUnavailable,
    ValidationFailed,
)

PROBLEM_JSON = "application/problem+json"
_LOCATIONS = frozenset({"body", "query", "path", "header", "cookie"})  # where, not a field name
_log = logging.getLogger("mtgvault.errors")


class FieldProblem(BaseModel):
    field: str
    message: str


class Problem(BaseModel):
    """The problem document returned for every error."""

    type: str
    title: str
    status: int
    detail: str
    correlation_id: str | None = None
    errors: list[FieldProblem] | None = None


# Documented on every operation so the OpenAPI contract (and the generated client) knows them.
PROBLEM_RESPONSES: dict[int | str, dict[str, object]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": Problem, "description": "Validation failed"},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": Problem, "description": "Unexpected error"},
}

_BY_DOMAIN_ERROR: list[tuple[type[DomainError], int, str]] = [
    (Unauthenticated, status.HTTP_401_UNAUTHORIZED, "unauthenticated"),
    (Forbidden, status.HTTP_403_FORBIDDEN, "forbidden"),
    (PayloadTooLarge, status.HTTP_413_CONTENT_TOO_LARGE, "payload-too-large"),
    (UnsupportedMediaType, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported-media-type"),
    (NotFound, status.HTTP_404_NOT_FOUND, "not-found"),
    (ValidationFailed, status.HTTP_422_UNPROCESSABLE_CONTENT, "validation-failed"),
    (Conflict, status.HTTP_409_CONFLICT, "conflict"),
    (RateLimited, status.HTTP_429_TOO_MANY_REQUESTS, "rate-limited"),
    (UpstreamUnavailable, status.HTTP_503_SERVICE_UNAVAILABLE, "upstream-unavailable"),
]


def _classify(error: DomainError) -> tuple[int, str]:
    for kind, code, slug in _BY_DOMAIN_ERROR:
        if isinstance(error, kind):
            return code, slug
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "internal-error"


def _title(code: int) -> str:
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return "Error"


def problem_response(
    code: int,
    slug: str,
    detail: str,
    *,
    errors: list[FieldProblem] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = Problem(
        type=f"urn:mtgvault:problem:{slug}",
        title=_title(code),
        status=code,
        detail=detail,
        correlation_id=current_correlation_id(),
        errors=errors,
    )
    return JSONResponse(
        body.model_dump(exclude_none=True),
        status_code=code,
        media_type=PROBLEM_JSON,
        headers=headers,
    )


def _headers_for(error: DomainError) -> dict[str, str] | None:
    if isinstance(error, RateLimited) and error.retry_after_seconds is not None:
        return {"Retry-After": str(error.retry_after_seconds)}
    if isinstance(error, Unauthenticated):
        challenge = 'Bearer error="invalid_token"' if error.invalid_token else "Bearer"
        return {"WWW-Authenticate": challenge}
    return None


def _domain_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, DomainError)  # noqa: S101  # registered for DomainError only
    code, slug = _classify(error)
    errors = (
        [FieldProblem(field=e.field, message=e.message) for e in error.errors]
        if isinstance(error, ValidationFailed)
        else None
    )
    headers = _headers_for(error)
    return problem_response(code, slug, error.detail, errors=errors or None, headers=headers)


def _request_validation(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)  # noqa: S101  # registered for it only
    fields = [
        FieldProblem(
            field=".".join(str(part) for part in problem["loc"] if part not in _LOCATIONS),
            message=problem["msg"],
        )
        for problem in error.errors()
    ]
    return problem_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation-failed",
        "The request is invalid.",
        errors=fields,
    )


def _http_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)  # noqa: S101  # registered for it only
    detail = error.detail if isinstance(error.detail, str) else _title(error.status_code)
    slug = _title(error.status_code).lower().replace(" ", "-")
    return problem_response(error.status_code, slug, detail, headers=dict(error.headers or {}))


def unexpected_error_response(error: Exception) -> JSONResponse:
    """Log the exception (with the correlation id) and answer with a generic 500 problem."""
    _log.error("unhandled exception", exc_info=error)
    return problem_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "internal-error", "An unexpected error occurred."
    )


def _unexpected(_: Request, error: Exception) -> JSONResponse:
    return unexpected_error_response(error)


def install_error_handlers(app: FastAPI) -> None:
    handlers: list[tuple[type[Exception], Callable[[Request, Exception], JSONResponse]]] = [
        (DomainError, _domain_error),
        (RequestValidationError, _request_validation),
        (StarletteHTTPException, _http_error),
        (Exception, _unexpected),
    ]
    for exception_type, handler in handlers:
        app.add_exception_handler(exception_type, handler)
