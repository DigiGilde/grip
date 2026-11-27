"""Which loops the worker starts. Needs no database."""

import asyncio

from grip import worker
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


def _started(monkeypatch, **update) -> list[str]:
    settings = get_settings().model_copy(
        update={
            "FEDERATION_OUTBOUND_ENABLED": False,
            "FEDERATION_INBOUND_ENABLED": False,
            **update,
        }
    )
    started: list[str] = []

    async def gather(*loops):
        for loop in loops:
            started.append(loop.__name__)
            loop.close()

    async def nothing() -> None:
        return None

    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "register_event_handlers", lambda: None)
    monkeypatch.setattr(worker, "close_db", nothing)
    monkeypatch.setattr(worker.asyncio, "gather", gather)
    asyncio.run(worker.main())
    return started


def test_the_retention_round_runs_when_it_has_an_hour(monkeypatch):
    assert "run_retention_loop" in _started(monkeypatch, RETENTION_HOUR="4")


def test_no_retention_round_without_an_hour(monkeypatch):
    started = _started(
        monkeypatch, RETENTION_HOUR="", TASKS_EVALUATE_INTERVAL_SECONDS=300
    )
    assert "run_retention_loop" not in started
    assert "run_task_loop" in started
