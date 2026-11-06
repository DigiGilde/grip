"""Reading a chronicle from the stream. No business rules here."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.chronicle.facts import (
    FACTS,
    ROW_ONLY_COLUMNS,
    row_only_parts,
    with_row_values,
)
from grip.chronicle.ledger import Gram
from grip.chronicle.writer import MODELS, RATE_BOOK, SUBJECT_KIND, fact_of, normal
from grip.models.organisation import Organisation
from grip.models.stream_event import CASE_ASSIGNMENT, StreamEvent

_COLUMNS = (
    StreamEvent.seq,
    StreamEvent.type,
    StreamEvent.occurred_at,
    StreamEvent.new_value,
    StreamEvent.refs,
    StreamEvent.actor_kind,
    StreamEvent.actor_person_id,
    StreamEvent.actor_ref,
    StreamEvent.origin,
    StreamEvent.origin_peer,
    StreamEvent.correlation_id,
    StreamEvent.erased_at,
)


def _gram(row: Any) -> Gram | None:
    fact = fact_of(row.type) if "." in row.type else row.type
    if fact not in FACTS:
        return None
    meta = row.new_value or {}
    return Gram(
        seq=row.seq,
        fact=fact,
        occurred_at=row.occurred_at,
        fields=None if row.erased_at is not None else meta.get("fields"),
        kind=meta.get("kind") or FACTS[fact].kind_of(None),
        plan_version=meta.get("plan_version"),
        recorded_on=meta.get("recorded_on"),
        effective_on=meta.get("effective_on"),
        basis=meta.get("basis"),
        refs=row.refs,
        actor_kind=row.actor_kind,
        actor_person_id=row.actor_person_id,
        actor_ref=row.actor_ref,
        origin=row.origin,
        origin_peer=row.origin_peer,
        correlation_id=row.correlation_id,
    )


class ChronicleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _grams(self, subject_id: str, upto: int | None) -> list[Gram]:
        query = select(*_COLUMNS).where(
            StreamEvent.subject_kind == SUBJECT_KIND,
            StreamEvent.subject_id == subject_id,
            # A plain change record that happens to name this kind is no fact.
            StreamEvent.action.is_(None),
        )
        if upto is not None:
            query = query.where(StreamEvent.seq <= upto)
        rows = await self.db.execute(query.order_by(StreamEvent.seq))
        return await self._with_rows(
            [gram for gram in map(_gram, rows) if gram is not None]
        )

    async def _with_rows(self, grams: list[Gram]) -> list[Gram]:
        """Put back what a fact leaves in its row, as the row holds it now."""
        wanted: dict[str, set[str]] = defaultdict(set)
        for gram in grams:
            for _part, table, row_id, _columns in row_only_parts(
                gram.fact, gram.fields
            ):
                wanted[table].add(row_id)
        held: dict[tuple[str, str], Any] = {}
        for table, ids in wanted.items():
            model = MODELS[table]
            columns = [getattr(model, name) for name in sorted(ROW_ONLY_COLUMNS[table])]
            found = await self.db.execute(
                select(model.id, *columns).where(
                    model.id.in_([UUID(row_id) for row_id in ids])
                )
            )
            held.update({(table, str(row.id)): row for row in found})

        def value(table: str, row_id: str, column: str) -> Any:
            # A row that is gone holds nothing any more.
            row = held.get((table, row_id))
            return normal(MODELS[table], column, getattr(row, column, None))

        return [
            replace(gram, fields=with_row_values(gram.fact, gram.fields, value))
            if gram.fields is not None and row_only_parts(gram.fact, gram.fields)
            else gram
            for gram in grams
        ]

    async def grams(self, assignment_id: UUID, upto: int | None = None) -> list[Gram]:
        """The facts of one assignment in the order they were recorded."""
        return await self._grams(str(assignment_id), upto)

    async def rate_grams(self, upto: int | None = None) -> list[Gram]:
        """The facts of the rate book in the order they were recorded."""
        return await self._grams(RATE_BOOK, upto)

    async def act_end(
        self,
        seq: int,
        correlation_id: str | None,
        occurred_at: datetime,
        before: int | None,
    ) -> int:
        """Where the act of the fact at ``seq`` ends: the last thing its
        transaction wrote, below the next fact of its chronicle.

        A correlation id alone can span requests: it can be a caller's trace.
        Every event of one transaction carries the same moment.
        """
        if correlation_id is None:
            return seq
        query = select(func.max(StreamEvent.seq)).where(
            StreamEvent.correlation_id == correlation_id,
            StreamEvent.occurred_at == occurred_at,
            StreamEvent.seq >= seq,
        )
        if before is not None:
            query = query.where(StreamEvent.seq < before)
        return await self.db.scalar(query) or seq

    async def changes_of_kind(
        self,
        subject_kind: str,
        upto: int,
        *,
        assignment_id: UUID | None = None,
        subject_id: str | None = None,
    ) -> Sequence[Any]:
        """Change records up to a position, oldest first."""
        query = select(
            StreamEvent.seq,
            StreamEvent.action,
            StreamEvent.subject_id,
            StreamEvent.new_value,
            StreamEvent.erased_at,
        ).where(
            StreamEvent.subject_kind == subject_kind,
            StreamEvent.action.is_not(None),
            StreamEvent.seq <= upto,
        )
        if assignment_id is not None:
            query = query.where(
                StreamEvent.case_kind == CASE_ASSIGNMENT,
                StreamEvent.case_id == assignment_id,
            )
        if subject_id is not None:
            query = query.where(StreamEvent.subject_id == subject_id)
        return (await self.db.execute(query.order_by(StreamEvent.seq))).all()

    async def organisation(self, organisation_id: UUID) -> Organisation | None:
        return await self.db.get(Organisation, organisation_id)
