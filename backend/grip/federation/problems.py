"""Errors of the federation routes, answered as application/problem+json."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

PROBLEM_MEDIA_TYPE = "application/problem+json"


class FederationProblem(Exception):  # noqa: N818 - named after RFC 9457
    """Raise anywhere under a federation route to answer with a problem.

    Domain handlers and providers use this to refuse a message or a request:
    404 when the caller has no relation with the object, 409 when a message
    does not fit the current state, 403 when access is not granted.
    """

    def __init__(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        *,
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.title = title
        self.detail = detail
        self.errors = errors

    def body(self, instance: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": "about:blank",
            "title": self.title,
            "status": self.status,
            # The contract requires a detail on every problem.
            "detail": self.detail or self.title,
        }
        if instance:
            body["instance"] = instance
        if self.errors:
            body["errors"] = self.errors
        return body


def problem_response(
    problem: FederationProblem, instance: str | None = None
) -> JSONResponse:
    return JSONResponse(
        problem.body(instance),
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
    )
