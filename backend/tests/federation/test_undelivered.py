"""What does not arrive, on both sides of the seam (ADR 0061).

The outbox reports per peer; the domain keeps one row per peer while
messages to it do not arrive, and every change is an event, so the tasks
look again at once.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from grip.federation.models import FAILURES
from grip.models.delivery_trouble import REASONS, DeliveryTrouble
from grip.models.stream_event import StreamEvent
from grip.services import delivery_trouble
from grip.services.delivery_trouble import Trouble

SINCE = datetime(2026, 11, 28, 9, 0, tzinfo=UTC)
GRIP = Path(__file__).resolve().parents[2] / "grip"


def test_both_sides_know_the_same_reasons_and_have_words_for_each():
    assert FAILURES == REASONS
    assert set(delivery_trouble.REASON_WORDS) == set(REASONS)
    assert delivery_trouble.reason_words("onbekend") == delivery_trouble.reason_words(
        "other"
    )


def test_the_tasks_know_nothing_of_how_messages_travel():
    for path in (GRIP / "tasks").rglob("*.py"):
        assert not re.search(r"\bgrip\.federation\b", path.read_text()), path.name


def test_the_audit_imports_on_its_own():
    """grip.core.audit reaches the outbox through the models; the outbox must
    not need audit's names while audit is still being read."""
    result = subprocess.run(  # noqa: S603 - fixed command, own interpreter
        [sys.executable, "-c", "import grip.core.audit"],
        cwd=GRIP.parent,
        env={**os.environ, "DEV_NO_AUTH": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _trouble(peer_id, **changes) -> Trouble:
    values = {
        "peer_id": peer_id,
        "peer_name": "Voorbeeldgilde",
        "since": SINCE,
        "message_count": 1,
        "final": False,
        "reason": "unknown_sender",
        "retry_until": SINCE + timedelta(days=7),
        **changes,
    }
    return Trouble(**values)


async def _events(db_session) -> list[StreamEvent]:
    rows = await db_session.scalars(
        select(StreamEvent)
        .where(StreamEvent.subject_kind == "delivery_trouble")
        .order_by(StreamEvent.seq)
    )
    return list(rows)


async def test_one_row_per_peer_while_messages_do_not_arrive(db_session):
    gilde, other = uuid.uuid4(), uuid.uuid4()
    await delivery_trouble.report(db_session, [_trouble(gilde)])
    await db_session.flush()
    row = await db_session.get(DeliveryTrouble, gilde)
    assert row is not None and (row.message_count, row.final) == (1, False)

    # The same report again changes nothing and says nothing.
    await delivery_trouble.report(db_session, [_trouble(gilde)])
    await db_session.flush()
    assert [event.type for event in await _events(db_session)] == [
        "delivery_trouble.created"
    ]

    await delivery_trouble.report(
        db_session,
        [
            _trouble(gilde, message_count=2, final=True, reason="conflict"),
            _trouble(other, peer_name="Ander voorbeeld"),
        ],
    )
    await db_session.flush()
    (changed,) = [
        event
        for event in await _events(db_session)
        if event.type == "delivery_trouble.updated"
    ]
    assert changed.subject_id == str(gilde)
    assert changed.new_value == {
        "message_count": 2,
        "final": True,
        "reason": "conflict",
    }

    # A complete report without a peer: everything to it arrived.
    await delivery_trouble.report(db_session, [_trouble(other, peer_name="Ander")])
    await db_session.flush()
    assert await db_session.get(DeliveryTrouble, gilde) is None
    last = (await _events(db_session))[-2:]
    assert [(event.type, event.subject_id) for event in last] == [
        ("delivery_trouble.updated", str(other)),
        ("delivery_trouble.deleted", str(gilde)),
    ]
    assert all(event.case_id is None for event in await _events(db_session))


async def test_a_report_about_some_peers_leaves_the_others(db_session):
    gilde, other = uuid.uuid4(), uuid.uuid4()
    await delivery_trouble.report(db_session, [_trouble(gilde), _trouble(other)])
    await delivery_trouble.report(db_session, [], peer_ids={gilde})
    await db_session.flush()
    assert await db_session.get(DeliveryTrouble, gilde) is None
    assert await db_session.get(DeliveryTrouble, other) is not None
