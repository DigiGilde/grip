"""Reads of the sensitive classes D, E and F are logged."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import select

from grip.access import build_response, in_class
from grip.access.types import DataClass
from grip.events import logboek
from grip.models.stream_event import StreamEvent

A = in_class(DataClass.ASSIGNMENT_BASIC)
D = in_class(DataClass.PERSON_RATE)
E = in_class(DataClass.PERSON_COST)


class _PersonRow(BaseModel):
    person_id: Annotated[UUID, A]
    name: Annotated[str, A]
    billing_scale: Annotated[int | None, D] = None
    cost_rate_cents: Annotated[int | None, E] = None


async def _reads(db, person_id) -> list[StreamEvent]:
    await db.flush()
    return list(
        await db.scalars(
            select(StreamEvent)
            .where(StreamEvent.type == "data.read", StreamEvent.person_id == person_id)
            .order_by(StreamEvent.seq)
        )
    )


def test_only_a_sensitive_field_that_goes_out_is_noted():
    ledger = logboek.start()
    first, second, third = uuid4(), uuid4(), uuid4()
    everything = {
        DataClass.ASSIGNMENT_BASIC,
        DataClass.PERSON_RATE,
        DataClass.PERSON_COST,
    }
    # Permitted and filled: noted, per class.
    build_response(
        _PersonRow(person_id=first, name="a", billing_scale=12, cost_rate_cents=5),
        everything,
    )
    # Not permitted: the field does not go out, so nothing was read.
    build_response(
        _PersonRow(person_id=second, name="b", billing_scale=12),
        {DataClass.ASSIGNMENT_BASIC},
    )
    # Permitted but empty: there was nothing to read.
    build_response(_PersonRow(person_id=third, name="c"), everything)
    assert ledger == {first: {DataClass.PERSON_RATE, DataClass.PERSON_COST}}


async def test_a_read_becomes_an_event_about_that_person(db_session):
    person_id = uuid4()
    ledger = logboek.start()
    build_response(
        _PersonRow(person_id=person_id, name="a", billing_scale=12, cost_rate_cents=5),
        {DataClass.PERSON_RATE, DataClass.PERSON_COST, DataClass.ASSIGNMENT_BASIC},
    )
    logboek.write_reads(db_session, ledger, purpose="GET /voorbeeld")
    (event,) = await _reads(db_session, person_id)
    assert event.new_value == {"classes": ["person_cost", "person_rate"]}
    assert event.purpose == "GET /voorbeeld"
    # Filed under the most sensitive class that was read; no value is kept.
    assert event.existence_class == "person_cost"
    assert "12" not in str(event.new_value)
    assert ledger == {}


async def test_reading_a_scale_through_the_api_is_logged(
    client, as_person, world, db_session
):
    answer = await as_person(world.beheerder).get(f"/api/people/{world.member.id}")
    assert answer.status_code == 200, answer.text
    assert "billing_scale" in answer.text
    reads = await _reads(db_session, world.member.id)
    assert reads, "the read of a billing scale left no event"
    event = reads[-1]
    assert (event.actor_kind, event.actor_person_id) == ("person", world.beheerder.id)
    assert "person_rate" in event.new_value["classes"]
    assert event.purpose == "GET /people/{person_id}"
    assert len(event.correlation_id) == 32

    # Who may not see the scale reads nothing, and nothing is logged.
    before = len(reads)
    other = await as_person(world.outsider).get(f"/api/people/{world.member.id}")
    assert "billing_scale" not in other.text
    assert len(await _reads(db_session, world.member.id)) == before


async def test_the_person_can_see_who_read_their_data(
    client, as_person, world, db_session
):
    await as_person(world.beheerder).get(f"/api/people/{world.member.id}")
    mine = await as_person(world.member).get(
        "/api/events", params={"kind": "reads", "person_id": str(world.member.id)}
    )
    items = mine.json()["items"]
    assert items and items[0]["actor_name"] == "Bea Beheer"
    theirs = await as_person(world.colleague).get(
        "/api/events", params={"kind": "reads"}
    )
    assert theirs.json()["items"] == []


async def test_a_list_is_one_read_with_the_number_of_persons(db_session):
    people = [uuid4() for _ in range(40)]
    ledger = logboek.start()
    for person_id in people:
        build_response(
            _PersonRow(person_id=person_id, name="a", billing_scale=12),
            {DataClass.PERSON_RATE, DataClass.ASSIGNMENT_BASIC},
        )
    events = logboek.write_reads(db_session, ledger, purpose="GET /people")
    await db_session.flush()
    (event,) = events
    assert event.type == "data.read" and event.person_id is None
    assert event.new_value == {"classes": ["person_rate"], "persons": 40}
    # Who was seen is kept, for the log record per person the standard asks.
    assert sorted(event.payload["person_ids"]) == sorted(str(p) for p in people)
    # A list of whose data was read is for the beheerder.
    assert event.existence_class is None

    from grip.core.config import get_settings

    records = logboek.to_log_records(event, get_settings())
    assert len(records) == 40 and logboek.is_processing(event)
    assert len({r["attributes"]["dpl.core.data_subject_id"] for r in records}) == 40
    assert len({r["span_id"] for r in records}) == 40
    assert {r["trace_id"] for r in records} == {event.correlation_id}
    assert not any(str(p) in str(records) for p in people)


async def test_a_page_that_lists_people_logs_one_read(
    client, as_person, world, db_session
):
    async def reads() -> int:
        await db_session.flush()
        return len(
            list(
                await db_session.scalars(
                    select(StreamEvent.seq).where(StreamEvent.type == "data.read")
                )
            )
        )

    before = await reads()
    answer = await as_person(world.beheerder).get("/api/people")
    assert answer.status_code == 200 and "billing_scale" in answer.text
    assert await reads() == before + 1
