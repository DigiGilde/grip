"""Taking a typed text that never belonged out of a chronicle (ADR 0057).

The database erases every value of an event or none, so a text goes with the
whole fact that holds it. A herstelfeit (``fact_restated``) records that fact
again without the text; when a chronicle is read, it takes the place of the fact
it restates, so every stand stays whole. This module says where typed text
stands in a fact, writes a fact without it, and puts a herstelfeit in the place
of what it restates. Pure: no database, no clock.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from grip.chronicle.effects import Drop, Insert, Patch
from grip.chronicle.facts import ASSIGNMENT, LINE, effects_of
from grip.chronicle.ledger import Gram

RESTATED = "fact_restated"
# What a column that may not be empty holds once its text is gone.
PLACEHOLDER = "Tekst verwijderd"
# A shorter text goes only where it is the whole value: inside a longer value
# it is too likely a coincidence ("Ja" in "Jaarplan").
MIN_EMBEDDED = 8


@dataclass(frozen=True)
class TypedText:
    """Text someone typed that a fact carries and a stand shows."""

    key: str
    label: str
    # The read model it stands in, or None for words only the fact holds.
    table: str | None
    column: str
    # A column that may not be empty keeps the placeholder instead.
    required: bool = False


# The texts a herstelfeit can take out. A name, an address or a note that stands
# only in its row is no part of a fact (``ROW_ONLY_COLUMNS``).
TYPED_TEXTS: tuple[TypedText, ...] = (
    TypedText("assignment.name", "Naam", ASSIGNMENT, "name", required=True),
    TypedText("assignment.notes", "Notities", ASSIGNMENT, "notes"),
    TypedText(
        "assignment.verbal_agreement_note",
        "Mondeling akkoord",
        ASSIGNMENT,
        "verbal_agreement_note",
    ),
    TypedText("budget_line.detail", "Omschrijving", LINE, "detail", required=True),
    # Given with a change of status or a corrected date; shown under the moment.
    TypedText("reason", "Reden", None, "reason"),
)
BY_KEY: dict[str, TypedText] = {text.key: text for text in TYPED_TEXTS}
TEXT_COLUMNS: dict[str, dict[str, TypedText]] = {
    table: {text.column: text for text in TYPED_TEXTS if text.table == table}
    for table in (ASSIGNMENT, LINE)
}

# Where a fact holds columns of a row: the part of its fields (None for the
# fields themselves) and the table.
_ROWS: dict[str, tuple[tuple[str | None, str], ...]] = {
    "assignment_created": (("assignment", ASSIGNMENT),),
    "assignment_requested": (("assignment", ASSIGNMENT),),
    "assignment_request_received": (("assignment", ASSIGNMENT),),
    "assignment_changed": (("changes", ASSIGNMENT),),
    "assignment_status_changed": ((None, ASSIGNMENT),),
    "budget_line_added": (("line", LINE),),
    "budget_line_changed": (("changes", LINE),),
}
# Words only the fact holds.
_OWN: dict[str, tuple[str, ...]] = {
    "assignment_status_changed": ("reason",),
    "acceptance_date_corrected": ("reason",),
}
# The name of a line as it was shown is its role and its detail.
_LINE_NAMES = frozenset({"budget_line_changed", "budget_line_removed"})

Path = tuple[str | int, ...]


@dataclass(frozen=True)
class Place:
    """Where in the fields of a fact a typed text stands."""

    path: Path
    text: TypedText
    # A moment offers it to take out; elsewhere it is part of another value.
    offered: bool = True
    # Holds the placeholder instead of nothing once the text is gone.
    required: bool = False

    @property
    def dotted(self) -> str:
        return ".".join(str(step) for step in self.path)


def _inner(place: Place, *prefix: str | int) -> Place:
    return replace(place, path=(*prefix, *place.path), offered=False)


def places(fact: str, fields: Mapping[str, Any] | None) -> list[Place]:
    """Every place in the fields of this fact where typed text stands.

    A herstelfeit holds the fact it restates, and the values it wrote to rows.
    """
    if not fields:
        return []
    if fact == RESTATED:
        found = [
            _inner(place, "fields")
            for place in places(str(fields.get("fact")), fields.get("fields"))
        ]
        for index, patch in enumerate(fields.get("patches") or ()):
            columns = TEXT_COLUMNS.get(patch.get("table"), {})
            for column in patch.get("values") or {}:
                if column in columns:
                    text = columns[column]
                    found.append(
                        Place(
                            ("patches", index, "values", column),
                            text,
                            offered=False,
                            required=text.required,
                        )
                    )
        return found
    found = []
    for part, table in _ROWS.get(fact, ()):
        holder = fields if part is None else fields.get(part)
        if not isinstance(holder, Mapping):
            continue
        for column, text in TEXT_COLUMNS[table].items():
            if column in holder:
                path: Path = (column,) if part is None else (part, column)
                found.append(Place(path, text, required=text.required))
    found += [
        Place((name,), BY_KEY[name]) for name in _OWN.get(fact, ()) if name in fields
    ]
    if fact in _LINE_NAMES and "name" in fields:
        found.append(Place(("name",), BY_KEY["budget_line.detail"], offered=False))
    return found


def _at(fields: Mapping[str, Any], path: Path) -> Any:
    value: Any = fields
    for step in path:
        value = value[step]
    return value


def _put(fields: dict[str, Any], path: Path, value: Any) -> None:
    holder: Any = fields
    for step in path[:-1]:
        holder = holder[step]
    holder[path[-1]] = value


def _thawed(value: Any) -> Any:
    """A copy of plain values that can be changed in place."""
    if isinstance(value, Mapping):
        return {key: _thawed(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_thawed(item) for item in value]
    return value


def wanted(texts: Iterable[str]) -> list[str]:
    """The texts to look for, the longest first: one can hold another."""
    return sorted(
        {text.strip() for text in texts if text.strip()}, key=len, reverse=True
    )


def removable(
    fact: str, fields: Mapping[str, Any] | None
) -> list[tuple[TypedText, str]]:
    """The typed texts of a moment that can be taken out of it, once each."""
    offered = sorted(
        (
            (place.text, value)
            for place in places(fact, fields)
            if place.offered
            and isinstance(value := _at(fields or {}, place.path), str)
            and value.strip()
            and value.strip() != PLACEHOLDER
        ),
        key=lambda item: TYPED_TEXTS.index(item[0]),
    )
    found: dict[str, tuple[TypedText, str]] = {}
    for text, value in offered:
        # A verbal agreement holds its note twice: as the note and as the reason.
        found.setdefault(value.strip(), (text, value))
    return list(found.values())


def _embedded(text: str) -> re.Pattern[str] | None:
    """The text as a whole word or phrase inside a longer value, when it is long
    enough to look for there."""
    if len(text) < MIN_EMBEDDED:
        return None
    return re.compile(rf"(?<!\w){re.escape(text)}(?!\w)")


def _in(value: str, texts: Sequence[str]) -> bool:
    for text in texts:
        pattern = _embedded(text)
        if value.strip() == text or (pattern is not None and pattern.search(value)):
            return True
    return False


def _taken_out(value: str, texts: Sequence[str], *, required: bool) -> str | None:
    if value.strip() in texts:
        return PLACEHOLDER if required else None
    for text in texts:
        pattern = _embedded(text)
        if pattern is not None:
            value = pattern.sub(PLACEHOLDER, value)
    return value


def holds(fact: str, fields: Mapping[str, Any] | None, texts: Sequence[str]) -> bool:
    """Whether one of the texts stands in a place of typed text of this fact."""
    for place in places(fact, fields):
        value = _at(fields or {}, place.path)
        if isinstance(value, str) and _in(value, texts):
            return True
    return False


def without(
    fact: str, fields: Mapping[str, Any], texts: Sequence[str]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """The fields of a fact without the texts, and where they stood, by label."""
    result: dict[str, Any] = _thawed(fields)
    removed = []
    for place in places(fact, result):
        value = _at(result, place.path)
        if not isinstance(value, str):
            continue
        kept = _taken_out(value, texts, required=place.required)
        if kept != value:
            _put(result, place.path, kept)
            removed.append({"path": place.dotted, "label": place.text.label})
    return result, removed


def contains(value: Any, texts: Sequence[str]) -> bool:
    """Whether one of the texts stands anywhere in these values."""
    if isinstance(value, str):
        return _in(value, texts)
    if isinstance(value, Mapping):
        return any(contains(item, texts) for item in value.values())
    if isinstance(value, list | tuple):
        return any(contains(item, texts) for item in value)
    return False


# What a herstelfeit keeps of the fact it restates, next to its fields: the
# erased fact holds none of it any more.
_RECORDED = ("kind", "plan_version", "recorded_on", "effective_on", "basis")


def _in_place_of(gram: Gram, herstel: Gram) -> Gram:
    fields = herstel.fields or {}
    return replace(
        gram,
        fields=fields["fields"],
        kind=fields.get("kind") or gram.kind,
        plan_version=fields.get("plan_version"),
        recorded_on=fields.get("recorded_on"),
        effective_on=fields.get("effective_on"),
        basis=fields.get("basis"),
        restated_by=(herstel.seq, *herstel.restated_by),
    )


def substituted(grams: Iterable[Gram], restating: Iterable[Gram] = ()) -> list[Gram]:
    """The grams with each erased fact read as the herstelfeit that restated it.

    ``restating`` holds the herstelfeiten wherever they stand, also beyond the
    last of the grams: a stand before one is whole too. A herstelfeit that was
    erased in turn reads as the one that restated it; the latest one wins.
    """
    grams = list(grams)
    if not any(gram.erased for gram in grams):
        return grams
    herstel = {gram.seq: gram for gram in (*restating, *grams) if gram.fact == RESTATED}
    by_target: dict[int, Gram] = {}
    # The latest first: what restates a herstelfeit always comes after it.
    for seq in sorted(herstel, reverse=True):
        gram = herstel[seq]
        if gram.erased and seq in by_target:
            gram = _in_place_of(gram, by_target[seq])
        if gram.fields is not None:
            by_target.setdefault(int(gram.fields["restates"]), gram)
    return [
        _in_place_of(gram, by_target[gram.seq])
        if gram.erased and gram.seq in by_target
        else gram
        for gram in grams
    ]


Cell = tuple[str, str, str]


def written(grams: Iterable[Gram]) -> dict[Cell, Any]:
    """The last value the chronicle wrote to each typed text of a row.

    A row the chronicle did not make (a case it starts later than) counts too:
    what a fact wrote there is what the row holds.
    """
    cells: dict[Cell, Any] = {}
    for gram in sorted(grams, key=lambda item: item.seq):
        if gram.fields is None:
            continue
        for effect in effects_of(gram.fact, gram.fields):
            if isinstance(effect, Insert | Patch):
                for column in TEXT_COLUMNS.get(effect.table, {}):
                    if column in effect.values:
                        cells[effect.table, effect.id, column] = effect.values[column]
            elif isinstance(effect, Drop):
                for cell in [c for c in cells if c[:2] == (effect.table, effect.id)]:
                    del cells[cell]
    return cells


def patches(
    before: Mapping[Cell, Any], after: Mapping[Cell, Any]
) -> list[dict[str, Any]]:
    """What the rows need to say what the chronicle says now, row by row."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for cell, value in after.items():
        if cell in before and before[cell] != value:
            rows.setdefault(cell[:2], {})[cell[2]] = value
    return [
        {"table": table, "id": row_id, "values": values}
        for (table, row_id), values in sorted(rows.items())
    ]


