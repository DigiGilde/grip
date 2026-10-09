"""Settings of an instance that the organisation itself changes.

Business rules that differ per organisation and change over time live here,
in the database, where the beheerder edits them and every change leaves an
audit row. What an operator sets once at deployment (addresses, secrets)
stays in the environment.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import EditCounted


class InstanceSetting(EditCounted, Base):
    """One setting: a key and its JSON value. A key that has no row has its default."""

    __tablename__ = "instance_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
