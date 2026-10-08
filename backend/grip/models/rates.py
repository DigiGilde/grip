import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

RATE_CARD_STATUSES = ("draft", "active", "closed")
RATE_CATEGORIES = ("A", "B", "C", "D", "E")


class RateCard(Base):
    """All rates of one calendar year (tarievenleaflet)."""

    __tablename__ = "rate_card"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'closed')", name="status_valid"),
        CheckConstraint("year BETWEEN 2000 AND 2100", name="year_valid"),
    )

    year: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    status: Mapped[str] = mapped_column(
        String(10), default="draft", server_default="draft"
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    rate_bands: Mapped[list["RateBand"]] = relationship(
        back_populates="rate_card",
        cascade="all, delete-orphan",
        order_by="RateBand.category",
    )
    scale_bands: Mapped[list["ScaleBand"]] = relationship(
        back_populates="rate_card",
        cascade="all, delete-orphan",
        order_by="ScaleBand.scale",
    )


class RateBand(Base):
    """Monthly rate per FTE for one category in one year."""

    __tablename__ = "rate_band"
    __table_args__ = (
        UniqueConstraint("year", "category"),
        CheckConstraint("category IN ('A', 'B', 'C', 'D', 'E')", name="category_valid"),
        CheckConstraint("monthly_rate_cents >= 0", name="rate_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    year: Mapped[int] = mapped_column(
        Integer, ForeignKey("rate_card.year", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(1))
    monthly_rate_cents: Mapped[int] = mapped_column(BigInteger)

    rate_card: Mapped[RateCard] = relationship(back_populates="rate_bands")


class ScaleBand(Base):
    """Which category a scale bills in, for one year."""

    __tablename__ = "scale_band"
    __table_args__ = (
        UniqueConstraint("year", "scale"),
        CheckConstraint("category IN ('A', 'B', 'C', 'D', 'E')", name="category_valid"),
        CheckConstraint("scale BETWEEN 1 AND 30", name="scale_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    year: Mapped[int] = mapped_column(
        Integer, ForeignKey("rate_card.year", ondelete="CASCADE"), index=True
    )
    scale: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(1))

    rate_card: Mapped[RateCard] = relationship(back_populates="scale_bands")
