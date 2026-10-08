"""The stream of what happened in this instance.

One row per event, append-only. The audit log is this same table read by
entity (``AuditLog`` is this class); the feed for other systems and the
handlers that react read it as well (ADR 0028).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String, Text, case
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, synonym

from grip.core.database import Base

ACTOR_PERSON = "person"
ACTOR_GUEST = "guest"
ACTOR_PEER = "peer"
ACTOR_SYSTEM = "system"

ORIGIN_LOCAL = "local"
ORIGIN_REMOTE = "remote"

CASE_ASSIGNMENT = "assignment"
CASE_VACANCY = "vacancy"


class StreamEvent(Base):
    """One thing that happened, written in the transaction of the change."""

    __tablename__ = "stream_event"
    __table_args__ = (
        Index("ix_stream_event_subject", "subject_kind", "subject_id"),
        Index("ix_stream_event_case", "case_kind", "case_id", "seq"),
        Index("ix_stream_event_person", "person_id", "seq"),
        Index("ix_stream_event_actor", "actor_person_id", "seq"),
    )

    # The position in the stream. Given out under a lock when the event is
    # flushed, so the order of ``seq`` is the order in which transactions
    # commit and a reader with a cursor never skips an event.
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid.uuid4
    )
    # The start of the transaction: events of one transaction share it.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Stable dotted name, e.g. ``quote.accepted`` or ``budget_line.updated``.
    type: Mapped[str] = mapped_column(String(120), index=True)
    # create, update or delete for a plain change record; NULL otherwise.
    action: Mapped[str | None] = mapped_column(String(20), nullable=True)

    subject_kind: Mapped[str] = mapped_column(String(100))
    subject_id: Mapped[str] = mapped_column(String(100))
    # The case the subject belongs to: an assignment or a vacancy.
    case_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # The person whose data this event is about, if any.
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    actor_kind: Mapped[str] = mapped_column(String(20))
    # No foreign key: the row is hashed and must not change when a person
    # is removed.
    actor_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # The invitation of a guest, the peer id of a peer, or the job of the
    # system.
    actor_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)

    origin: Mapped[str] = mapped_column(String(10))
    origin_peer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Everything one request or one incoming message caused shares this.
    # 32 hex characters, so it doubles as a W3C trace id.
    correlation_id: Mapped[str] = mapped_column(String(32), index=True)
    # Why data was read or processed, where the caller knows.
    purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)

    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # What a domain event announces to its handlers.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Pointers to evidence kept elsewhere, by hash.
    refs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Who may know that this happened (a data class of ``grip.access``, or
    # NULL for administration of the instance), and the class of each field
    # of the old and new value. ``*`` is the class of every other field and
    # of the payload and the note.
    existence_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    field_classes: Mapped[dict[str, Any]] = mapped_column(JSONB)

    # The chain hashes digests of the values, not the values, so a value
    # can be erased while the chain stays verifiable. Erasing drops the
    # salt too: a digest of a small value cannot be guessed back.
    salt: Mapped[str | None] = mapped_column(String(32), nullable=True)
    old_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    erased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # The names the audit log has always used.
    entity = synonym("subject_kind")
    entity_id = synonym("subject_id")
    actor_id = synonym("actor_person_id")

    # A plain change record (it has an action) is an audit row; reading
    # ``AuditLog`` returns only those.
    __mapper_args__ = {
        "polymorphic_on": case((action.column.isnot(None), "change"), else_="event"),
        "polymorphic_identity": "event",
    }


class AuditLog(StreamEvent):
    """Who changed what, when, with the old and the new value.

    The change records of the stream, under the name and the column names
    the audit log has always had.
    """

    __mapper_args__ = {"polymorphic_identity": "change"}
