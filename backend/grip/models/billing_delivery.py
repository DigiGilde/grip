import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

BILLING_RHYTHMS = ("month", "quarter")
DELIVERY_VIAS = ("mail", "self")


class BillingTerms(Base):
    """How an assignment is billed: a term of the agreement.

    The rhythm says over which periods the financial administration gets
    what it needs to invoice. The details are what the client gave for the
    invoice (the annex "Factuurinformatie" of the quote): where it goes and
    which reference it must carry.
    """

    __tablename__ = "billing_terms"
    __table_args__ = (
        CheckConstraint("rhythm IN ('month', 'quarter')", name="rhythm_valid"),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rhythm: Mapped[str] = mapped_column(String(10))
    # organisation, attention_of, address, postcode_city, reference,
    # contact_name, contact_phone, contact_email: all text, all optional.
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    # Whether the specification that goes with a delivery names people. Off
    # by default: a quote names roles, and so does what follows from it.
    names_on_specification: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class BillingDelivery(Base):
    """What was handed to the financial administration for one billing period.

    A delivery groups the frozen billing data of the months of the period
    (and the corrections on earlier months that travel with it), carries the
    document that was made of it once, and records to whom and how it went.
    From it the administration makes the invoice; the invoice that results
    is recorded against the delivery.
    """

    __tablename__ = "billing_delivery"
    __table_args__ = (
        CheckConstraint("via IN ('mail', 'self')", name="via_valid"),
        CheckConstraint("period_end >= period_start", name="period_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="RESTRICT"),
        index=True,
    )
    # "2026-Q3" or "2026-07".
    period_key: Mapped[str] = mapped_column(String(10))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    rhythm: Mapped[str] = mapped_column(String(10))
    # The reference the document carries and an invoice can cite.
    reference: Mapped[str] = mapped_column(String(80))
    total_cents: Mapped[int] = mapped_column(BigInteger)
    # "mail": grip mailed the financial administration a link to it.
    # "self": the manager hands it over outside grip.
    via: Mapped[str] = mapped_column(String(10))
    recipient: Mapped[str | None] = mapped_column(String(320), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
