import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, uuid_pk
from grip.services.canonical import contract_form, read

QUOTE_STATUSES = ("issued", "accepted", "rejected", "superseded")
ACCEPTANCE_FORMS = ("own_instance", "signing_link", "uploaded_pdf")
# How an issued quote is put before the client. Chosen per offer; one quote
# may be offered more than once and through more than one channel.
OFFER_CLIENT_INSTANCE = "client_instance"
OFFER_SIGNING_LINK = "signing_link"
OFFER_DOCUMENT = "document"
OFFER_CHANNELS = (OFFER_CLIENT_INSTANCE, OFFER_SIGNING_LINK, OFFER_DOCUMENT)


class Quote(Base):
    """An issued quote: frozen content of lines, rates and totals.

    This is the one place where derived values are stored. A quote has one
    canonical form, stored as the exact bytes that were issued, and one hash
    over those bytes (ADR 0020). Neither changes after issue; a changed
    quote is a new quote.
    """

    __tablename__ = "quote"
    __table_args__ = (
        CheckConstraint(
            "status IN ('issued', 'accepted', 'rejected', 'superseded')",
            name="status_valid",
        ),
        CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        # The hash is the hash of the stored bytes: an invariant of the row,
        # not something the application has to remember.
        CheckConstraint(
            "snapshot_hash = encode(sha256(canonical), 'hex')",
            name="hash_of_canonical",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    uri: Mapped[str] = mapped_column(String(500), unique=True)
    # The reference people quote on the phone and in a mail, as in
    # "DG-2026-0007": prefix of the instance, year of issue, and a number per
    # year that is never reused. Assigned when the quote is issued here; for
    # a quote received from another instance it is that instance's reference.
    # The URI stays the identifier for machines.
    reference: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
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
    # The canonical form: the content in contract terms as RFC 8785 JSON,
    # exactly as issued (or as received from the instance that issued it).
    canonical: Mapped[bytes] = mapped_column(LargeBinary)
    # SHA-256 over ``canonical``. The one hash of this quote, everywhere.
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

    @property
    def snapshot(self) -> dict[str, Any]:
        """The content in code names, read from the canonical form.

        A view for screens, documents and reports. It is derived on every
        read and never stored, so there is no second copy that could differ
        from what was hashed.
        """
        return read(self.canonical)

    @property
    def contract_snapshot(self) -> dict[str, Any]:
        """The content in contract terms, as it crosses to another instance."""
        return contract_form(self.canonical)


class QuoteReferenceCounter(Base):
    """The last sequence number given out for quote references in a year.

    One row per year. A number is taken with a single statement that adds
    one and returns the result, so two quotes issued at the same moment can
    never get the same number, and a number is never given out twice.
    """

    __tablename__ = "quote_reference_counter"

    year: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_number: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


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
    # The first time the invited person opened the quote behind the link.
    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when whoever manages the assignment took the invitation back. A
    # withdrawn invitation grants nothing; inviting again revives it.
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    withdrawn_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()


class QuoteOffer(Base):
    """One time an issued quote was put before the client, through a channel.

    Issuing a quote freezes it; offering it is a separate act. The channel
    says how the client gets it: in the client's own grip instance, through
    a signing link in this instance, or as a document. How the quote is
    eventually signed is recorded on the acceptance, not here.
    """

    __tablename__ = "quote_offer"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('client_instance', 'signing_link', 'document')",
            name="channel_valid",
        ),
        Index("ix_quote_offer_quote", "quote_id", "offered_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote.id", ondelete="CASCADE")
    )
    channel: Mapped[str] = mapped_column(String(20))
    # To whom: the base URI of the client's instance, the invited email
    # address, or nothing for a document.
    recipient: Mapped[str | None] = mapped_column(String(500), nullable=True)
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quote_invitation.id", ondelete="SET NULL"),
        nullable=True,
    )
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    offered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()


APPROVAL_REQUESTED = "requested"
APPROVAL_APPROVED = "approved"
APPROVAL_SENT_BACK = "sent_back"
APPROVAL_WITHDRAWN = "withdrawn"
APPROVAL_STATUSES = (
    APPROVAL_REQUESTED,
    APPROVAL_APPROVED,
    APPROVAL_SENT_BACK,
    APPROVAL_WITHDRAWN,
)


class QuoteApproval(Base):
    """Internal approval of a made quote, before it may be offered.

    Someone inside the organisation with the right to do so approves a quote
    or sends it back. The approval is about exactly the bytes of the quote:
    it cites the hash. It is knowledge of this organisation only; nothing of
    it goes to the client.

    One row is one request with its outcome. A quote has at most one request
    that is open or approved at a time.
    """

    __tablename__ = "quote_approval"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'approved', 'sent_back', 'withdrawn')",
            name="status_valid",
        ),
        CheckConstraint("quote_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        Index(
            "uq_quote_approval_one_in_force",
            "quote_id",
            unique=True,
            postgresql_where=text("status IN ('requested', 'approved')"),
        ),
        Index("ix_quote_approval_status", "status", "requested_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote.id", ondelete="CASCADE"), index=True
    )
    # The hash of the quote the request and the decision are about.
    quote_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default=APPROVAL_REQUESTED)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # What the maker wants the approver to know.
    request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The maker approved the own quote, which the instance setting allowed.
    self_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    withdrawn_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(
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
