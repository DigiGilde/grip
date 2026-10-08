"""Standard vacancy texts, the course of a text on a vacancy, and where a
vacancy was published.

Three things live here:

- The library: a standard text per role (``VacancyTextTemplate``) built from
  sections, with the sections every role shares stored once
  (``VacancyTextSharedSection``). Shipped defaults are loaded at start; a
  text a person changed is never overwritten.
- The course of a text: a round of review (``VacancyTextReview``) with a
  verdict per reviewer (``VacancyTextVerdict``) and remarks on a section
  (``VacancyTextRemark``). The versions themselves are ``VacancyText`` rows.
- ``VacancyPublication``: the public address of a published vacancy.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

ORIGIN_EXAMPLE = "example"
ORIGIN_DERIVED = "derived"
ORIGIN_MANUAL = "manual"
ORIGINS = (ORIGIN_EXAMPLE, ORIGIN_DERIVED, ORIGIN_MANUAL)

VERDICT_AGREED = "agreed"
VERDICT_REMARKS = "remarks"
VERDICTS = (VERDICT_AGREED, VERDICT_REMARKS)

PLACE_INTERNAL = "internal"
PLACE_GOVERNMENT_WIDE = "government_wide"
PLACE_EXTERNAL = "external"
PLACES = (PLACE_INTERNAL, PLACE_GOVERNMENT_WIDE, PLACE_EXTERNAL)


def _person_fk(*, ondelete: str = "SET NULL") -> Mapped[uuid.UUID | None]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete=ondelete), nullable=True
    )


class VacancyTextSharedSection(Base):
    """A section every standard text shares: what we offer, how to apply."""

    __tablename__ = "vacancy_text_shared_section"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    heading: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The version of the shipped library this text was loaded from; None for
    # a section a person added.
    shipped_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Set when a person changed the text: the loader then leaves it alone.
    changed_by_id: Mapped[uuid.UUID | None] = _person_fk()
    changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = updated_at()


class VacancyTextTemplate(Base):
    """The standard vacancy text of a role."""

    __tablename__ = "vacancy_text_template"
    __table_args__ = (
        Index(
            "uq_vacancy_text_template_role_lower", text("lower(role_name)"), unique=True
        ),
        CheckConstraint(
            "origin IN ('example', 'derived', 'manual')", name="origin_valid"
        ),
        CheckConstraint("btrim(role_name) <> ''", name="role_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    catalogue_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalogue_role.id", ondelete="SET NULL"),
        nullable=True,
    )
    role_name: Mapped[str] = mapped_column(String(255))
    # Other names the same role goes by, for finding the text of a vacancy.
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    scale_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scale_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Name of the function group of the Functiegebouw Rijk the role usually
    # falls in; used to find the nearest text for a role without one.
    function_group: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # example: reworked from a text of the organisation. derived: written
    # from the shared outline, not one of theirs. manual: added by a person.
    origin: Mapped[str] = mapped_column(String(10), default=ORIGIN_MANUAL)
    # A person read the text and stands for it. A derived text starts unread.
    reviewed_by_id: Mapped[uuid.UUID | None] = _person_fk()
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Ordered list of {"key", "heading", "body", "optional"?} or {"shared": key}.
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    shipped_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    changed_by_id: Mapped[uuid.UUID | None] = _person_fk()
    changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class VacancyTextReview(Base):
    """One round: a version of a text offered to people to judge."""

    __tablename__ = "vacancy_text_review"
    __table_args__ = (
        UniqueConstraint("vacancy_id", "kind", "round"),
        Index("ix_vacancy_text_review_vacancy", "vacancy_id", "kind"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancy.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20))
    round: Mapped[int] = mapped_column(Integer)
    text_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancy_text.id", ondelete="CASCADE")
    )
    offered_by_id: Mapped[uuid.UUID | None] = _person_fk()
    offered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Withdrawn by the writer before everyone answered.
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    verdicts: Mapped[list["VacancyTextVerdict"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="VacancyTextVerdict.created_at",
        lazy="selectin",
    )


class VacancyTextVerdict(Base):
    """What one reviewer said in a round; empty until that person answers."""

    __tablename__ = "vacancy_text_verdict"
    __table_args__ = (
        UniqueConstraint("review_id", "reviewer_id"),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('agreed', 'remarks')", name="verdict_valid"
        ),
        CheckConstraint(
            "(verdict IS NULL) = (decided_at IS NULL)", name="decided_complete"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancy_text_review.id", ondelete="CASCADE")
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE")
    )
    verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at()

    review: Mapped[VacancyTextReview] = relationship(back_populates="verdicts")


class VacancyTextRemark(Base):
    """A remark on a section of a text, with its answers."""

    __tablename__ = "vacancy_text_remark"
    __table_args__ = (Index("ix_vacancy_text_remark_vacancy", "vacancy_id", "kind"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancy.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20))
    # The version the remark was made on.
    text_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancy_text.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Heading of the section the remark is about; empty for the whole text.
    section: Mapped[str] = mapped_column(String(200), default="", server_default="")
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID | None] = _person_fk()
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancy_text_remark.id", ondelete="CASCADE"),
        nullable=True,
    )
    resolved_by_id: Mapped[uuid.UUID | None] = _person_fk()
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class VacancyPublication(Base):
    """Where a published vacancy can be read by anyone: its public address.

    Not the reference in the recruitment system (``vacancy_recruitment_ref``),
    which only recruiters can open.
    """

    __tablename__ = "vacancy_publication"
    __table_args__ = (
        UniqueConstraint("vacancy_id", "place"),
        CheckConstraint(
            "place IN ('internal', 'government_wide', 'external')", name="place_valid"
        ),
        CheckConstraint("url LIKE 'https://%'", name="url_https"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancy.id", ondelete="CASCADE")
    )
    place: Mapped[str] = mapped_column(String(20))
    url: Mapped[str] = mapped_column(String(1000))
    published_on: Mapped[date] = mapped_column(Date)
    recorded_by_id: Mapped[uuid.UUID | None] = _person_fk()
    created_at: Mapped[datetime] = created_at()
