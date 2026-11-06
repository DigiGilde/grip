"""The federation fixtures, for a chronicle that starts at another instance."""

import pytest

from grip.services import events
from tests.federation.conftest import (  # noqa: F401
    fake_outway,
    fed_app,
    fed_client,
    fed_settings,
    make_peer,
    outway,
)


@pytest.fixture(autouse=True)
def _no_event_handlers():
    # A handler flushes in the middle of an act, which moves audit rows that
    # share a flush. Importing the routes registers them: without this a test
    # would depend on which file ran before it.
    events.clear_handlers()
    yield
    events.clear_handlers()
