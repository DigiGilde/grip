"""What a fact does to the rows, as plain data.

An effect names a table, a row and plain JSON values. It holds no database
objects, so the same effects drive the projection into the tables and the
fold of a chronicle in memory.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class Insert:
    table: str
    id: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class Patch:
    table: str
    id: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class Drop:
    table: str
    id: str


@dataclass(frozen=True)
class Flush:
    """What came before must reach the database first.

    The unit of work orders rows by relationship and by primary key, not by
    the order of the effects. A foreign key without a relationship, or a
    unique index that holds only after an earlier update, needs this barrier.
    Means nothing in a fold.
    """


Effect = Insert | Patch | Drop | Flush


def moment_text(value: datetime) -> str:
    """One text for one instant, whatever offset it came with."""
    if value.tzinfo is None:
        raise ValueError(f"a moment in a fact needs a time zone: {value!r}")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def decimal_text(value: Decimal) -> str:
    """Exact, without an exponent or trailing zeros."""
    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text


def plain(value: Any) -> Any:
    """The value as a fact holds it. Refuses what it has no one form for.

    A float passes for what a peer sent in a JSON column; ``writer.normal``
    keeps it out of every other column.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, datetime):
        return moment_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [plain(item) for item in value]
    raise TypeError(f"a fact holds no value of type {type(value).__name__}")
