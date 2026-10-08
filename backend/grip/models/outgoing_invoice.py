import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

INVOICE_SOURCES = ("manual", "financial_system")


class OutgoingInvoice(Base):
    """The recorded fact that an invoice was sent to the client.

    Grip sends no invoices and cannot see one being sent. Someone records
    it: the number, the date and the amount as invoiced, for one or several
    deliveries of billing data. ``source`` says where the fact comes from,
    so the financial system can become its source later without the model
    changing.

    A wrongly recorded invoice is withdrawn, not deleted: the row stays with
    who withdrew it and why, and its deliveries become free again.

    Not to be confused with ``invoice_line``, which is the purchase side: an
    amount on a cost item.
    """

    __tablename__ = "outgoing_invoice"
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'financial_system')", name="source_valid"
        ),
        CheckConstraint("btrim(invoice_number) <> ''", name="number_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="RESTRICT"),
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(100))
    invoice_date: Mapped[date] = mapped_column(Date)
    # The amount on the invoice. May differ from what was delivered; the
    # difference is shown, never corrected away. Negative for a credit note.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(
        String(20), default="manual", server_default="manual"
    )
    # Identifier of the invoice in the financial system, when it is the source.
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    withdrawn_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    withdrawn_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    deliveries: Mapped[list["OutgoingInvoiceDelivery"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class OutgoingInvoiceDelivery(Base):
    """Which delivery of billing data an invoice covers.

    A delivery (a billing export) is on at most one invoice. Withdrawing an
    invoice removes its rows here; the audit row of the withdrawal keeps
    which deliveries it covered.
    """

    __tablename__ = "outgoing_invoice_delivery"
    __table_args__ = (UniqueConstraint("billing_export_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    outgoing_invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outgoing_invoice.id", ondelete="CASCADE"),
        index=True,
    )
    billing_export_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_export.id", ondelete="RESTRICT")
    )

    invoice: Mapped[OutgoingInvoice] = relationship(back_populates="deliveries")
