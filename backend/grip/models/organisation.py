import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import EditCounted, created_at, updated_at, uuid_pk

SOURCE_REGISTRY = "registry"
SOURCE_MANUAL = "manual"
ORGANISATION_SOURCES = (SOURCE_REGISTRY, SOURCE_MANUAL)


class Organisation(EditCounted, Base):
    """A counterparty: the client or contractor of an assignment.

    Two kinds of rows live here.

    - ``registry``: a government organisation taken over from the public
      register (organisaties.overheid.nl). Its descriptive fields follow the
      register and are not edited by hand. Identified by the TOOI URI, or by
      the register's own id for the parts of an organisation that have none.
    - ``manual``: a party the register does not hold (a foundation, a
      company), or a unit below a registered organisation (a guild, a team).
      A unit carries the TOOI URI of the nearest registered organisation
      above it plus an own key, so two units of the same organisation share
      a TOOI URI and differ in key.

    ``instance_uri`` belongs to grip in both kinds: the base URI of the grip
    instance of that organisation, when it has one.
    """

    __tablename__ = "organisation"
    __table_args__ = (
        Index(
            "uq_organisation_tooi_uri_unit_key",
            "tooi_uri",
            "unit_key",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("tooi_uri IS NOT NULL"),
        ),
        Index(
            "uq_organisation_registry_id",
            "registry_id",
            unique=True,
            postgresql_where=text("registry_id IS NOT NULL"),
        ),
        CheckConstraint("source IN ('registry', 'manual')", name="source_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    # The name to show: the register writes a ministry as "Financiën", the
    # label is "Ministerie van Financiën".
    label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    tooi_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Base URI of the grip instance of this organisation, when it has one.
    instance_uri: Mapped[str | None] = mapped_column(
        String(500), nullable=True, unique=True
    )
    source: Mapped[str] = mapped_column(
        String(10), default=SOURCE_MANUAL, server_default=SOURCE_MANUAL, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisation.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # First in the list is the main abbreviation.
    abbreviations: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    # Type names as the register gives them; the first is the main type.
    organisation_types: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    main_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    # TOOI URI of the ministry the register relates this organisation to.
    related_ministry_tooi: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    # The register's own id (systeemId): the key for parts without a TOOI URI.
    registry_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Public page of the organisation in the register.
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Day on which the organisation ceased to exist, or left the register.
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    parent: Mapped["Organisation | None"] = relationship(
        remote_side="Organisation.id", foreign_keys=[parent_id]
    )

    @property
    def display_name(self) -> str:
        return self.label or self.name

    @property
    def abbreviation(self) -> str | None:
        return self.abbreviations[0] if self.abbreviations else None


class OrganisationSyncRun(Base):
    """One run of the sync with the public register, with what it changed."""

    __tablename__ = "organisation_sync_run"
    __table_args__ = (
        CheckConstraint("status IN ('completed', 'failed')", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(10))
    source_url: Mapped[str] = mapped_column(String(500))
    # Counts per outcome; empty for a failed run.
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
