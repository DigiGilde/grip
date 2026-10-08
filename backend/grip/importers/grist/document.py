"""Reading a Grist document download.

A Grist document is a SQLite file. Every user table is a SQL table with the
table id as its name and the column ids as column names, plus an integer
``id`` (the row id) and ``manualSort``. Two metadata tables describe them:
``_grist_Tables`` (``id``, ``tableId``) and ``_grist_Tables_column``
(``parentId``, ``colId``, ``type``, ``isFormula``, ``formula``, ``label``).

Values are stored natively where SQLite can hold them. Three things differ
from what a reader might expect:

- A ``Date`` is the number of seconds since the epoch, at midnight UTC.
- A ``RefList`` or ``ChoiceList`` is a JSON array in a text cell.
- Anything that does not fit the column type (an error, text typed into a
  number column) is a BLOB holding a Python-marshal value. Only the small
  subset Grist writes is decoded here; nothing is unmarshalled with the
  standard library, because ``marshal.loads`` is not safe on a file that
  came from elsewhere.

The file is opened read-only and never written to.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

TABLES_META = "_grist_Tables"
COLUMNS_META = "_grist_Tables_column"
ROW_ID = "id"
# Columns Grist adds itself; they are never part of a mapping.
_INTERNAL_COLUMNS = ("manualSort",)
_INTERNAL_PREFIX = "gristHelper_"


class GristDocumentError(Exception):
    """The file is not a readable Grist document."""


@dataclass(frozen=True)
class CellError:
    """A cell that holds a formula error instead of a value."""

    name: str
    message: str = ""

    def __str__(self) -> str:
        return f"{self.name}: {self.message}" if self.message else self.name


@dataclass(frozen=True)
class Undecoded:
    """A stored value this reader does not understand."""

    raw: bytes


@dataclass(frozen=True)
class GristColumn:
    col_id: str
    type: str
    is_formula: bool
    formula: str
    label: str
    position: float = 0.0

    @property
    def base_type(self) -> str:
        return self.type.split(":", 1)[0]

    @property
    def ref_table(self) -> str | None:
        """The table a Ref or RefList column points at."""
        if self.base_type in ("Ref", "RefList") and ":" in self.type:
            return self.type.split(":", 1)[1]
        return None

    @property
    def is_internal(self) -> bool:
        return self.col_id in _INTERNAL_COLUMNS or self.col_id.startswith(
            _INTERNAL_PREFIX
        )

    @property
    def has_default_formula(self) -> bool:
        """A data column with a formula that only fills in new records."""
        return not self.is_formula and bool(self.formula.strip())


@dataclass(frozen=True)
class GristTable:
    table_id: str
    columns: tuple[GristColumn, ...]
    row_count: int
    is_summary: bool = False

    def column(self, col_id: str) -> GristColumn | None:
        for column in self.columns:
            if column.col_id == col_id:
                return column
        return None

    @property
    def user_columns(self) -> tuple[GristColumn, ...]:
        return tuple(c for c in self.columns if not c.is_internal)


@dataclass(frozen=True)
class GristRow:
    row_id: int
    values: dict[str, Any] = field(default_factory=dict)

    def get(self, col_id: str | None) -> Any:
        if not col_id:
            return None
        return self.values.get(col_id)


# -- marshal subset -----------------------------------------------------------


class _Unmarshal:
    """Decode the few Python-marshal types Grist writes into a BLOB."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def _take(self, count: int) -> bytes:
        chunk = self.data[self.pos : self.pos + count]
        if len(chunk) != count:
            raise ValueError("truncated")
        self.pos += count
        return chunk

    def _int32(self) -> int:
        return int(struct.unpack("<i", self._take(4))[0])

    def read(self) -> Any:
        # The high bit marks a reference-able object in newer marshal
        # versions; the type is in the low seven bits.
        code = chr(self._take(1)[0] & 0x7F)
        if code == "N":
            return None
        if code == "T":
            return True
        if code == "F":
            return False
        if code == "i":
            return self._int32()
        if code == "I":
            return struct.unpack("<q", self._take(8))[0]
        if code == "g":
            return struct.unpack("<d", self._take(8))[0]
        if code == "f":
            return float(self._take(self._take(1)[0]).decode("ascii"))
        if code in ("u", "t", "s"):
            raw = self._take(self._int32())
            return raw.decode("utf-8", errors="replace")
        if code in ("z", "Z"):
            raw = self._take(self._take(1)[0])
            return raw.decode("utf-8", errors="replace")
        if code in ("a", "A"):
            return self._take(self._int32()).decode("ascii", errors="replace")
        if code in ("(", "["):
            return [self.read() for _ in range(self._int32())]
        if code == ")":
            return [self.read() for _ in range(self._take(1)[0])]
        if code == "{":
            result: dict[Any, Any] = {}
            while self.data[self.pos : self.pos + 1] != b"0":
                key = self.read()
                result[key] = self.read()
            self.pos += 1
            return result
        raise ValueError(f"unsupported marshal type {code!r}")


