"""Where a person stands with the organisation, and the proposal to Wies.

Neither grip nor Wies is the personnel administration. That someone is hired,
from when, and that someone left are facts that belong there. Until that
system is connected the fact is recorded here, with the system it came from in
``source``, so another source can take over later without changing the shape.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base


class Stage(enum.StrEnum):
    # Hired, with a start date; no account or address of the organisation yet.
    prospective = "prospective"
    colleague = "colleague"
    left = "left"


class StandingSource(enum.StrEnum):
    grip = "grip"
    wies = "wies"
    # The system in which candidates are selected; the hire comes from there.
    recruitment = "recruitment"
    # The personnel administration: the eventual source of existence and
    # employment.
    personnel = "personnel"


class ProposalState(enum.StrEnum):
    open = "open"
    confirmed = "confirmed"
    declined = "declined"
    withdrawn = "withdrawn"


STAGES = tuple(s.value for s in Stage)
STANDING_SOURCES = tuple(s.value for s in StandingSource)
PROPOSAL_STATES = tuple(s.value for s in ProposalState)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PersonStanding(Base):
    """The current standing of one person. History is in the audit log."""

    __tablename__ = "person_standing"
    __table_args__ = (
        CheckConstraint(_in("stage", STAGES), name="stage_valid"),
        CheckConstraint(_in("source", STANDING_SOURCES), name="source_valid"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="dates_ordered",
        ),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        primary_key=True,
    )
    stage: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(20))
    # The reference of this fact in the source system, and a link to it.
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Set when a hire fell through: the day the person record is removed.
    remove_after: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ColleagueProposal(Base):
    """Grip proposes a new colleague to Wies; staff there confirms or declines.

    One per person. Wies fetches the open and withdrawn ones; its answer comes
    back with the colleagues grip reads from Wies.
    """

    __tablename__ = "colleague_proposal"
    __table_args__ = (
        CheckConstraint(_in("state", PROPOSAL_STATES), name="state_valid"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # The merk in Wies. Grip sets it with the proposal; Wies owns it after.
    suborganization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(
        String(20), default=ProposalState.open.value, server_default=text("'open'")
    )
    withdrawn_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
