import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base

# The functions a person can hold in an instance. They are assigned; the
# relations to an opdracht or a person are derived from data and are not
# roles (see docs: rollen en toegang).
BEHEERDER = "beheerder"
PLANNER = "planner"
LEZER = "lezer"
AANVRAGER = "aanvrager"
TEKENBEVOEGDE = "tekenbevoegde"

FUNCTIONS = (BEHEERDER, PLANNER, LEZER, AANVRAGER, TEKENBEVOEGDE)


class Role(Base):
    """A function in the instance. Seeded by migration, not user-editable."""

    __tablename__ = "role"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))


class PersonRole(Base):
    """A function held by a person for a period."""

    __tablename__ = "person_role"
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="period_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        index=True,
    )
    role_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("role.id", ondelete="RESTRICT"), index=True
    )
    start_date: Mapped[date] = mapped_column(
        Date, default=date.today, server_default=func.current_date()
    )
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # NULL means granted by the system (bootstrap).
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    role: Mapped[Role] = relationship()
