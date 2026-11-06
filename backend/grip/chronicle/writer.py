"""The one way a fact enters the chronicle and the read models.

``establish`` writes the rows a fact says and the fact itself. Guards are the
caller's business and come first; audit rows and domain events come after, so
whatever reacts to them finds the rows.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, LargeBinary, Numeric, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError

from grip.chronicle.effects import (
    Drop,
    Effect,
    Flush,
    Insert,
    Patch,
    decimal_text,
    moment_text,
    plain,
)
from grip.chronicle.facts import FACTS, effects_of
from grip.core import clock
from grip.events import stream
from grip.models.assignment import Assignment, AssignmentRole, BudgetLine
from grip.models.person import Person
from grip.models.quote import (
    Quote,
    QuoteAcceptance,
    QuoteApproval,
    QuoteInvitation,
    QuoteOffer,
    QuoteRejection,
)
from grip.models.task import TaskCase

# The subject kind of the rows of a chronicle in the stream.
SUBJECT_KIND = "chronolexogram"
# The chronicle of the rate book, next to one per assignment.
RATE_BOOK = "rate_book"

MODELS: dict[str, type] = {
    model.__tablename__: model
    for model in (
        Assignment,
        AssignmentRole,
        BudgetLine,
        Quote,
        QuoteInvitation,
        QuoteOffer,
        QuoteApproval,
        QuoteAcceptance,
        QuoteRejection,
    )
}

# Counters and moments the database keeps: no part of what a fact says.
NOT_IN_A_FACT = frozenset({"version", "updated_at", "created_at"})

# Rows written by ``establish`` since the last flush, for the guard in tests.
BLESSED = "grip_chronicle_blessed"


def event_type(fact: str) -> str:
    return f"{SUBJECT_KIND}.{fact}"


def fact_of(event_type_name: str) -> str:
    return event_type_name.split(".", 1)[1]


def _column(model: type, key: str) -> Any:
    return sa_inspect(model).column_attrs[key].columns[0]


def normal(model: type, key: str, value: Any) -> Any:
    """The one plain form of a value in this column.

    What the fold holds and what the row reads must be the same text, so a
    value is cut to what the column keeps before it enters a fact.
    """
    if value is None:
        return None
    kind = _column(model, key).type
    if isinstance(value, float) and not isinstance(kind, JSONB):
        # A float never holds an amount or an FTE here; refusing it keeps it so.
        raise TypeError(f"{model.__name__}.{key} holds no value of type float")
    if isinstance(kind, PG_UUID):
        return str(UUID(str(value)))
    if isinstance(kind, DateTime):
        moment = datetime.fromisoformat(value) if isinstance(value, str) else value
        return moment_text(moment)
    if isinstance(kind, Date):
        return value if isinstance(value, str) else value.isoformat()
    if isinstance(kind, Numeric):
        number = Decimal(str(value))
        if kind.scale is not None:
            number = number.quantize(
                Decimal(1).scaleb(-kind.scale), rounding=ROUND_HALF_UP
            )
        return decimal_text(number)
    if isinstance(kind, LargeBinary):
        return value if isinstance(value, str) else plain(value)
    return plain(value)


def typed(model: type, key: str, value: Any) -> Any:
    """A plain value as the column of this attribute holds it."""
    if value is None:
        return None
    kind = _column(model, key).type
    if isinstance(kind, PG_UUID):
        return UUID(str(value))
    if isinstance(kind, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(kind, Date):
        return date.fromisoformat(value)
    if isinstance(kind, Numeric):
        return Decimal(str(value))
    if isinstance(kind, LargeBinary):
        return base64.b64decode(value)
    return value


def columns_of(model: type) -> list[str]:
    """The attributes a fact says something about."""
    return [
        attr.key
        for attr in sa_inspect(model).column_attrs
        if attr.key not in NOT_IN_A_FACT
    ]


def default_of(model: type, key: str) -> Any:
    """What a column holds when a fact says nothing about it, in its plain form:
    its scalar default, or None."""
    default = _column(model, key).default
    if default is not None and default.is_scalar:
        return normal(model, key, default.arg)
    return None


def row_of(model: type, **values: Any) -> dict[str, Any]:
    """A whole row as a fact holds it. A column left out gets its default."""
    known = set(columns_of(model))
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"{model.__name__} has no column {sorted(unknown)}")
    row: dict[str, Any] = {}
    for key in known:
        if key in values:
            row[key] = normal(model, key, values[key])
            continue
        row[key] = default_of(model, key)
        if row[key] is None and not _column(model, key).nullable:
            raise ValueError(f"a new {model.__name__} needs a value for {key}")
    return row


def changes_of(model: type, **values: Any) -> dict[str, Any]:
    """Some columns of a row as a fact holds them."""
    return {key: normal(model, key, value) for key, value in values.items()}


def check_effect(effect: Effect) -> None:
    """A fact must say a whole new row, and in the form the row reads."""
    if isinstance(effect, (Flush, Drop)):
        return
    model = MODELS[effect.table]
    if isinstance(effect, Insert):
        missing = set(columns_of(model)) - set(effect.values)
        if missing:
            raise ValueError(f"{effect.table}: a new row lacks {sorted(missing)}")
    for key, value in effect.values.items():
        if normal(model, key, value) != value:
            raise ValueError(f"{effect.table}.{key}: {value!r} is not in its form")


def _bless(session: AsyncSession, row: Any) -> None:
    session.sync_session.info.setdefault(BLESSED, set()).add(id(row))


@dataclass
class Established:
    """A fact that was just recorded, with the rows it wrote."""

    event: Any
    _rows: dict[tuple[str, str], Any] = field(default_factory=dict)

    def row(self, table: str, row_id: UUID | str) -> Any:
        return self._rows[table, str(row_id)]


async def plan_version_of(session: AsyncSession, assignment_id: UUID) -> str:
    """The version of the plan this case runs on, as the engine remembers it."""
    # Imported here: the plan module reads files that nothing else on the
    # write path needs.
    from grip.tasks.plan import current_plan

    version = await session.scalar(
        select(TaskCase.plan_version).where(
            TaskCase.case_kind == "assignment", TaskCase.case_id == assignment_id
        )
    )
    return version or current_plan().version


async def _in_hand(
    session: AsyncSession, effects: tuple[Effect, ...]
) -> dict[tuple[str, str], Any]:
    """The rows the effects name, once everything recorded earlier is committed.

    Read first: a read flushes what is pending. A row lock reads past what the
    session holds, so a row with a version counter that moved since this
    request read it raises StaleDataError here, and so does a row that is gone.
    An empty Patch decides nothing about its row and is not refused for moving.
    """
    held: dict[tuple[str, str], Any] = {}
    if any(isinstance(effect, (Patch, Drop)) for effect in effects):
        await stream.hold_head(session)
    for effect in effects:
        if isinstance(effect, (Patch, Drop)):
            says_something = isinstance(effect, Drop) or bool(effect.values)
            row = await session.get(
                MODELS[effect.table],
                UUID(effect.id),
                with_for_update={"key_share": True} if says_something else None,
            )
            if row is None:
                raise StaleDataError(
                    f"a fact names a row that is gone: {effect.table}/{effect.id}"
                )
            held[effect.table, effect.id] = row
    return held


async def _write(
    session: AsyncSession,
    effects: tuple[Effect, ...],
    held: dict[tuple[str, str], Any],
) -> Established:
    """Apply the effects in order. ``Flush`` keeps what came before it first."""
    written = Established(event=None)
    with session.no_autoflush:
        for effect in effects:
            if isinstance(effect, Flush):
                await session.flush()
            elif isinstance(effect, Insert):
                model = MODELS[effect.table]
                row = model(**{k: typed(model, k, v) for k, v in effect.values.items()})
                _bless(session, row)
                session.add(row)
                written._rows[effect.table, effect.id] = row
            elif isinstance(effect, Patch):
                model = MODELS[effect.table]
                row = held[effect.table, effect.id]
                _bless(session, row)
                # A row without a version counter may have moved since this
                # session read it, and a value equal to that read sends no
                # UPDATE while the fact still says it.
                unversioned = sa_inspect(model).version_id_col is None
                for key, value in effect.values.items():
                    python_value = typed(model, key, value)
                    if getattr(row, key) != python_value:
                        setattr(row, key, python_value)
                    elif unversioned:
                        flag_modified(row, key)
                written._rows[effect.table, effect.id] = row
            else:
                row = held[effect.table, effect.id]
                _bless(session, row)
                await session.delete(row)
    return written


def _gram(
    session: AsyncSession,
    fact: str,
    *,
    subject_id: UUID | str,
    assignment_id: UUID | None,
    values: Mapping[str, Any],
    plan_version: str | None,
    actor: Person | None,
    effective_on: date | None,
    basis: Mapping[str, Any] | None,
    refs: Mapping[str, Any] | None,
) -> Any:
    return stream.append(
        session,
        event_type(fact),
        subject=(SUBJECT_KIND, subject_id),
        actor_person_id=actor.id if actor is not None else None,
        assignment_id=assignment_id,
        new={
            "kind": FACTS[fact].kind_of(values),
            "plan_version": plan_version,
            "recorded_on": clock.today().isoformat(),
            "effective_on": plain(effective_on),
            "basis": plain(basis),
            "fields": values,
        },
        refs=plain(refs) if refs else None,
    )


async def establish(
    session: AsyncSession,
    fact: str,
    *,
    assignment_id: UUID,
    fields: Mapping[str, Any],
    actor: Person | None = None,
    effective_on: date | None = None,
    basis: Mapping[str, Any] | None = None,
    refs: Mapping[str, Any] | None = None,
) -> Established:
    """Record one fact in the chronicle of an assignment and write its rows.

    Everything the fact decides is in ``fields``, whole rows through
    ``row_of`` and parts through ``changes_of``. ``effective_on`` is the day
    the fact counts from when that is not the day it is recorded. ``basis``
    is the rule that was weighed, ``refs`` the hashes of evidence kept
    elsewhere.
    """
    if fact not in FACTS:
        raise ValueError(f"unknown fact: {fact}")
    values = plain(fields)
    effects = effects_of(fact, values)
    for effect in effects:
        check_effect(effect)
    plan_version = await plan_version_of(session, assignment_id)
    held = await _in_hand(session, effects)
    # The fact goes first: whichever flush comes first carries it, so nothing
    # flushes as a change without an event.
    event = _gram(
        session,
        fact,
        subject_id=assignment_id,
        assignment_id=assignment_id,
        values=values,
        plan_version=plan_version,
        actor=actor,
        effective_on=effective_on,
        basis=basis,
        refs=refs,
    )
    info = session.sync_session.info
    # A barrier splits the rows over flushes; the fact covers them all.
    info[stream.ACT_OPEN] = True
    try:
        written = await _write(session, effects, held)
        written.event = event
        await session.flush()
    finally:
        info.pop(stream.ACT_OPEN, None)
        info.pop(BLESSED, None)
    return written


def record_without_rows(
    session: AsyncSession,
    fact: str,
    *,
    subject_id: UUID | str,
    assignment_id: UUID | None,
    fields: Mapping[str, Any],
    actor: Person | None = None,
    effective_on: date | None = None,
    plan_version: str | None = None,
) -> Any:
    """A fact that writes no read model: about the chronicle, or the rate book."""
    return _gram(
        session,
        fact,
        subject_id=subject_id,
        assignment_id=assignment_id,
        values=plain(fields),
        plan_version=plan_version,
        actor=actor,
        effective_on=effective_on,
        basis=None,
        refs=None,
    )
