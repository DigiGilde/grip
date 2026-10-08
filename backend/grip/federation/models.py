"""Tables of the federation module: peers, outbox and inbox."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base

# What another instance or corpus system is to this instance. A parent or a
# child is also a counterpart: an assignment can run between them.
PEER_ROLE_COUNTERPART = "counterpart"
PEER_ROLE_PARENT = "parent"
PEER_ROLE_CHILD = "child"
PEER_ROLE_CORPUS = "corpus"
PEER_ROLES = (
    PEER_ROLE_COUNTERPART,
    PEER_ROLE_PARENT,
    PEER_ROLE_CHILD,
    PEER_ROLE_CORPUS,
)

OUTBOX_PENDING = "pending"
OUTBOX_SENT = "sent"
# The receiver refused the message for good (4xx); retrying will not help.
OUTBOX_REJECTED = "rejected"
# Retries are used up without ever reaching the receiver.
OUTBOX_DEAD = "dead"
OUTBOX_STATUSES = (OUTBOX_PENDING, OUTBOX_SENT, OUTBOX_REJECTED, OUTBOX_DEAD)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class Peer(Base):
    """Another grip instance or a corpus system, known by its FSC peer id."""

    __tablename__ = "peer"
    __table_args__ = (CheckConstraint(_in_list("role", PEER_ROLES), name="role_valid"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    # The peer id the inway passes on: the serial number in the certificate.
    peer_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    organisation_tooi_uri: Mapped[str] = mapped_column(String(500), default="")
    # Base of the URIs this peer mints: an instance base or a corpus base.
    base_uri: Mapped[str] = mapped_column(String(500), index=True)
    role: Mapped[str] = mapped_column(String(20))
    # FSC service name to the grant hash of the contract with this peer.
    grant_hashes: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    # Public keys of the peer, cached from its JWKS or entered by hand.
    jwks: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    jwks_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    # The contract with this peer covers financial inspection: as client it
    # may ask for budget usage and billing data of its own assignments. Off
    # by default; the beheerder switches it on for a peer on request.
    financial_inspection: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FederationOutbox(Base):
    """A message waiting to be sent to a peer through the outway."""

    __tablename__ = "federation_outbox"
    __table_args__ = (
        UniqueConstraint("peer_id", "message_id"),
        CheckConstraint(_in_list("status", OUTBOX_STATUSES), name="status_valid"),
        Index("ix_federation_outbox_due", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    peer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("peer.id", ondelete="RESTRICT"), index=True
    )
    service: Mapped[str] = mapped_column(String(100))
    # operationId in the contract, for example sendQuote.
    operation: Mapped[str] = mapped_column(String(100))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(20), default=OUTBOX_PENDING, server_default=OUTBOX_PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    peer: Mapped[Peer] = relationship(lazy="joined")


class FederationInbox(Base):
    """A message received from a peer. One row per message id per peer."""

    __tablename__ = "federation_inbox"
    __table_args__ = (
        UniqueConstraint("peer_id", "message_id"),
        Index("ix_federation_inbox_unprocessed", "processed_at", "received_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    peer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("peer.id", ondelete="RESTRICT"), index=True
    )
    operation: Mapped[str] = mapped_column(String(100))
    # SHA-256 over the canonical JSON of the payload; decides duplicate or conflict.
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # NULL: stored, not yet processed by a domain handler.
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    peer: Mapped[Peer] = relationship(lazy="joined")
