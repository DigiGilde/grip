"""The command line: the steps a person runs, in order."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grip.importers.grist.cli import (
    EXIT_DIFFERENCES,
    EXIT_ERRORS,
    EXIT_OK,
    EXIT_USAGE,
    main,
)
from grip.importers.grist.confirmation import read_confirmations
from tests.importers.grist.builder import build_grist
from tests.importers.grist.conftest import fictional_tables
from tests.importers.grist.helpers import confirm_all


def test_inspect_prints_structure_and_formulas_but_no_cell_values(
    grist_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["inspect", str(grist_path)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "Inzet: 4 rijen" in out
    assert "Kosten: 1 rij\n" in out
    assert "Inzetbedrag  [Numeric, formule]" in out
    assert '(DATEDIF($Startdatum, $Einddatum, "M") + 1) * $Maandbedrag' in out
    assert "oordeel: herkend -> grist_datedif" in out
    assert "verified = false" in out
    assert "Tabel Notities" in out
    # Structure only: no names, notes or amounts from the cells.
    for cell in ("Vera Voorbeeld", "rekent met 12", "172800", "Hostingcontract"):
        assert cell not in out
    assert "gristHelper" not in out


def test_check_says_whether_the_mapping_fits(
    grist_path: Path,
    mapping_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["check", str(grist_path), "--mapping", str(mapping_path)]) == EXIT_OK
    assert "De koppeling past op het document." in capsys.readouterr().out

    tables = [t for t in fictional_tables() if t.table_id != "Inzet"]
    other = build_grist(tmp_path / "zonder-inzet.grist", tables)
    assert main(["check", str(other), "--mapping", str(mapping_path)]) == EXIT_ERRORS
    out = capsys.readouterr().out
    assert "[fout] allocations: Tabel Inzet staat niet in het document." in out
    assert "De koppeling past niet" in out


def test_unreadable_input_is_a_clear_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wrong = tmp_path / "tekst.grist"
    wrong.write_text("geen database")
    assert main(["inspect", str(wrong)]) == EXIT_USAGE
    assert "geen SQLite-bestand" in capsys.readouterr().err


def test_propose_then_confirm_then_propose_again(
    grist_path: Path,
    mapping_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    listing = tmp_path / "lijst.json"
    base = [
        str(grist_path),
        "--mapping",
        str(mapping_path),
        "--confirmations",
        str(listing),
    ]

    assert main(["propose", *base]) == EXIT_OK
    out = capsys.readouterr().out
    assert "12 items: 12 te beoordelen" in out
    assert "hoog: 7, laag: 3, middel: 2" in out

    assert main(["confirm", str(listing), "--confidence", "hoog"]) == EXIT_OK
    assert "7 items" in capsys.readouterr().out
    confirmations = read_confirmations(listing)
    assert confirmations.counts() == {"voorstel": 5, "bevestigd": 7, "overslaan": 0}

    # A newer download with one changed description: that decision is asked
    # again, the others are kept.
    tables = fictional_tables()
    for table in tables:
        if table.table_id == "Begroting":
            table.rows[2]["Omschrijving"] = "80k externe expertise"
            table.rows[2]["Begroot"] = 80_000
    newer = build_grist(tmp_path / "later.grist", tables)
    assert (
        main(
            [
                "propose",
                str(newer),
                "--mapping",
                str(mapping_path),
                "--confirmations",
                str(listing),
            ]
        )
        == EXIT_OK
    )
    out = capsys.readouterr().out
    assert "Uit de vorige lijst behouden: 6." in out
    assert "Terug naar voorstel omdat de bron wijzigde: 1." in out
    changed = read_confirmations(listing).get("budget_line:3")
    assert changed is not None
    assert changed.status == "voorstel"
    assert changed.previous_values is not None
    assert changed.proposal["amount_cents"] == 8_000_000


def test_load_refuses_an_unverified_mapping(
    grist_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    listing = tmp_path / "lijst.json"
    main(["propose", str(grist_path), "--confirmations", str(listing)])
    capsys.readouterr()
    code = main(["load", str(grist_path), "--confirmations", str(listing), "--dry-run"])
    assert code == EXIT_USAGE
    assert "De koppeling is nog niet bevestigd voor:" in capsys.readouterr().out


def test_load_refuses_while_items_are_unreviewed(
    grist_path: Path,
    mapping_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    listing = tmp_path / "lijst.json"
    base = [
        str(grist_path),
        "--mapping",
        str(mapping_path),
        "--confirmations",
        str(listing),
    ]
    assert main(["load", *base, "--dry-run"]) == EXIT_USAGE
    assert "nog geen bevestigingslijst" in capsys.readouterr().out

    main(["propose", *base])
    capsys.readouterr()
    assert main(["load", *base, "--dry-run"]) == EXIT_USAGE
    out = capsys.readouterr().out
    assert "12 items op de bevestigingslijst zijn nog niet beoordeeld" in out


def test_dry_run_loads_reconciles_and_writes_nothing(
    grist_path: Path,
    mapping_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The whole procedure on the test database, rolled back at the end."""
    listing = tmp_path / "lijst.json"
    report = tmp_path / "aansluiting.txt"
    base = [
        str(grist_path),
        "--mapping",
        str(mapping_path),
        "--confirmations",
        str(listing),
    ]
    main(["propose", *base])
    confirm_all(confirmations := read_confirmations(listing))
    confirmations.write(listing)
    capsys.readouterr()

    args = [
        "load",
        *base,
        "--dry-run",
        "--document-key",
        "cli-test",
        "--report",
        str(report),
    ]
    # The fictional document has an allocation into 2027 and the import only
    # brings the rate card of 2026, so this run shows differences.
    assert main(args) == EXIT_DIFFERENCES
    out = capsys.readouterr().out
    assert "Proefrun: er is niets geschreven." in out
    assert "assignment: 3" in out
    assert "Uitkomst: SLUIT NIET AAN" in out
    assert "tarievenkaart voor 2027" in report.read_text(encoding="utf-8")

    # Nothing was written: the same dry run again creates everything anew.
    assert main(args) == EXIT_DIFFERENCES
    assert "assignment: 3" in capsys.readouterr().out.split("Proefrun")[0]


def test_confirmation_file_with_a_typo_stops_the_run(
    grist_path: Path,
    mapping_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    listing = tmp_path / "lijst.json"
    base = [
        str(grist_path),
        "--mapping",
        str(mapping_path),
        "--confirmations",
        str(listing),
    ]
    main(["propose", *base])
    data = json.loads(listing.read_text(encoding="utf-8"))
    data["items"][0]["status"] = "goed"
    listing.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()
    assert main(["load", *base, "--dry-run"]) == EXIT_USAGE
    assert "status is 'goed'" in capsys.readouterr().err
