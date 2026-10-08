"""Error responses as application/problem+json (RFC 9457).

Every error the API returns has the same shape, so the frontend has one
place to look: ``title`` is the short kind of problem, ``detail`` the
sentence for the user, both in Dutch. Unhandled errors never leak internals:
the traceback goes to the log, the response is a fixed sentence.
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"

_TITLES: dict[int, str] = {
    400: "Ongeldig verzoek",
    401: "Niet ingelogd",
    403: "Geen toegang",
    404: "Niet gevonden",
    405: "Methode niet toegestaan",
    409: "Conflict",
    422: "Ongeldige invoer",
    429: "Te veel verzoeken",
    500: "Interne fout",
    501: "Niet beschikbaar",
    503: "Tijdelijk niet beschikbaar",
}


def problem_title(status_code: int) -> str:
    if status_code in _TITLES:
        return _TITLES[status_code]
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Fout"


def problem_body(
    status_code: int, detail: str | None = None, **extensions: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": problem_title(status_code),
        "status": status_code,
    }
    if detail:
        body["detail"] = detail
    body.update(extensions)
    return body


def problem_bytes(status_code: int, detail: str | None = None) -> bytes:
    """Serialized problem, for ASGI middleware that answers without a route."""
    return json.dumps(problem_body(status_code, detail)).encode("utf-8")


def problem_response(
    status_code: int,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    return JSONResponse(
        problem_body(status_code, detail, **extensions),
        status_code=status_code,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


async def _http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # A string detail is written for the user. Anything else (a dict or
    # list a route passed along) goes into an extension, not into detail.
    if isinstance(exc.detail, str):
        # Starlette fills in the English status phrase when no detail was
        # given; the Dutch title already says that.
        try:
            is_default = exc.detail == HTTPStatus(exc.status_code).phrase
        except ValueError:
            is_default = False
        detail = None if is_default else exc.detail
        return problem_response(exc.status_code, detail, headers=exc.headers)
    return problem_response(
        exc.status_code, None, headers=exc.headers, errors=exc.detail
    )


async def _validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Location, message and kind of each error; never the submitted value
    # or the validator context, which can echo input back.
    errors = [
        {
            "loc": [str(part) for part in error.get("loc", ())],
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in exc.errors()
    ]
    return problem_response(422, "De invoer is niet geldig.", errors=errors)


async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.error(
        "Unhandled error on %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return problem_response(500, "Er ging iets mis. Probeer het later opnieuw.")


def domain_error_status(exc: Exception) -> int:
    """The HTTP status for an error the service layer raised on purpose.

    Not found is 404. A request that is well formed but clashes with the
    state of the data (an illegal transition, a closed month or year, a quote
    that is already decided) is 409. Everything else the service layer
    refuses is invalid input: 422.
    """
    from grip.services import errors

    if isinstance(exc, errors.NotFoundError):
        return 404
    if getattr(exc, "http_status", None) == 409:
        return 409
    if isinstance(
        exc,
        errors.IllegalTransitionError
        | errors.ClosedYearError
        | errors.MonthClosedError
        | errors.QuoteAlreadyDecidedError,
    ):
        return 409
    return 422


_DOMAIN_TITLES: dict[str, str] = {
    "NotFoundError": "Niet gevonden",
    "IllegalTransitionError": "Statusovergang niet toegestaan",
    "ClosedYearError": "Jaar is gesloten",
    "MonthClosedError": "Maand is afgesloten",
    "QuoteAlreadyDecidedError": "Offerte is al afgehandeld",
    "QuoteHashMismatchError": "Hash komt niet overeen",
}


async def _domain_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    # The message of a DomainError is written for the user (Dutch), so it
    # is safe as detail. ``code`` lets a client tell the kinds apart without
    # parsing the sentence.
    status_code = domain_error_status(exc)
    name = type(exc).__name__
    body = problem_body(status_code, str(exc), code=name)
    if name in _DOMAIN_TITLES:
        body["title"] = _DOMAIN_TITLES[name]
    return JSONResponse(body, status_code=status_code, media_type=PROBLEM_MEDIA_TYPE)


def install_exception_handlers(app: FastAPI) -> None:
    from grip.services.errors import DomainError

    app.add_exception_handler(DomainError, _domain_exception_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_exception_handler)
