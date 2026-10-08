import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk


class PersonScale(Base):
    """The scale a person is billed at, with history.

    Only the billing scale is stored; the salary scale is not (ADR 0014).
    """

    __tablename__ = "person_scale"
    __table_args__ = (
        UniqueConstraint("person_id", "valid_from"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="period_valid"
        ),
        CheckConstraint("billing_scale BETWEEN 1 AND 30", name="scale_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    billing_scale: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at()


class BillabilityTarget(Base):
    """Share of a person's year that must be billable."""

    __tablename__ = "billability_target"
    __table_args__ = (
        UniqueConstraint("person_id", "year"),
        CheckConstraint("target_pct BETWEEN 0 AND 100", name="pct_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)
    target_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))


class Hire(Base):
    """Cost side of a hired person: supplier and cost rate for a period.

    The margin is derived (billing rate minus cost rate) and not stored.
    """

    __tablename__ = "hire"
    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="period_valid"
        ),
        CheckConstraint("cost_monthly_rate_cents >= 0", name="rate_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    supplier: Mapped[str] = mapped_column(String(255))
    # Cost per FTE per month, comparable with the monthly billing rate.
    cost_monthly_rate_cents: Mapped[int] = mapped_column(BigInteger)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
