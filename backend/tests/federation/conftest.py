"""Fixtures for the federation tests.

Database tests use the same per-test transaction as the rest of the suite
and need a migrated database (``alembic upgrade head``).
"""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.federation import registry
from grip.federation.app import create_federation_app
from grip.federation.contract_loader import CONTRACT_DIR
from grip.federation.models import PEER_ROLE_COUNTERPART, Peer
from grip.federation.outway import OutwayClient
from grip.federation.routes import get_outway_client

PEER_HEADER = "Fsc-Request-Peer-Id"
CLIENT_PEER_ID = "00000000000000000001"
CONTRACTOR_PEER_ID = "00000000000000000002"
CLIENT_BASE = "https://grip.opdrachtgever.example"
CONTRACTOR_BASE = "https://grip.opdrachtnemer.example"
OUTWAY_URL = "http://outway.test"


def example(name: str, kind: str = "valid") -> dict[str, Any]:
    """A contract example by file name, without the ``.json`` suffix."""
    return json.loads((CONTRACT_DIR / "examples" / kind / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
def _clean_registries():
    registry.clear_registries()
    yield
    registry.clear_registries()


@pytest.fixture
def fed_settings() -> Settings:
    return get_settings().model_copy(
        update={
            "FEDERATION_INBOUND_ENABLED": True,
            "FEDERATION_OUTBOUND_ENABLED": True,
            "OUTWAY_URL": OUTWAY_URL,
            "FSC_PEER_ID_HEADER": PEER_HEADER,
            "FEDERATION_MAX_ATTEMPTS": 3,
        }
    )


class FakeOutway:
    """Records what is sent to the outway and answers from a handler."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.handler: Callable[[httpx.Request], httpx.Response] = lambda _request: (
            httpx.Response(503, text="no handler")
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def client(self, settings: Settings) -> OutwayClient:
        return OutwayClient(
            settings,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self._handle)),
        )


@pytest.fixture
def fake_outway() -> FakeOutway:
    return FakeOutway()


@pytest.fixture
def outway(fake_outway: FakeOutway, fed_settings: Settings) -> OutwayClient:
    return fake_outway.client(fed_settings)


@pytest.fixture(scope="session")
def fed_app():
    return create_federation_app()


@pytest.fixture
async def fed_client(db_session, fed_app, fed_settings, outway):
    """HTTPX client on the federation app, with the test's database session."""

    async def _override_get_db():
        yield db_session

    fed_app.dependency_overrides[get_db] = _override_get_db
    fed_app.dependency_overrides[get_settings] = lambda: fed_settings
    fed_app.dependency_overrides[get_outway_client] = lambda: outway
    async with AsyncClient(
        transport=ASGITransport(app=fed_app, raise_app_exceptions=False),
        base_url="http://inway.test",
    ) as client:
        yield client
    fed_app.dependency_overrides.clear()


@pytest.fixture
def make_peer(db_session):
    async def _make(
        peer_id: str = CONTRACTOR_PEER_ID,
        *,
        base_uri: str = CONTRACTOR_BASE,
        role: str = PEER_ROLE_COUNTERPART,
        **kwargs: Any,
    ) -> Peer:
        values: dict[str, Any] = {
            "name": f"Peer {peer_id[-2:]}",
            "organisation_tooi_uri": "",
            "grant_hashes": {
                "grip-opdrachtverkeer": f"$1$4$grant-{peer_id[-2:]}",
                "corpus-context": f"$1$4$corpus-{peer_id[-2:]}",
            },
        }
        values.update(kwargs)
        peer = Peer(peer_id=peer_id, base_uri=base_uri, role=role, **values)
        db_session.add(peer)
        await db_session.flush()
        return peer

    return _make


def as_peer(peer_id: str) -> dict[str, str]:
    return {PEER_HEADER: peer_id}