def decode_blob(data: bytes) -> Any:
    """A marshalled cell value, or ``Undecoded`` when it is something else."""
    try:
        value = _Unmarshal(data).read()
    except (ValueError, IndexError, struct.error, UnicodeDecodeError):
        return Undecoded(bytes(data))
    if isinstance(value, list) and value and value[0] == "E":
        name = str(value[1]) if len(value) > 1 else "Error"
        message = str(value[2]) if len(value) > 2 and value[2] else ""
        return CellError(name, message)
    return value


def decode_value(raw: Any, column: GristColumn) -> Any:
    """Turn a stored cell into a Python value according to the column type."""
    value = decode_blob(bytes(raw)) if isinstance(raw, bytes | memoryview) else raw
    if isinstance(value, CellError | Undecoded) or value is None:
        return value
    base = column.base_type
    if base == "Bool":
        return bool(value) if value in (0, 1) else value
    if base == "Date":
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value, tz=UTC).date()
        return value
    if base == "DateTime":
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value, tz=UTC)
        return value
    if base in ("RefList", "ChoiceList", "Attachments"):
        if isinstance(value, str) and value.startswith("["):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        if isinstance(value, list):
            return value[1:] if value and value[0] == "L" else value
        return value
    if base == "Ref":
        # Row id 0 is Grist's "no reference".
        return value or None if isinstance(value, int) else value
    return value


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class GristDocument:
    """A read-only view on one downloaded Grist document."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise GristDocumentError(f"Bestand niet gevonden: {self.path.name}")
        try:
            self._db = sqlite3.connect(
                f"{self.path.resolve().as_uri()}?mode=ro", uri=True
            )
            self._db.row_factory = sqlite3.Row
            names = {
                row[0]
                for row in self._db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        except sqlite3.DatabaseError as exc:
            raise GristDocumentError(
                "Dit is geen SQLite-bestand. Download het document in Grist via "
                "Delen, Exporteren, 'Download'."
            ) from exc
        if TABLES_META not in names or COLUMNS_META not in names:
            raise GristDocumentError(
                "De metadata-tabellen van Grist ontbreken; dit is geen Grist-document."
            )
        self._sql_tables = names
        self._tables = self._read_tables()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> GristDocument:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _meta_columns(self, table: str) -> set[str]:
        return {
            row[1] for row in self._db.execute(f"PRAGMA table_info({_quote(table)})")
        }

    def _read_tables(self) -> dict[str, GristTable]:
        table_cols = self._meta_columns(TABLES_META)
        summary = "summarySourceTable" if "summarySourceTable" in table_cols else "0"
        tables: dict[str, GristTable] = {}
        for row in self._db.execute(
            f"SELECT id, tableId, {summary} AS summary FROM {TABLES_META} ORDER BY id"
        ):
            table_id = row["tableId"]
            if not table_id or table_id not in self._sql_tables:
                continue
            columns = []
            for col in self._db.execute(
                f"SELECT colId, type, isFormula, formula, label, parentPos "
                f"FROM {COLUMNS_META} WHERE parentId = ? ORDER BY parentPos, id",
                (row["id"],),
            ):
                columns.append(
                    GristColumn(
                        col_id=col["colId"],
                        type=col["type"] or "Any",
                        is_formula=bool(col["isFormula"]),
                        formula=col["formula"] or "",
                        label=col["label"] or "",
                        position=float(col["parentPos"] or 0),
                    )
                )
            count = int(
                self._db.execute(f"SELECT COUNT(*) FROM {_quote(table_id)}").fetchone()[
                    0
                ]
            )
            tables[table_id] = GristTable(
                table_id=table_id,
                columns=tuple(columns),
                row_count=count,
                is_summary=bool(row["summary"]),
            )
        return tables

    @property
    def tables(self) -> tuple[GristTable, ...]:
        return tuple(self._tables.values())

    def table(self, table_id: str) -> GristTable | None:
        return self._tables.get(table_id)

    def rows(self, table_id: str) -> list[GristRow]:
        table = self._tables.get(table_id)
        if table is None:
            raise GristDocumentError(f"Tabel {table_id} bestaat niet in het document.")
        present = self._meta_columns(table_id)
        columns = [c for c in table.columns if c.col_id in present]
        order = "manualSort, id" if "manualSort" in present else "id"
        select = ", ".join([ROW_ID, *(_quote(c.col_id) for c in columns)])
        result = []
        for row in self._db.execute(
            f"SELECT {select} FROM {_quote(table_id)} ORDER BY {order}"
        ):
            values = {
                column.col_id: decode_value(row[column.col_id], column)
                for column in columns
            }
            result.append(GristRow(row_id=row[ROW_ID], values=values))
        return result

    def snapshot_date(self) -> date:
        """The modification date of the file, as a stand-in for the snapshot."""
        return datetime.fromtimestamp(self.path.stat().st_mtime, tz=UTC).date()
