"""Regression guard: every API route must declare an authorization dependency.

Walks the app's route table and fails the build when a route under ``/api/``
has neither one of the recognised dependencies nor an entry on the explicit
public list. This catches the common mistake of adding an endpoint and
forgetting who may call it.

A route that is public on purpose goes in ``_PUBLIC_ROUTES`` with the reason.
The list must stay in step with the middleware: a route listed here that the
middleware still blocks, or the other way around, also fails.

Needs no database.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import routing
from fastapi.routing import APIRoute

from grip.middleware.auth_required import is_public_path

# Routes reachable without a session, each with the reason.
_PUBLIC_ROUTES: dict[str, str] = {
    "/api/health/": "platform health probe",
    "/api/health/live": "platform liveness probe",
    "/api/health/ready": "platform readiness probe",
    "/api/auth/login": "starts the OIDC flow",
    "/api/auth/callback": "OIDC redirect target",
    "/api/auth/logout": "ends the session",
    "/api/auth/status": "tells the frontend whether anyone is logged in",
    "/api/auth/diagnose": (
        "404 unless OIDC_DIAGNOSTICS is on (refused when deployed): shows, "
        "masked, what the provider sent, also after a refused login"
    ),
    "/api/auth/diagnose/reauth": (
        "404 unless OIDC_DIAGNOSTICS is on: starts the forced re-authentication test"
    ),
    "/api/auth/passkey/options": "logging in with a passkey: gives a challenge",
    "/api/auth/passkey/verify": "logging in with a passkey: the assertion is checked",
    "/api/instance": "name and base URI only; the login page shows the name",
    "/api/integrations/wies/export": "no session: a machine with a key (Wies)",
    "/api/integrations/wies/proposed-colleagues": (
        "no session: a machine with a key (Wies)"
    ),
    "/api/gebeurtenissen": "no session: a system with a key reads the event feed",
}

# Dependency callables that count as authorization.
_AUTHZ_DEP_NAMES = {
    "get_current_person",  # any active, logged-in person
    "_check",  # inner closure of require_function
    # A person of this instance, or an invited signer with a guest session;
    # the access model then matches the invitation per quote.
    "get_signer",
}


@dataclass(frozen=True)
class _Route:
    path: str
    methods: frozenset[str]
    dependant: Any


def _has_authz_dep(route: _Route) -> bool:
    def _walk(deps) -> bool:
        for dep in deps:
            call = getattr(dep, "call", None)
            if call is not None and call.__name__ in _AUTHZ_DEP_NAMES:
                return True
            if _walk(getattr(dep, "dependencies", [])):
                return True
        return False

    return _walk(route.dependant.dependencies)


def _api_routes(app) -> list[_Route]:
    """Every API route with its effective dependencies.

    Recent FastAPI versions keep included routers as lazy nodes in
    ``app.routes`` instead of flattening them, so a plain loop over
    ``app.routes`` finds nothing and the guard would pass vacuously.
    ``iter_route_contexts`` resolves them, including dependencies that were
    added on ``include_router``.
    """
    found: list[_Route] = []
    iter_contexts = getattr(routing, "iter_route_contexts", None)
    if iter_contexts is None:
        for route in app.routes:
            if isinstance(route, APIRoute):
                found.append(
                    _Route(route.path, frozenset(route.methods), route.dependant)
                )
    else:
        for ctx in iter_contexts(app.routes):
            if not isinstance(ctx.original_route, APIRoute):
                continue
            effective = getattr(ctx, "_effective_route", ctx.original_route)
            found.append(
                _Route(ctx.path, frozenset(ctx.methods or ()), effective.dependant)
            )
    return [r for r in found if r.path.startswith("/api/")]


def test_route_table_is_not_empty(_test_app):
    """Without this the other tests pass when route discovery breaks."""
    paths = {route.path for route in _api_routes(_test_app)}
    assert {"/api/instance", "/api/auth/status", "/api/health/"} <= paths


def test_every_route_has_authorization(_test_app):
    offenders = sorted(
        f"{sorted(route.methods)} {route.path}"
        for route in _api_routes(_test_app)
        if route.path not in _PUBLIC_ROUTES and not _has_authz_dep(route)
    )
    assert not offenders, (
        "Routes without an authorization dependency. Add CurrentPerson or "
        "require_function(...), or list the route in _PUBLIC_ROUTES with the "
        "reason:\n" + "\n".join(f"  - {o}" for o in offenders)
    )


def test_public_list_matches_middleware(_test_app):
    paths = {route.path for route in _api_routes(_test_app)}

    stale = sorted(set(_PUBLIC_ROUTES) - paths)
    assert not stale, f"Public routes that no longer exist: {stale}"

    blocked = sorted(p for p in _PUBLIC_ROUTES if not is_public_path(p))
    assert not blocked, f"Listed as public but blocked by the middleware: {blocked}"

    open_by_middleware = sorted(
        p for p in paths if is_public_path(p) and p not in _PUBLIC_ROUTES
    )
    assert not open_by_middleware, (
        f"Let through by the middleware but not listed as public: {open_by_middleware}"
    )


def test_guard_detects_an_unprotected_route(_test_app):
    """The guard itself must work: an unprotected route is an offender."""
    from fastapi import APIRouter, Depends, FastAPI

    from grip.core.auth import CurrentPerson, require_function

    router = APIRouter()

    @router.get("/api/open")
    async def _open() -> dict:
        return {}

    @router.get("/api/person")
    async def _person(_p: CurrentPerson) -> dict:
        return {}

    @router.get("/api/function", dependencies=[Depends(require_function("lezer"))])
    async def _function() -> dict:
        return {}

    app = FastAPI()
    app.include_router(router)
    result = {r.path: _has_authz_dep(r) for r in _api_routes(app)}
    assert result == {
        "/api/open": False,
        "/api/person": True,
        "/api/function": True,
    }
