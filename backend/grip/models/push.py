"""Notifications on a person's own device (web push).

Five tables. Two hold what a person chose: the devices that may be notified
(``push_subscription``) and how they want to be told (``notification_preference``).
Three are the machinery around sending: what to send (``push_outbox``), what
a person was already told about (``push_notice``) and how far the stream of
events has been read (``push_cursor``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

PUSH_QUEUED = "queued"
PUSH_SENT = "sent"
PUSH_FAILED = "failed"
# Not sent on purpose: the day's cap was reached, or nobody to send it to.
PUSH_SKIPPED = "skipped"
PUSH_STATUSES = (PUSH_QUEUED, PUSH_SENT, PUSH_FAILED, PUSH_SKIPPED)

# What a push can be about. The text on the device is chosen by the service
# worker from this word and a number; the server sends no sentence.
KIND_TASKS = "tasks"
KIND_OVERDUE = "overdue"
KIND_QUOTE_ACCEPTED = "quote_accepted"
KIND_QUOTE_REJECTED = "quote_rejected"
KIND_APPROVAL_GIVEN = "approval_given"
KIND_APPROVAL_SENT_BACK = "approval_sent_back"
KIND_TEST = "test"
PUSH_KINDS = (
    KIND_TASKS,
    KIND_OVERDUE,
    KIND_QUOTE_ACCEPTED,
    KIND_QUOTE_REJECTED,
    KIND_APPROVAL_GIVEN,
    KIND_APPROVAL_SENT_BACK,
    KIND_TEST,
)


class PushSubscription(Base):
    """One device of one person that agreed to be notified.

    The endpoint is an address at the browser vendor's push service that
    reaches this one browser; with the two keys it is all that is needed to
    send to it. It is personal data and is never shown back in full.
    """

    __tablename__ = "push_subscription"

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    # The browser's public key and shared secret, base64url as it gave them.
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    # What the person calls the device ("Telefoon").
    label: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = created_at()
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class NotificationPreference(Base):
    """How one person wants to be told that something waits for them.

    One preference for both ways of telling, so they never double up. A
    person without a row has the defaults below.
    """

    __tablename__ = "notification_preference"

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Notifications on the devices the person registered.
    push: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # A summary by mail once a day. Kept as a choice; not sent yet.
    mail_summary: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Per kind of notice: {"tasks": true, "overdue": true, "decisions": true}.
    kinds: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Nothing is sent between these two times of day; both NULL is never quiet.
    quiet_from: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_until: Mapped[time | None] = mapped_column(Time, nullable=True)
    weekends_quiet: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    updated_at: Mapped[datetime] = updated_at()


class PushOutbox(Base):
    """One notice for one person, to be sent to their devices by the worker."""

    __tablename__ = "push_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'skipped')", name="status_valid"
        ),
        Index("ix_push_outbox_due", "status", "next_attempt_at"),
        Index("ix_push_outbox_person", "person_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(30))
    # How many things the notice is about (three tasks: one notice).
    count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # How many tasks are the person's to do at that moment, for the badge
    # on the application's icon; NULL leaves the badge alone.
    badge: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A path inside the application to open on a click. Ids only.
    path: Mapped[str] = mapped_column(String(300), default="/")
    # The same key is queued once.
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(
        String(10), default=PUSH_QUEUED, server_default=PUSH_QUEUED
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = created_at()
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PushNotice(Base):
    """That a person was told about a task, so they are told once."""

    __tablename__ = "push_notice"
    __table_args__ = (
        UniqueConstraint("person_id", "task_id", "kind", name="uq_push_notice_once"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task.id", ondelete="CASCADE")
    )
    # "tasks" (it became yours) or "overdue" (its date passed).
    kind: Mapped[str] = mapped_column(String(30))
    # False when the person was not notified on purpose: they caused it
    # themselves, or that kind is switched off.
    notified: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = created_at()


class PushCursor(Base):
    """How far a reader of the event stream has come."""

    __tablename__ = "push_cursor"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    updated_at: Mapped[datetime] = updated_at()
