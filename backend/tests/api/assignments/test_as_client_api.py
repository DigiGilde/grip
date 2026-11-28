"""Whether this instance is the client of an assignment, on the list.

An assignment this instance asked for is followed under Aanvragen; the list
says so, and only to who may read the assignment at all.
"""

import json

import pytest
from fastapi import Depends

from grip.access import LocalDecider
from grip.access.deps import get_decider, get_relation_source
from grip.access.types import DataClass, deny
from grip.federation.bridge.organisations import own_organisation
from grip.services import assignments

from .conftest import by_id

A = DataClass.ASSIGNMENT_BASIC


@pytest.fixture
async def asked(world, db_session):
    """An assignment with this instance as client, as a request makes it."""
    own = await own_organisation(db_session)
    contractor = await assignments.upsert_organisation(
        db_session, name="Voorbeeldleverancier"
    )
    assignment, _ = await assignments.create_assignment_request(
        db_session,
        name="Aanvraag Zeta 2026",
        contractor_organisation_id=contractor.id,
        client_organisation_id=own.id,
        actor=world.owner,
    )
    await db_session.flush()
    return assignment


def _deny_basic_of(_test_app, assignment_id):
    """The normal rules, except class A of one assignment."""

    class Refuses(LocalDecider):
        async def evaluate(self, request):
            if (
                request.data_class is A
                and request.resource.assignment_id == assignment_id
            ):
                return deny("test")
            return await super().evaluate(request)

    def decider(relations=Depends(get_relation_source)):
        return Refuses(relations)

    _test_app.dependency_overrides[get_decider] = decider


async def test_the_list_says_which_assignment_this_instance_is_client_of(
    world, asked, as_person
):
    items = (await as_person(world.beheerder).get("/api/assignments")).json()["items"]
    assert by_id(items, "id", asked.id)["as_client"] is True
    assert by_id(items, "id", world.assignment.id)["as_client"] is False
    assert by_id(items, "id", world.other_assignment.id)["as_client"] is False


async def test_the_detail_says_it_too(world, asked, as_person):
    client = as_person(world.owner)
    theirs = (await client.get(f"/api/assignments/{asked.id}")).json()
    own = (await client.get(f"/api/assignments/{world.assignment.id}")).json()
    assert theirs["as_client"] is True
    assert own["as_client"] is False


async def test_without_class_a_the_field_is_not_there(
    world, asked, as_person, _test_app
):
    _deny_basic_of(_test_app, asked.id)
    body = (await as_person(world.beheerder).get("/api/assignments")).json()
    assert str(asked.id) not in json.dumps(body)
    assert [item["as_client"] for item in body["items"]] == [False, False]
    response = await as_person(world.beheerder).get(f"/api/assignments/{asked.id}")
    assert response.status_code == 404
    assert "as_client" not in response.text


async def test_who_reads_nothing_hears_nothing_of_it(world, asked, as_person):
    body = (await as_person(world.outsider).get("/api/assignments")).json()
    assert body["items"] == []
    assert "as_client" not in json.dumps(body)
