import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import Versioned, created_at, updated_at, uuid_pk

INVOICE_LINE_KINDS = ("actual", "estimate")
# What became of the last request to the executor of a cost item (ADR 0052).
REQUEST_WAITING = "waiting"
REQUEST_APPLIED = "applied"
REQUEST_REFUSED = "refused"
REQUEST_UNDELIVERED = "undelivered"
REQUEST_STATUSES = (
    REQUEST_WAITING,
    REQUEST_APPLIED,
    REQUEST_REFUSED,
    REQUEST_UNDELIVERED,
)


class CostItem(Versioned, Base):
    """External costs, for example a hosting contract.

    A cost item does not belong to one assignment: its coverage can be spread
    over budget lines of several assignments.

    With an executor the item is a reference (ADR 0052, 0053): the executor
    owns description, amount and invoice lines, and this row keeps only what
    is this organisation's own. Description and amount are then those of a
    request the executor has not applied yet, and empty once it has.
    """

    __tablename__ = "cost_item"
    __table_args__ = (
        CheckConstraint("budgeted_cents >= 0", name="budgeted_not_negative"),
        CheckConstraint(
            "executor_organisation_id IS NOT NULL "
            "OR (description IS NOT NULL AND budgeted_cents IS NOT NULL)",
            name="own_item_has_content",
        ),
        CheckConstraint(
            "executor_organisation_id IS NULL OR reference_uri IS NULL",
            name="reference_not_requested",
        ),
        CheckConstraint(
            "request_status IS NULL OR request_status IN "
            "('waiting', 'applied', 'refused', 'undelivered')",
            name="request_status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    budgeted_cents: Mapped[int | None] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=True
    )
    # Who added the item. Until a budget line covers it nobody manages it
    # through an assignment, so the creator does (see grip.access.sql).
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), index=True
    )
    # The organisation that makes the expense and owns the item.
    executor_organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisation.id", ondelete="RESTRICT"), index=True
    )
    # The requests to the executor are numbered; the last one has this
    # number and this status.
    request_sequence: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    request_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # A day in the period of the expense, asked with the first request.
    request_period: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The executor applied a request, so it has the item.
    executor_has_item: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # On the executor's side: who asked for the item, the URI of their
    # reference and the number of the last request applied.
    requester_organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organisation.id", ondelete="SET NULL"), index=True
    )
    reference_uri: Mapped[str | None] = mapped_column(String(500), unique=True)
    reference_sequence: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    invoice_lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="cost_item", cascade="all, delete-orphan"
    )
    coverages: Mapped[list["CostCoverage"]] = relationship(
        back_populates="cost_item", cascade="all, delete-orphan"
    )


class InvoiceLine(Versioned, Base):
    """An amount on a cost item, realised or estimated (purchase side)."""

    __tablename__ = "invoice_line"
    __table_args__ = (
        CheckConstraint("kind IN ('actual', 'estimate')", name="kind_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    cost_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cost_item.id", ondelete="CASCADE"),
        index=True,
    )
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    # Any day in the period the amount belongs to; used for the year filter.
    period: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = created_at()

    cost_item: Mapped[CostItem] = relationship(back_populates="invoice_lines")


class CostCoverage(Versioned, Base):
    """Which budget line covers which share of a cost item."""

    __tablename__ = "cost_coverage"
    __table_args__ = (
        UniqueConstraint("cost_item_id", "budget_line_id"),
        CheckConstraint("pct > 0 AND pct <= 100", name="pct_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    cost_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cost_item.id", ondelete="CASCADE"),
        index=True,
    )
    budget_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_line.id", ondelete="CASCADE"),
        index=True,
    )
    pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = created_at()

    cost_item: Mapped[CostItem] = relationship(back_populates="coverages")
