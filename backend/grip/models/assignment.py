import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ColumnElement,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    case,
    event,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

if TYPE_CHECKING:
    from grip.models.catalogue_role import CatalogueRole

ASSIGNMENT_KINDS = ("external", "internal")
ASSIGNMENT_STATUSES = (
    "draft",
    "requested",
    "quoted",
    # Agreed by word of mouth, not formally accepted yet. Known to the
    # contractor only; see grip.services.phase.counterparty_status.
    "verbally_agreed",
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
            "status IN ('draft', 'requested', 'quoted', 'verbally_agreed', "
            "'accepted', 'in_progress', 'completed', 'accounted', 'rejected', "
            "'cancelled')",
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
    # The grip instance of the other party this assignment is shared with,
    # by its base URI. Not a setting: it arises from an exchange. A request
    # came in from that instance, a request was sent to it, or a quote was
    # offered to it. NULL as long as nothing was exchanged; how a quote
    # reaches the client is chosen per quote, when it is offered.
    shared_with_instance_uri: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    shared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    # Who agreed verbally and when, as noted by the owner or manager. Kept
    # after formal acceptance, as the trail of how the assignment started.
    verbal_agreement_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verbal_agreement_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
        # The name of the role is kept on the line next to the reference, and
        # this key keeps the two equal: renaming a role in the catalogue
        # renames it on every line, and a name the catalogue does not hold
        # cannot be written.
        ForeignKeyConstraint(
            ["role_id", "role"],
            ["catalogue_role.id", "catalogue_role.name"],
            name="fk_budget_line_role_catalogue_role",
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(role_id IS NULL) = (role IS NULL)", name="role_with_reference"
        ),
        # A line is named by its role, by its description, or by both.
        CheckConstraint("description <> '' OR role IS NOT NULL", name="named"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="CASCADE"),
        index=True,
    )
    # The free text that tells this line apart ("#2, vanaf Q2"). Optional once
    # a role is chosen. Stored in the column "description"; the attribute
    # ``description`` below is the name of the line as it is shown.
    detail: Mapped[str] = mapped_column(
        "description", String(500), default="", server_default=""
    )
    kind: Mapped[str] = mapped_column(String(10))
    position: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # personnel
    # The role from the catalogue, and its name. Set either one: the other
    # follows before the line is written (see ``_resolve_budget_line_roles``).
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fte: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    rate_category: Mapped[str | None] = mapped_column(String(1), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The colleague the role is meant for, when that is already known. This
    # is staffing data (class C). It never enters a quote: see
    # grip.services.quote_content for what a quote line may be built from.
    intended_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # fixed
    amount_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    assignment: Mapped[Assignment] = relationship(back_populates="budget_lines")
    allocations: Mapped[list["Allocation"]] = relationship(
        back_populates="budget_line", cascade="all, delete-orphan"
    )
    # Only so a new catalogue entry is written before the line that uses it.
    role_entry: Mapped["CatalogueRole | None"] = relationship(
        "CatalogueRole",
        primaryjoin="BudgetLine.role_id == CatalogueRole.id",
        foreign_keys="BudgetLine.role_id",
        lazy="raise",
    )

    @hybrid_property
    def description(self) -> str:
        """The name of the line as it is shown: the role plus the detail.

        A detail that already names the role is shown as it is, so a line
        written before roles came from a catalogue keeps its words.
        """
        return line_display_name(self.role, self.detail)

    @description.inplace.setter
    def _set_description(self, value: str | None) -> None:
        self.detail = value or ""

    @description.inplace.expression
    @classmethod
    def _description_expression(cls) -> ColumnElement[str]:
        return case(
            (cls.role.is_(None), cls.detail),
            (cls.detail == "", cls.role),
            (
                func.strpos(func.lower(cls.detail), func.lower(cls.role)) > 0,
                cls.detail,
            ),
            else_=func.concat(cls.role, ": ", cls.detail),
        )

    @property
    def display_name(self) -> str:
        return self.description


def line_display_name(role: str | None, detail: str | None) -> str:
    """Role plus detail, without saying the role twice."""
    detail = detail or ""
    if not role:
        return detail
    if not detail:
        return role
    if role.lower() in detail.lower():
        return detail
    return f"{role}: {detail}"


def canonical_role_name(value: str) -> str:
    """A role name as it is stored: one line, single spaces."""
    return " ".join(value.split())[:255]


def _role_changed(line: "BudgetLine") -> bool:
    state = inspect(line)
    if state.pending or state.transient:
        return line.role is not None or line.role_id is not None
    attrs = state.attrs
    return attrs.role.history.has_changes() or attrs.role_id.history.has_changes()


@event.listens_for(Session, "before_flush")
def _resolve_budget_line_roles(
    session: Session, _context: Any, _instances: Any
) -> None:
    """Make role and role_id of a budget line agree before it is written.

    A caller sets the reference or the name. Given the reference, the name is
    read from the catalogue. Given a name, the catalogue entry with that name
    is looked up without regard to capitals; a name the catalogue does not
    hold becomes a manual entry marked for review, so no value is lost and
    the beheerder can merge it later. Deciding who may add a role is the
    business of the service layer; this only keeps the two columns in step.

    A line with neither a role nor a description is refused here, with a
    message for the person filling in the budget.
    """
    touched = [o for o in (*session.new, *session.dirty) if isinstance(o, BudgetLine)]
    lines = [o for o in touched if _role_changed(o)]
    if lines:
        _resolve_roles(session, lines)
    for line in touched:
        if not line.role and not (line.detail or "").strip():
            from grip.services.errors import DomainValidationError

            raise DomainValidationError(
                "Kies een rol of geef de regel een omschrijving."
            )


def _resolve_roles(session: Session, lines: list["BudgetLine"]) -> None:
    from grip.models.catalogue_role import ROLE_SOURCE_MANUAL, CatalogueRole

    pending = {
        o.name.lower(): o
        for o in session.new
        if isinstance(o, CatalogueRole) and o.name
    }
    with session.no_autoflush:
        for line in lines:
            state = inspect(line)
            # A new line given only the reference, or a line whose
            # reference was changed. Clearing the name of an existing line
            # clears the role and is not mistaken for this.
            by_reference = line.role_id is not None and (
                state.attrs.role_id.history.has_changes()
                if state.persistent
                else line.role is None
            )
            if by_reference:
                entry = next(
                    (r for r in pending.values() if r.id == line.role_id), None
                ) or session.get(CatalogueRole, line.role_id)
                if entry is not None:
                    line.role = entry.name
                continue
            name = canonical_role_name(line.role or "")
            if not name:
                line.role = None
                line.role_id = None
                continue
            entry = (
                pending.get(name.lower())
                or session.execute(
                    select(CatalogueRole).where(
                        func.lower(CatalogueRole.name) == name.lower()
                    )
                ).scalar_one_or_none()
            )
            if entry is None:
                entry = CatalogueRole(
                    id=uuid.uuid4(),
                    name=name,
                    source=ROLE_SOURCE_MANUAL,
                    needs_review=True,
                )
                session.add(entry)
                pending[name.lower()] = entry
            line.role_entry = entry
            line.role_id = entry.id
            line.role = entry.name


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
    # True for the reservation that naming an intended person on the budget
    # line made. It follows the line while the two are in step.
    from_budget: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    budget_line: Mapped[BudgetLine] = relationship(back_populates="allocations")
