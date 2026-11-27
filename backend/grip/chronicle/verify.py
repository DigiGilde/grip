"""Whether the read models say what the chronicle says, and putting it right.

``differences`` compares the fold of a chronicle with the rows, reading the
tables past whatever the session holds. ``rebuild`` writes the fold back: the
proof that the tables are derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.chronicle.facts import (
    ACCEPTANCE,
    APPROVAL,
    ASSIGNMENT,
    INVITATION,
    LINE,
    OFFER,
    QUOTE,
    READ_MODELS,
    REJECTION,
    ROLE,
)
from grip.chronicle.ledger import Ledger, fold, is_born
from grip.chronicle.writer import (
    BLESSED,
    MODELS,
    NOT_IN_A_FACT,
    columns_of,
    normal,
    record_without_rows,
    typed,
)
from grip.events.stream import ACT_OPEN
from grip.models.assignment import ROLE_OWNER
from grip.models.person import Person
from grip.models.quote import Quote
from grip.repositories.chronicle import ChronicleRepository

# Changes when the catalogue renames a role, in the database, outside any
# chronicle. The reference is compared; the name in a fact is the name then.
_NOT_COMPARED: dict[str, frozenset[str]] = {LINE: frozenset({"role"})}
# In the order a rebuild writes them: what is referred to comes first.
_ORDER = (
    ASSIGNMENT,
    ROLE,
    LINE,
    QUOTE,
    INVITATION,
    OFFER,
    APPROVAL,
    ACCEPTANCE,
    REJECTION,
)
_BY_ASSIGNMENT = frozenset({ROLE, LINE, QUOTE})


@dataclass(frozen=True)
class Difference:
    table: str
    row_id: str
    column: str | None
    chronicle: Any
    row: Any

    def __str__(self) -> str:
        where = f"{self.table}/{self.row_id}"
        if self.column is None:
            return f"{where}: de kroniek zegt {self.chronicle}, de tabel {self.row}"
        return (
            f"{where}.{self.column}: de kroniek zegt {self.chronicle!r}, "
            f"de tabel {self.row!r}"
        )


@dataclass
class Report:
    # False when this chronicle says nothing about all of its rows.
    checked: bool
    reason: str | None = None
    differences: list[Difference] = field(default_factory=list)


def _attrs(table: str) -> list[str]:
    skip = _NOT_COMPARED.get(table, frozenset())
    return [key for key in columns_of(MODELS[table]) if key not in skip]


def _person_attrs(table: str) -> list[str]:
    """Columns that point at a person: the database empties them on removal."""
    mapper = sa_inspect(MODELS[table])
    return [
        attr.key
        for attr in mapper.column_attrs
        if attr.key not in NOT_IN_A_FACT
        and any(
            key.column.table.name == Person.__tablename__
            for key in attr.columns[0].foreign_keys
        )
    ]


async def _rows_of(
    session: AsyncSession, table: str, assignment_id: UUID
) -> dict[str, dict[str, Any]]:
    """The rows of a case as the database holds them, not as the session does."""
    model = MODELS[table]
    mapper = sa_inspect(model)
    columns = {attr.key: attr.columns[0] for attr in mapper.column_attrs}
    query = select(*(column.label(key) for key, column in columns.items()))
    if table == ASSIGNMENT:
        query = query.where(columns["id"] == assignment_id)
    elif table in _BY_ASSIGNMENT:
        query = query.where(columns["assignment_id"] == assignment_id)
    else:
        query = query.where(
            columns["quote_id"].in_(
                select(Quote.id).where(Quote.assignment_id == assignment_id)
            )
        )
    rows = await session.execute(query)
    return {
        str(row.id): {
            key: normal(model, key, getattr(row, key)) for key in columns_of(model)
        }
        for row in rows
    }


async def _people_present(session: AsyncSession, ledger: Ledger) -> set[str]:
    wanted: set[str] = set()
    for table in READ_MODELS:
        attrs = _person_attrs(table)
        for row in ledger.table(table).values():
            wanted.update(str(row[key]) for key in attrs if row.get(key))
    if not wanted:
        return set()
    found = await session.execute(
        select(Person.id).where(Person.id.in_([UUID(value) for value in wanted]))
    )
    return {str(row[0]) for row in found}


def _as_the_database_keeps_it(
    table: str, row: dict[str, Any], present: set[str]
) -> dict[str, Any] | None:
    """A person who left the instance empties references, and ends a role."""
    kept = dict(row)
    for key in _person_attrs(table):
        if kept.get(key) and str(kept[key]) not in present:
            if table == ROLE:
                return None
            kept[key] = None
    return kept


async def _expected(session: AsyncSession, ledger: Ledger) -> dict[str, dict[str, Any]]:
    present = await _people_present(session, ledger)
    result: dict[str, dict[str, Any]] = {}
    for table in READ_MODELS:
        result[table] = {}
        for row_id, row in ledger.table(table).items():
            kept = _as_the_database_keeps_it(table, row, present)
            if kept is not None:
                result[table][row_id] = kept
    return result


async def differences(session: AsyncSession, assignment_id: UUID) -> Report:
    """Where the rows of a case differ from the fold of its chronicle."""
    grams = await ChronicleRepository(session).grams(assignment_id)
    if not grams:
        return Report(False, "geen kroniek")
    if not is_born(grams):
        return Report(False, "de kroniek begint later dan de opdracht")
    ledger = fold(grams)
    if ledger.erased:
        return Report(False, "er zijn waarden gewist")
    actual = {
        table: await _rows_of(session, table, assignment_id) for table in READ_MODELS
    }
    if not actual[ASSIGNMENT]:
        return Report(False, "de opdracht zelf is weg")
    expected = await _expected(session, ledger)
    found: list[Difference] = []
    for table in READ_MODELS:
        attrs = _attrs(table)
        for row_id in sorted({*expected[table], *actual[table]}):
            want, have = expected[table].get(row_id), actual[table].get(row_id)
            if want is None:
                found.append(Difference(table, row_id, None, "geen rij", "een rij"))
            elif have is None:
                found.append(Difference(table, row_id, None, "een rij", "geen rij"))
            else:
                # A column added after a fact says nothing about what it holds.
                found.extend(
                    Difference(table, row_id, key, want[key], have.get(key))
                    for key in attrs
                    if key in want and want[key] != have.get(key)
                )
    return Report(True, None, found)


def _bless(session: AsyncSession, row: Any) -> None:
    session.sync_session.info.setdefault(BLESSED, set()).add(id(row))


async def rebuild(session: AsyncSession, assignment_id: UUID) -> int:
    """Write the fold of the chronicle back to the rows. Returns what it changed.

    A line is written by its reference to the catalogue: the name in a fact
    is the name at that moment, and writing an old name would make a new role.
    """
    report = await differences(session, assignment_id)
    if not report.checked:
        raise ValueError(f"Deze opdracht is niet te herstellen: {report.reason}.")
    if not report.differences:
        return 0
    ledger = fold(await ChronicleRepository(session).grams(assignment_id))
    expected = await _expected(session, ledger)
    touched = {(item.table, item.row_id) for item in report.differences}
    # The fact comes first, so nothing flushes as a change without an event.
    record_without_rows(
        session,
        "chronicle_rebuilt",
        subject_id=assignment_id,
        assignment_id=assignment_id,
        fields={"differences": len(report.differences)},
    )
    info = session.sync_session.info
    info[ACT_OPEN] = True
    for table in _ORDER:
        model = MODELS[table]
        # One owner per assignment: each read below flushes the row before it,
        # so the old owner steps down before the new one steps up.
        in_order = sorted(
            expected[table].items(),
            key=lambda item: table == ROLE and item[1].get("role") == ROLE_OWNER,
        )
        for row_id, values in in_order:
            if (table, row_id) not in touched:
                continue
            row = await session.get(model, UUID(row_id), populate_existing=True)
            wanted = {
                key: typed(model, key, value)
                for key, value in values.items()
                if key not in _NOT_COMPARED.get(table, ())
            }
            if row is None:
                row = model(**wanted)
                _bless(session, row)
                session.add(row)
            else:
                _bless(session, row)
                for key, value in wanted.items():
                    if getattr(row, key) != value:
                        setattr(row, key, value)
        await session.flush()
    for table in reversed(_ORDER):
        for row_id in {
            item.row_id
            for item in report.differences
            if item.table == table and item.row_id not in expected[table]
        }:
            row = await session.get(MODELS[table], UUID(row_id), populate_existing=True)
            if row is not None:
                _bless(session, row)
                await session.delete(row)
        await session.flush()
    info.pop(ACT_OPEN, None)
    info.pop(BLESSED, None)
    return len(report.differences)
