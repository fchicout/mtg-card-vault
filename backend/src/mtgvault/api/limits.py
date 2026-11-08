"""Request-body limit for upload endpoints, enforced while the body streams in (FR-SCN-08).

A pure ASGI middleware: it refuses a body larger than the limit with a ``413`` problem document
from the ``Content-Length`` header when there is one, and while counting bytes when there is not,
so an oversized upload never has to be buffered in full.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mtgvault.api.errors import problem_response


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, path_prefix: str, max_bytes: int) -> None:
        self.app = app
        self._prefix = path_prefix
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self._prefix):
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max:
            await self._refuse(scope, receive, send)
            return
        seen = 0
        refused = False

        async def limited() -> Message:
            nonlocal seen, refused
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self._max:
                    refused = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        sent_start = False

        async def guarded_send(message: Message) -> None:
            nonlocal sent_start
            if refused and not sent_start:
                return  # the app answered an empty body; our 413 replaces it below
            sent_start = sent_start or message["type"] == "http.response.start"
            await send(message)

        await self.app(scope, limited, guarded_send)
        if refused and not sent_start:
            await self._refuse(scope, receive, send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(413, "payload-too-large", "The upload is larger than allowed.")
        await response(scope, receive, send)
