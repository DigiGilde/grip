"""Tamper evidence: the chain, the check, the guard, and erasure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from grip.events import chain, check, retention, stream
from grip.models.stream_event import StreamEvent
from grip.services import instance_settings


async def _write(db, count: int = 4) -> list[StreamEvent]:
    events = [
        stream.append(
            db,
            subject=("rate_card", f"card-{index}"),
            action="update",
            old={"rate": index},
            new={"rate": index + 1},
            note=f"stap {index}",
        )
        for index in range(count)
    ]
    await db.flush()
    return events


async def _rows(db, first_seq: int) -> list[dict]:
    table = StreamEvent.__table__
    result = await db.execute(
        select(table).where(table.c.seq >= first_seq).order_by(table.c.seq)
    )
    return [dict(row) for row in result.mappings()]


async def test_each_event_points_at_the_one_before(db_session):
    events = await _write(db_session)
    for previous, event in zip(events, events[1:], strict=False):
        assert event.seq == previous.seq + 1
        assert event.prev_hash == previous.hash
    verdict = await check.verify_stream(db_session, from_seq=events[0].seq)
    assert verdict.intact and verdict.checked == len(events)
    assert verdict.head_hash == events[-1].hash
    assert "De keten klopt" in check.describe(verdict)[0]


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [
        (lambda rows: rows[1].update(subject_id="someone-else"), "hash"),
        (lambda rows: rows[1].update(actor_kind="person"), "hash"),
        (
            lambda rows: rows[1].update(
                occurred_at=rows[1]["occurred_at"] + timedelta(1)
            ),
            "hash",
        ),
        (lambda rows: rows[1].update(new_value={"rate": 999}), "value"),
        (lambda rows: rows[1].update(note="anders"), "value"),
        (lambda rows: rows[1].update(field_classes={"*": "assignment_basic"}), "hash"),
        (lambda rows: rows.pop(1), "prev_hash"),
        (lambda rows: rows.insert(1, rows.pop(2)), "prev_hash"),
    ],
)
async def test_the_check_says_where_the_chain_breaks(db_session, tamper, reason):
    events = await _write(db_session)
    rows = await _rows(db_session, events[0].seq)
    at = rows[1]["seq"] if reason != "prev_hash" else None
    tamper(rows)
    verdict = chain.verify(rows, expected_prev=events[0].prev_hash)
    assert not verdict.intact
    found = [(found.seq, found.reason) for found in verdict.breaks]
    assert reason in {r for _seq, r in found}
    if at is not None:
        assert (at, reason) in found
    assert "gebroken" in check.describe(verdict)[0]


async def test_a_rewritten_tail_does_not_join_the_old_chain(db_session):
    """Changing an event and recomputing its own hash still shows: the next
    event points at the hash that was there before."""
    events = await _write(db_session)
    rows = await _rows(db_session, events[0].seq)
    rows[1]["subject_id"] = "someone-else"
    rows[1]["hash"] = chain.hash_of(rows[1])
    verdict = chain.verify(rows, expected_prev=events[0].prev_hash)
    assert [(found.seq, found.reason) for found in verdict.breaks] == [
        (rows[2]["seq"], "prev_hash")
    ]


async def test_the_database_refuses_to_change_or_remove_an_event(db_session):
    events = await _write(db_session, 2)
    for statement in (
        update(StreamEvent)
        .where(StreamEvent.seq == events[0].seq)
        .values(subject_id="x"),
        update(StreamEvent).where(StreamEvent.seq == events[0].seq).values(note="x"),
        delete(StreamEvent).where(StreamEvent.seq == events[0].seq),
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(
                    statement.execution_options(synchronize_session=False)
                )
    assert (await check.verify_stream(db_session, from_seq=events[0].seq)).intact


async def test_erasing_values_keeps_the_chain(db_session, create_person):
    person = await create_person("gewist@example.org")
    first = stream.append(
        db_session,
        subject=("person_scale", "s1"),
        action="update",
        person_id=person.id,
        old={"billing_scale": 11},
        new={"billing_scale": 12},
        note="promotie",
    )
    other = stream.append(
        db_session, subject=("rate_card", "2026"), action="update", new={"x": 1}
    )
    await db_session.flush()

    erased = await retention.erase_person(db_session, person.id, reason="verzoek")
    assert erased == 1

    rows = await _rows(db_session, first.seq)
    gone, kept, record = rows[0], rows[1], rows[-1]
    assert gone["old_value"] is None and gone["new_value"] is None
    assert gone["note"] is None and gone["salt"] is None
    assert gone["erased_at"] is not None
    # What was hashed is still there: the digests, and the fact itself.
    assert gone["new_digest"] and gone["hash"] == first.hash
    assert kept["new_value"] == {"x": 1} and kept["seq"] == other.seq
    # The erasure is itself an event.
    assert record["type"] == "stream.erased"
    assert record["new_value"]["person_id"] == str(person.id)
    assert record["new_value"]["count"] == 1
    assert chain.verify(rows, expected_prev=first.prev_hash).intact
    # Erasing twice finds nothing left.
    assert await retention.erase_person(db_session, person.id, reason="verzoek") == 0


async def test_retention_is_a_setting(db_session):
    await _write(db_session, 2)
    stream.append(
        db_session,
        "data.read",
        subject=("person", "p"),
        new={"classes": ["person_rate"]},
        existence_class="person_rate",
        field_classes={"*": "person_rate"},
    )
    await db_session.flush()
    later = datetime.now(UTC) + timedelta(days=400)

    # Nothing is erased while the instance keeps everything.
    assert await retention.apply_retention(db_session, now=later) == 0

    await instance_settings.set_values(
        db_session, {retention.READ_RETENTION_DAYS.key: 365}, actor=None
    )
    await db_session.flush()
    assert await retention.apply_retention(db_session, now=later) >= 1
    left = await db_session.scalar(
        select(text("count(*)"))
        .select_from(StreamEvent)
        .where(StreamEvent.type == "data.read", StreamEvent.erased_at.is_(None))
    )
    assert left == 0
    unread = await db_session.scalar(
        select(text("count(*)"))
        .select_from(StreamEvent)
        .where(
            StreamEvent.subject_kind == "rate_card",
            StreamEvent.erased_at.is_(None),
            StreamEvent.new_value.is_not(None),
        )
    )
    assert unread >= 2

    with pytest.raises(Exception, match="bewaartermijn"):
        await instance_settings.set_values(
            db_session, {retention.RETENTION_DAYS.key: -1}, actor=None
        )


async def test_the_beheerder_can_have_the_chain_checked(client, as_person, world):
    answer = await as_person(world.beheerder).get("/api/events/chain")
    assert answer.status_code == 200
    body = answer.json()
    assert body["intact"] is True and body["checked"] > 0 and body["breaks"] == []
    assert (await as_person(world.planner).get("/api/events/chain")).status_code == 403
