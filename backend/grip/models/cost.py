import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import Versioned, created_at, updated_at, uuid_pk

INVOICE_LINE_KINDS = ("actual", "estimate")


class CostItem(Versioned, Base):
    """External costs, for example a hosting contract.

    A cost item does not belong to one assignment: its coverage can be spread
    over budget lines of several assignments.
    """

    __tablename__ = "cost_item"
    __table_args__ = (
        CheckConstraint("budgeted_cents >= 0", name="budgeted_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    description: Mapped[str] = mapped_column(String(500))
    budgeted_cents: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0"
    )
    # Who added the item. Until a budget line covers it nobody manages it
    # through an assignment, so the creator does (see grip.access.sql).
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), index=True
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
