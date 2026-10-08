"""Which loops the worker starts. Needs no database."""

from grip.core.config import get_settings
from grip.worker import _loops


def _names(**update) -> list[str]:
    loops = _loops(get_settings().model_copy(update=update))
    names = [loop.__name__ for loop in loops]
    for loop in loops:
        loop.close()
    return names


def test_nothing_runs_when_federation_is_off():
    assert (
        _names(FEDERATION_OUTBOUND_ENABLED=False, FEDERATION_INBOUND_ENABLED=False)
        == []
    )


def test_each_direction_has_its_own_loop():
    assert _names(
        FEDERATION_OUTBOUND_ENABLED=True, FEDERATION_INBOUND_ENABLED=False
    ) == ["run_outbox_loop"]
    assert _names(
        FEDERATION_OUTBOUND_ENABLED=False, FEDERATION_INBOUND_ENABLED=True
    ) == ["run_inbox_loop"]


def test_federation_is_off_by_default():
    settings = type(get_settings())(_env_file=None, DEV_NO_AUTH=True)
    assert settings.FEDERATION_INBOUND_ENABLED is False
    assert settings.FEDERATION_OUTBOUND_ENABLED is False
