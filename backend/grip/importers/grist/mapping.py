"""The declarative mapping from a Grist document to grip, and its check.

The mapping names, per logical source table, the Grist table id and the
Grist column id of every field the import reads. It is data, not code: when
the real document turns out to use other ids, only the TOML file changes.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from grip.importers.grist.document import GristDocument

BUNDLED_MAPPING = "mapping.toml"


class MappingError(Exception):
    """The mapping file itself is wrong."""


@dataclass(frozen=True)
class FieldSpec:
    name: str
    required: bool = False
    # A value Grist computes; only read to compare against grip.
    computed: bool = False


@dataclass(frozen=True)
class TableSpec:
    name: str
    fields: tuple[FieldSpec, ...]
    required: bool = True
    purpose: str = ""

    def field(self, name: str) -> FieldSpec:
        for spec in self.fields:
            if spec.name == name:
                return spec
        raise KeyError(name)


def _f(name: str, *, required: bool = False, computed: bool = False) -> FieldSpec:
    return FieldSpec(name, required=required, computed=computed)


# What the import knows how to read. A field that is not listed here cannot
# be mapped; a required field must be mapped for its table to be usable.
SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        "rates",
        (
            _f("category", required=True),
            _f("scale", required=True),
            _f("monthly_rate", required=True),
        ),
        purpose="tarievenkaart: categorie, schaal en maandtarief",
    ),
    TableSpec(
        "team",
        (
            _f("name", required=True),
            _f("email"),
            _f("scale"),
            _f("note"),
            _f("manager"),
            _f("active"),
            _f("target_pct"),
            _f("kpi_target_amount", computed=True),
            _f("kpi_realisation", computed=True),
        ),
        purpose="personen, schaal en notitie",
    ),
    TableSpec(
        "kpi",
        (
            _f("person", required=True),
            _f("target_pct"),
            _f("target_amount", computed=True),
            _f("realisation", computed=True),
        ),
        required=False,
        purpose="KPI per persoon, als die in een eigen tabel staat",
    ),
    TableSpec(
        "assignments",
        (
            _f("name", required=True),
            _f("status"),
            _f("quote_date"),
            _f("client_contact"),
            _f("owner"),
            _f("amount"),
            _f("notes"),
            _f("start_date"),
            _f("end_date"),
            _f("budgeted", computed=True),
            _f("used", computed=True),
            _f("available", computed=True),
        ),
        purpose="opdrachten",
    ),
    TableSpec(
        "budget_lines",
        (
            _f("assignment", required=True),
            _f("description", required=True),
            _f("budgeted", required=True),
            _f("used", computed=True),
            _f("available", computed=True),
            _f("is_person"),
            _f("fte"),
            _f("scale"),
            _f("start_date"),
            _f("end_date"),
        ),
        purpose="begrotingsregels",
    ),
    TableSpec(
        "allocations",
        (
            _f("person", required=True),
            _f("budget_line", required=True),
            _f("start_date", required=True),
            _f("end_date", required=True),
            _f("fte_pct", required=True),
            _f("monthly_amount", computed=True),
            _f("amount", computed=True),
        ),
        purpose="inzet",
    ),
    TableSpec(
        "cost_items",
        (
            _f("description", required=True),
            _f("budgeted"),
            _f("forecast", computed=True),
            _f("covered", computed=True),
        ),
        purpose="kostenposten",
    ),
    TableSpec(
        "invoice_lines",
        (
            _f("reference"),
            _f("description"),
            _f("kind"),
            _f("amount", required=True),
            _f("cost_item", required=True),
            _f("period"),
        ),
        purpose="factuurregels op een kostenpost",
    ),
    TableSpec(
        "coverages",
        (
            _f("cost_item", required=True),
            _f("budget_line", required=True),
            _f("pct", required=True),
            _f("amount", computed=True),
        ),
        purpose="kostendekking",
    ),
)
SPEC_BY_NAME = {spec.name: spec for spec in SPECS}


@dataclass(frozen=True)
class TableMapping:
    name: str
    grist_table: str
    verified: bool
    columns: dict[str, str] = field(default_factory=dict)

    def col(self, field_name: str) -> str | None:
        """The Grist column id of a logical field, or None when unmapped."""
        return self.columns.get(field_name) or None


@dataclass(frozen=True)
class Mapping:
    tables: dict[str, TableMapping]
    rate_card_year: int
    status: dict[str, str]
    internal_statuses: frozenset[str]
    default_status: str
    invoice_kind: dict[str, str]
    source: str = BUNDLED_MAPPING

    def table(self, name: str) -> TableMapping | None:
        mapping = self.tables.get(name)
        if mapping is None or not mapping.grist_table:
            return None
        return mapping

    def grip_status(self, grist_status: str | None) -> str | None:
        if not grist_status:
            return None
        return self.status.get(grist_status.strip().casefold())

    def is_internal(self, grist_status: str | None) -> bool:
        if not grist_status:
            return False
        return grist_status.strip().casefold() in self.internal_statuses


def parse_mapping(data: dict[str, Any], *, source: str = BUNDLED_MAPPING) -> Mapping:
    if data.get("version") != 1:
        raise MappingError("De koppeling heeft geen 'version = 1'.")
    tables: dict[str, TableMapping] = {}
    for name, raw in (data.get("tables") or {}).items():
        spec = SPEC_BY_NAME.get(name)
        if spec is None:
            known = ", ".join(sorted(SPEC_BY_NAME))
            raise MappingError(f"Onbekende tabel '{name}' in de koppeling ({known}).")
        columns = {k: str(v) for k, v in (raw.get("columns") or {}).items() if v}
        known_fields = {f.name for f in spec.fields}
        unknown = sorted(set(raw.get("columns") or {}) - known_fields)
        if unknown:
            raise MappingError(
                f"Onbekend veld bij tabel '{name}': {', '.join(unknown)}."
            )
        tables[name] = TableMapping(
            name=name,
            grist_table=str(raw.get("grist_table") or ""),
            verified=bool(raw.get("verified", False)),
            columns=columns,
        )
    values = data.get("values") or {}
    year = data.get("rate_card_year", 2026)
    if not isinstance(year, int):
        raise MappingError("'rate_card_year' moet een jaartal zijn.")
    return Mapping(
        tables=tables,
        rate_card_year=year,
        status={
            k.strip().casefold(): v for k, v in (values.get("status") or {}).items()
        },
        internal_statuses=frozenset(
            s.strip().casefold() for s in values.get("internal_statuses") or ()
        ),
        default_status=str(values.get("default_status") or "draft"),
        invoice_kind={
            k.strip().casefold(): v
            for k, v in (values.get("invoice_kind") or {}).items()
        },
        source=source,
    )


def load_mapping(path: str | Path | None = None) -> Mapping:
    """The mapping from a file, or the one shipped with grip."""
    if path is None:
        text = (
            resources.files("grip.importers.grist")
            .joinpath(BUNDLED_MAPPING)
            .read_text(encoding="utf-8")
        )
        return parse_mapping(tomllib.loads(text))
    file = Path(path)
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise MappingError(f"De koppeling is niet te lezen: {exc}") from exc
    return parse_mapping(data, source=file.name)


# -- check against a document -------------------------------------------------


@dataclass(frozen=True)
class MappingFinding:
    severity: str  # "fout" | "waarschuwing" | "info"
    table: str
    message: str


@dataclass(frozen=True)
class MappingCheck:
    findings: tuple[MappingFinding, ...]
    usable_tables: frozenset[str]

    @property
    def errors(self) -> tuple[MappingFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "fout")

    @property
    def ok(self) -> bool:
        return not self.errors

    def usable(self, name: str) -> bool:
        return name in self.usable_tables


def check_mapping(document: GristDocument, mapping: Mapping) -> MappingCheck:
    """Compare the mapping with a document and report everything at once.

    A missing table or a missing required column is an error for that table.
    An unmapped column that exists in the document is reported too, so
    nothing in the document is silently left behind.
    """
    findings: list[MappingFinding] = []
    usable: set[str] = set()
    mapped_grist_tables: set[str] = set()

    for spec in SPECS:
        table_mapping = mapping.table(spec.name)
        if table_mapping is None:
            if spec.required:
                findings.append(
                    MappingFinding(
                        "fout", spec.name, "Geen Grist-tabel opgegeven in de koppeling."
                    )
                )
            continue
        mapped_grist_tables.add(table_mapping.grist_table)
        table = document.table(table_mapping.grist_table)
        if table is None:
            severity = "fout" if spec.required else "info"
            findings.append(
                MappingFinding(
                    severity,
                    spec.name,
                    f"Tabel {table_mapping.grist_table} staat niet in het document.",
                )
            )
            continue

        table_ok = True
        present = {c.col_id for c in table.columns}
        for field_spec in spec.fields:
            col_id = table_mapping.col(field_spec.name)
            if col_id is None:
                if field_spec.required:
                    table_ok = False
                    findings.append(
                        MappingFinding(
                            "fout",
                            spec.name,
                            f"Verplicht veld '{field_spec.name}' heeft geen kolom "
                            "in de koppeling.",
                        )
                    )
                continue
            if col_id not in present:
                severity = "fout" if field_spec.required else "waarschuwing"
                if field_spec.required:
                    table_ok = False
                findings.append(
                    MappingFinding(
                        severity,
                        spec.name,
                        f"Kolom {table_mapping.grist_table}.{col_id} (veld "
                        f"'{field_spec.name}') staat niet in het document.",
                    )
                )
        mapped_cols = set(table_mapping.columns.values())
        for column in table.user_columns:
            if column.col_id not in mapped_cols:
                kind = "formule" if column.is_formula else column.type
                findings.append(
                    MappingFinding(
                        "info",
                        spec.name,
                        f"Kolom {table.table_id}.{column.col_id} ({kind}) is niet "
                        "gekoppeld en wordt niet gelezen.",
                    )
                )
        if not table_mapping.verified:
            findings.append(
                MappingFinding(
                    "waarschuwing",
                    spec.name,
                    f"De koppeling van {table_mapping.grist_table} is nog niet "
                    "bevestigd (verified = false).",
                )
            )
        if table_ok:
            usable.add(spec.name)

    for table in document.tables:
        if table.table_id not in mapped_grist_tables and not table.is_summary:
            findings.append(
                MappingFinding(
                    "info",
                    "-",
                    f"Tabel {table.table_id} (rijen: {table.row_count}) is niet "
                    "gekoppeld en wordt niet gelezen.",
                )
            )
    return MappingCheck(tuple(findings), frozenset(usable))


def unverified_tables(mapping: Mapping, names: frozenset[str] | set[str]) -> list[str]:
    return sorted(
        name
        for name in names
        if (table := mapping.table(name)) is not None and not table.verified
    )
