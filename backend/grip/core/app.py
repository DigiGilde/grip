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
from grip.middleware.csrf import CSRFMiddleware
from grip.middleware.proxy_headers import TrustedProxyMiddleware
from grip.middleware.security_headers import SecurityHeadersMiddleware
from grip.middleware.session import ServerSideSessionMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from grip.core.auth import check_oidc_transport, close_http_client
    from grip.core.bootstrap import bootstrap_beheerders

    settings = get_settings()
    # A provider whose endpoints are plain http would let people log in and
    # then refuse every session; say so now instead.
    await check_oidc_transport(settings)
    async with async_session() as db:
        await bootstrap_beheerders(db, settings)
        await db.commit()

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
    #   TrustedProxy -> CORS -> Session -> Auth -> CSRF -> SecurityHeaders
    #   -> GZip -> route
    #
    # TrustedProxy is outermost so everything below sees the scheme, host
    # and client address the user actually used.
    #
    # CORS must be outermost so that responses short-circuited by Auth or
    # CSRF also carry Access-Control-Allow-Origin. Without it the browser
    # hides the response and the frontend only sees "Failed to fetch".
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(SecurityHeadersMiddleware)
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_middleware(TrustedProxyMiddleware, trusted_proxies=settings.TRUSTED_PROXIES)

    install_exception_handlers(app)

    from grip.api.routes import api_router

    app.include_router(api_router, prefix="/api")

    return app
