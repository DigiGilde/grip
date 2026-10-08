import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

ASSIGNMENT_KINDS = ("external", "internal")
TRAFFIC_FORMS = ("federated", "document", "none")
ASSIGNMENT_STATUSES = (
    "draft",
    "requested",
    "quoted",
    "accepted",
    "in_progress",
    "completed",
    "accounted",
    "rejected",
    "cancelled",
)
ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
BUDGET_LINE_KINDS = ("personnel", "fixed")


class Assignment(Base):
    """An opdracht: the unit a quote is made for."""

    __tablename__ = "assignment"
    __table_args__ = (
        CheckConstraint("kind IN ('external', 'internal')", name="kind_valid"),
        CheckConstraint(
            "traffic_form IN ('federated', 'document', 'none')",
            name="traffic_form_valid",
        ),
        CheckConstraint(
            "status IN ('draft', 'requested', 'quoted', 'accepted', 'in_progress', "
            "'completed', 'accounted', 'rejected', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="period_valid",
        ),
        CheckConstraint(
            "quoted_amount_cents IS NULL OR quoted_amount_cents >= 0",
            name="quoted_amount_not_negative",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Minted by the instance that creates the assignment; for an incoming
    # request it is the URI the client gave.
    uri: Mapped[str] = mapped_column(String(500), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(
        String(10), default="external", server_default="external"
    )
    traffic_form: Mapped[str] = mapped_column(
        String(10), default="none", server_default="none"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft", index=True
    )
    client_organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisation.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    contractor_organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisation.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    parent_assignment_uri: Mapped[str | None] = mapped_column(
        String(500), nullable=True, index=True
    )
    # Node URIs in one or more corpora. May be empty.
    context_refs: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    client_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quote_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The agreed amount, entered; the budget is derived and may differ.
    quoted_amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    budget_lines: Mapped[list["BudgetLine"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
        order_by="BudgetLine.position",
    )
    roles: Mapped[list["AssignmentRole"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )


class AssignmentRole(Base):
    """Owner or manager of an assignment. One owner, any number of managers."""

    __tablename__ = "assignment_role"
    __table_args__ = (
        UniqueConstraint("assignment_id", "person_id"),
        CheckConstraint("role IN ('owner', 'manager')", name="role_valid"),
        Index(
            "uq_assignment_role_one_owner",
            "assignment_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="CASCADE"),
        index=True,
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = created_at()

    assignment: Mapped[Assignment] = relationship(back_populates="roles")


class BudgetLine(Base):
    """One line of an assignment's budget: a role (personnel) or a fixed post."""

    __tablename__ = "budget_line"
    __table_args__ = (
        CheckConstraint("kind IN ('personnel', 'fixed')", name="kind_valid"),
        CheckConstraint(
            "kind <> 'personnel' OR (fte IS NOT NULL AND rate_category IS NOT NULL "
            "AND start_date IS NOT NULL AND end_date IS NOT NULL "
            "AND amount_cents IS NULL AND year IS NULL)",
            name="personnel_fields",
        ),
        CheckConstraint(
            "kind <> 'fixed' OR (amount_cents IS NOT NULL AND year IS NOT NULL "
            "AND fte IS NULL AND rate_category IS NULL)",
            name="fixed_fields",
        ),
        CheckConstraint("fte IS NULL OR fte > 0", name="fte_positive"),
        CheckConstraint(
            "rate_category IS NULL OR rate_category IN ('A', 'B', 'C', 'D', 'E')",
            name="category_valid",
        ),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="period_valid",
        ),
        CheckConstraint(
            "amount_cents IS NULL OR amount_cents >= 0", name="amount_not_negative"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="CASCADE"),
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(10))
    position: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # personnel
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fte: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    rate_category: Mapped[str | None] = mapped_column(String(1), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # fixed
    amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    assignment: Mapped[Assignment] = relationship(back_populates="budget_lines")
    allocations: Mapped[list["Allocation"]] = relationship(
        back_populates="budget_line", cascade="all, delete-orphan"
    )


class Allocation(Base):
    """Inzet: a person on a personnel budget line, for a period, at an FTE
    percentage."""

    __tablename__ = "allocation"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="period_valid"),
        CheckConstraint("fte_pct > 0 AND fte_pct <= 100", name="pct_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="RESTRICT"), index=True
    )
    budget_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_line.id", ondelete="CASCADE"),
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    fte_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    budget_line: Mapped[BudgetLine] = relationship(back_populates="allocations")
