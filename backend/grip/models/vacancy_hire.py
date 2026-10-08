"""A vacancy's counterpart in the recruitment system, and who was hired on it.

Grip holds the demand: the role, the scale, the approval, the request form and
the text. Who applied and who is being considered lives in the recruitment
system; grip keeps no candidates. What grip does keep is a reference to the
vacancy there, and, at the moment of hire, who was hired and from when.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base

# The first recruitment system connected by reference. Another organisation
# may use another one; the field is free text with this as the default.
DEFAULT_RECRUITMENT_SYSTEM = "emply"


class VacancyRecruitmentRef(Base):
    """Where this vacancy lives in the recruitment system. Entered by hand."""

    __tablename__ = "vacancy_recruitment_ref"

    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancy.id", ondelete="CASCADE"),
        primary_key=True,
    )
    system: Mapped[str] = mapped_column(
        String(40),
        default=DEFAULT_RECRUITMENT_SYSTEM,
        server_default=text(f"'{DEFAULT_RECRUITMENT_SYSTEM}'"),
    )
    reference: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VacancyHire(Base):
    """Who filled the vacancy. Present from the hire, not before."""

    __tablename__ = "vacancy_hire"

    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancy.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Cleared when the person record is removed after a hire fell through.
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
