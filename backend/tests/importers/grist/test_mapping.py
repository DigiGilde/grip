"""The declarative mapping and its check against a document."""

from __future__ import annotations

from pathlib import Path

import pytest

from grip.importers.grist.document import GristDocument
from grip.importers.grist.mapping import (
    SPECS,
    Mapping,
    MappingError,
    check_mapping,
    load_mapping,
    parse_mapping,
    unverified_tables,
)
from tests.importers.grist.builder import Col, Table, build_grist
from tests.importers.grist.conftest import fictional_tables


def test_bundled_mapping_parses_and_is_marked_unverified() -> None:
    mapping = load_mapping()
    assert mapping.rate_card_year == 2026
    assert {spec.name for spec in SPECS} == set(mapping.tables)
    # Nothing in the bundled mapping has been checked against the real
    # document; the loader relies on this flag.
    assert not any(table.verified for table in mapping.tables.values())
    assert mapping.grip_status("akkoord") == "in_progress"
    assert mapping.is_internal("Interne opdracht")
    assert not mapping.is_internal("Akkoord")


def test_mapping_fits_the_fictional_document(
    document: GristDocument, mapping: Mapping
) -> None:
    check = check_mapping(document, mapping)
    assert check.ok
    assert check.usable_tables == frozenset(spec.name for spec in SPECS)
    unmapped = [f.message for f in check.findings if f.severity == "info"]
    assert any("Notities" in message for message in unmapped)
    assert any("Inzet.Maandbedrag" not in message for message in unmapped)


def test_everything_wrong_is_reported_at_once(tmp_path: Path, mapping: Mapping) -> None:
    tables = [t for t in fictional_tables() if t.table_id != "Kosten"]
    for table in tables:
        if table.table_id == "Inzet":
            table.columns = [c for c in table.columns if c.col_id != "FTE"]
            table.columns.append(Col("Opmerking"))
        if table.table_id == "Team":
            table.columns = [c for c in table.columns if c.col_id != "Notitie"]
    path = build_grist(tmp_path / "anders.grist", tables)
    with GristDocument(path) as doc:
        check = check_mapping(doc, mapping)

    assert not check.ok
    messages = {(f.severity, f.table): f.message for f in check.findings}
    errors = [f for f in check.errors]
    assert any(f.table == "cost_items" and "Kosten" in f.message for f in errors)
    assert any(f.table == "allocations" and "Inzet.FTE" in f.message for f in errors)
    # An optional column that is gone is a warning, not an error.
    assert any(
        f.severity == "waarschuwing" and "Team.Notitie" in f.message
        for f in check.findings
    )
    # A column the mapping does not know is reported, not silently dropped.
    assert any(
        f.severity == "info" and "Inzet.Opmerking" in f.message for f in check.findings
    )
    assert "allocations" not in check.usable_tables
    assert "cost_items" not in check.usable_tables
    assert "team" in check.usable_tables
    assert messages


def test_optional_table_may_be_absent(tmp_path: Path, mapping: Mapping) -> None:
    tables = [t for t in fictional_tables() if t.table_id != "KPI_per_persoon"]
    with GristDocument(build_grist(tmp_path / "zonder-kpi.grist", tables)) as doc:
        check = check_mapping(doc, mapping)
    assert check.ok
    assert "kpi" not in check.usable_tables


def test_mapping_file_errors_are_clear(tmp_path: Path) -> None:
    with pytest.raises(MappingError, match="version"):
        parse_mapping({})
    with pytest.raises(MappingError, match="Onbekende tabel"):
        parse_mapping({"version": 1, "tables": {"onzin": {"grist_table": "X"}}})
    with pytest.raises(MappingError, match="Onbekend veld"):
        parse_mapping(
            {
                "version": 1,
                "tables": {
                    "team": {"grist_table": "Team", "columns": {"salaris": "S"}}
                },
            }
        )
    broken = tmp_path / "kapot.toml"
    broken.write_text("version = ")
    with pytest.raises(MappingError, match="niet te lezen"):
        load_mapping(broken)


def test_unverified_tables_are_named(mapping: Mapping) -> None:
    assert unverified_tables(mapping, {"team", "rates"}) == []
    assert unverified_tables(load_mapping(), {"team", "rates"}) == ["rates", "team"]


def test_a_table_with_another_id_is_one_line_in_the_mapping(tmp_path: Path) -> None:
    """The point of the mapping: other ids need no code change."""
    tables = fictional_tables()
    for table in tables:
        if table.table_id == "Team":
            table.table_id = "Medewerkers"
            table.columns[0] = Col("Volledige_naam")
            for row in table.rows:
                row["Volledige_naam"] = row.pop("Naam")
    for table in tables:
        for col in table.columns:
            if col.type == "Ref:Team":
                col.type = "Ref:Medewerkers"
    path = build_grist(tmp_path / "hernoemd.grist", tables)
    data = {
        "version": 1,
        "tables": {
            name: {
                "grist_table": table.grist_table,
                "verified": True,
                "columns": dict(table.columns),
            }
            for name, table in load_mapping().tables.items()
        },
    }
    data["tables"]["team"]["grist_table"] = "Medewerkers"
    data["tables"]["team"]["columns"]["name"] = "Volledige_naam"
    with GristDocument(path) as doc:
        assert check_mapping(doc, parse_mapping(data)).ok
        assert not check_mapping(doc, load_mapping()).ok


def test_table_helper() -> None:
    table = Table("X", [Col("a")])
    assert table.rows == []
