"""Investeerruimte: what the organisation has left to invest, in money and in time.

The definition is provisional (docs/domein.md, begrippenlijst) and is
therefore spelled out here and on the screen.

**In money**, for a year:

    expected turnover of external assignments (realised plus still planned,
        agreed formally or verbally; the pipeline is shown apart)
    minus the sum of the billability targets of the people
        (what each person must bring in)
    minus uncovered costs
    minus what internal assignments are budgeted to consume
    = investeerruimte; negative is a shortfall

**In time**, for this month and the three after it: the capacity that is
free, in FTE and valued at each person's billing rate of that month. It
assumes everyone is available full-time, since the model has no FTE factor
per person.

Nothing is priced here. Turnover comes from the steering read model, targets
from the pricing service (R13), budgets from its per-year split, uncovered
costs from the cost overview, and a billing rate from rule R1 through the
rate book the pricing service loads.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.calc import Month
from grip.models.assignment import Assignment
from grip.repositories.domain import PersonDetailRepository
from grip.services import pricing
from grip.services.outgoing_invoices import spread
from grip.services.phase import Commitment, commitment_of
from grip.services.pricing import DEFAULT_OPTIONS, PricingOptions
from grip.services.reports import steering

EXTERNAL = "external"
INTERNAL = "internal"

# Assignments that count: agreed formally or verbally.
_AGREED = (Commitment.COMMITTED, Commitment.VERBAL)


@dataclass(frozen=True)
class MoneyMonth:
    month: Month
    # Turnover of external assignments in this month.
    realised_cents: int
    planned_cents: int
    # The share of the year's targets that falls in this month.
    target_cents: int

    @property
    def turnover_minus_target_cents(self) -> int:
        return self.realised_cents + self.planned_cents - self.target_cents


@dataclass(frozen=True)
class MoneyReading:
    year: int
    # External assignments, agreed formally or verbally.
    realised_cents: int
    planned_cents: int
    # The part of what is planned that rests on a verbal agreement only.
    verbal_cents: int
    # Planned on external assignments that are not agreed yet. Not counted.
    pipeline_cents: int
    # The sum of the billability targets, and how many people it covers.
    target_cents: int
    target_person_count: int
    uncovered_cents: int
    # Budgeted for the year on internal assignments, and how many there are.
    internal_budget_cents: int
    internal_count: int
    months: tuple[MoneyMonth, ...]
    # Assignments left out because they could not be priced.
    unpriced: tuple[str, ...]

    @property
    def expected_cents(self) -> int:
        return self.realised_cents + self.planned_cents

    @property
    def room_cents(self) -> int:
        """Investeerruimte in money. Negative is a shortfall."""
        return (
            self.expected_cents
            - self.target_cents
            - self.uncovered_cents
            - self.internal_budget_cents
        )

    @property
    def room_with_pipeline_cents(self) -> int:
        """The same, if everything in the pipeline is agreed as planned."""
        return self.room_cents + self.pipeline_cents

    @property
    def shortfall(self) -> bool:
        return self.room_cents < 0


@dataclass(frozen=True)
class TimeMonth:
    month: Month
    available_fte: Decimal
    free_fte: Decimal
    # Free capacity valued at each person's billing rate of the month.
    value_cents: int
    # People with free capacity whose billing rate is unknown this month;
    # their free capacity is in the FTE and not in the value.
    unvalued_count: int


@dataclass(frozen=True)
class TimeReading:
    months: tuple[TimeMonth, ...]
    person_count: int

    @property
    def free_fte(self) -> Decimal:
        return sum((m.free_fte for m in self.months), Decimal(0))

    @property
    def value_cents(self) -> int:
        return sum(m.value_cents for m in self.months)


async def _agreed_ids_by_kind(session: AsyncSession) -> dict[str, list[UUID]]:
    """Ids of the assignments that count, external and internal apart.

    External assignments in the pipeline are kept too: the turnover read
    model sorts their planned inzet under pipeline by itself.
    """
    result = await session.execute(
        select(Assignment.id, Assignment.kind, Assignment.status)
    )
    by_kind: dict[str, list[UUID]] = {EXTERNAL: [], INTERNAL: []}
    for assignment_id, kind, status in result.all():
        commitment = commitment_of(status)
        if kind == EXTERNAL and commitment is not Commitment.NONE:
            by_kind[EXTERNAL].append(assignment_id)
        elif kind == INTERNAL and commitment in _AGREED:
            by_kind[INTERNAL].append(assignment_id)
    return by_kind


class _Rates:
    """The billing rate of a person in a month (R1), or None when unknown."""

    def __init__(self, rates: calc.RateBook, scales: Sequence[calc.PersonScale]):
        self._rates = rates
        self._scales = scales

    @classmethod
    async def load(
        cls,
        session: AsyncSession,
        person_ids: Iterable[UUID],
        options: PricingOptions,
    ) -> _Rates:
        scales = await PersonDetailRepository(session).scales(set(person_ids))
        return cls(
            await pricing.load_rate_book(session, include_draft=options.include_draft),
            tuple(pricing.to_calc_scale(scale) for scale in scales),
        )

    def monthly_cents(self, person_id: UUID, month: Month) -> int | None:
        try:
            return calc.person_monthly_rate(
                self._rates, self._scales, str(person_id), month
            )
        except calc.CalcError:
            return None


async def _targets(
    session: AsyncSession, year: int, options: PricingOptions
) -> tuple[int, int, list[int]]:
    """The sum of the targets, how many people it covers, and its split per month.

    A person's target for the year (R13) is spread over the months in
    proportion to the billing rate of each month, so the months add up to
    the year exactly.
    """
    people = await steering.kpi_person_ids(session, year)
    rates = await _Rates.load(session, [person_id for person_id, _ in people], options)
    year_months = steering.months_of(year)
    total = 0
    count = 0
    per_month = [0] * len(year_months)
    rows = await steering.kpi_rows(session, people, year, options=options)
    for (person_id, _name), row in zip(people, rows, strict=True):
        target = row.overview.target_cents if row.overview is not None else None
        if target is None:
            continue
        total += target
        count += 1
        weights = [rates.monthly_cents(person_id, month) or 0 for month in year_months]
        for index, part in enumerate(spread(target, weights)):
            per_month[index] += part
    return total, count, per_month


async def money_reading(
    session: AsyncSession,
    year: int,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> MoneyReading:
    """Investeerruimte in money, for the whole organisation."""
    ids = await _agreed_ids_by_kind(session)
    turnover = await steering.turnover(
        session, year, assignment_ids=ids[EXTERNAL], options=options
    )
    target_cents, target_count, target_per_month = await _targets(
        session, year, options
    )

    uncovered = sum(
        item.uncovered_cents or 0
        for item in await steering.cost_items(session, year, options=options)
    )

    internal_budget = 0
    unpriced = set(turnover.unpriced)
    names: dict[UUID, str] = {}
    if ids[INTERNAL]:
        result = await session.execute(
            select(Assignment.id, Assignment.name).where(
                Assignment.id.in_(ids[INTERNAL])
            )
        )
        names = {row.id: row.name for row in result}
    for assignment_id in ids[INTERNAL]:
        try:
            by_year = await pricing.budgeted_by_year(
                session, assignment_id, options=options
            )
        except calc.CalcError:
            unpriced.add(names.get(assignment_id, str(assignment_id)))
            continue
        internal_budget += by_year.get(year, 0)

    return MoneyReading(
        year=year,
        realised_cents=turnover.realised_cents,
        planned_cents=turnover.forecast_cents,
        verbal_cents=turnover.verbal_cents,
        pipeline_cents=turnover.pipeline_cents,
        target_cents=target_cents,
        target_person_count=target_count,
        uncovered_cents=uncovered,
        internal_budget_cents=internal_budget,
        internal_count=len(ids[INTERNAL]),
        months=tuple(
            MoneyMonth(
                month=month.month,
                realised_cents=month.realised_cents,
                planned_cents=month.forecast_cents,
                target_cents=target_per_month[index],
            )
            for index, month in enumerate(turnover.months)
        ),
        unpriced=tuple(sorted(unpriced)),
    )


def _round_fte(value: Fraction) -> Decimal:
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        Decimal("0.01")
    )


async def time_reading(
    session: AsyncSession,
    window: Sequence[Month],
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> TimeReading:
    """Free capacity in ``window``, in FTE and valued at the billing rate.

    Available is one FTE per person per month. Overbooking of one person is
    not set off against the room of another.
    """
    rows = await steering.occupancy(session, window, options=options)
    rates = await _Rates.load(session, [row.person_id for row in rows], options)
    months: list[TimeMonth] = []
    for index, month in enumerate(window):
        free = Fraction(0)
        available = 0
        value = 0
        unvalued = 0
        for row in rows:
            cell = row.cells[index]
            if not cell.available:
                continue
            available += 1
            room = max(Fraction(0), 100 - cell.exact) / 100
            if room == 0:
                continue
            free += room
            rate = rates.monthly_cents(row.person_id, month)
            if rate is None:
                unvalued += 1
            else:
                value += calc.round_cents(room * rate)
        months.append(
            TimeMonth(
                month=month,
                available_fte=Decimal(available),
                free_fte=_round_fte(free),
                value_cents=value,
                unvalued_count=unvalued,
            )
        )
    return TimeReading(months=tuple(months), person_count=len(rows))
