"""Tamper evidence: the chain, the check, the guard, and erasure."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import rfc8785
from sqlalchemy import delete, insert, null, select, text, update
from sqlalchemy.exc import DBAPIError

from grip.chronicle.rates import FACT as RATES_FACT
from grip.chronicle.rates import record_rate_book
from grip.chronicle.writer import event_type
from grip.events import chain, check, retention, stream
from grip.models.stream_event import StreamEvent
from grip.services import instance_settings, quote_approval, rates


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


@pytest.mark.parametrize(
    "value",
    [
        1e21,
        1e22,
        -1e22,
        1.5e300,
        1e23,
        {"veel": 1e22, "minder": 1e20},
        {"veel": 1e22, "heel": 1.0, "klein": 1.5e-7},
        {"veel": 1e22, "nul": -0.0},
        {"minder": 1e20, "heel": 1.0},
        {"minder": 1e16, "klein": 1.5e-7},
        {"diep": [{"veel": -1e25}, 1e20]},
    ],
)
async def test_a_huge_number_says_after_the_database_what_it_said_before(
    db_session, value
):
    stream.append(db_session, subject=("peer", "p"), action="update", new={"v": value})
    await db_session.flush()
    verdict = await check.verify_stream(db_session)
    assert verdict.intact, verdict.breaks


def test_a_float_from_where_jsonb_returns_a_whole_number_is_that_number():
    assert chain.plain({"v": 1e23}) == {"v": 10**23}
    assert chain.plain([-1.5e16]) == [-15000000000000000]
    assert isinstance(chain.plain(1e16), int)
    assert isinstance(chain.plain(9999999999999998.0), float)


@pytest.mark.parametrize(
    "number",
    [
        1.5,
        1.0,
        1e3,
        0.1,
        -0.0,
        1e-7,
        1.5e-7,
        1e15,
        9999999999999998.0,
        1e16,
        1e20,
        1.2345678901234568e20,
        999999999999999900000.0,
    ],
)
def test_a_number_below_the_form_rfc8785_changes_at_keeps_its_digest(number):
    value = {"gewicht": number, "naam": "é"}
    as_it_was = hashlib.sha256(b"zout\x00" + rfc8785.dumps(value)).hexdigest()
    assert chain.digest("zout", chain.plain(value)) == as_it_was


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


async def test_retention_keeps_what_every_look_back_needs(db_session):
    first = await _write(db_session, 1)
    await instance_settings.set_values(
        db_session, {retention.READ_RETENTION_DAYS.key: 365}, actor=None
    )
    await instance_settings.set_values(
        db_session, {quote_approval.MODE.key: "from_amount"}, actor=None
    )
    await instance_settings.set_values(
        db_session,
        {quote_approval.THRESHOLD.key: 500000, retention.READ_RETENTION_DAYS.key: 400},
        actor=None,
    )
    await instance_settings.set_values(
        db_session, {retention.RETENTION_DAYS.key: 365}, actor=None
    )
    # A settings row that says nothing about a key at all, as a removal would.
    stream.append(
        db_session,
        subject=("instance_setting", "instance"),
        action="delete",
        old={quote_approval.MODE.key: "never"},
    )
    await rates.create_rate_card(db_session, 2031, actor=None)
    await rates.set_rate_card_status(db_session, 2031, "active", actor=None)
    await db_session.flush()

    later = datetime.now(UTC) + timedelta(days=400)
    assert await retention.apply_retention(db_session, now=later) >= 1

    table = StreamEvent.__table__
    rows = (await db_session.execute(select(table))).mappings().all()
    kept = [row for row in rows if row["erased_at"] is None]
    settings = [row for row in rows if row["subject_kind"] == "instance_setting"]
    assert [row["new_value"] for row in settings if row["erased_at"] is None] == [
        {quote_approval.MODE.key: "from_amount"},
        {
            quote_approval.THRESHOLD.key: 500000,
            retention.READ_RETENTION_DAYS.key: 400,
        },
    ], "the rule of a moment holds no personal data and a look-back needs it"
    assert len(settings) == 5
    [rate_fact] = [row for row in kept if row["type"] == event_type(RATES_FACT)]
    assert rate_fact["new_value"]["fields"]["book"]["cards"]
    assert first[0].seq not in {row["seq"] for row in kept}
    assert not any(row["type"].startswith("rate_card.") for row in kept)
    verdict = await check.verify_stream(db_session)
    assert verdict.intact


async def test_retention_reaches_a_settings_row_migrated_without_new_values(db_session):
    [written] = await _write(db_session, 1)
    table = StreamEvent.__table__
    source = await db_session.execute(select(table).where(table.c.seq == written.seq))
    migrated = {
        **source.mappings().one(),
        "id": uuid4(),
        "seq": written.seq + 1,
        "subject_kind": "instance_setting",
        "subject_id": "instance",
        "old_value": {quote_approval.MODE.key: "never"},
        "new_value": null(),
    }
    await db_session.execute(insert(table).values(**migrated))
    await instance_settings.set_values(
        db_session, {retention.RETENTION_DAYS.key: 365}, actor=None
    )
    await db_session.flush()

    later = datetime.now(UTC) + timedelta(days=400)
    assert await retention.apply_retention(db_session, now=later) >= 2
    erased_at = await db_session.scalar(
        select(table.c.erased_at).where(table.c.seq == migrated["seq"])
    )
    assert erased_at is not None


async def test_a_first_draft_leaves_no_fact_and_an_empty_book_no_second_one(db_session):
    async def rate_facts() -> int:
        await db_session.flush()
        found = await db_session.scalars(
            select(StreamEvent.seq).where(StreamEvent.type == event_type(RATES_FACT))
        )
        return len(list(found))

    assert await record_rate_book(db_session, actor=None, cause="Niets") is False
    await rates.create_rate_card(db_session, 2031, actor=None)
    assert await rate_facts() == 0
    await rates.set_rate_card_status(db_session, 2031, "active", actor=None)
    assert await rate_facts() == 1
    assert await record_rate_book(db_session, actor=None, cause="Niets") is False
    assert await rate_facts() == 1
