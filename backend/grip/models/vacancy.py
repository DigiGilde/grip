"""Vacancies: an open role, the recruitment procedure, and its texts.

A vacancy usually hangs on a personnel budget line. A vacancy that is not
declarable has no budget line. The steps of the procedure, the advice and
approval records and the text versions are separate tables so each keeps its
own history.

The value sets are plain strings with check constraints, defined once in the
StrEnums below and repeated literally in the migration.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base


class VacancyType(enum.StrEnum):
    regulier = "regulier"
    specialistisch = "specialistisch"
    beoogd = "beoogd"
    gerede = "gerede"


class ContractType(enum.StrEnum):
    temporary_project = "temporary_project"
    temporary_before_permanent = "temporary_before_permanent"


class VacancyStatus(enum.StrEnum):
    draft = "draft"
    requested = "requested"
    approved = "approved"
    rejected = "rejected"
    open = "open"
    filled = "filled"
    withdrawn = "withdrawn"


class VacancyChannel(enum.StrEnum):
    internal = "internal"
    federated = "federated"
    recruitment = "recruitment"


class StepKind(enum.StrEnum):
    request = "request"
    hr_advice = "hr_advice"
    control_advice = "control_advice"
    approval = "approval"
    internal_opening = "internal_opening"
    priority_candidates = "priority_candidates"
    government_wide_opening = "government_wide_opening"
    external_market = "external_market"


class DecisionKind(enum.StrEnum):
    hr_advice = "hr_advice"
    control_advice = "control_advice"
    approval = "approval"


class TextKind(enum.StrEnum):
    vacancy_text = "vacancy_text"
    motivation = "motivation"


class TextSource(enum.StrEnum):
    human = "human"
    model = "model"


def _in(column: str, values: type[enum.StrEnum]) -> str:
    quoted = ", ".join(f"'{v.value}'" for v in values)
    return f"{column} IN ({quoted})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class FormTemplate(Base):
    """The blank request form of this instance, with its field mapping.

    Every organisation has its own form, so the file is uploaded per instance
    and never lives in the repository. The mapping says which form field gets
    which value from grip.
    """

    __tablename__ = "form_template"
    __table_args__ = (
        # At most one active template per kind of form.
        Index(
            "uq_form_template_active_kind",
            "kind",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String(50), default="vacancy_request")
    name: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Vacancy(Base):
    """An open role that has to be filled."""

    __tablename__ = "vacancy"
    __table_args__ = (
        CheckConstraint(_in("vacancy_type", VacancyType), name="vacancy_type"),
        CheckConstraint(_in("contract_type", ContractType), name="contract_type"),
        CheckConstraint(_in("status", VacancyStatus), name="status"),
        CheckConstraint("fte > 0", name="fte_positive"),
        # A declarable vacancy is paid from a budget line; one without a line
        # cannot be declarable.
        CheckConstraint(
            "declarable = false OR budget_line_id IS NOT NULL",
            name="declarable_has_budget_line",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    budget_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_line.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    function_title: Mapped[str] = mapped_column(String(255))
    # Name of the function in the government's function framework (FGR).
    fgr_function_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The function group of the Functiegebouw Rijk the name above was taken
    # from. The name stays as it was printed when chosen, so a later renaming
    # of the group does not change a request that was already issued.
    function_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("function_group.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scale: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Why the scale lies outside the scales of the function group, when it
    # does. Without a reason such a scale is refused.
    scale_deviation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fte: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    declarable: Mapped[bool] = mapped_column(Boolean)
    vacancy_type: Mapped[str] = mapped_column(
        String(30), default=VacancyType.regulier.value
    )
    contract_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=VacancyStatus.draft.value,
        server_default=text("'draft'"),
        index=True,
    )
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), default=list, server_default=text("'{}'")
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    requester_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Who the request is addressed to. Often not a user of this instance, so
    # it is a name and not a reference.
    addressee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Set when the addressee has an account here; the name above is then the
    # name of that person at the time.
    addressee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    requester = relationship("Person", foreign_keys=[requester_id])
    steps: Mapped[list["VacancyStep"]] = relationship(
        back_populates="vacancy",
        cascade="all, delete-orphan",
        order_by="VacancyStep.position",
    )
    decisions: Mapped[list["VacancyDecision"]] = relationship(
        back_populates="vacancy", cascade="all, delete-orphan"
    )
    texts: Mapped[list["VacancyText"]] = relationship(
        back_populates="vacancy",
        cascade="all, delete-orphan",
        order_by="VacancyText.created_at",
    )


class VacancyStep(Base):
    """One step of the recruitment procedure, with its dates."""

    __tablename__ = "vacancy_step"
    __table_args__ = (
        UniqueConstraint("vacancy_id", "kind"),
        CheckConstraint(_in("kind", StepKind), name="kind"),
        CheckConstraint(
            "ended_on IS NULL OR ended_on >= started_on", name="ends_after_start"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancy.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer)
    started_on: Mapped[date] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    vacancy: Mapped[Vacancy] = relationship(back_populates="steps")


class VacancyDecision(Base):
    """An advice or the approval on a vacancy request.

    The adviser is often someone outside this instance (HR, concern control),
    so the name is stored next to an optional reference to a person.
    """

    __tablename__ = "vacancy_decision"
    __table_args__ = (
        UniqueConstraint("vacancy_id", "kind"),
        CheckConstraint(_in("kind", DecisionKind), name="kind"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancy.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20))
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    person_name: Mapped[str] = mapped_column(String(255))
    # NULL: the adviser is known but has not decided yet.
    agreed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )

    vacancy: Mapped[Vacancy] = relationship(back_populates="decisions")


class VacancyText(Base):
    """A version of a text on a vacancy, with where it came from.

    A version is never edited: a change is a new version that points back at
    the one it was based on. That keeps the provenance: a text a person
    rewrote from a model draft still shows that a model was involved.
    Only an established version may leave grip.
    """

    __tablename__ = "vacancy_text"
    __table_args__ = (
        CheckConstraint(_in("kind", TextKind), name="kind"),
        CheckConstraint(_in("source", TextSource), name="source"),
        CheckConstraint(
            "source <> 'model' OR (model_id IS NOT NULL "
            "AND prompt_version IS NOT NULL)",
            name="model_has_provenance",
        ),
        CheckConstraint(
            "(established_at IS NULL) = (established_by_id IS NULL)",
            name="established_complete",
        ),
        Index("ix_vacancy_text_vacancy_kind", "vacancy_id", "kind", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vacancy.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10))
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    based_on_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vacancy_text.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    # ON DELETE RESTRICT: with SET NULL the pair below would break the
    # established_complete constraint when a person is removed.
    established_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="RESTRICT"),
        nullable=True,
    )
    established_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    vacancy: Mapped[Vacancy] = relationship(back_populates="texts")
    based_on: Mapped["VacancyText | None"] = relationship(
        remote_side="VacancyText.id", foreign_keys=[based_on_id]
    )

    @property
    def is_established(self) -> bool:
        return self.established_at is not None
