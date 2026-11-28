"""Messages to another instance that do not arrive (ADR 0061).

One row per peer while messages to it do not arrive. The part of grip that
sends them reports after every round; a task for the beheerder is read from
here. It holds what the beheerder must know, never what the receiver
answered.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base

# Why the messages do not arrive. The same codes as the outbox keeps
# (grip.federation.models.FAILURES); a test holds the two lists equal.
NO_CONNECTION = "no_connection"
TIMEOUT = "timeout"
UNKNOWN_SENDER = "unknown_sender"
NOT_FOUND = "not_found"
RECEIVER_ERROR = "receiver_error"
CONFIGURATION = "configuration"
INVALID = "invalid"
CONFLICT = "conflict"
GONE = "gone"
OTHER = "other"
REASONS = (
    NO_CONNECTION,
    TIMEOUT,
    UNKNOWN_SENDER,
    NOT_FOUND,
    RECEIVER_ERROR,
    CONFIGURATION,
    INVALID,
    CONFLICT,
    GONE,
    OTHER,
)


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class DeliveryTrouble(Base):
    """Messages to one peer that do not arrive."""

    __tablename__ = "delivery_trouble"
    __table_args__ = (CheckConstraint(_in("reason", REASONS), name="reason_valid"),)

    # The peer on Beheer > Koppelingen. No foreign key: the peer belongs to
    # the part of grip that talks to other instances.
    peer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    peer_name: Mapped[str] = mapped_column(String(200))
    # When the first of these messages counted as not arriving.
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    message_count: Mapped[int] = mapped_column(Integer)
    # One of them is final: refused for good, or tried for the whole window.
    final: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(String(20))
    # The first moment grip stops trying one of them; empty when none is tried.
    retry_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
