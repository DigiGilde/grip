import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk

ROLE_SOURCE_WIES = "wies"
ROLE_SOURCE_MANUAL = "manual"
ROLE_SOURCES = (ROLE_SOURCE_WIES, ROLE_SOURCE_MANUAL)


class CatalogueRole(Base):
    """A role people are staffed in: "Developer", "Product owner".

    The catalogue is what a personnel budget line picks its role from, so the
    same role is the same word everywhere and can be counted. Not to be
    confused with ``Role`` (a function a person holds in this instance) or
    with the function groups of the Functiegebouw Rijk.

    Where the link with Wies is configured the catalogue is filled from the
    skills of Wies, which is what a role is called there. An instance without
    Wies keeps the catalogue by hand.
    """

    __tablename__ = "catalogue_role"
    __table_args__ = (
        # One role per name, whatever the capitals.
        Index("uq_catalogue_role_name_lower", text("lower(name)"), unique=True),
        # Target of the foreign key from budget_line (role_id, role), which
        # keeps the name on a budget line equal to the name here.
        UniqueConstraint("id", "name"),
        Index(
            "uq_catalogue_role_wies_public_id",
            "wies_public_id",
            unique=True,
            postgresql_where=text("wies_public_id IS NOT NULL"),
        ),
        CheckConstraint("source IN ('wies', 'manual')", name="source_valid"),
        CheckConstraint("btrim(name) <> ''", name="name_not_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(
        String(10), default=ROLE_SOURCE_MANUAL, server_default=ROLE_SOURCE_MANUAL
    )
    # The public id of the skill in Wies this role came from.
    wies_public_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # An inactive role stays on the lines that use it and is not offered anew.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    # Added on the spot by someone filling in a budget, or taken over from
    # free text: for the beheerder to keep, rename or merge.
    needs_review: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class CatalogueRoleSyncRun(Base):
    """One run of taking over the skills of Wies into the catalogue."""

    __tablename__ = "catalogue_role_sync_run"
    __table_args__ = (
        CheckConstraint("status IN ('completed', 'failed')", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(10))
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )


class PersonCatalogueRole(Base):
    """A role a person can be staffed in.

    From the skills of the person in Wies (source ``wies``) or set by the
    beheerder (source ``manual``). What Wies says never overwrites a role set
    by hand: a change in Wies is proposed and applied on confirmation, and it
    only ever touches the links that came from Wies.
    """

    __tablename__ = "person_catalogue_role"
    __table_args__ = (
        UniqueConstraint("person_id", "role_id"),
        CheckConstraint("source IN ('wies', 'manual')", name="source_valid"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalogue_role.id", ondelete="CASCADE"),
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(10), default=ROLE_SOURCE_MANUAL, server_default=ROLE_SOURCE_MANUAL
    )
    created_at: Mapped[datetime] = created_at()
