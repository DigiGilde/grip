"""A fictional Grist document for the import tests.

The names, amounts and rates are invented. The amounts in the formula
columns are what the document's own formulas would give: an allocation is
(DATEDIF(start, end, "M") + 1) months at the monthly amount, and coverage is
a percentage of the forecast.
"""

from __future__ import annotations

from datetime import date
from importlib import resources
from pathlib import Path

import pytest

from grip.importers.grist.document import GristDocument
from grip.importers.grist.mapping import Mapping, load_mapping
from tests.importers.grist.builder import Col, Table, build_grist, error, formula

DATEDIF_FORMULA = '(DATEDIF($Startdatum, $Einddatum, "M") + 1) * $Maandbedrag'
FORECAST_FORMULA = "SUM(Factuur.lookupRecords(Kosten=$id).Bedrag)"
COVERAGE_FORMULA = "$Percentage * $Kosten.Prognose_realisatie"

RATES = {"A": 9000, "B": 12000, "C": 15000, "D": 18000, "E": 21000}
SCALES = {
    8: "A",
    9: "A",
    10: "B",
    11: "B",
    12: "C",
    13: "C",
    14: "D",
    15: "D",
    16: "E",
    17: "E",
}


def fictional_tables() -> list[Table]:
    return [
        Table(
            "Tarievenleaflet",
            [
                Col("Categorie"),
                Col("Inzetschaal", "Int"),
                Col("Maandtarief", "Numeric"),
            ],
            [
                {
                    "Categorie": category,
                    "Inzetschaal": scale,
                    "Maandtarief": RATES[category],
                }
                for scale, category in SCALES.items()
            ],
        ),
        Table(
            "Team",
            [
                Col("Naam"),
                Col("Schaal", "Int"),
                Col("Notitie"),
                Col("Target_KPI_declarabel", "Numeric"),
            ],
            [
                {
                    "Naam": "Vera Voorbeeld",
                    "Schaal": 14,
                    "Notitie": "",
                    "Target_KPI_declarabel": 0.9,
                },
                {
                    "Naam": "Tom Test",
                    "Schaal": 11,
                    "Notitie": "Schaal 11, maar rekent met 12",
                },
                {"Naam": "Dana Demo", "Schaal": 10, "Notitie": ""},
                {"Naam": "Developer #3", "Schaal": 10, "Notitie": ""},
            ],
        ),
        Table(
            "KPI_per_persoon",
            [
                Col("Naam", "Ref:Team"),
                Col("Target_KPI_declarabel", "Numeric"),
                formula("Target", "$Target_KPI_declarabel * 12 * $Naam.Maandtarief"),
                formula(
                    "Realisatie", "SUM(Inzet.lookupRecords(Naam=$Naam).Inzetbedrag)"
                ),
            ],
            [
                {
                    "Naam": 1,
                    "Target_KPI_declarabel": 0.9,
                    "Target": 194400,
                    "Realisatie": 172800,
                }
            ],
        ),
        Table(
            "Opdracht",
            [
                Col("Naam"),
                Col("Status", "Choice"),
                Col("Offertedatum", "Date"),
                Col("Contactpersoon"),
                Col("Bedrag", "Numeric"),
                formula(
                    "Begroot",
                    "SUM(Begroting.lookupRecords(Opdracht=CONTAINS($id)).Begroot)",
                ),
                formula(
                    "Uitputting",
                    "SUM(Begroting.lookupRecords(Opdracht=CONTAINS($id)).Uitputting)",
                ),
                formula("Beschikbaar", "$Begroot - $Uitputting"),
            ],
            [
                {
                    "Naam": "Opdracht Alfa 2026",
                    "Status": "Akkoord",
                    "Offertedatum": date(2025, 11, 3),
                    "Contactpersoon": "Contact Voorbeeldministerie",
                    "Bedrag": 400000,
                    "Begroot": 377800,
                    "Uitputting": 312300,
                    "Beschikbaar": 65500,
                },
                {
                    "Naam": "Opdracht Beta 2026",
                    "Status": "Offerte verstuurd",
                    "Bedrag": 150000,
                    "Begroot": 144000,
                    "Uitputting": 91500,
                    "Beschikbaar": 52500,
                },
                {
                    "Naam": "Interne opdracht Kennis 2026",
                    "Status": "Interne opdracht",
                    "Begroot": 0,
                    "Uitputting": 0,
                    "Beschikbaar": 0,
                },
            ],
        ),
        Table(
            "Begroting",
            [
                Col("Opdracht", "RefList:Opdracht"),
                Col("Omschrijving"),
                Col("Begroot", "Numeric"),
                formula(
                    "Uitputting",
                    "SUM(Inzet.lookupRecords(Begrotingsregel=$id).Inzetbedrag)"
                    " + SUM(Kostendekking.lookupRecords(Begrotingsregel=$id).Bedrag)",
                ),
                formula("Beschikbaar", "$Begroot - $Uitputting"),
            ],
            [
                {
                    "Opdracht": [1],
                    "Omschrijving": "Productmanager (0,8 FTE, schaal 14/15)",
                    "Begroot": 172800,
                    "Uitputting": 172800,
                    "Beschikbaar": 0,
                },
                {
                    "Opdracht": [1],
                    "Omschrijving": "Developer #2 (vanaf Q2, schaal 12/13)",
                    "Begroot": 135000,
                    "Uitputting": 135000,
                    "Beschikbaar": 0,
                },
                {
                    "Opdracht": [1],
                    "Omschrijving": "60k externe expertise",
                    "Begroot": 60000,
                    "Uitputting": error(),
                    "Beschikbaar": error(),
                },
                {
                    "Opdracht": [2],
                    "Omschrijving": "Developer (schaal 10/11)",
                    "Begroot": 144000,
                    "Uitputting": 91500,
                    "Beschikbaar": 52500,
                },
                {
                    "Opdracht": [1],
                    "Omschrijving": "Hosting (stelpost)",
                    "Begroot": 10000,
                    "Uitputting": 4500,
                    "Beschikbaar": 5500,
                },
            ],
        ),
        Table(
            "Inzet",
            [
                Col("Naam", "Ref:Team"),
                Col("Begrotingsregel", "Ref:Begroting"),
                Col("Startdatum", "Date"),
                Col("Einddatum", "Date"),
                Col("FTE", "Numeric"),
                formula("Maandbedrag", "$FTE * $Naam.Maandtarief"),
                formula("Inzetbedrag", DATEDIF_FORMULA),
            ],
            [
                {
                    "Naam": 1,
                    "Begrotingsregel": 1,
                    "Startdatum": date(2026, 1, 1),
                    "Einddatum": date(2026, 12, 31),
                    "FTE": 0.8,
                    "Maandbedrag": 14400,
                    "Inzetbedrag": 172800,
                },
                {
                    "Naam": 2,
                    "Begrotingsregel": 2,
                    "Startdatum": date(2026, 4, 1),
                    "Einddatum": date(2026, 12, 31),
                    "FTE": 1,
                    "Maandbedrag": 15000,
                    "Inzetbedrag": 135000,
                },
                # Across the year boundary.
                {
                    "Naam": 3,
                    "Begrotingsregel": 4,
                    "Startdatum": date(2026, 7, 1),
                    "Einddatum": date(2027, 6, 30),
                    "FTE": 0.5,
                    "Maandbedrag": 6000,
                    "Inzetbedrag": 72000,
                },
                # A partial period: DATEDIF gives one month, plus one is two.
                {
                    "Naam": 3,
                    "Begrotingsregel": 4,
                    "Startdatum": date(2026, 1, 16),
                    "Einddatum": date(2026, 3, 10),
                    "FTE": 0.5,
                    "Maandbedrag": 6000,
                    "Inzetbedrag": 12000,
                },
            ],
        ),
        Table(
            "Kosten",
            [
                Col("Omschrijving"),
                Col("Begroot", "Numeric"),
                formula("Prognose_realisatie", FORECAST_FORMULA),
                formula(
                    "Dekking", "SUM(Kostendekking.lookupRecords(Kosten=$id).Bedrag)"
                ),
            ],
            [
                {
                    "Omschrijving": "Hostingcontract",
                    "Begroot": 12000,
                    "Prognose_realisatie": 15000,
                    "Dekking": 12000,
                }
            ],
        ),
        Table(
            "Factuur",
            [
                Col("Factuur"),
                Col("Omschrijving"),
                Col("Soort", "Choice"),
                Col("Bedrag", "Numeric"),
                Col("Kosten", "Ref:Kosten"),
            ],
            [
                {
                    "Factuur": "HOST-26-01",
                    "Omschrijving": "Eerste halfjaar",
                    "Soort": "Realisatie",
                    "Bedrag": 9000,
                    "Kosten": 1,
                },
                {
                    "Factuur": "HOST-26-02",
                    "Omschrijving": "Tweede halfjaar",
                    "Soort": "Inschatting",
                    "Bedrag": 6000,
                    "Kosten": 1,
                },
            ],
        ),
        Table(
            "Kostendekking",
            [
                Col("Kosten", "Ref:Kosten"),
                Col("Begrotingsregel", "Ref:Begroting"),
                Col("Percentage", "Numeric"),
                formula("Bedrag", COVERAGE_FORMULA),
            ],
            [
                # One cost item covered from two assignments.
                {"Kosten": 1, "Begrotingsregel": 5, "Percentage": 0.3, "Bedrag": 4500},
                {"Kosten": 1, "Begrotingsregel": 4, "Percentage": 0.5, "Bedrag": 7500},
            ],
        ),
        Table("Notities", [Col("Tekst")], [{"Tekst": "niet gekoppeld"}]),
    ]


@pytest.fixture
def grist_path(tmp_path: Path) -> Path:
    return build_grist(tmp_path / "voorbeeld.grist", fictional_tables())


@pytest.fixture
def document(grist_path: Path):
    with GristDocument(grist_path) as doc:
        yield doc


@pytest.fixture
def mapping_path(tmp_path: Path) -> Path:
    """The bundled mapping, marked as verified for the fictional document."""
    text = (
        resources.files("grip.importers.grist")
        .joinpath("mapping.toml")
        .read_text(encoding="utf-8")
        .replace("verified = false", "verified = true")
    )
    path = tmp_path / "mapping.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def mapping(mapping_path: Path) -> Mapping:
    return load_mapping(mapping_path)
