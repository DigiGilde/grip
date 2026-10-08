import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, uuid_pk

QUOTE_STATUSES = ("issued", "accepted", "rejected", "superseded")
ACCEPTANCE_FORMS = ("own_instance", "signing_link", "uploaded_pdf")


class Quote(Base):
    """An issued quote: a frozen snapshot of lines, rates and totals.

    This is the one place where derived values are stored. The snapshot
    never changes after issue; a changed quote is a new quote.
    """

    __tablename__ = "quote"
    __table_args__ = (
        CheckConstraint(
            "status IN ('issued', 'accepted', 'rejected', 'superseded')",
            name="status_valid",
        ),
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    uri: Mapped[str] = mapped_column(String(500), unique=True)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="RESTRICT"),
        index=True,
    )
    # Id of the assignment request this quote answers; NULL on own initiative.
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(12), default="issued", server_default="issued"
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # SHA-256 over the RFC 8785 canonical JSON of the snapshot.
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    total_cents: Mapped[int] = mapped_column(BigInteger)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # NULL when the quote came in from another instance.
    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = created_at()


class QuoteInvitation(Base):
    """An invitation to sign one quote through a signing link."""

    __tablename__ = "quote_invitation"
    __table_args__ = (
        Index(
            "uq_quote_invitation_quote_email",
            "quote_id",
            text("lower(email)"),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    # Bound on the first login of the invited guest.
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at()


class QuoteAcceptance(Base):
    """Akkoord: the record that the client accepted a quote."""

    __tablename__ = "quote_acceptance"
    __table_args__ = (
        CheckConstraint(
            "form IN ('own_instance', 'signing_link', 'uploaded_pdf')",
            name="form_valid",
        ),
        CheckConstraint("quote_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        CheckConstraint(
            "form <> 'own_instance' OR jws IS NOT NULL", name="own_instance_has_jws"
        ),
        CheckConstraint(
            "form <> 'uploaded_pdf' OR document_sha256 IS NOT NULL",
            name="uploaded_pdf_has_document",
        ),
    )

    # Also the id of the acceptance message, which makes it idempotent.
    id: Mapped[uuid.UUID] = uuid_pk()
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote.id", ondelete="RESTRICT"), unique=True
    )
    quote_hash: Mapped[str] = mapped_column(String(64))
    signer_name: Mapped[str] = mapped_column(String(255))
    signer_email: Mapped[str] = mapped_column(String(320))
    signer_function: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signer_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Organisation reference as signed (tooi_uri, name, unit_key, instance_uri).
    organisation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    form: Mapped[str] = mapped_column(String(20))
    jws: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Who recorded it in this instance (uploaded pdf); NULL otherwise.
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()


class QuoteRejection(Base):
    """The record that the client rejected a quote."""

    __tablename__ = "quote_rejection"

    id: Mapped[uuid.UUID] = uuid_pk()
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote.id", ondelete="RESTRICT"), unique=True
    )
    quote_hash: Mapped[str] = mapped_column(String(64))
    organisation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()
