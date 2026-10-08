import uuid
from datetime import datetime

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk


class Organisation(Base):
    """A counterparty: the client or contractor of an assignment.

    Identified by the TOOI URI of the nearest registered organisation plus an
    own key for a unit that is not registered itself. Two units of the same
    registered organisation therefore share a TOOI URI and differ in key.
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
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    tooi_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Base URI of the grip instance of this organisation, when it has one.
    instance_uri: Mapped[str | None] = mapped_column(
        String(500), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
