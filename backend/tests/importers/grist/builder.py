"""Build a small Grist document file for tests.

Writes the same layout Grist does: the two metadata tables, one SQL table
per user table, dates as seconds since the epoch, reference lists as JSON
text and errors as marshalled BLOBs. Everything in it is fictional.
"""

from __future__ import annotations

import json
import marshal
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


@dataclass
class Col:
    col_id: str
    type: str = "Text"
    formula: str = ""
    is_formula: bool = False
    label: str = ""


@dataclass
class Table:
    table_id: str
    columns: list[Col]
    rows: list[dict[str, Any]] = field(default_factory=list)


def formula(col_id: str, text: str, type: str = "Numeric") -> Col:
    return Col(col_id, type, text, is_formula=True)


def error(name: str = "ZeroDivisionError") -> bytes:
    """A cell holding a formula error, the way Grist stores it."""
    return marshal.dumps(["E", name], 2)


def _sql_type(grist_type: str) -> str:
    base = grist_type.split(":", 1)[0]
    return {
        "Text": "TEXT",
        "Choice": "TEXT",
        "Numeric": "NUMERIC",
        "ManualSortPos": "NUMERIC",
        "Int": "INTEGER",
        "Bool": "BOOLEAN",
        "Date": "DATE",
        "Ref": "INTEGER",
        "RefList": "TEXT",
        "ChoiceList": "TEXT",
    }.get(base, "BLOB")


def _encode(value: Any, grist_type: str) -> Any:
    if isinstance(value, bytes) or value is None:
        return value
    base = grist_type.split(":", 1)[0]
    if base == "Date" and isinstance(value, date):
        return int(datetime(value.year, value.month, value.day, tzinfo=UTC).timestamp())
    if base in ("RefList", "ChoiceList") and isinstance(value, list):
        return json.dumps(value)
    if base == "Bool" and isinstance(value, bool):
        return int(value)
    return value


def build_grist(path: Path, tables: list[Table]) -> Path:
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE _grist_Tables (id INTEGER PRIMARY KEY, tableId TEXT, "
        "primaryViewId INTEGER DEFAULT 0, summarySourceTable INTEGER DEFAULT 0, "
        "onDemand BOOLEAN DEFAULT 0)"
    )
    db.execute(
        "CREATE TABLE _grist_Tables_column (id INTEGER PRIMARY KEY, "
        "parentId INTEGER, parentPos NUMERIC, colId TEXT, type TEXT, "
        "widgetOptions TEXT DEFAULT '', isFormula BOOLEAN, formula TEXT, "
        "label TEXT, description TEXT DEFAULT '')"
    )
    column_id = 0
    for table_number, table in enumerate(tables, start=1):
        db.execute(
            "INSERT INTO _grist_Tables (id, tableId) VALUES (?, ?)",
            (table_number, table.table_id),
        )
        # Grist adds manualSort and helper columns to every table.
        columns = [
            Col("manualSort", "ManualSortPos"),
            *table.columns,
            Col("gristHelper_Display", "Any", "$id", is_formula=True),
        ]
        for position, col in enumerate(columns, start=1):
            column_id += 1
            db.execute(
                "INSERT INTO _grist_Tables_column (id, parentId, parentPos, colId, "
                "type, isFormula, formula, label) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    column_id,
                    table_number,
                    position,
                    col.col_id,
                    col.type,
                    int(col.is_formula),
                    col.formula,
                    col.label or col.col_id,
                ),
            )
        defs = ", ".join(f'"{c.col_id}" {_sql_type(c.type)}' for c in columns)
        db.execute(f'CREATE TABLE "{table.table_id}" (id INTEGER PRIMARY KEY, {defs})')
        for number, row in enumerate(table.rows, start=1):
            row_id = row.get("id", number)
            names = ["id", "manualSort"]
            values: list[Any] = [row_id, number]
            for col in table.columns:
                if col.col_id in row:
                    names.append(col.col_id)
                    values.append(_encode(row[col.col_id], col.type))
            quoted = ", ".join(f'"{n}"' for n in names)
            marks = ", ".join("?" for _ in names)
            db.execute(
                f'INSERT INTO "{table.table_id}" ({quoted}) VALUES ({marks})', values
            )
    db.commit()
    db.close()
    return path
