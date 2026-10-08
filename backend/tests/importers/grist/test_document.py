"""Reading a Grist document file."""

from __future__ import annotations

import hashlib
import marshal
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from grip.importers.grist.document import (
    CellError,
    GristDocument,
    GristDocumentError,
    Undecoded,
    decode_blob,
)


def test_lists_user_tables_with_row_counts(document: GristDocument) -> None:
    counts = {table.table_id: table.row_count for table in document.tables}
    assert counts["Tarievenleaflet"] == 10
    assert counts["Team"] == 4
    assert counts["Inzet"] == 4
    assert "_grist_Tables" not in counts


def test_columns_carry_type_and_formula(document: GristDocument) -> None:
    inzet = document.table("Inzet")
    assert inzet is not None
    amount = inzet.column("Inzetbedrag")
    assert amount is not None and amount.is_formula
    assert "DATEDIF" in amount.formula
    person = inzet.column("Naam")
    assert person is not None
    assert person.base_type == "Ref" and person.ref_table == "Team"
    assert not person.is_formula


def test_internal_columns_are_not_user_columns(document: GristDocument) -> None:
    team = document.table("Team")
    assert team is not None
    names = [column.col_id for column in team.user_columns]
    assert names == ["Naam", "Schaal", "Notitie", "Target_KPI_declarabel"]
    assert {c.col_id for c in team.columns} > set(names)


def test_dates_references_and_lists_are_decoded(document: GristDocument) -> None:
    first = document.rows("Inzet")[0]
    assert first.row_id == 1
    assert first.get("Startdatum") == date(2026, 1, 1)
    assert first.get("Einddatum") == date(2026, 12, 31)
    assert first.get("Naam") == 1
    assert document.rows("Begroting")[0].get("Opdracht") == [1]


def test_a_formula_error_is_a_cell_error_not_a_number(document: GristDocument) -> None:
    row = document.rows("Begroting")[2]
    value = row.get("Uitputting")
    assert isinstance(value, CellError)
    assert value.name == "ZeroDivisionError"


def test_marshal_subset() -> None:
    assert decode_blob(marshal.dumps("tekst in een getalkolom", 2)) == (
        "tekst in een getalkolom"
    )
    assert decode_blob(marshal.dumps(12.5, 2)) == 12.5
    assert decode_blob(marshal.dumps(None, 2)) is None
    assert decode_blob(marshal.dumps(["L", 1, 2], 2)) == ["L", 1, 2]
    assert decode_blob(marshal.dumps(["E", "TypeError", "kapot"], 2)) == CellError(
        "TypeError", "kapot"
    )
    # Something that is not marshal data is kept, never executed or guessed.
    assert isinstance(decode_blob(b"\xff\xfe\x00"), Undecoded)
    assert isinstance(
        decode_blob(marshal.dumps(compile("1", "x", "eval"), 2)), Undecoded
    )


def test_the_file_is_never_written(grist_path: Path) -> None:
    before = hashlib.sha256(grist_path.read_bytes()).hexdigest()
    with GristDocument(grist_path) as doc:
        doc.rows("Team")
        with pytest.raises(sqlite3.OperationalError):
            doc._db.execute("DELETE FROM Team")  # noqa: SLF001
    assert hashlib.sha256(grist_path.read_bytes()).hexdigest() == before


def test_refuses_what_is_not_a_grist_document(tmp_path: Path) -> None:
    text = tmp_path / "geen.grist"
    text.write_text("dit is geen database")
    with pytest.raises(GristDocumentError, match="geen SQLite"):
        GristDocument(text)

    plain = tmp_path / "leeg.sqlite"
    sqlite3.connect(plain).execute("CREATE TABLE iets (id INTEGER)").connection.commit()
    with pytest.raises(GristDocumentError, match="metadata"):
        GristDocument(plain)

    with pytest.raises(GristDocumentError, match="niet gevonden"):
        GristDocument(tmp_path / "bestaat-niet.grist")
