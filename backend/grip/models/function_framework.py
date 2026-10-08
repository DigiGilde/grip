"""The Functiegebouw Rijk: function families, function groups and their scales.

The national government classifies its jobs in function families, each with
function groups; a group is tied to one or more salary scales. The name of
the group is what a vacancy request form asks for as "FGR-functienaam".

Rows come from the reference file under ``grip/data/function_framework``
(source ``reference``) or are added by the beheerder (source ``manual``). A
row that is no longer valid gets an end date instead of being removed, so a
vacancy that points at it keeps its meaning.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

SOURCE_REFERENCE = "reference"
SOURCE_MANUAL = "manual"
MIN_SCALE = 1
MAX_SCALE = 19


class FunctionFamily(Base):
    __tablename__ = "function_family"
    __table_args__ = (
        CheckConstraint("source IN ('reference', 'manual')", name="source_valid"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_order",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Stable short name; for a reference row the last part of its address.
    key: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    source: Mapped[str] = mapped_column(
        String(10), default=SOURCE_MANUAL, server_default=SOURCE_MANUAL
    )
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    groups: Mapped[list["FunctionGroup"]] = relationship(
        back_populates="family",
        cascade="all, delete-orphan",
        order_by="FunctionGroup.position",
    )


class FunctionGroup(Base):
    __tablename__ = "function_group"
    __table_args__ = (
        CheckConstraint("source IN ('reference', 'manual')", name="source_valid"),
        CheckConstraint("cardinality(scales) >= 1", name="has_scales"),
        CheckConstraint(
            f"{MIN_SCALE} <= ALL(scales) AND {MAX_SCALE} >= ALL(scales)",
            name="scales_in_range",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_order",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("function_family.id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    # The scales the group is tied to, ascending.
    scales: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    source: Mapped[str] = mapped_column(
        String(10), default=SOURCE_MANUAL, server_default=SOURCE_MANUAL
    )
    # The identifier the source gives the group; what a reload matches on.
    source_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Set when a beheerder changed the row by hand. A reload of the reference
    # file leaves such a row alone.
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    edited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    family: Mapped[FunctionFamily] = relationship(back_populates="groups")

    def is_valid_on(self, day: date) -> bool:
        if self.valid_from is not None and day < self.valid_from:
            return False
        return self.valid_to is None or day <= self.valid_to


__all__ = [
    "MAX_SCALE",
    "MIN_SCALE",
    "SOURCE_MANUAL",
    "SOURCE_REFERENCE",
    "FunctionFamily",
    "FunctionGroup",
]
