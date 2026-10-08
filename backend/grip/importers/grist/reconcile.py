"""Reconciliation: what Grist computed next to what grip computes.

For every assignment, budget line, allocation, cost item and KPI the report
puts the amount from the Grist snapshot next to grip's own calculation on
the loaded data. "Equal to the euro" means the two differ by less than half
a euro.

Two questions in docs/domein.md are open until the real data answers them:
how a partial month is priced, and whether a coverage percentage applies to
the forecast or to the budgeted amount. The report therefore runs every
combination of those options and says which one reconciles best.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.calc import CoverageBasis, PartialMonths
from grip.importers.grist.load import LoadResult
from grip.importers.grist.transform import ImportPlan
from grip.services import pricing
from grip.services.errors import DomainError

# Half a euro, in cents: amounts that round to the same euro are equal.
TOLERANCE_CENTS = 50

G_ASSIGNMENT = "opdracht"
G_LINE = "begrotingsregel"
G_ALLOCATION = "inzet"
G_COST = "kostenpost"
G_KPI = "KPI"

_MEASURES = {
    "budgeted": "begroot",
    "used": "uitputting",
    "available": "beschikbaar",
    "forecast": "prognose",
    "covered": "dekking",
    "target": "target",
    "realisation": "realisatie",
    "amount": "inzetbedrag",
}


@dataclass(frozen=True)
class Row:
    group: str
    label: str
    measure: str
    grist_cents: int
    grip_cents: int | None
    note: str = ""

    @property
    def difference(self) -> int | None:
        if self.grip_cents is None:
            return None
        return self.grip_cents - self.grist_cents

    @property
    def matches(self) -> bool:
        difference = self.difference
        return difference is not None and abs(difference) < TOLERANCE_CENTS


@dataclass
class Variant:
    partial_months: PartialMonths
    coverage_basis: CoverageBasis
    rows: list[Row] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.partial_months.value} / {self.coverage_basis.value}"

    @property
    def differing(self) -> list[Row]:
        return [row for row in self.rows if not row.matches]

    @property
    def absolute_difference(self) -> int:
        return sum(abs(row.difference or row.grist_cents) for row in self.differing)

    def score(self) -> tuple[int, int]:
        return (len(self.differing), self.absolute_difference)


@dataclass
class ReconciliationReport:
    variants: list[Variant]
    default: tuple[PartialMonths, CoverageBasis]
    not_loaded: list[str] = field(default_factory=list)

    @property
    def compared(self) -> int:
        return len(self.variants[0].rows) if self.variants else 0

    @property
    def best(self) -> Variant | None:
        if not self.variants or not self.compared:
            return None
        return min(
            self.variants, key=lambda v: (*v.score(), _preference(v, self.default))
        )

    @property
    def default_variant(self) -> Variant | None:
        for variant in self.variants:
            if (variant.partial_months, variant.coverage_basis) == self.default:
                return variant
        return None

    @property
    def reconciles(self) -> bool:
        best = self.best
        return best is not None and not best.differing


def _preference(variant: Variant, default: tuple[PartialMonths, CoverageBasis]) -> int:
    """Ties go to the current default, so the report does not suggest a change
    the data does not ask for."""
    return 0 if (variant.partial_months, variant.coverage_basis) == default else 1


def explain(exc: Exception) -> str:
    """Why grip could not compute an amount, in the words of the screens."""
    if isinstance(exc, calc.MissingRateCardError):
        return (
            f"geen actieve tarievenkaart voor {exc.year}; maak die aan onder "
            "Tarieven en sluit opnieuw aan"
        )
    if isinstance(exc, calc.MissingRateError):
        return (
            f"tarievenkaart {exc.year} heeft geen tarief voor categorie {exc.category}"
        )
    if isinstance(exc, calc.MissingScaleBandError):
        return f"tarievenkaart {exc.year} koppelt schaal {exc.scale} aan geen categorie"
    if isinstance(exc, calc.MissingPersonScaleError):
        return f"de persoon heeft geen inzetschaal op {exc.day.isoformat()}"
    return str(exc)


def _label(text: str, row_id: int) -> str:
    return f"{text} (rij {row_id})"


async def _variant(
    session: AsyncSession,
    plan: ImportPlan,
    loaded: LoadResult,
    partial_months: PartialMonths,
    coverage_basis: CoverageBasis,
) -> Variant:
    variant = Variant(partial_months, coverage_basis)
    options = pricing.PricingOptions(
        partial_months=partial_months, coverage_basis=coverage_basis
    )
    figures = plan.figures
    lines_by_row = {line.row_id: line for line in plan.lines}
    line_overviews: dict[UUID, pricing.LineOverview] = {}
    allocation_amounts: dict[str, int | str] = {}

    for assignment in plan.assignments:
        assignment_id = loaded.assignments.get(assignment.row_id)
        wanted = figures.assignments.get(assignment.row_id, {})
        if assignment_id is None:
            continue
        overview = None
        note = ""
        try:
            overview = await pricing.assignment_overview(
                session, assignment_id, options=options
            )
        except (calc.CalcError, DomainError) as exc:
            note = explain(exc)
        if overview is not None:
            for line in overview.lines:
                line_overviews[line.budget_line_id] = line
        try:
            inputs = await pricing.load_inputs_for_assignment(
                session, assignment_id, options=options
            )
        except (calc.CalcError, DomainError):
            inputs = None
        if inputs is not None:
            for allocation in inputs.allocations:
                try:
                    allocation_amounts[allocation.id] = calc.allocation_amount(
                        allocation,
                        inputs.rates,
                        inputs.scales,
                        partial_months=partial_months,
                        actuals=inputs.actuals,
                    )
                except calc.CalcError as exc:
                    allocation_amounts[allocation.id] = explain(exc)
        for measure in ("budgeted", "used", "available"):
            if measure not in wanted:
                continue
            value = getattr(overview, f"{measure}_cents") if overview else None
            variant.rows.append(
                Row(
                    G_ASSIGNMENT,
                    _label(assignment.name, assignment.row_id),
                    _MEASURES[measure],
                    wanted[measure],
                    value,
                    note,
                )
            )

    for row_id, wanted in sorted(figures.lines.items()):
        plan_line = lines_by_row.get(row_id)
        line_id = loaded.lines.get(row_id)
        if plan_line is None or line_id is None:
            continue
        overview_line = line_overviews.get(line_id)
        note = (
            ""
            if plan_line.confirmed
            else "regel is niet bevestigd; als vast bedrag geladen"
        )
        for measure in ("budgeted", "used", "available"):
            if measure not in wanted:
                continue
            value = (
                getattr(overview_line, f"{measure}_cents") if overview_line else None
            )
            variant.rows.append(
                Row(
                    G_LINE,
                    _label(plan_line.description, row_id),
                    _MEASURES[measure],
                    wanted[measure],
                    value,
                    note if value is not None else "geen berekening mogelijk",
                )
            )

    for planned in plan.allocations:
        wanted_amount = figures.allocations.get(planned.row_id)
        allocation_id = loaded.allocations.get(planned.row_id)
        if wanted_amount is None or allocation_id is None:
            continue
        computed = allocation_amounts.get(str(allocation_id))
        person = plan.person_names.get(planned.person_row, "?")
        on_line = lines_by_row.get(planned.line_row)
        label = f"{person} op {on_line.description if on_line else '?'}"
        variant.rows.append(
            Row(
                G_ALLOCATION,
                _label(label, planned.row_id),
                _MEASURES["amount"],
                wanted_amount,
                computed if isinstance(computed, int) else None,
                computed if isinstance(computed, str) else "",
            )
        )

    for item in plan.cost_items:
        wanted = figures.cost_items.get(item.row_id, {})
        cost_id = loaded.cost_items.get(item.row_id)
        if cost_id is None or not wanted:
            continue
        forecast = covered = None
        note = ""
        try:
            on_forecast = await pricing.cost_item_coverage(
                session,
                cost_id,
                options=pricing.PricingOptions(coverage_basis=CoverageBasis.FORECAST),
            )
            forecast = on_forecast.basis_cents
            chosen = await pricing.cost_item_coverage(session, cost_id, options=options)
            covered = chosen.covered_cents
        except (calc.CalcError, DomainError) as exc:
            note = explain(exc)
        for measure, value in (("forecast", forecast), ("covered", covered)):
            if measure in wanted:
                variant.rows.append(
                    Row(
                        G_COST,
                        _label(item.description, item.row_id),
                        _MEASURES[measure],
                        wanted[measure],
                        value,
                        note,
                    )
                )

    for person_row, wanted in sorted(figures.kpi.items()):
        person_id = loaded.persons.get(person_row)
        if person_id is None:
            continue
        overview_kpi = None
        note = ""
        try:
            overview_kpi = await pricing.kpi_overview(
                session, person_id, plan.year, options=options
            )
        except (calc.CalcError, DomainError) as exc:
            note = explain(exc)
        name = plan.person_names.get(person_row, "?")
        if "target" in wanted:
            variant.rows.append(
                Row(
                    G_KPI,
                    _label(name, person_row),
                    _MEASURES["target"],
                    wanted["target"],
                    overview_kpi.target_cents if overview_kpi else None,
                    note,
                )
            )
        if "realisation" in wanted:
            variant.rows.append(
                Row(
                    G_KPI,
                    _label(name, person_row),
                    _MEASURES["realisation"],
                    wanted["realisation"],
                    overview_kpi.realisation_cents if overview_kpi else None,
                    note,
                )
            )
    return variant


async def reconcile(
    session: AsyncSession,
    plan: ImportPlan,
    loaded: LoadResult,
    *,
    default: tuple[PartialMonths, CoverageBasis] = (
        pricing.DEFAULT_OPTIONS.partial_months,
        pricing.DEFAULT_OPTIONS.coverage_basis,
    ),
) -> ReconciliationReport:
    """Compare under every combination of the two open options."""
    variants = [
        await _variant(session, plan, loaded, partial_months, coverage_basis)
        for partial_months in PartialMonths
        for coverage_basis in CoverageBasis
    ]
    not_loaded = []
    for assignment in plan.assignments:
        if assignment.row_id not in loaded.assignments:
            not_loaded.append(f"opdracht {assignment.name} (rij {assignment.row_id})")
    return ReconciliationReport(
        variants=variants, default=default, not_loaded=not_loaded
    )


# -- rendering ----------------------------------------------------------------


def euro(cents: int | None) -> str:
    if cents is None:
        return "-"
    sign = "-" if cents < 0 else ""
    whole, rest = divmod(abs(cents), 100)
    text = f"{whole:,}".replace(",", ".")
    return f"{sign}€ {text},{rest:02d}"


def _table(rows: list[Row]) -> list[str]:
    header = ("Soort", "Wat", "Maat", "Grist", "Grip", "Verschil", "Opmerking")
    body = [
        (
            row.group,
            row.label,
            row.measure,
            euro(row.grist_cents),
            euro(row.grip_cents),
            euro(row.difference),
            row.note,
        )
        for row in rows
    ]
    widths = [max(len(str(line[i])) for line in [header, *body]) for i in range(7)]
    right = {3, 4, 5}

    def fmt(line: tuple[str, ...]) -> str:
        cells = [
            str(cell).rjust(widths[i]) if i in right else str(cell).ljust(widths[i])
            for i, cell in enumerate(line)
        ]
        return "  ".join(cells).rstrip()

    return [
        fmt(header),
        "  ".join("-" * w for w in widths),
        *(fmt(line) for line in body),
    ]


def render(report: ReconciliationReport, *, all_rows: bool = False) -> str:
    lines = ["Aansluiting Grist en grip", "=" * 25, ""]
    best = report.best
    if best is None:
        lines += [
            "Er is niets vergeleken: de koppeling noemt geen kolommen met bedragen "
            "die Grist berekent (begroot, uitputting, prognose, dekking, KPI), of "
            "er is niets geladen.",
            "",
            "Uitkomst: NIET AANGETOOND.",
        ]
        return "\n".join(lines) + "\n"

    lines.append(
        f"Vergeleken waarden: {report.compared}. Gelijk betekent: minder dan "
        "een halve euro verschil."
    )
    lines.append("")
    lines.append("Per combinatie van de twee open rekenkeuzes:")
    lines.append("")
    name_width = max(len(v.name) for v in report.variants)
    for variant in sorted(report.variants, key=lambda v: v.score()):
        marks = []
        if variant is best:
            marks.append("sluit het best aan")
        if (variant.partial_months, variant.coverage_basis) == report.default:
            marks.append("huidige standaard in grip")
        suffix = f"  ({', '.join(marks)})" if marks else ""
        lines.append(
            f"  {variant.name.ljust(name_width)}  {len(variant.differing):>4} "
            f"afwijkend  som {euro(variant.absolute_difference)}{suffix}"
        )
    lines.append("")
    if (best.partial_months, best.coverage_basis) != report.default:
        default_variant = report.default_variant
        better = default_variant is None or best.score() < default_variant.score()
        if better:
            lines.append(
                "De best aansluitende combinatie is niet de standaard van grip. "
                f"Gedeeltelijke maanden: {best.partial_months.value}; "
                f"dekkingsgrondslag: {best.coverage_basis.value}. Leg dit besluit "
                "vast en pas de standaard aan voordat de cijfers in grip gelden."
            )
            lines.append("")
    shown = best.rows if all_rows else best.differing
    title = "Alle waarden" if all_rows else "Afwijkingen"
    lines.append(f"{title} bij {best.name}:")
    lines.append("")
    if shown:
        lines += _table(shown)
    else:
        lines.append("  geen")
    lines.append("")
    if report.not_loaded:
        lines.append("Niet geladen en dus niet vergeleken:")
        lines += [f"  {item}" for item in report.not_loaded]
        lines.append("")
    if report.reconciles:
        lines.append(
            f"Uitkomst: SLUIT AAN. Alle {report.compared} waarden zijn tot op de "
            f"euro gelijk bij {best.name}."
        )
    else:
        lines.append(
            f"Uitkomst: SLUIT NIET AAN. {len(best.differing)} van {report.compared} "
            f"waarden wijken af bij {best.name}."
        )
    return "\n".join(lines) + "\n"
