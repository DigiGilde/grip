"""From a Grist document to an import plan.

Reads the mapped tables, proposes what free text means, applies the
decisions from the confirmation list, and produces a plan: plain records
for the loader, the figures Grist computed (for the reconciliation), a
fresh confirmation list, and every problem found along the way. Nothing
here touches the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from grip.importers.grist.confirmation import (
    KIND_LINE,
    KIND_PERSON,
    KIND_SCALE,
    PERSON_LOAD,
    PERSON_SKIP,
    ConfirmationError,
    ConfirmationItem,
    ConfirmationList,
)
from grip.importers.grist.document import (
    CellError,
    GristColumn,
    GristDocument,
    GristRow,
    Undecoded,
)
from grip.importers.grist.freetext import (
    FIXED,
    HIGH,
    LOW,
    PERSONNEL,
    LineProposal,
    assignment_year,
    parse_budget_line,
    parse_scale_note,
)
from grip.importers.grist.mapping import Mapping, MappingCheck, TableMapping

ERROR = "fout"
WARNING = "waarschuwing"
INFO = "info"

CATEGORIES = ("A", "B", "C", "D", "E")
PLACEHOLDER_EMAIL_DOMAIN = "import.invalid"

_PLACEHOLDER_NAME = re.compile(
    r"(#\s*\d+|^\s*(vacature|tbd|n\.?n\.?b\.?|nnb|nog in te vullen|open)\b|\(open\))",
    re.I,
)


@dataclass(frozen=True)
class Issue:
    severity: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.where}: {self.message}"


@dataclass(frozen=True)
class PlanPerson:
    row_id: int
    name: str
    email: str
    active: bool
    manager_row: int | None
    placeholder_email: bool


@dataclass(frozen=True)
class PlanScale:
    person_row: int
    billing_scale: int
    valid_from: date


@dataclass(frozen=True)
class PlanTarget:
    person_row: int
    year: int
    target_pct: Decimal


@dataclass(frozen=True)
class PlanAssignment:
    row_id: int
    name: str
    year: int
    kind: str
    status: str
    client_contact: str | None
    owner_row: int | None
    quoted_amount_cents: int | None
    start_date: date
    end_date: date
    notes: str | None


@dataclass(frozen=True)
class PlanLine:
    row_id: int
    assignment_row: int
    description: str
    kind: str
    position: int
    confirmed: bool
    role: str | None = None
    fte: Decimal | None = None
    rate_category: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount_cents: int | None = None
    year: int | None = None


@dataclass(frozen=True)
class PlanAllocation:
    row_id: int
    person_row: int
    line_row: int
    start_date: date
    end_date: date
    fte_pct: Decimal


@dataclass(frozen=True)
class PlanCostItem:
    row_id: int
    description: str
    budgeted_cents: int


@dataclass(frozen=True)
class PlanInvoiceLine:
    row_id: int
    cost_row: int
    reference: str | None
    description: str | None
    kind: str
    amount_cents: int
    period: date | None


@dataclass(frozen=True)
class PlanCoverage:
    row_id: int
    cost_row: int
    line_row: int
    pct: Decimal


@dataclass
class GristFigures:
    """Amounts the Grist document computed, in cents, keyed by Grist row id."""

    assignments: dict[int, dict[str, int]] = field(default_factory=dict)
    lines: dict[int, dict[str, int]] = field(default_factory=dict)
    allocations: dict[int, int] = field(default_factory=dict)
    cost_items: dict[int, dict[str, int]] = field(default_factory=dict)
    coverages: dict[int, int] = field(default_factory=dict)
    kpi: dict[int, dict[str, int]] = field(default_factory=dict)


@dataclass
class ImportPlan:
    year: int
    rate_bands: dict[str, int] = field(default_factory=dict)
    scale_bands: dict[int, str] = field(default_factory=dict)
    persons: list[PlanPerson] = field(default_factory=list)
    scales: list[PlanScale] = field(default_factory=list)
    targets: list[PlanTarget] = field(default_factory=list)
    assignments: list[PlanAssignment] = field(default_factory=list)
    lines: list[PlanLine] = field(default_factory=list)
    allocations: list[PlanAllocation] = field(default_factory=list)
    cost_items: list[PlanCostItem] = field(default_factory=list)
    invoice_lines: list[PlanInvoiceLine] = field(default_factory=list)
    coverages: list[PlanCoverage] = field(default_factory=list)
    figures: GristFigures = field(default_factory=GristFigures)
    confirmations: ConfirmationList = field(
        default_factory=lambda: ConfirmationList(document="")
    )
    issues: list[Issue] = field(default_factory=list)
    # Grist table id per logical table, for references and messages.
    grist_tables: dict[str, str] = field(default_factory=dict)
    # Names for the reports, keyed by Grist row id.
    person_names: dict[int, str] = field(default_factory=dict)
    skipped_persons: set[int] = field(default_factory=set)
    unconfirmed: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == ERROR]

    def counts(self) -> dict[str, int]:
        return {
            "tarieven (categorieën)": len(self.rate_bands),
            "schalen in de tarievenkaart": len(self.scale_bands),
            "personen": len(self.persons),
            "inzetschalen": len(self.scales),
            "KPI-targets": len(self.targets),
            "opdrachten": len(self.assignments),
            "begrotingsregels": len(self.lines),
            "inzet": len(self.allocations),
            "kostenposten": len(self.cost_items),
            "factuurregels": len(self.invoice_lines),
            "kostendekking": len(self.coverages),
        }


# -- value helpers ------------------------------------------------------------


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def to_text(value: Any) -> str | None:
    if _blank(value) or isinstance(value, CellError | Undecoded):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def to_decimal(value: Any) -> Decimal | None:
    if _blank(value) or isinstance(value, CellError | Undecoded | bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    text = str(value).strip().replace("€", "").replace("%", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def to_cents(value: Any) -> int | None:
    amount = to_decimal(value)
    if amount is None:
        return None
    return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_int(value: Any) -> int | None:
    number = to_decimal(value)
    if number is None or number != number.to_integral_value():
        return None
    return int(number)


def to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for parser in (date.fromisoformat,):
            try:
                return parser(text[:10])
            except ValueError:
                pass
        match = re.fullmatch(r"(\d{1,2})-(\d{1,2})-(\d{4})", text)
        if match:
            try:
                return date(int(match[3]), int(match[2]), int(match[1]))
            except ValueError:
                return None
    return None


def to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in ("ja", "true", "waar", "x", "1", "persoon"):
            return True
        if text in ("nee", "false", "onwaar", "", "0", "anders"):
            return False
    return None


def normalise(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


# -- reading ------------------------------------------------------------------


class _Source:
    """One mapped Grist table with its rows."""

    def __init__(self, document: GristDocument, mapping: TableMapping) -> None:
        self.mapping = mapping
        self.grist_table = mapping.grist_table
        table = document.table(mapping.grist_table)
        assert table is not None
        self.table = table
        self.rows = document.rows(mapping.grist_table)
        self.row_ids = {row.row_id for row in self.rows}

    def value(self, row: GristRow, field_name: str) -> Any:
        col_id = self.mapping.col(field_name)
        if col_id is None or self.table.column(col_id) is None:
            return None
        return row.get(col_id)

    def column(self, field_name: str) -> GristColumn | None:
        col_id = self.mapping.col(field_name)
        return self.table.column(col_id) if col_id else None

    def has(self, field_name: str) -> bool:
        return self.column(field_name) is not None

    def where(self, row: GristRow) -> str:
        return f"{self.grist_table} rij {row.row_id}"


class _Builder:
    def __init__(
        self,
        document: GristDocument,
        mapping: Mapping,
        check: MappingCheck,
        confirmations: ConfirmationList | None,
        year: int,
    ) -> None:
        self.document = document
        self.mapping = mapping
        self.check = check
        self.given = confirmations
        self.plan = ImportPlan(year=year)
        self.plan.confirmations = ConfirmationList(document=document.path.name)
        self.sources: dict[str, _Source] = {}
        for name in check.usable_tables:
            table_mapping = mapping.table(name)
            if table_mapping is not None:
                self.sources[name] = _Source(document, table_mapping)
                self.plan.grist_tables[name] = table_mapping.grist_table
        self._name_index: dict[str, dict[str, list[int]]] = {}
        self._assignment_years: dict[int, int] = {}
        self._line_rows: set[int] = set()
        self._personnel_lines: set[int] = set()
        self._unconfirmed_lines: set[int] = set()

    # -- shared ---------------------------------------------------------------

    def issue(self, severity: str, where: str, message: str) -> None:
        self.plan.issues.append(Issue(severity, where, message))

    def _fits(
        self, source: _Source, row: GristRow, what: str, text: str | None, limit: int
    ) -> None:
        """A text that grip has no room for stops the import before it writes.

        Without this the database refuses the row halfway through the load,
        with an error that names neither the table nor the row in Grist.
        """
        if text is not None and len(text) > limit:
            self.issue(
                ERROR,
                source.where(row),
                f"{what} is {len(text)} tekens lang; grip bewaart er hooguit "
                f"{limit}. Kort de tekst in Grist in.",
            )

    def _cell_problem(self, source: _Source, row: GristRow, field_name: str) -> bool:
        value = source.value(row, field_name)
        if isinstance(value, CellError):
            self.issue(
                WARNING,
                source.where(row),
                f"Veld '{field_name}' bevat een formulefout ({value}).",
            )
            return True
        if isinstance(value, Undecoded):
            self.issue(
                WARNING,
                source.where(row),
                f"Veld '{field_name}' bevat een waarde die niet te lezen is.",
            )
            return True
        return False

    def _index(self, target: str, name_field: str) -> dict[str, list[int]]:
        key = f"{target}.{name_field}"
        if key not in self._name_index:
            index: dict[str, list[int]] = {}
            source = self.sources.get(target)
            if source is not None:
                for row in source.rows:
                    text = to_text(source.value(row, name_field))
                    if text:
                        index.setdefault(normalise(text), []).append(row.row_id)
            self._name_index[key] = index
        return self._name_index[key]

    def _resolve(
        self,
        source: _Source,
        row: GristRow,
        field_name: str,
        target: str,
        name_field: str,
    ) -> list[int]:
        """Row ids in the target table that a reference cell points at.

        Handles a reference, a reference list, and a name typed as text.
        """
        value = source.value(row, field_name)
        if _blank(value) or isinstance(value, CellError | Undecoded):
            return []
        target_source = self.sources.get(target)
        if target_source is None:
            return []
        column = source.column(field_name)
        is_ref = column is not None and column.base_type in ("Ref", "RefList")
        candidates = value if isinstance(value, list) else [value]
        found: list[int] = []
        for candidate in candidates:
            if (
                is_ref
                and isinstance(candidate, int | float)
                and not isinstance(candidate, bool)
            ):
                row_id = int(candidate)
                if row_id == 0:
                    continue
                if row_id in target_source.row_ids:
                    found.append(row_id)
                else:
                    self.issue(
                        WARNING,
                        source.where(row),
                        f"Veld '{field_name}' verwijst naar rij {row_id} van "
                        f"{target_source.grist_table}, die niet bestaat.",
                    )
                continue
            text = to_text(candidate)
            if not text:
                continue
            matches = self._index(target, name_field).get(normalise(text), [])
            if len(matches) == 1:
                found.append(matches[0])
            elif not matches:
                self.issue(
                    WARNING,
                    source.where(row),
                    f"'{text}' (veld '{field_name}') is niet gevonden in "
                    f"{target_source.grist_table}.",
                )
            else:
                self.issue(
                    WARNING,
                    source.where(row),
                    f"'{text}' (veld '{field_name}') komt {len(matches)} keer voor "
                    f"in {target_source.grist_table}; niet gekoppeld.",
                )
        return found

    def _percent_scale(self, source: _Source, field_name: str, what: str) -> Decimal:
        """1 or 100: whether a percentage column holds fractions."""
        values = [
            number
            for row in source.rows
            if (number := to_decimal(source.value(row, field_name))) is not None
        ]
        if values and max(values) <= 1:
            self.issue(
                INFO,
                source.grist_table,
                f"{what} staat als fractie (0 tot 1) en wordt met 100 vermenigvuldigd.",
            )
            return Decimal(100)
        return Decimal(1)

    def _item(self, item: ConfirmationItem) -> None:
        self.plan.confirmations.items.append(item)

    # -- rates ----------------------------------------------------------------

    def rates(self) -> None:
        source = self.sources.get("rates")
        if source is None:
            return
        for row in source.rows:
            category = (to_text(source.value(row, "category")) or "").upper()
            scale = to_int(source.value(row, "scale"))
            rate = to_cents(source.value(row, "monthly_rate"))
            if not category and scale is None and rate is None:
                continue
            # "Categorie D" and "D" both name category D.
            match = re.search(r"\b([A-E])\b", category)
            category = match.group(1) if match else category
            if category not in CATEGORIES:
                self.issue(
                    ERROR, source.where(row), f"Onbekende tariefcategorie '{category}'."
                )
                continue
            if rate is None:
                self.issue(ERROR, source.where(row), "Maandtarief ontbreekt.")
                continue
            known = self.plan.rate_bands.get(category)
            if known is not None and known != rate:
                self.issue(
                    ERROR,
                    source.where(row),
                    f"Categorie {category} heeft twee verschillende maandtarieven.",
                )
                continue
            self.plan.rate_bands[category] = rate
            if scale is None:
                self.issue(
                    WARNING, source.where(row), "Schaal ontbreekt of is geen getal."
                )
                continue
            if (
                scale in self.plan.scale_bands
                and self.plan.scale_bands[scale] != category
            ):
                self.issue(
                    ERROR,
                    source.where(row),
                    f"Schaal {scale} staat bij twee categorieën.",
                )
                continue
            self.plan.scale_bands[scale] = category

    # -- team -----------------------------------------------------------------

    def team(self) -> None:
        source = self.sources.get("team")
        if source is None:
            return
        year = self.plan.year
        pct_scale = (
            self._percent_scale(source, "target_pct", "Het KPI-target")
            if source.has("target_pct")
            else Decimal(1)
        )
        for row in source.rows:
            name = to_text(source.value(row, "name"))
            if not name:
                continue
            self.plan.person_names[row.row_id] = name
            key = f"{KIND_PERSON}:{row.row_id}"
            column_email = to_text(source.value(row, "email"))
            looks_placeholder = bool(_PLACEHOLDER_NAME.search(name))
            remarks = []
            if looks_placeholder:
                remarks.append(
                    "De naam lijkt een plaatshouder voor een onbezette rol; "
                    "voorgesteld om over te slaan."
                )
            if not column_email and not looks_placeholder:
                remarks.append(
                    "Geen e-mailadres in Grist. Vul het in bij 'values'; zonder "
                    "adres kan deze persoon niet inloggen."
                )
            proposal = {
                "action": PERSON_SKIP if looks_placeholder else PERSON_LOAD,
                "email": column_email or "",
            }
            self._item(
                ConfirmationItem(
                    key=key,
                    kind=KIND_PERSON,
                    label=name,
                    source={"naam": name, "email": column_email or ""},
                    proposal=proposal,
                    confidence=HIGH if (column_email or looks_placeholder) else LOW,
                    remarks=remarks,
                )
            )

            decision = self._decision(
                lambda k=key: self.given.person(k) if self.given else None
            )
            if decision is None:
                self.plan.unconfirmed.append(key)
                load, email = not looks_placeholder, column_email
            else:
                load, email = decision.load, decision.email or column_email
            if not load:
                self.plan.skipped_persons.add(row.row_id)
                continue

            active = (
                to_bool(source.value(row, "active")) if source.has("active") else True
            )
            managers = self._resolve(source, row, "manager", "team", "name")
            self.plan.persons.append(
                PlanPerson(
                    row_id=row.row_id,
                    name=name,
                    email=email
                    or f"grist-team-{row.row_id}@{PLACEHOLDER_EMAIL_DOMAIN}",
                    active=True if active is None else active,
                    manager_row=managers[0] if managers else None,
                    placeholder_email=not email,
                )
            )
            if not email:
                self.issue(
                    WARNING,
                    source.where(row),
                    f"{name} heeft geen e-mailadres en krijgt een plaatshouder; "
                    "inloggen kan pas na aanpassen in grip.",
                )

            # Billing scale: from the scale column and the note.
            scale_key = f"{KIND_SCALE}:{row.row_id}"
            note = to_text(source.value(row, "note"))
            scale_column = to_int(source.value(row, "scale"))
            proposed = parse_scale_note(note, scale_column, year)
            self._item(
                ConfirmationItem(
                    key=scale_key,
                    kind=KIND_SCALE,
                    label=name,
                    source={"schaal": scale_column, "notitie": note or ""},
                    proposal={
                        "billing_scale": proposed.billing_scale,
                        "valid_from": _iso(proposed.valid_from),
                    },
                    confidence=proposed.confidence,
                    remarks=list(proposed.remarks),
                )
            )
            scale_decision = self._decision(
                lambda k=scale_key: self.given.scale(k) if self.given else None
            )
            if scale_decision is None:
                self.plan.unconfirmed.append(scale_key)
            elif scale_decision.billing_scale is not None:
                self.plan.scales.append(
                    PlanScale(
                        person_row=row.row_id,
                        billing_scale=scale_decision.billing_scale,
                        valid_from=scale_decision.valid_from or date(year, 1, 1),
                    )
                )

            target = to_decimal(source.value(row, "target_pct"))
            if target is not None:
                self.plan.targets.append(
                    PlanTarget(row.row_id, year, target * pct_scale)
                )
            figures: dict[str, int] = {}
            for field_name, label in (
                ("kpi_target_amount", "target"),
                ("kpi_realisation", "realisation"),
            ):
                cents = to_cents(source.value(row, field_name))
                if cents is not None:
                    figures[label] = cents
            if figures:
                self.plan.figures.kpi[row.row_id] = figures

    def _decision(self, getter: Any) -> Any:
        try:
            return getter()
        except ConfirmationError as exc:
            self.issue(ERROR, "bevestigingslijst", str(exc))
            return None

    def kpi(self) -> None:
        source = self.sources.get("kpi")
        if source is None or "team" not in self.sources:
            return
        pct_scale = (
            self._percent_scale(source, "target_pct", "Het KPI-target")
            if source.has("target_pct")
            else Decimal(1)
        )
        have_target = {target.person_row for target in self.plan.targets}
        for row in source.rows:
            persons = self._resolve(source, row, "person", "team", "name")
            if not persons:
                continue
            person_row = persons[0]
            if person_row in self.plan.skipped_persons:
                continue
            target = to_decimal(source.value(row, "target_pct"))
            if target is not None and person_row not in have_target:
                self.plan.targets.append(
                    PlanTarget(person_row, self.plan.year, target * pct_scale)
                )
                have_target.add(person_row)
            figures = self.plan.figures.kpi.setdefault(person_row, {})
            for field_name, label in (
                ("target_amount", "target"),
                ("realisation", "realisation"),
            ):
                cents = to_cents(source.value(row, field_name))
                if cents is not None:
                    figures.setdefault(label, cents)

    # -- assignments ----------------------------------------------------------

    def assignments(self) -> None:
        source = self.sources.get("assignments")
        if source is None:
            return
        for row in source.rows:
            name = to_text(source.value(row, "name"))
            if not name:
                continue
            self._fits(source, row, "De naam", name, 255)
            self._fits(
                source,
                row,
                "De contactpersoon",
                to_text(source.value(row, "client_contact")),
                255,
            )
            _, name_year = assignment_year(name)
            year = name_year or self.plan.year
            if name_year is None:
                self.issue(
                    INFO,
                    source.where(row),
                    f"'{name}' heeft geen jaar in de naam; {year} aangenomen.",
                )
            self._assignment_years[row.row_id] = year

            grist_status = to_text(source.value(row, "status"))
            status = self.mapping.grip_status(grist_status)
            if status is None:
                status = self.mapping.default_status
                if grist_status:
                    self.issue(
                        WARNING,
                        source.where(row),
                        f"Status '{grist_status}' staat niet in de koppeling; "
                        f"'{status}' gebruikt.",
                    )
            kind = "internal" if self.mapping.is_internal(grist_status) else "external"

            notes = []
            if text := to_text(source.value(row, "notes")):
                notes.append(text)
            if grist_status:
                notes.append(f"Status in Grist: {grist_status}.")
            if quote_date := to_date(source.value(row, "quote_date")):
                notes.append(f"Offertedatum in Grist: {quote_date.isoformat()}.")

            owners = self._resolve(source, row, "owner", "team", "name")
            owner = owners[0] if owners else None
            if owner in self.plan.skipped_persons:
                owner = None
            self.plan.assignments.append(
                PlanAssignment(
                    row_id=row.row_id,
                    name=name,
                    year=year,
                    kind=kind,
                    status=status,
                    client_contact=to_text(source.value(row, "client_contact")),
                    owner_row=owner,
                    quoted_amount_cents=to_cents(source.value(row, "amount")),
                    start_date=to_date(source.value(row, "start_date"))
                    or date(year, 1, 1),
                    end_date=to_date(source.value(row, "end_date"))
                    or date(year, 12, 31),
                    notes=" ".join(notes) or None,
                )
            )
            figures = {
                label: cents
                for label in ("budgeted", "used", "available")
                if (cents := to_cents(source.value(row, label))) is not None
            }
            if figures:
                self.plan.figures.assignments[row.row_id] = figures

    # -- budget lines ---------------------------------------------------------

    def budget_lines(self) -> None:
        source = self.sources.get("budget_lines")
        if source is None or "assignments" not in self.sources:
            return
        positions: dict[int, int] = {}
        known_assignments = {a.row_id for a in self.plan.assignments}
        for row in source.rows:
            description = to_text(source.value(row, "description"))
            assignments = self._resolve(
                source, row, "assignment", "assignments", "name"
            )
            if not description and not assignments:
                continue
            if not assignments:
                self.issue(
                    ERROR,
                    source.where(row),
                    "Begrotingsregel zonder opdracht; niet geladen.",
                )
                continue
            if len(assignments) > 1:
                self.issue(
                    WARNING,
                    source.where(row),
                    f"De regel hangt aan {len(assignments)} opdrachten; alleen de "
                    "eerste is gebruikt.",
                )
            assignment_row = assignments[0]
            if assignment_row not in known_assignments:
                continue
            self._cell_problem(source, row, "budgeted")
            year = self._assignment_years.get(assignment_row, self.plan.year)
            budgeted = to_cents(source.value(row, "budgeted"))
            description = description or "(geen omschrijving)"
            self._fits(source, row, "De omschrijving", description, 500)
            positions[assignment_row] = positions.get(assignment_row, 0) + 1
            position = positions[assignment_row]

            proposed = parse_budget_line(
                description,
                year=year,
                budgeted_cents=budgeted,
                scale_to_category=self.plan.scale_bands,
                column_fte=to_decimal(source.value(row, "fte")),
                column_scale=to_int(source.value(row, "scale")),
                column_start=to_date(source.value(row, "start_date")),
                column_end=to_date(source.value(row, "end_date")),
                column_is_person=(
                    to_bool(source.value(row, "is_person"))
                    if source.has("is_person")
                    else None
                ),
            )
            proposed = self._against_budget(proposed, budgeted)
            key = f"{KIND_LINE}:{row.row_id}"
            proposal = {
                "kind": proposed.kind,
                "role": proposed.role,
                "fte": str(proposed.fte) if proposed.fte is not None else None,
                "rate_category": proposed.rate_category,
                "start_date": _iso(proposed.start_date),
                "end_date": _iso(proposed.end_date),
                "amount_cents": proposed.amount_cents,
                "year": proposed.year,
            }
            remarks = list(proposed.remarks)
            if proposed.scale_low is not None:
                band = (
                    f"{proposed.scale_low}/{proposed.scale_high}"
                    if proposed.scale_high not in (None, proposed.scale_low)
                    else str(proposed.scale_low)
                )
                remarks.append(f"Schaal in de bron: {band}.")
            if not proposed.complete:
                remarks.append("Het voorstel is onvolledig; vul 'values' aan.")
            self._item(
                ConfirmationItem(
                    key=key,
                    kind=KIND_LINE,
                    label=description,
                    source={"omschrijving": description, "begroot_centen": budgeted},
                    proposal=proposal,
                    confidence=proposed.confidence if proposed.complete else LOW,
                    remarks=remarks,
                )
            )

            decision = self._decision(
                lambda k=key: self.given.line(k) if self.given else None
            )
            self._line_rows.add(row.row_id)
            if decision is None:
                # Unconfirmed: the text stays text. The line can only be
                # loaded as a fixed amount, and only when that is allowed.
                self.plan.unconfirmed.append(key)
                self._unconfirmed_lines.add(row.row_id)
                self.plan.lines.append(
                    PlanLine(
                        row_id=row.row_id,
                        assignment_row=assignment_row,
                        description=description,
                        kind=FIXED,
                        position=position,
                        confirmed=False,
                        amount_cents=budgeted or 0,
                        year=year,
                    )
                )
            elif decision.kind == PERSONNEL:
                self._personnel_lines.add(row.row_id)
                self.plan.lines.append(
                    PlanLine(
                        row_id=row.row_id,
                        assignment_row=assignment_row,
                        description=description,
                        kind=PERSONNEL,
                        position=position,
                        confirmed=True,
                        role=decision.role,
                        fte=decision.fte,
                        rate_category=decision.rate_category,
                        start_date=decision.start_date,
                        end_date=decision.end_date,
                    )
                )
            else:
                self.plan.lines.append(
                    PlanLine(
                        row_id=row.row_id,
                        assignment_row=assignment_row,
                        description=description,
                        kind=FIXED,
                        position=position,
                        confirmed=True,
                        amount_cents=decision.amount_cents,
                        year=decision.year,
                    )
                )
            figures = {
                label: cents
                for label in ("budgeted", "used", "available")
                if (cents := to_cents(source.value(row, label))) is not None
            }
            if figures:
                self.plan.figures.lines[row.row_id] = figures

    def _against_budget(
        self, proposed: LineProposal, budgeted: int | None
    ) -> LineProposal:
        """Compare a personnel proposal with the budgeted amount in Grist.

        R4 says budgeted is FTE times monthly rate times months. When the
        description names no FTE, the amount tells what it must have been;
        when it does, a difference is worth a remark.
        """
        if (
            proposed.kind != PERSONNEL
            or not budgeted
            or proposed.rate_category is None
            or proposed.start_date is None
            or proposed.end_date is None
            or proposed.fte is None
        ):
            return proposed
        rate = self.plan.rate_bands.get(proposed.rate_category)
        if not rate:
            return proposed
        months = (
            (proposed.end_date.year - proposed.start_date.year) * 12
            + proposed.end_date.month
            - proposed.start_date.month
            + 1
        )
        expected = int(proposed.fte * rate * months)
        if abs(expected - budgeted) < 100:
            return proposed
        assumed = any("aangenomen" in remark for remark in proposed.remarks)
        if assumed:
            implied = (Decimal(budgeted) / Decimal(rate * months)).quantize(
                Decimal("0.001")
            )
            if 0 < implied <= 2 and abs(int(implied * rate * months) - budgeted) < 100:
                remarks = tuple(
                    r for r in proposed.remarks if "aangenomen" not in r
                ) + (
                    f"Geen FTE genoemd; {implied.normalize()} FTE afgeleid uit het "
                    "begrote bedrag.",
                )
                return replace(proposed, fte=implied, remarks=remarks)
        return replace(
            proposed,
            confidence=LOW,
            remarks=(
                *proposed.remarks,
                f"Begroot in Grist ({budgeted / 100:.0f} euro) wijkt af van FTE maal "
                f"maandtarief maal {months} maanden ({expected / 100:.0f} euro).",
            ),
        )

    # -- allocations ----------------------------------------------------------

    def allocations(self) -> None:
        source = self.sources.get("allocations")
        if source is None or "team" not in self.sources:
            return
        pct_scale = self._percent_scale(source, "fte_pct", "Het inzetpercentage")
        loaded_persons = {p.row_id for p in self.plan.persons}
        for row in source.rows:
            persons = self._resolve(source, row, "person", "team", "name")
            lines = self._resolve(
                source, row, "budget_line", "budget_lines", "description"
            )
            start = to_date(source.value(row, "start_date"))
            end = to_date(source.value(row, "end_date"))
            pct = to_decimal(source.value(row, "fte_pct"))
            if not persons and not lines and start is None and pct is None:
                continue
            amount = to_cents(source.value(row, "amount"))
            if amount is not None:
                self.plan.figures.allocations[row.row_id] = amount
            self._cell_problem(source, row, "amount")
            problems = []
            if not persons:
                problems.append("persoon ontbreekt")
            if not lines:
                problems.append("begrotingsregel ontbreekt")
            if start is None or end is None:
                problems.append("begin- of einddatum ontbreekt")
            if pct is None:
                problems.append("percentage ontbreekt")
            if problems:
                self.issue(
                    ERROR,
                    source.where(row),
                    f"Inzet niet geladen: {', '.join(problems)}.",
                )
                continue
            assert start and end and pct is not None
            person_row, line_row = persons[0], lines[0]
            if person_row in self.plan.skipped_persons:
                self.issue(
                    WARNING,
                    source.where(row),
                    "Inzet van een overgeslagen persoon (plaatshouder); niet "
                    "geladen. Het bedrag telt in Grist wel mee in de uitputting.",
                )
                continue
            if person_row not in loaded_persons or line_row not in self._line_rows:
                continue
            if line_row in self._unconfirmed_lines:
                # The gate on unconfirmed items already says so, once.
                continue
            if line_row not in self._personnel_lines:
                self.issue(
                    WARNING,
                    source.where(row),
                    "Inzet op een regel die niet als personeelsregel is bevestigd; "
                    "niet geladen.",
                )
                continue
            if end < start:
                self.issue(ERROR, source.where(row), "Einddatum ligt voor begindatum.")
                continue
            percentage = pct * pct_scale
            if not 0 < percentage <= 100:
                self.issue(
                    ERROR,
                    source.where(row),
                    f"Percentage {percentage} ligt niet tussen 0 en 100.",
                )
                continue
            self.plan.allocations.append(
                PlanAllocation(row.row_id, person_row, line_row, start, end, percentage)
            )

    # -- costs ----------------------------------------------------------------

    def costs(self) -> None:
        source = self.sources.get("cost_items")
        if source is None:
            return
        for row in source.rows:
            description = to_text(source.value(row, "description"))
            if not description:
                continue
            self._fits(source, row, "De omschrijving", description, 500)
            self.plan.cost_items.append(
                PlanCostItem(
                    row.row_id,
                    description,
                    to_cents(source.value(row, "budgeted")) or 0,
                )
            )
            figures = {
                label: cents
                for label in ("forecast", "covered")
                if (cents := to_cents(source.value(row, label))) is not None
            }
            if figures:
                self.plan.figures.cost_items[row.row_id] = figures

    def invoice_lines(self) -> None:
        source = self.sources.get("invoice_lines")
        if source is None or "cost_items" not in self.sources:
            return
        known = {c.row_id for c in self.plan.cost_items}
        for row in source.rows:
            amount = to_cents(source.value(row, "amount"))
            costs = self._resolve(source, row, "cost_item", "cost_items", "description")
            if amount is None and not costs:
                continue
            if amount is None or not costs or costs[0] not in known:
                self.issue(
                    ERROR,
                    source.where(row),
                    "Factuurregel niet geladen: bedrag of kostenpost ontbreekt.",
                )
                continue
            raw_kind = source.value(row, "kind")
            if isinstance(raw_kind, bool):
                kind = "actual" if raw_kind else "estimate"
            else:
                text = to_text(raw_kind)
                kind = self.mapping.invoice_kind.get((text or "").casefold(), "")
                if not kind:
                    kind = "actual"
                    if source.has("kind"):
                        self.issue(
                            WARNING,
                            source.where(row),
                            f"Soort '{text or ''}' staat niet in de koppeling; "
                            "als realisatie geladen.",
                        )
            period = to_date(source.value(row, "period"))
            self._fits(
                source,
                row,
                "De omschrijving",
                to_text(source.value(row, "description")),
                500,
            )
            self._fits(
                source, row, "Het kenmerk", to_text(source.value(row, "reference")), 100
            )
            self.plan.invoice_lines.append(
                PlanInvoiceLine(
                    row_id=row.row_id,
                    cost_row=costs[0],
                    reference=to_text(source.value(row, "reference")),
                    description=to_text(source.value(row, "description")),
                    kind=kind,
                    amount_cents=amount,
                    period=period.replace(day=1) if period else None,
                )
            )

    def coverages(self) -> None:
        source = self.sources.get("coverages")
        if source is None or "cost_items" not in self.sources:
            return
        pct_scale = self._percent_scale(source, "pct", "Het dekkingspercentage")
        known_costs = {c.row_id for c in self.plan.cost_items}
        for row in source.rows:
            costs = self._resolve(source, row, "cost_item", "cost_items", "description")
            lines = self._resolve(
                source, row, "budget_line", "budget_lines", "description"
            )
            pct = to_decimal(source.value(row, "pct"))
            if not costs and not lines and pct is None:
                continue
            amount = to_cents(source.value(row, "amount"))
            if amount is not None:
                self.plan.figures.coverages[row.row_id] = amount
            if not costs or not lines or pct is None:
                self.issue(
                    ERROR,
                    source.where(row),
                    "Kostendekking niet geladen: kostenpost, begrotingsregel of "
                    "percentage ontbreekt.",
                )
                continue
            if costs[0] not in known_costs or lines[0] not in self._line_rows:
                continue
            self.plan.coverages.append(
                PlanCoverage(row.row_id, costs[0], lines[0], pct * pct_scale)
            )

    def build(self) -> ImportPlan:
        self.rates()
        self.team()
        self.kpi()
        self.assignments()
        self.budget_lines()
        self.allocations()
        self.costs()
        self.invoice_lines()
        self.coverages()
        if not self.plan.rate_bands and "rates" in self.sources:
            self.issue(
                ERROR, self.sources["rates"].grist_table, "Geen tarieven gelezen."
            )
        return self.plan


def build_plan(
    document: GristDocument,
    mapping: Mapping,
    check: MappingCheck,
    *,
    confirmations: ConfirmationList | None = None,
    year: int | None = None,
) -> ImportPlan:
    """Read the document into a plan. Does not touch the database."""
    return _Builder(
        document, mapping, check, confirmations, year or mapping.rate_card_year
    ).build()
