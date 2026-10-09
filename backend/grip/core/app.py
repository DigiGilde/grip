import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from grip.core.config import get_settings
from grip.core.database import async_session, close_db
from grip.core.problem import install_exception_handlers
from grip.core.session_store import DatabaseSessionStore, run_cleanup_loop
from grip.middleware.auth_required import AuthRequiredMiddleware
from grip.middleware.body_limit import BodyLimitMiddleware
from grip.middleware.csrf import CSRFMiddleware
from grip.middleware.event_context import EventContextMiddleware
from grip.middleware.expected_version import ExpectedVersionMiddleware
from grip.middleware.proxy_headers import TrustedProxyMiddleware
from grip.middleware.security_headers import SecurityHeadersMiddleware
from grip.middleware.session import ServerSideSessionMiddleware

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Let the application's own INFO lines reach the container log.

    uvicorn configures only its own loggers, so without this a line such as
    "OIDC login: ..." or "Example instance: the example data was loaded" is
    dropped and only warnings come through. Other libraries stay as they are.
    """
    own = logging.getLogger("grip")
    own.setLevel(logging.INFO)
    if not own.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s:     %(name)s: %(message)s")
        )
        own.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from grip.core.auth import check_oidc_transport, close_http_client
    from grip.core.bootstrap import bootstrap_beheerders

    settings = get_settings()
    # A deployed instance never signs with a throwaway key. Without a key of
    # its own no decision can be recorded: a person would log in again and
    # then be told nothing was laid down. Say so at start.
    if settings.PUBLIC_HOST:
        from grip.federation import signing

        if signing.get_signing_key(settings) is None:
            logger.error(
                "FEDERATION_SIGNING_KEY is not set: no decision (akkoord, "
                "afwijzing, interne goedkeuring) can be recorded."
            )
    # A provider whose endpoints are plain http would let people log in and
    # then refuse every session; say so now instead.
    await check_oidc_transport(settings)
    # An example instance fills itself on an empty database; an instance for
    # real work refuses a database that was ever filled as an example.
    from grip.core import example

    async with async_session() as db:
        await example.prepare(db, settings)
        await db.commit()
    async with async_session() as db:
        await bootstrap_beheerders(db, settings)
        await db.commit()

    # The shipped standard vacancy texts come along with the application.
    # Loading is idempotent and leaves what a person changed alone.
    if settings.VACANCY_TEXT_PROFILE.strip():
        from grip.services.vacancies import library

        async with async_session() as db:
            try:
                await library.load_profile(db, settings.VACANCY_TEXT_PROFILE.strip())
                await db.commit()
            except Exception:
                await db.rollback()
                logging.getLogger(__name__).exception(
                    "Loading the standard vacancy texts failed; the application "
                    "starts without them."
                )

    # Domain events are emitted inside web requests, so the handlers that
    # turn them into outbox messages must be registered here as well as in
    # the worker.
    if settings.FEDERATION_OUTBOUND_ENABLED:
        from grip.federation.events import register_event_handlers

        register_event_handlers()

    cleanup_task = asyncio.create_task(run_cleanup_loop(app.state.session_store))
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await close_http_client()
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    # Only expose OpenAPI and docs when OIDC is not configured (local
    # development), so a deployed instance does not show its API surface to
    # unauthenticated visitors.
    show_docs = not settings.OIDC_ISSUER

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="Opdrachten uitvoeren: begroting, inzet, kosten en offertes.",
        debug=settings.DEBUG,
        lifespan=lifespan,
        redirect_slashes=False,
        openapi_url="/api/openapi.json" if show_docs else None,
        docs_url="/api/docs" if show_docs else None,
        redoc_url="/api/redoc" if show_docs else None,
    )

    session_store = DatabaseSessionStore(
        session_factory=async_session,
        ttl_seconds=settings.SESSION_TTL_SECONDS,
        encryption_key=settings.SESSION_SECRET_KEY,
    )
    app.state.session_store = session_store

    # Starlette's add_middleware prepends, so the LAST one added is the
    # OUTERMOST. Request flow, outermost to innermost:
    #
    #   TrustedProxy -> CORS -> SecurityHeaders -> BodyLimit -> Session
    #   -> Auth -> CSRF -> GZip -> route
    #
    # TrustedProxy is outermost so everything below sees the scheme, host
    # and client address the user actually used.
    #
    # CORS must be outermost so that responses short-circuited by Auth or
    # CSRF also carry Access-Control-Allow-Origin. Without it the browser
    # hides the response and the frontend only sees "Failed to fetch".
    # Innermost: a fresh event context (correlation id, actor) per request.
    app.add_middleware(EventContextMiddleware)
    app.add_middleware(ExpectedVersionMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        CSRFMiddleware,
        cookie_domain=settings.SESSION_COOKIE_DOMAIN,
        cookie_secure=settings.SESSION_COOKIE_SECURE,
    )
    app.add_middleware(AuthRequiredMiddleware, settings=settings)
    app.add_middleware(
        ServerSideSessionMiddleware,
        store=session_store,
        secret_key=settings.SESSION_SECRET_KEY,
        cookie_domain=settings.SESSION_COOKIE_DOMAIN,
        cookie_secure=settings.SESSION_COOKIE_SECURE,
        cookie_max_age=settings.SESSION_TTL_SECONDS,
    )
    app.add_middleware(BodyLimitMiddleware)
    # Outside everything that can answer by itself (a 401, a refused CSRF
    # token, a body that is too large), so those answers carry the headers.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "If-Match"],
    )
    app.add_middleware(TrustedProxyMiddleware, trusted_proxies=settings.TRUSTED_PROXIES)
    if settings.DEV_NO_AUTH and settings.DEV_SPEED_TIMING:
        from grip.core.database import engine
        from grip.middleware import speed_timing

        speed_timing.watch(engine.sync_engine)
        app.add_middleware(speed_timing.SpeedTimingMiddleware)

    install_exception_handlers(app)

    from grip.api.routes import api_router

    app.include_router(api_router, prefix="/api")

    return app
