"""Refuse a request body that is larger than anything grip accepts.

Without this a single request can hand the process as much as the sender
cares to send: a JSON body is read whole before a field is looked at. The
routes that take a file check its size themselves; this is the ceiling over
all of them, applied before a byte is read where the sender states a length.

Three ceilings:

* a JSON or other plain body: 1 MiB (the longest texts are 20,000 characters
  per part);
* a file upload (``multipart/form-data``): 12 MiB, above the 10 MiB a stored
  document may be;
* a proof bundle offered for checking: 13 MiB.
"""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from grip.core.problem import PROBLEM_MEDIA_TYPE, problem_bytes

MAX_BODY_BYTES = 1024 * 1024
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_BUNDLE_BODY_BYTES = 13 * 1024 * 1024

_BUNDLE_PATHS = ("/api/proof/verify", "/api/signing/verify")
_DETAIL = "Dit is groter dan grip aanneemt."


def limit_for(path: str, content_type: str) -> int:
    """The largest body a request to ``path`` with this content type may have."""
    if path in _BUNDLE_PATHS:
        return MAX_BUNDLE_BODY_BYTES
    if content_type.split(";", 1)[0].strip().lower() == "multipart/form-data":
        return MAX_UPLOAD_BYTES
    return MAX_BODY_BYTES


class BodyLimitMiddleware:
    """ASGI middleware that answers 413 to a body over the ceiling."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").decode("latin-1")
        limit = limit_for(scope.get("path", ""), content_type)

        declared = headers.get(b"content-length", b"").decode("latin-1").strip()
        if declared.isdigit() and int(declared) > limit:
            body = problem_bytes(413, _DETAIL)
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [
                        (b"content-type", PROBLEM_MEDIA_TYPE.encode()),
                        (b"content-length", str(len(body)).encode()),
                        (b"connection", b"close"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        received = 0

        async def counted() -> Message:
            # A sender that states no length (or a false one) is counted as
            # the body comes in.
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=_DETAIL)
            return message

        await self.app(scope, counted, send)
