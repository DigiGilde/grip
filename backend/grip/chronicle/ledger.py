"""The state of a case at a moment: the fold of its chronicle.

Pure: grams go in, rows as plain values come out. No database, no clock.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from grip.chronicle.effects import Drop, Effect, Flush, Insert, Patch
from grip.chronicle.facts import FACTS, effects_of


@dataclass(frozen=True)
class Gram:
    """One recorded fact of a chronicle, as the stream holds it."""

    seq: int
    fact: str
    occurred_at: datetime
    # None once the values were erased; that it happened remains.
    fields: Mapping[str, Any] | None
    kind: str = ""
    plan_version: str | None = None
    recorded_on: str | None = None
    effective_on: str | None = None
    basis: Mapping[str, Any] | None = None
    refs: Mapping[str, Any] | None = None
    actor_kind: str | None = None
    actor_person_id: Any = None
    actor_ref: str | None = None
    origin: str | None = None
    origin_peer: str | None = None
    correlation_id: str | None = None
    # The facts that later took a typed text out of this one, oldest first: its
    # fields are what the last of them recorded (ADR 0057).
    restated_by: tuple[int, ...] = ()

    @property
    def erased(self) -> bool:
        return self.fields is None


Rows = dict[str, dict[str, dict[str, Any]]]


@dataclass
class Ledger:
    """The rows of a case as its chronicle says they are."""

    rows: Rows = field(default_factory=dict)
    # Positions of the grams whose values are gone: this state is incomplete.
    erased: list[int] = field(default_factory=list)

    def table(self, name: str) -> dict[str, dict[str, Any]]:
        return self.rows.get(name, {})

    def apply(self, effect: Effect) -> None:
        if isinstance(effect, Flush):
            return
        table = self.rows.setdefault(effect.table, {})
        if isinstance(effect, Insert):
            table[effect.id] = dict(effect.values)
        elif isinstance(effect, Patch):
            # No row: a chronicle that started later than its case, or values
            # that were erased.
            if effect.id in table:
                table[effect.id].update(effect.values)
        elif isinstance(effect, Drop):
            table.pop(effect.id, None)


def apply_gram(ledger: Ledger, gram: Gram) -> None:
    if gram.fields is None:
        ledger.erased.append(gram.seq)
        return
    for effect in effects_of(gram.fact, gram.fields):
        ledger.apply(effect)


def fold(grams: Iterable[Gram], upto: int | None = None) -> Ledger:
    """The state after the grams up to and including position ``upto``."""
    ledger = Ledger()
    for gram in sorted(grams, key=lambda item: item.seq):
        if upto is not None and gram.seq > upto:
            break
        apply_gram(ledger, gram)
    return ledger


def is_born(grams: Iterable[Gram]) -> bool:
    """Whether the chronicle starts with the creation of its case."""
    first = min(grams, key=lambda item: item.seq, default=None)
    return first is not None and FACTS[first.fact].birth


@dataclass(frozen=True)
class RowChange:
    table: str
    id: str
    # "added", "changed" or "removed".
    change: str
    # Column to (old, new).
    columns: Mapping[str, tuple[Any, Any]]


def diff(before: Ledger, after: Ledger) -> list[RowChange]:
    """What the later state says differently, row by row."""
    changes: list[RowChange] = []
    for table in sorted({*before.rows, *after.rows}):
        old_rows, new_rows = before.table(table), after.table(table)
        for row_id in sorted({*old_rows, *new_rows}):
            old, new = old_rows.get(row_id), new_rows.get(row_id)
            if old is None and new is not None:
                columns = {key: (None, value) for key, value in new.items()}
                changes.append(RowChange(table, row_id, "added", columns))
            elif new is None and old is not None:
                columns = {key: (value, None) for key, value in old.items()}
                changes.append(RowChange(table, row_id, "removed", columns))
            elif old is not None and new is not None:
                columns = {
                    key: (old.get(key), new.get(key))
                    for key in {*old, *new}
                    if old.get(key) != new.get(key)
                }
                if columns:
                    changes.append(RowChange(table, row_id, "changed", columns))
    return changes
