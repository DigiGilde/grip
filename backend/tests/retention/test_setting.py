"""What the instance keeps of an assignment after its dossier closes."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from grip.core.auth import DEV_PERSON_COOKIE
from grip.events import retention as event_retention
from grip.services import instance_settings, retention
from grip.services.errors import DomainValidationError

KEY = "retention.assignment"


@pytest.mark.parametrize(
    "value",
    [
        None,
        {"outcome": "keep"},
        {"outcome": "destroy", "years": 1},
        {"outcome": "destroy", "years": 7},
        {"outcome": "destroy", "years": 100},
    ],
)
def test_what_the_selection_list_can_say(value):
    assert retention.ASSIGNMENT.check(value) == value


@pytest.mark.parametrize(
    "value",
    [
        {"outcome": "destroy", "years": 0},
        {"outcome": "destroy", "years": 101},
        {"outcome": "destroy", "years": -5},
        {"outcome": "destroy", "years": 7.0},
        {"outcome": "destroy", "years": "7"},
        {"outcome": "destroy", "years": True},
        {"outcome": "destroy", "years": None},
        {"outcome": "destroy"},
        {"outcome": "destroy", "years": 7, "extra": 1},
        {"outcome": "keep", "years": 7},
        {"outcome": "vernietig", "years": 7},
        {"outcome": "Keep"},
        {"outcome": None},
        {},
        "keep",
        "destroy",
        7,
        0,
        False,
        [],
        ["keep"],
    ],
)
def test_anything_else_is_refused(value):
    with pytest.raises(DomainValidationError):
        retention.ASSIGNMENT.check(value)


def test_nothing_is_destroyed_until_it_is_set():
    assert retention.ASSIGNMENT.key == KEY
    assert retention.ASSIGNMENT.default is None


def test_the_web_process_lists_every_term_the_page_shows():
    """The page shows only the keys the server lists, so a module that the web
    process no longer imports would drop its section without a sound."""
    keys = {
        "retention.assignment",
        "dossier.propose_close_after_days",
        "dossier.close_after_proposal_days",
        "events.retention_days",
        "events.read_retention_days",
        "vacancy.request_form_retention_days",
    }
    script = (
        "from grip.core.app import create_app\n"
        "from grip.services import instance_settings\n"
        "create_app()\n"
        "print(' '.join(sorted(instance_settings.declared())))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "DEV_NO_AUTH": "1"},
        check=False,
    )
    assert result.returncode == 0, result.stderr[-600:]
    assert keys <= set(result.stdout.split())


@pytest.mark.parametrize(
    "setting", [event_retention.RETENTION_DAYS, event_retention.READ_RETENTION_DAYS]
)
def test_a_term_in_days_stays_on_the_calendar(setting):
    assert setting.check(0) == 0
    assert setting.check(event_retention.MAX_DAYS) == event_retention.MAX_DAYS
    for wrong in (-1, event_retention.MAX_DAYS + 1, 1_000_000, 7.0, "7", True, None):
        with pytest.raises(DomainValidationError):
            setting.check(wrong)


async def test_the_beheerder_sets_it_and_nobody_else_sees_it(
    client, db_session, create_person
):
    beheerder = await create_person(
        "beheerder@example.org", name="Beheerder Voorbeeld", functions=["beheerder"]
    )
    lezer = await create_person(
        "lezer@example.org", name="Lezer Voorbeeld", functions=["lezer"]
    )
    planner = await create_person(
        "planner@example.org", name="Planner Voorbeeld", functions=["planner"]
    )
    other = await create_person("ander@example.org", name="Ander Voorbeeld")

    def act_as(person):
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))
        return client

    for person in (lezer, planner, other):
        answer = await act_as(person).get("/api/instance-settings")
        assert answer.status_code == 403
        assert KEY not in answer.text
        refused = await act_as(person).patch(
            "/api/instance-settings", json={"values": {KEY: {"outcome": "keep"}}}
        )
        assert refused.status_code == 403

    shown = (await act_as(beheerder).get("/api/instance-settings")).json()
    [item] = [item for item in shown["items"] if item["key"] == KEY]
    assert item["value"] is None and item["default"] is None
    assert item["label"]

    rule = {"outcome": "destroy", "years": 7}
    saved = await act_as(beheerder).patch(
        "/api/instance-settings", json={"values": {KEY: rule}}
    )
    assert saved.status_code == 200, saved.text
    assert await instance_settings.get(db_session, KEY) == rule

    for wrong in ({"outcome": "destroy", "years": 0}, {"outcome": "weg"}, "keep"):
        refused = await act_as(beheerder).patch(
            "/api/instance-settings", json={"values": {KEY: wrong}}
        )
        assert refused.status_code in (400, 422), wrong
    assert await instance_settings.get(db_session, KEY) == rule
