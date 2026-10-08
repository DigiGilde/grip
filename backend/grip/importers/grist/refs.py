"""Where a row of a Grist document ended up in grip.

The domain tables have no place for an external id, so the import keeps its
own table: one row per Grist row and per entity made from it. A rerun finds
the entity again and updates it instead of creating a second one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base


class GristImportRef(Base):
    __tablename__ = "grist_import_ref"
    __table_args__ = (
        UniqueConstraint(
            "document_key",
            "grist_table",
            "grist_row_id",
            "entity",
            name="uq_grist_import_ref_source",
        ),
    )

    # The column helpers of grip.models are not used here: importing that
    # package from a module it imports itself would be circular.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    # Names the Grist document, so two documents can be imported side by side.
    document_key: Mapped[str] = mapped_column(String(100))
    grist_table: Mapped[str] = mapped_column(String(100))
    grist_row_id: Mapped[int] = mapped_column(Integer)
    # What was made from the row: one Team row gives a person and a scale.
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RefIndex:
    """The references of one document, loaded once and kept up to date."""

    def __init__(self, session: AsyncSession, document_key: str) -> None:
        self._session = session
        self.document_key = document_key
        self._refs: dict[tuple[str, int, str], GristImportRef] = {}
        self._seen: set[tuple[str, int, str]] = set()

    async def load(self) -> None:
        rows = await self._session.scalars(
            select(GristImportRef).where(
                GristImportRef.document_key == self.document_key
            )
        )
        self._refs = {(r.grist_table, r.grist_row_id, r.entity): r for r in rows}

    def get(self, table: str, row_id: int, entity: str) -> uuid.UUID | None:
        key = (table, row_id, entity)
        self._seen.add(key)
        ref = self._refs.get(key)
        return ref.entity_id if ref else None

    async def put(
        self, table: str, row_id: int, entity: str, entity_id: uuid.UUID
    ) -> None:
        key = (table, row_id, entity)
        self._seen.add(key)
        ref = self._refs.get(key)
        if ref is None:
            ref = GristImportRef(
                document_key=self.document_key,
                grist_table=table,
                grist_row_id=row_id,
                entity=entity,
                entity_id=entity_id,
            )
            self._session.add(ref)
            self._refs[key] = ref
        elif ref.entity_id != entity_id:
            ref.entity_id = entity_id
        await self._session.flush()

    def unseen(self) -> list[tuple[str, int, str, uuid.UUID]]:
        """References from an earlier run whose Grist row was not read now."""
        return sorted(
            (table, row_id, entity, ref.entity_id)
            for (table, row_id, entity), ref in self._refs.items()
            if (table, row_id, entity) not in self._seen
        )
