"""Writing: one record, in the transaction of the change, handlers in two kinds."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text

from grip.core.audit import UPDATE, record_audit
from grip.events import chain, check, completeness, context, stream
from grip.models.instance_setting import InstanceSetting
from grip.models.stream_event import AuditLog, StreamEvent
from grip.services import events


async def _count(db, kind: str) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(StreamEvent)
        .where(StreamEvent.subject_kind == kind)
    )


# -- the record ---------------------------------------------------------------


async def test_an_event_carries_the_whole_record(db_session, world):
    with context.scope(correlation_id="ab" * 16):
        context.set_person(world.owner.id)
        event = record_audit(
            db_session,
            actor=None,
            action=UPDATE,
            entity="budget_line",
            entity_id=world.line.id,
            old_value={"amount_cents": 100},
            new_value={"amount_cents": 200, "intended_person_id": None},
            note="na overleg",
        )
        await db_session.flush()
    assert event.type == "budget_line.updated"
    assert (event.subject_kind, event.subject_id) == ("budget_line", str(world.line.id))
    # The case was not named: it is found through the line.
    assert (event.case_kind, event.case_id) == ("assignment", world.assignment.id)
    assert (event.actor_kind, event.actor_person_id) == ("person", world.owner.id)
    assert (event.origin, event.origin_peer) == ("local", None)
    assert event.correlation_id == "ab" * 16
    assert event.existence_class == "assignment_basic"
    assert event.field_classes == {
        "*": "assignment_financial",
        "intended_person_id": "staffing",
    }
    assert event.note == "na overleg"
    assert event.seq and len(event.hash) == 64 and event.prev_hash


async def test_without_a_context_the_system_is_the_actor(db_session):
    event = stream.append(db_session, subject=("rate_card", "2026"), action="update")
    await db_session.flush()
    assert (event.actor_kind, event.actor_ref) == ("system", "system")


async def test_a_job_and_a_peer_are_named(db_session):
    with context.scope(job="wies.sync"):
        job = stream.append(
            db_session, subject=("person", uuid.uuid4()), action="update"
        )
        await db_session.flush()
    with context.scope():
        context.set_peer("12345678901234567890")
        peer = stream.append(
            db_session, subject=("quote", uuid.uuid4()), action="create"
        )
        await db_session.flush()
    assert (job.actor_kind, job.actor_ref) == ("system", "wies.sync")
    assert (peer.actor_kind, peer.actor_ref) == ("peer", "12345678901234567890")
    assert (peer.origin, peer.origin_peer) == ("remote", "12345678901234567890")
    assert job.correlation_id != peer.correlation_id


async def test_events_of_one_request_share_a_correlation_id(client, as_person, world):
    response = await as_person(world.owner).patch(
        f"/api/assignments/{world.assignment.id}", json={"name": "Opdracht Alfa II"}
    )
    assert response.status_code == 200, response.text
    other = await as_person(world.owner).patch(
        f"/api/assignments/{world.assignment.id}", json={"name": "Opdracht Alfa III"}
    )
    assert other.status_code == 200
    page = (
        await as_person(world.beheerder).get(
            "/api/events", params={"type": "assignment.updated", "limit": 2}
        )
    ).json()["items"]
    assert len(page) == 2
    assert page[0]["correlation_id"] != page[1]["correlation_id"]
    assert {item["actor_person_id"] for item in page} == {str(world.owner.id)}


async def test_a_traceparent_becomes_the_correlation_id(client, as_person, world):
    trace = "4bf92f3577b34da6a3ce929d0e0e4736"
    response = await as_person(world.owner).patch(
        f"/api/assignments/{world.assignment.id}",
        json={"name": "Met trace"},
        headers={"traceparent": f"00-{trace}-00f067aa0ba902b7-01"},
    )
    assert response.status_code == 200
    page = (
        await as_person(world.beheerder).get(
            "/api/events", params={"correlation_id": trace}
        )
    ).json()["items"]
    assert page and all(item["correlation_id"] == trace for item in page)


async def test_the_audit_log_is_the_change_records_of_the_stream(db_session, world):
    await events.emit(
        db_session,
        events.ASSIGNMENT_STATUS_CHANGED,
        {"assignment_id": str(world.assignment.id), "new_status": "active"},
    )
    await db_session.flush()
    in_stream = await db_session.scalars(
        select(StreamEvent.type).where(
            StreamEvent.subject_id == str(world.assignment.id)
        )
    )
    in_audit = await db_session.scalars(
        select(AuditLog.type).where(AuditLog.entity_id == str(world.assignment.id))
    )
    assert "assignment.status_changed" in set(in_stream)
    audit_types = set(in_audit)
    assert "assignment.status_changed" not in audit_types
    assert "assignment.created" in audit_types


# -- same transaction ---------------------------------------------------------


async def test_a_change_that_is_undone_leaves_no_event(db_session):
    before = await _count(db_session, "instance_setting")
    savepoint = await db_session.begin_nested()
    db_session.add(InstanceSetting(key="test.undone", value=1))
    stream.append(
        db_session, subject=("instance_setting", "test.undone"), action="create"
    )
    await db_session.flush()
    assert await _count(db_session, "instance_setting") == before + 1
    await savepoint.rollback()
    assert await _count(db_session, "instance_setting") == before
    assert await db_session.get(InstanceSetting, "test.undone") is None


async def test_event_and_change_commit_or_vanish_together(committing):
    key_kept, key_lost = f"test.{uuid.uuid4().hex}", f"test.{uuid.uuid4().hex}"
    async with committing() as db:
        db.add(InstanceSetting(key=key_kept, value=1))
        stream.append(db, subject=("instance_setting", key_kept), action="create")
        await db.commit()
    async with committing() as db:
        db.add(InstanceSetting(key=key_lost, value=1))
        stream.append(db, subject=("instance_setting", key_lost), action="create")
        await db.flush()
        await db.rollback()
    async with committing() as db:
        for key, expected in ((key_kept, 1), (key_lost, 0)):
            row = await db.get(InstanceSetting, key)
            found = await db.scalar(
                select(func.count())
                .select_from(StreamEvent)
                .where(StreamEvent.subject_id == key)
            )
            assert (row is not None, found) == (bool(expected), expected)


# -- handlers -----------------------------------------------------------------


async def test_a_transactional_handler_runs_in_the_transaction(db_session, world):
    seen = []

    async def handler(session, event_type, payload):
        seen.append((session is db_session, event_type, payload["assignment_id"]))

    events.register_handler(events.ASSIGNMENT_STATUS_CHANGED, handler)
    payload = {"assignment_id": str(world.assignment.id), "new_status": "active"}
    await events.emit(db_session, events.ASSIGNMENT_STATUS_CHANGED, payload)
    assert seen == [(True, "assignment.status_changed", str(world.assignment.id))]


async def test_a_transactional_handler_that_raises_refuses_the_change(db_session):
    async def refuse(session, event_type, payload):
        raise RuntimeError("no")

    events.register_handler(events.QUOTE_OFFERED, refuse)
    with pytest.raises(RuntimeError):
        await events.emit(db_session, events.QUOTE_OFFERED, {"quote_id": "q"})


async def test_emit_refuses_an_unknown_type(db_session):
    with pytest.raises(ValueError, match="unknown event type"):
        await events.emit(db_session, "something.else", {})


async def test_after_commit_handlers_run_only_once_the_commit_is_real(committing):
    seen: list[tuple[str, int]] = []

    async def handler(event: StreamEvent) -> None:
        seen.append((event.subject_id, event.seq))

    stream.after_commit(stream.ANY, handler)

    # Rolled back: nothing runs.
    async with committing() as db:
        stream.append(db, subject=("rate_card", "rolled-back"), action="update")
        await db.flush()
        await db.rollback()
    await stream.drain()
    assert seen == []

    # A savepoint that is released is not a commit; the outer transaction
    # rolls back afterwards, so its event must never reach a handler.
    async with committing() as db:
        async with db.begin_nested():
            stream.append(db, subject=("rate_card", "savepoint"), action="update")
            await db.flush()
        await stream.drain()
        assert seen == []
        await db.rollback()
    await stream.drain()
    assert seen == []

    # Inside a savepoint that rolls back, with an outer commit: only the
    # event that became durable is handed over.
    async with committing() as db:
        stream.append(db, subject=("rate_card", "kept"), action="update")
        await db.flush()
        savepoint = await db.begin_nested()
        stream.append(db, subject=("rate_card", "dropped"), action="update")
        await db.flush()
        await savepoint.rollback()
        assert seen == []
        await db.commit()
    await stream.drain()
    assert [subject for subject, _seq in seen] == ["kept"]


async def test_a_failing_after_commit_handler_does_not_undo_the_change(committing):
    async def broken(event: StreamEvent) -> None:
        raise RuntimeError("boom")

    stream.after_commit(stream.ANY, broken)
    key = f"after-{uuid.uuid4().hex}"
    async with committing() as db:
        stream.append(db, subject=("rate_card", key), action="update")
        await db.commit()
    await stream.drain()
    async with committing() as db:
        assert await _count(db, "rate_card") >= 1
        assert await db.scalar(
            select(StreamEvent.seq).where(StreamEvent.subject_id == key)
        )


# -- order and chain under concurrent writers ----------------------------------


async def test_concurrent_writers_keep_one_order_and_one_chain(committing):
    marker = uuid.uuid4().hex[:8]
    writers, per_writer = 8, 6
    seen: list[int] = []
    done = asyncio.Event()

    async def write(number: int) -> None:
        for index in range(per_writer):
            async with committing() as db:
                stream.append(
                    db,
                    subject=("rate_card", f"{marker}-{number}-{index}"),
                    action="update",
                )
                stream.append(
                    db,
                    subject=("rate_card", f"{marker}-{number}-{index}b"),
                    action="update",
                )
                await db.flush()
                # Hold the transaction open for a moment: a later position
                # must not become visible before this one.
                await asyncio.sleep(0.002 * (number % 3))
                await db.commit()

    async def follow() -> None:
        """A reader with a cursor, reading while the writers write."""
        async with committing() as db:
            cursor = await db.scalar(
                select(func.coalesce(func.max(StreamEvent.seq), 0))
            )
        while True:
            finished = done.is_set()
            async with committing() as db:
                rows = (
                    await db.scalars(
                        select(StreamEvent.seq)
                        .where(StreamEvent.seq > cursor)
                        .order_by(StreamEvent.seq)
                        .limit(5)
                    )
                ).all()
            if rows:
                seen.extend(rows)
                cursor = rows[-1]
            elif finished:
                return
            else:
                await asyncio.sleep(0.001)

    async with committing() as db:
        start = await db.scalar(select(func.coalesce(func.max(StreamEvent.seq), 0)))
    reader = asyncio.create_task(follow())
    await asyncio.gather(*(write(number) for number in range(writers)))
    done.set()
    await reader

    total = writers * per_writer * 2
    # The reader saw every event exactly once, in order, without a gap.
    assert seen == list(range(start + 1, start + total + 1))
    async with committing() as db:
        verdict = await check.verify_stream(db)
        assert verdict.intact, verdict.breaks
        assert verdict.head_seq == start + total
        # The two events of one transaction sit next to each other.
        rows = (
            await db.execute(
                select(StreamEvent.seq, StreamEvent.subject_id)
                .where(StreamEvent.subject_id.startswith(marker))
                .order_by(StreamEvent.seq)
            )
        ).all()
    for first, second in zip(rows[::2], rows[1::2], strict=True):
        assert second.subject_id == f"{first.subject_id}b"
        assert second.seq == first.seq + 1


# -- the migration of the audit rows that were there ---------------------------


async def test_existing_audit_rows_become_the_start_of_the_stream(
    migrated_database_url, committing
):
    _url, before, person_id, assignment_id = migrated_database_url
    async with committing() as db:
        rows = (
            await db.scalars(
                select(StreamEvent)
                .where(StreamEvent.seq <= len(before))
                .order_by(StreamEvent.seq)
            )
        ).all()
        assert not await db.scalar(text("SELECT to_regclass('audit_log')"))
        table = StreamEvent.__table__
        stored = (
            (
                await db.execute(
                    select(table)
                    .where(table.c.seq <= len(before))
                    .order_by(table.c.seq)
                )
            )
            .mappings()
            .all()
        )
    # Every row, in the order it happened, with its id, actor and values.
    assert [row.id for row in rows] == [old["id"] for old in before]
    assert [row.seq for row in rows] == [1, 2, 3, 4]
    assert [row.type for row in rows] == [
        "assignment.created",
        "assignment.updated",
        "person_scale.updated",
        "rate_card.updated",
    ]
    assert [row.occurred_at for row in rows] == [old["occurred_at"] for old in before]
    assert rows[1].old_value == {"status": "draft"}
    assert [row.actor_kind for row in rows] == ["person"] * 3 + ["system"]
    assert rows[0].actor_person_id == person_id
    # Case, person and classes are worked out for the old rows too.
    assert (rows[0].case_kind, rows[0].case_id) == ("assignment", assignment_id)
    assert rows[2].person_id == person_id
    assert (rows[2].existence_class, rows[2].field_classes) == (
        "staffing",
        {"*": "person_rate"},
    )
    assert rows[3].existence_class is None
    # The chain starts at the first old row and holds under the code of today.
    assert rows[0].prev_hash == chain.GENESIS
    assert chain.verify([dict(row) for row in stored]).intact
    # They read as audit rows, as before.
    assert all(isinstance(row, AuditLog) for row in rows)


# -- completeness ---------------------------------------------------------------


async def test_a_domain_change_without_an_event_is_found(db_session):
    with completeness.watch(db_session) as unit:
        db_session.add(InstanceSetting(key="test.silent", value=1))
        await db_session.flush()
    assert [missing.table for missing in unit.unrecorded()] == ["instance_setting"]

    with completeness.watch(db_session) as unit:
        db_session.add(InstanceSetting(key="test.recorded", value=1))
        stream.append(db_session, subject=("instance_setting", "x"), action="create")
        await db_session.flush()
    assert unit.unrecorded() == []


async def test_a_change_by_statement_is_seen_too(db_session):
    from sqlalchemy import update

    db_session.add(InstanceSetting(key="test.bulk", value=1))
    await db_session.flush()
    with completeness.watch(db_session) as unit:
        await db_session.execute(
            update(InstanceSetting)
            .where(InstanceSetting.key == "test.bulk")
            .values(value=2)
        )
    assert [missing.table for missing in unit.unrecorded()] == ["instance_setting"]


async def test_tables_outside_the_domain_need_no_event(db_session):
    from grip.models.http_session import HttpSession

    assert "stream_event" in completeness.NOT_DOMAIN
    with completeness.watch(db_session) as unit:
        stream.append(db_session, subject=("rate_card", "2026"), action="update")
        await db_session.flush()
    assert unit.unrecorded() == []
    assert HttpSession.__tablename__ in completeness.NOT_DOMAIN


def test_every_table_is_domain_or_listed_with_a_reason():
    from grip.core.database import Base

    tables = set(Base.metadata.tables)
    assert set(completeness.NOT_DOMAIN) <= tables
    assert all(completeness.NOT_DOMAIN.values())
    # Whatever covers a table is a kind that is classified.
    from grip.events.classification import SPECS

    kinds = {kind for covering in completeness.COVERED_BY.values() for kind in covering}
    assert kinds - set(SPECS) - {"invoice"} == set()


def test_every_entity_that_is_audited_is_classified():
    """A new kind of change record must say who may read it."""
    import re
    from pathlib import Path

    from grip.events.classification import SPECS, TYPE_SUBJECTS

    root = Path(__file__).resolve().parents[2] / "grip"
    used = set()
    for path in root.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        used |= set(re.findall(r'\bentity="([a-z_]+)"', path.read_text()))
    assert used - set(SPECS) == set()
    for event_type in events.EVENT_TYPES:
        kind = TYPE_SUBJECTS.get(event_type, event_type.split(".")[0])
        assert kind in SPECS, event_type


async def test_a_signed_statement_is_tied_into_the_chain_by_its_hash(db_session, world):
    statement = "ab" * 32
    await events.emit(
        db_session,
        events.QUOTE_ACCEPTED,
        {
            "quote_id": str(uuid.uuid4()),
            "assignment_id": str(world.assignment.id),
            "statement_hash": statement,
            "quote_hash": "cd" * 32,
        },
    )
    await db_session.flush()
    event = (
        await db_session.scalars(
            select(StreamEvent)
            .where(StreamEvent.type == "quote.accepted")
            .order_by(StreamEvent.seq.desc())
        )
    ).first()
    assert event.refs == {"statement_hash": statement, "quote_hash": "cd" * 32}
    # The reference is part of what is hashed: another statement, another hash.
    facts = stream.columns_of(event)
    assert chain.hash_of(facts) == event.hash
    assert chain.hash_of({**facts, "refs": {"statement_hash": "ef" * 32}}) != event.hash
