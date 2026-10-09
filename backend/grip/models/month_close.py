import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import Versioned, created_at, uuid_pk


class MonthClose(Versioned, Base):
    """The established actual inzet of one month of one assignment.

    Reopening keeps the row and marks it; a new close is a new row. At most
    one close per assignment and month is in force.
    """

    __tablename__ = "month_close"
    __table_args__ = (
        CheckConstraint("extract(day from month) = 1", name="month_is_first_day"),
        Index(
            "uq_month_close_in_force",
            "assignment_id",
            "month",
            unique=True,
            postgresql_where=text("reopened_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="RESTRICT"),
        index=True,
    )
    # First day of the calendar month.
    month: Mapped[date] = mapped_column(Date)
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reopened_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    reopened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reopen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    lines: Mapped[list["MonthCloseLine"]] = relationship(
        back_populates="month_close", cascade="all, delete-orphan"
    )


class MonthCloseLine(Base):
    """Established FTE percentage of one allocation in a closed month.

    The amount is not stored: it follows from the percentage and the rate
    card, through the calculation module.
    """

    __tablename__ = "month_close_line"
    __table_args__ = (
        UniqueConstraint("month_close_id", "allocation_id"),
        CheckConstraint(
            "established_fte_pct >= 0 AND established_fte_pct <= 100",
            name="pct_valid",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    month_close_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("month_close.id", ondelete="CASCADE"),
        index=True,
    )
    allocation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("allocation.id", ondelete="RESTRICT"),
        index=True,
    )
    # The planned percentage at the moment of closing, kept for the trail.
    planned_fte_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    established_fte_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3))

    month_close: Mapped[MonthClose] = relationship(back_populates="lines")


class BillingExport(Base):
    """Factuurgegevens of one assignment for one closed month, as exported.

    An export is a frozen record of what went to the financial system.
    """

    __tablename__ = "billing_export"
    __table_args__ = (
        CheckConstraint("extract(day from month) = 1", name="month_is_first_day"),
        CheckConstraint("kind IN ('original', 'correction')", name="kind_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="RESTRICT"),
        index=True,
    )
    month: Mapped[date] = mapped_column(Date)
    month_close_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("month_close.id", ondelete="RESTRICT")
    )
    total_cents: Mapped[int] = mapped_column(BigInteger)
    # "original": the delivery of the month. "correction" (naverrekening):
    # the difference that arose after it, because the price of the month
    # changed; its lines hold differences and may be negative. The original
    # is never rewritten.
    kind: Mapped[str] = mapped_column(
        String(12), default="original", server_default="original"
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The delivery to the financial administration this record went with.
    # Empty for a record from before deliveries per billing period existed.
    delivery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("billing_delivery.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = created_at()

    lines: Mapped[list["BillingExportLine"]] = relationship(
        back_populates="billing_export", cascade="all, delete-orphan"
    )


class BillingExportLine(Base):
    __tablename__ = "billing_export_line"

    id: Mapped[uuid.UUID] = uuid_pk()
    billing_export_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("billing_export.id", ondelete="CASCADE"),
        index=True,
    )
    budget_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_line.id", ondelete="RESTRICT")
    )
    allocation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("allocation.id", ondelete="RESTRICT")
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="RESTRICT")
    )
    # Role of the budget line; the description that may cross the boundary.
    description: Mapped[str] = mapped_column(String(500))
    fte_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    category: Mapped[str] = mapped_column(String(1))
    monthly_rate_cents: Mapped[int] = mapped_column(BigInteger)
    amount_cents: Mapped[int] = mapped_column(BigInteger)

    billing_export: Mapped[BillingExport] = relationship(back_populates="lines")
