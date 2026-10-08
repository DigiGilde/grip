import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

RATE_CARD_STATUSES = ("draft", "active", "closed")
RATE_CATEGORIES = ("A", "B", "C", "D", "E")


class RateCard(Base):
    """The rates and the scale mapping valid for a period (tarievenkaart).

    A card is valid from a date and to a date, or open-ended. Often that is a
    calendar year, but rates can change halfway through one, and then a new
    card starts there. A card starts on the first day of a month and ends on
    the last day of a month, so every calendar month is priced by exactly one
    card (ADR 0021). Cards that price (active and closed) do not overlap; a
    draft may overlap the card it is going to follow.
    """

    __tablename__ = "rate_card"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'closed')", name="status_valid"),
        CheckConstraint("extract(day from valid_from) = 1", name="starts_on_first"),
        CheckConstraint(
            "valid_to IS NULL OR (valid_to >= valid_from AND "
            "extract(day from valid_to + 1) = 1)",
            name="ends_on_last",
        ),
        CheckConstraint("btrim(name) <> ''", name="name_not_empty"),
        ExcludeConstraint(
            (text("daterange(valid_from, valid_to, '[]')"), "&&"),
            where=text("status <> 'draft'"),
            using="gist",
            name="ex_rate_card_no_overlap",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(100))
    valid_from: Mapped[date] = mapped_column(Date, index=True)
    # NULL: open-ended.
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
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

    @property
    def year(self) -> int:
        """The calendar year the card starts in. For callers and screens
        from before a card had a validity; a year can hold more than one
        card."""
        return self.valid_from.year

    @property
    def spans_calendar_year(self) -> bool:
        return (
            self.valid_from.month == 1
            and self.valid_to is not None
            and self.valid_to == date(self.valid_from.year, 12, 31)
        )


class RateBand(Base):
    """Monthly rate per FTE for one category on one card."""

    __tablename__ = "rate_band"
    __table_args__ = (
        UniqueConstraint("rate_card_id", "category"),
        CheckConstraint("category IN ('A', 'B', 'C', 'D', 'E')", name="category_valid"),
        CheckConstraint("monthly_rate_cents >= 0", name="rate_not_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    rate_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rate_card.id", ondelete="CASCADE"),
        index=True,
    )
    category: Mapped[str] = mapped_column(String(1))
    monthly_rate_cents: Mapped[int] = mapped_column(BigInteger)

    rate_card: Mapped[RateCard] = relationship(back_populates="rate_bands")


class ScaleBand(Base):
    """Which category a scale bills in, on one card."""

    __tablename__ = "scale_band"
    __table_args__ = (
        UniqueConstraint("rate_card_id", "scale"),
        CheckConstraint("category IN ('A', 'B', 'C', 'D', 'E')", name="category_valid"),
        CheckConstraint("scale BETWEEN 1 AND 30", name="scale_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    rate_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rate_card.id", ondelete="CASCADE"),
        index=True,
    )
    scale: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(1))

    rate_card: Mapped[RateCard] = relationship(back_populates="scale_bands")