def plan(
    grams: Sequence[Gram], texts: Sequence[str], *, assignment_id: str
) -> list[tuple[Gram, dict[str, Any]]]:
    """The herstelfeiten that take the texts out of a chronicle, in order.

    ``grams`` is the chronicle as the stream holds it. Every fact that holds one
    of the texts is restated, a herstelfeit too, so the texts go everywhere at
    once. Each carries the patches that its own restatement asks of the rows.
    Returns the fact each one restates with its fields.
    """
    texts = wanted(texts)
    holders = [
        gram
        for gram in sorted(grams, key=lambda item: item.seq)
        if not gram.erased and holds(gram.fact, gram.fields, texts)
    ]
    chronicle = list(grams)
    before = written(substituted(chronicle))
    seq = max((gram.seq for gram in chronicle), default=0)
    planned = []
    for holder in holders:
        restated, removed = without(holder.fact, holder.fields or {}, texts)
        fields: dict[str, Any] = {
            "assignment_id": assignment_id,
            "restates": holder.seq,
            "fact": holder.fact,
            **{key: getattr(holder, key) for key in _RECORDED},
            "fields": restated,
            "removed": removed,
            "patches": [],
        }
        seq += 1
        chronicle = [
            replace(gram, fields=None) if gram.seq == holder.seq else gram
            for gram in chronicle
        ]
        chronicle.append(Gram(seq, RESTATED, holder.occurred_at, fields))
        after = written(substituted(chronicle))
        fields["patches"] = patches(before, after)
        before = after
        planned.append((holder, fields))
    return planned
