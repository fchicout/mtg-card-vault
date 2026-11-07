"""Correlation id and access logging (FR-OPS-02). Pure ASGI, so it also wraps error responses."""

import logging
import time

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mtgvault.api.errors import unexpected_error_response
from mtgvault.correlation import accept_or_generate, reset_correlation_id, set_correlation_id

HEADER = "X-Request-ID"
_access = logging.getLogger("mtgvault.access")


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        correlation_id = accept_or_generate(Headers(scope=scope).get(HEADER))
        token = set_correlation_id(correlation_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_header(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[HEADER] = correlation_id
            await send(message)

        try:
            try:
                await self._app(scope, receive, send_with_header)
            except Exception as error:  # last line of defence: answer with a problem document
                # Starlette would handle this outside this middleware, after the id is reset.
                await unexpected_error_response(error)(scope, receive, send_with_header)
        finally:
            # Path only: query strings can carry tokens and are never logged.
            _access.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            reset_correlation_id(token)
