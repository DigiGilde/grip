"""The federation listener: a separate ASGI app with only the contract routes.

The routes other organisations call are not part of the main application.
They trust the peer id header that the FSC inway sets, so they must listen
on an address that only the inway can reach. A separate app on its own port
makes that a network rule instead of a path rule::

    uvicorn grip.federation.app:app --host 0.0.0.0 --port 8090

Paths are exactly those of the contract, under ``/v1``. There are no
sessions, no cookies and no CSRF here: the caller is a machine behind FSC.

A running instance with federation has three processes:

- the main application (people), on its own port;
- this listener (other instances, through the inway), on port 8090, with
  ``FEDERATION_INBOUND_ENABLED=1``;
- the worker, ``python -m grip.worker``, which sends the outbox through the
  outway (``FEDERATION_OUTBOUND_ENABLED=1`` and ``OUTWAY_URL``) and catches
  up on stored messages.

On start-up the listener registers the bridge to the domain
(:func:`grip.federation.bridge.register_bridge`), so received messages are
processed and pull operations are answered.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from grip.federation.contract_loader import (
    PATH_PREFIX,
    SERVICE_OPDRACHTVERKEER,
    api_version,
    load_openapi,
)
from grip.federation.problems import FederationProblem, problem_response
from grip.federation.routes import router
from grip.middleware.event_context import EventContextMiddleware

logger = logging.getLogger(__name__)

# The only route without a peer check: a probe for the hosting platform.
HEALTH_PATH = "/healthz"


def install_problem_handlers(app: FastAPI) -> None:
    """Answer every error of the federation routes as problem+json."""

    @app.exception_handler(FederationProblem)
    async def _problem(request: Request, exc: FederationProblem) -> JSONResponse:
        return problem_response(exc, instance=request.url.path)

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            f"{'/'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        ]
        return problem_response(
            FederationProblem(
                400,
                "Ongeldig verzoek",
                "Een parameter van het verzoek is ongeldig of ontbreekt.",
                errors=errors,
            ),
            instance=request.url.path,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(
            FederationProblem(exc.status_code, str(exc.detail)),
            instance=request.url.path,
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on a federation route")
        return problem_response(
            FederationProblem(500, "Interne fout"), instance=request.url.path
        )


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    from grip.federation.bridge import register_bridge
    from grip.federation.events import register_event_handlers

    # A received message can cause a domain change that has to go out again
    # (not back to its sender), so the event handlers belong here as well.
    register_bridge()
    register_event_handlers()
    yield


def create_federation_app() -> FastAPI:
    app = FastAPI(
        title=SERVICE_OPDRACHTVERKEER,
        lifespan=_lifespan,
        version=api_version(),
        # The contract is served by the router itself, behind the peer check.
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        redirect_slashes=False,
    )
    install_problem_handlers(app)
    # A fresh event context per incoming message.
    app.add_middleware(EventContextMiddleware)
    app.include_router(router, prefix=PATH_PREFIX)

    @app.get(HEALTH_PATH, include_in_schema=False)
    async def _health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def generated_openapi(app: FastAPI) -> dict[str, Any]:
    """The OpenAPI document FastAPI generates for the federation routes.

    Used by the conformance test, which compares it with the contract. The
    schemas are the contract's own; the routes refer to them by name.
    """
    document = get_openapi(
        title=app.title, version=app.version, openapi_version="3.1.0", routes=app.routes
    )
    components = document.setdefault("components", {})
    components.setdefault("schemas", {}).update(
        load_openapi(SERVICE_OPDRACHTVERKEER)["components"]["schemas"]
    )
    return document


app = create_federation_app()
