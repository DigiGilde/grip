"""Shared fixtures for API tests.

Tests that touch the database use a running PostgreSQL (the compose db on
port 5434 by default) with a per-test transaction that is rolled back, so
nothing is ever committed. Tests that need no database must not request the
``db_session`` or ``client`` fixtures.
"""

import os
from typing import Any

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# The test environment has no OIDC. Settings fails closed in that state, so
# opt in to the no-auth mode before the first get_settings() call below (it
# is cached, so this must run first).
os.environ.setdefault("DEV_NO_AUTH", "1")
# Every read model that is remembered between requests is computed again on
# each use and compared: a value that changed without an event that says so
# fails the test (grip.services.read_cache).
os.environ.setdefault("READ_CACHE", "verify")

from grip.core.config import get_settings  # noqa: E402
from grip.core.database import get_db  # noqa: E402
from grip.core.session_store import SessionStore  # noqa: E402
from grip.events import completeness  # noqa: E402
from grip.middleware.csrf import CSRF_COOKIE_NAME  # noqa: E402
from grip.middleware.csrf import _starts as _csrf_starts  # noqa: E402
from grip.middleware.session import ServerSideSessionMiddleware  # noqa: E402
from grip.models.person import Person  # noqa: E402
from grip.models.role import PersonRole  # noqa: E402

settings = get_settings()


class InMemorySessionStore(SessionStore):
    """Session store for tests: no database connections."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def get(self, session_id: str) -> dict[str, Any] | None:
        return self._data.get(session_id)

    async def set(self, session_id: str, data: dict[str, Any]) -> None:
        self._data[session_id] = data

    async def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)

    async def cleanup(self) -> int:
        return 0


@pytest.fixture(scope="session")
def _test_engine():
    return create_async_engine(settings.DATABASE_URL, echo=False, poolclass=NullPool)


@pytest.fixture(scope="session")
def _test_app():
    """The FastAPI app, created once for the whole test run."""
    from grip.core.app import create_app

    return create_app()


@pytest.fixture
async def db_session(_test_engine):
    """A session in a transaction that is rolled back after the test."""
    async with _test_engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await txn.rollback()


def _find_session_middleware(app):
    mw = app.middleware_stack
    while mw is not None:
        if isinstance(mw, ServerSideSessionMiddleware):
            return mw
        mw = getattr(mw, "app", None)
    return None


@pytest.fixture
async def client(db_session: AsyncSession, _test_app):
    """HTTPX client on the app, with the test's database session.

    Fetches a CSRF token first and sends it on every state-changing request.
    """
    app = _test_app

    # Completeness of the event stream: a request that changes domain data
    # without an event that covers it fails the test (grip.events.completeness).
    unrecorded: list[str] = []

    async def _override_get_db(request: Request):
        with completeness.watch(db_session) as unit:
            yield db_session
            # In production the request commits here.
            await db_session.flush()
        route = getattr(request.scope.get("route"), "path", request.url.path)
        unrecorded.extend(
            f"{request.method} {route}: {missing}" for missing in unit.unrecorded()
        )

    app.dependency_overrides[get_db] = _override_get_db

    if app.middleware_stack is None:
        app.middleware_stack = app.build_middleware_stack()
    session_mw = _find_session_middleware(app)
    original_store = session_mw.store
    session_mw.store = InMemorySessionStore()

    csrf = {"token": ""}

    async def _inject_csrf(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and csrf["token"]:
            request.headers["X-CSRF-Token"] = csrf["token"]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        event_hooks={"request": [_inject_csrf]},
    ) as ac:
        init_resp = await ac.get("/api/auth/status")
        csrf["token"] = init_resp.cookies.get(CSRF_COOKIE_NAME, "")
        yield ac

    app.dependency_overrides.clear()
    session_mw.store = original_store
    report = os.environ.get("GRIP_COMPLETENESS_REPORT")
    if report and unrecorded:
        with open(report, "a") as out:
            out.writelines(f"{line}\n" for line in unrecorded)
    elif not report:
        assert not unrecorded, "changes without an event: " + "; ".join(
            dict.fromkeys(unrecorded)
        )


@pytest.fixture
def create_person(db_session: AsyncSession):
    """Factory for persons, optionally holding functions.

    Usage::

        person = await create_person("a@example.org", functions=["beheerder"])
    """

    async def _create(
        email: str = "persoon@example.org",
        *,
        name: str = "Test Persoon",
        functions: list[str] | None = None,
        **kwargs: Any,
    ) -> Person:
        person = Person(name=name, email=email, **kwargs)
        db_session.add(person)
        await db_session.flush()
        for role_id in functions or []:
            db_session.add(PersonRole(person_id=person.id, role_id=role_id))
        await db_session.flush()
        return person

    return _create


@pytest.fixture(autouse=True)
def _nothing_remembered():
    """What the process remembers between requests (read models, the last
    look of the task engine) starts empty in every test."""
    from grip.services import read_cache
    from grip.tasks import engine

    read_cache.clear()
    engine.forget_evaluation()


@pytest.fixture(autouse=True)
def _fresh_session_starts():
    """Every test opens the application anew from one address; the limit on
    sessions without a login is not what is being tested."""
    _csrf_starts.reset()
