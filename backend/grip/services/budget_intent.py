"""The intended person of a budget line: who the role is meant for.

When a budget is made it is often already known who will do the work. Naming
that colleague on a personnel line does three things:

- It derives the rate category of the line from the person's billing scale,
  through the scale mapping of the rate card (rule R1), so the line is
  budgeted at what that person will bill. The derivation is a proposal: the
  caller may send another category, and then the R14 signal says so.
- It reserves the person: an allocation on the line for the line's period.
  While the assignment is potential that allocation is tentative
  (``grip.services.staffing``), so planning shows it "onder voorbehoud".
- It stays out of the quote. The intended person is staffing data; a quote
  shows a role, a size, a period, a category and a rate
  (``grip.services.quote_content``).

Rules that had to be chosen:

- A line has one category. When the person's category differs inside the
  period (the scale changes, or the rate card of a later year maps the scale
  differently) the line takes the category at the start of the period, and a
  note says which months differ. Inzet itself is priced per month on the
  scale of that month, as always.
- FTE is never proposed: grip knows what is planned, not what someone has
  free. The period is proposed from the assignment's period when the caller
  gives none, starting no earlier than the person's own start date.
- The reservation follows the line. A change of period or size on the line
  is carried to the reservation for each field in which the two were still
  in step; a field someone changed on the reservation by hand is left alone.
  A change that would make the reservation enter or leave a closed month is
  not carried over; the budget view then says the two differ.
- Replacing or removing the intended person removes the reservation. When
  that cannot be done (a month is closed, or the allocation is in a monthly
  close) the allocation stays as ordinary inzet, no longer tied to the line.
- A person without a billing scale can be named. No category follows, so the
  caller has to choose one; the reservation is made all the same.
- A hired person is budgeted at the billing rate like anyone else. Cost rate
  and margin are class E and play no part here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.calc import Month
from grip.calc.periods import months_between, overlap
from grip.core.audit import UPDATE, record_audit
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.person import Person
from grip.repositories.domain import PersonDetailRepository
from grip.services import assignments, standing
from grip.services.errors import (
    DomainValidationError,
    MonthClosedError,
    NotFoundError,
)
from grip.services.phase import is_tentative
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    PricingOptions,
    load_rate_book,
    to_calc_scale,
)

_MONTH_NAMES = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)
_HUNDRED = Decimal(100)


def _month_text(month: Month) -> str:
    return f"{_MONTH_NAMES[month.month - 1]} {month.year}"


def _date_text(day: date) -> str:
    return f"{day.day} {_MONTH_NAMES[day.month - 1]} {day.year}"


@dataclass(frozen=True)
class CategoryRun:
    """Consecutive months in which the person bills in one category."""

    category: str
    first_month: Month
    last_month: Month
    billing_scale: int


@dataclass(frozen=True)
class Derivation:
    """What naming a person on a line implies. Every value is a proposal."""

    person_id: UUID
    # The period the derivation is about: the one given, or proposed from
    # the assignment. None when neither exists.
    start_date: date | None
    end_date: date | None
    # True when the period was proposed here and not given by the caller.
    period_proposed: bool
    # Never proposed; see the module docstring.
    fte: Decimal | None
    # Class D from here on: this says what the person bills.
    rate_category: str | None
    category_runs: tuple[CategoryRun, ...]
    monthly_rate_by_year: dict[int, int]
    budgeted_cents: int | None
    # Class C: says nothing about the rate.
    notes: tuple[str, ...]
    # Class D: names categories.
    category_notes: tuple[str, ...]

    @property
    def category_varies(self) -> bool:
        return len({run.category for run in self.category_runs}) > 1


@dataclass(frozen=True)
class LineIntent:
    """The intended person of one line, as the budget view shows it."""

    person_id: UUID
    person_name: str
    # The reservation: the allocation naming the person made, if it exists.
    allocation_id: UUID | None
    # Whether the reservation still has the period and size of the line.
    in_step: bool
    # "Onder voorbehoud": the assignment is still potential.
    tentative: bool
    notes: tuple[str, ...]
    # Whether the line's category differs from what the person bills in some
    # month. A fact without the category: the R14 signal.
    category_differs: bool
    # Class D.
    implied_category: str | None
    category_notes: tuple[str, ...]


def reservation_pct(fte: Decimal) -> Decimal:
    """FTE percentage of the reservation for a line of this size.

    One person fills at most 100 percent; a line of more than 1 FTE is a role
    for more than one person.
    """
    return min(Decimal(fte) * _HUNDRED, _HUNDRED)


# -- derivation -----------------------------------------------------------------


def _months(start: date, end: date) -> list[tuple[Month, date, date]]:
    result = []
    for month in months_between(start, end):
        span = overlap(month, start, end)
        assert span is not None
        result.append((month, span[0], span[1]))
    return result


def _runs_and_gaps(
    rates: calc.RateBook,
    scales: tuple[calc.PersonScale, ...],
    person_id: UUID,
    start: date,
    end: date,
) -> tuple[list[CategoryRun], list[Month], list[int]]:
    """Category per month: runs, months without a scale, years without a card."""
    runs: list[CategoryRun] = []
    no_scale: list[Month] = []
    unpriced_years: list[int] = []
    for month, first, last in _months(start, end):
        scale = calc.billing_scale(scales, str(person_id), first, last)
        if scale is None:
            no_scale.append(month)
            continue
        try:
            category = rates.category_for_scale(month.year, scale)
        except (calc.MissingRateCardError, calc.MissingScaleBandError):
            if month.year not in unpriced_years:
                unpriced_years.append(month.year)
            continue
        if (
            runs
            and runs[-1].category == category
            and runs[-1].billing_scale == scale
            and runs[-1].last_month.next() == month
        ):
            runs[-1] = CategoryRun(category, runs[-1].first_month, month, scale)
        else:
            runs.append(CategoryRun(category, month, month, scale))
    return runs, no_scale, unpriced_years


def _category_notes(runs: list[CategoryRun], chosen: str) -> list[str]:
    if len({run.category for run in runs}) <= 1:
        return []
    parts = []
    for run in runs:
        span = (
            _month_text(run.first_month)
            if run.first_month == run.last_month
            else f"{_month_text(run.first_month)} t/m {_month_text(run.last_month)}"
        )
        parts.append(f"categorie {run.category} in {span}")
    cause = (
        "De inzetschaal van deze persoon wijzigt in deze periode"
        if len({run.billing_scale for run in runs}) > 1
        else "De tarievenkaarten delen de schaal van deze persoon per jaar anders in"
    )
    return [
        f"{cause}: {'; '.join(parts)}. De regel krijgt categorie {chosen}, die van "
        "het begin van de periode. Inzet wordt per maand geprijsd op de schaal van "
        "die maand, dus de regel loopt in de andere maanden over of onder."
    ]


def _budget_proposal(
    rates: calc.RateBook,
    category: str,
    fte: Decimal,
    start: date,
    end: date,
    options: PricingOptions,
) -> tuple[dict[int, int], int | None]:
    line = calc.BudgetLine(
        id="proposal",
        assignment_id="proposal",
        kind=calc.BudgetLineKind.PERSONNEL,
        fte=fte,
        rate_category=category,
        start_date=start,
        end_date=end,
    )
    try:
        months = calc.budget_line_months(
            line, rates, partial_months=options.partial_months
        )
    except calc.CalcError:
        return {}, None
    rate_by_year = {m.month.year: m.monthly_rate_cents for m in months}
    return rate_by_year, sum(m.cents for m in months)


async def _selectable_person(session: AsyncSession, person_id: UUID) -> Person:
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError("Persoon", person_id)
    if not person.is_active:
        raise DomainValidationError(
            "Deze persoon is niet meer actief en kan niet worden ingepland."
        )
    return person


async def derive(
    session: AsyncSession,
    assignment_id: UUID,
    person_id: UUID,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    fte: Decimal | None = None,
    today: date | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> Derivation:
    """What follows from naming this person on a line of this assignment.

    Nothing is saved. The form shows the result and the user may change it.
    """
    assignment = await assignments.get_assignment(session, assignment_id)
    await _selectable_person(session, person_id)
    today = today or date.today()
    notes: list[str] = []
    person_start = (await standing.get_standing(session, person_id)).start_date

    proposed = False
    start, end = start_date, end_date
    if start is None and end is None and assignment.start_date and assignment.end_date:
        # The only period grip can sensibly propose: that of the assignment,
        # from the day the person is there.
        start, end = assignment.start_date, assignment.end_date
        if person_start is not None and start < person_start <= end:
            start = person_start
        proposed = True
    if start is not None and end is not None and end < start:
        raise DomainValidationError("De einddatum ligt voor de begindatum.")
    if person_start is not None and start is not None and start < person_start:
        notes.append(
            f"Deze persoon begint op {_date_text(person_start)}; de periode van de "
            "regel begint eerder."
        )

    scales = tuple(
        to_calc_scale(s)
        for s in await PersonDetailRepository(session).scales([person_id])
    )
    rates = await load_rate_book(session, include_draft=options.include_draft)

    if start is not None and end is not None:
        span = (start, end)
    else:
        # Without a period: what the person bills now, or on the first day.
        day = start or end or max(today, person_start or today)
        span = (day, day)
        notes.append(
            "Er is nog geen periode; de categorie is die van "
            f"{_month_text(Month.of(day))}."
        )
    runs, no_scale, unpriced_years = _runs_and_gaps(rates, scales, person_id, *span)

    category = runs[0].category if runs else None
    if no_scale and not runs:
        notes.append(
            "Deze persoon heeft in deze periode geen inzetschaal. Er volgt geen "
            "categorie; kies die zelf, of leg eerst de inzetschaal vast."
        )
    elif no_scale:
        notes.append(
            "Deze persoon heeft in een deel van deze periode geen inzetschaal "
            f"(vanaf {_month_text(no_scale[0])}). Inzet in die maanden is niet te "
            "prijzen tot de inzetschaal is vastgelegd."
        )
    for year in unpriced_years:
        notes.append(
            f"Voor {year} is er geen tarievenkaart die deze schaal indeelt; voor "
            "dat jaar volgt geen categorie."
        )

    rate_by_year: dict[int, int] = {}
    budgeted = None
    if category and fte is not None and start is not None and end is not None:
        rate_by_year, budgeted = _budget_proposal(
            rates, category, Decimal(fte), start, end, options
        )
    if fte is not None and Decimal(fte) > 1:
        notes.append(
            "De regel is groter dan 1 FTE; deze persoon wordt voor 100 procent "
            "gereserveerd."
        )
    return Derivation(
        person_id=person_id,
        start_date=start,
        end_date=end,
        period_proposed=proposed,
        fte=None,
        rate_category=category,
        category_runs=tuple(runs),
        monthly_rate_by_year=rate_by_year,
        budgeted_cents=budgeted,
        notes=tuple(notes),
        category_notes=tuple(_category_notes(runs, category) if category else ()),
    )


# -- the reservation ------------------------------------------------------------


async def reservation_of(session: AsyncSession, line_id: UUID) -> Allocation | None:
    """The allocation that naming the intended person made, if it exists."""
    result = await session.execute(
        select(Allocation)
        .where(Allocation.budget_line_id == line_id, Allocation.from_budget.is_(True))
        .order_by(Allocation.created_at, Allocation.id)
    )
    return result.scalars().first()


async def _reserve(
    session: AsyncSession,
    line: BudgetLine,
    *,
    actor: Person | None,
    allow_closed_year: bool,
) -> Allocation | None:
    assert line.intended_person_id and line.start_date and line.end_date
    assert line.fte is not None
    try:
        allocation = await assignments.add_allocation(
            session,
            line.id,
            line.intended_person_id,
            start_date=line.start_date,
            end_date=line.end_date,
            fte_pct=reservation_pct(line.fte),
            actor=actor,
            allow_closed_year=allow_closed_year,
        )
    except MonthClosedError:
        # A month of the period is already closed: inzet cannot be added
        # there. The person stays named; the view says there is no inzet.
        return None
    allocation.from_budget = True
    await session.flush()
    return allocation


async def _release(
    session: AsyncSession,
    reservation: Allocation,
    *,
    actor: Person | None,
    allow_closed_year: bool,
) -> None:
    try:
        await assignments.delete_allocation(
            session, reservation.id, actor=actor, allow_closed_year=allow_closed_year
        )
    except (MonthClosedError, DomainValidationError):
        # Work was already established on it. It stays as ordinary inzet.
        reservation.from_budget = False
        await session.flush()


async def _follow(
    session: AsyncSession,
    line: BudgetLine,
    reservation: Allocation,
    before: dict[str, Any],
    *,
    actor: Person | None,
    allow_closed_year: bool,
) -> None:
    """Carry a change of the line to the reservation, field by field."""
    assert line.start_date and line.end_date and line.fte is not None
    changes: dict[str, Any] = {}
    if (
        line.start_date != before["start_date"]
        and reservation.start_date == before["start_date"]
    ):
        changes["start_date"] = line.start_date
    if (
        line.end_date != before["end_date"]
        and reservation.end_date == before["end_date"]
    ):
        changes["end_date"] = line.end_date
    if line.fte != before["fte"] and reservation.fte_pct == reservation_pct(
        before["fte"]
    ):
        changes["fte_pct"] = reservation_pct(line.fte)
    if not changes:
        return
    try:
        await assignments.update_allocation(
            session,
            reservation.id,
            actor=actor,
            allow_closed_year=allow_closed_year,
            **changes,
        )
    except (MonthClosedError, DomainValidationError):
        # The reservation would enter or leave a closed month, or end before
        # it starts. It stays as it is; the view shows that the two differ.
        return


def _audit_intent(
    session: AsyncSession,
    line: BudgetLine,
    old: UUID | None,
    actor: Person | None,
) -> None:
    record_audit(
        session,
        actor=actor,
        action=UPDATE,
        entity="budget_line",
        entity_id=line.id,
        old_value={"intended_person_id": str(old) if old else None},
        new_value={
            "intended_person_id": str(line.intended_person_id)
            if line.intended_person_id
            else None
        },
    )


async def _set_person(
    session: AsyncSession,
    line: BudgetLine,
    person_id: UUID | None,
    *,
    actor: Person | None,
    allow_closed_year: bool,
) -> None:
    """Name, replace or remove the intended person, and the reservation."""
    old = line.intended_person_id
    reservation = await reservation_of(session, line.id)
    if person_id == old and (reservation is not None or person_id is None):
        return
    if person_id is not None:
        if line.kind != "personnel":
            raise DomainValidationError(
                "Een beoogde persoon kan alleen op een personeelsregel."
            )
        await _selectable_person(session, person_id)
    if reservation is not None and reservation.person_id != person_id:
        await _release(
            session, reservation, actor=actor, allow_closed_year=allow_closed_year
        )
        reservation = None
    line.intended_person_id = person_id
    await session.flush()
    if person_id != old:
        _audit_intent(session, line, old, actor)
    if person_id is not None and reservation is None:
        await _reserve(session, line, actor=actor, allow_closed_year=allow_closed_year)


# -- budget lines with an intended person --------------------------------------------


async def add_line(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    actor: Person | None,
    intended_person_id: UUID | None = None,
    allow_closed_year: bool = False,
    options: PricingOptions = DEFAULT_OPTIONS,
    **values: Any,
) -> BudgetLine:
    """Add a budget line, optionally meant for a person.

    With an intended person and no ``rate_category`` the category is derived
    from that person. With a category given, that one is kept.
    """
    if intended_person_id is not None:
        if values.get("kind") != "personnel":
            raise DomainValidationError(
                "Een beoogde persoon kan alleen op een personeelsregel."
            )
        await _selectable_person(session, intended_person_id)
        if values.get("rate_category") is None:
            derived = await derive(
                session,
                assignment_id,
                intended_person_id,
                start_date=values.get("start_date"),
                end_date=values.get("end_date"),
                options=options,
            )
            if derived.rate_category is None:
                raise DomainValidationError(
                    "Voor deze persoon volgt geen tariefcategorie: er is in deze "
                    "periode geen inzetschaal of geen tarievenkaart. Kies zelf een "
                    "categorie; de persoon blijft de beoogde persoon."
                )
            values["rate_category"] = derived.rate_category
    line = await assignments.add_budget_line(
        session,
        assignment_id,
        actor=actor,
        allow_closed_year=allow_closed_year,
        **values,
    )
    if intended_person_id is not None:
        await _set_person(
            session,
            line,
            intended_person_id,
            actor=actor,
            allow_closed_year=allow_closed_year,
        )
    return line


async def update_line(
    session: AsyncSession,
    line_id: UUID,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
    derive_category: bool = False,
    options: PricingOptions = DEFAULT_OPTIONS,
    **changes: Any,
) -> BudgetLine:
    """Change a budget line; the reservation of its intended person follows.

    ``intended_person_id`` in the changes names, replaces or (with None)
    removes the intended person. The category of the line changes only when
    it is sent, or when ``derive_category`` asks to take it from the person.
    """
    line = await assignments.get_budget_line(session, line_id)
    set_person = "intended_person_id" in changes
    person_id = changes.pop("intended_person_id", line.intended_person_id)
    before = {
        "start_date": line.start_date,
        "end_date": line.end_date,
        "fte": line.fte,
    }
    if derive_category and "rate_category" not in changes:
        if person_id is None:
            raise DomainValidationError(
                "Zonder beoogde persoon is er geen categorie om af te leiden."
            )
        derived = await derive(
            session,
            line.assignment_id,
            person_id,
            start_date=changes.get("start_date", line.start_date),
            end_date=changes.get("end_date", line.end_date),
            options=options,
        )
        if derived.rate_category is None:
            raise DomainValidationError(
                "Voor deze persoon volgt geen tariefcategorie: er is in deze "
                "periode geen inzetschaal of geen tarievenkaart."
            )
        changes["rate_category"] = derived.rate_category
    if changes:
        line = await assignments.update_budget_line(
            session,
            line_id,
            actor=actor,
            allow_closed_year=allow_closed_year,
            **changes,
        )
    reservation = await reservation_of(session, line.id)
    if reservation is not None and reservation.person_id == person_id:
        await _follow(
            session,
            line,
            reservation,
            before,
            actor=actor,
            allow_closed_year=allow_closed_year,
        )
    if set_person:
        await _set_person(
            session, line, person_id, actor=actor, allow_closed_year=allow_closed_year
        )
    return line


async def delete_line(
    session: AsyncSession,
    line_id: UUID,
    *,
    actor: Person | None,
    allow_closed_year: bool = False,
) -> None:
    """Delete a budget line, and the reservation it made with it.

    Other inzet on the line still blocks the delete, as before.
    """
    reservation = await reservation_of(session, line_id)
    if reservation is not None:
        await _release(
            session, reservation, actor=actor, allow_closed_year=allow_closed_year
        )
    await assignments.delete_budget_line(
        session, line_id, actor=actor, allow_closed_year=allow_closed_year
    )


# -- the view -------------------------------------------------------------------


async def line_intents(
    session: AsyncSession,
    lines: Iterable[BudgetLine],
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> dict[UUID, LineIntent]:
    """The intended person per line, with what stands out about it.

    Computed from what is stored now, so the notes are true on every read
    and disappear when their cause does.
    """
    lines = [line for line in lines if line.intended_person_id is not None]
    if not lines:
        return {}
    person_ids = {line.intended_person_id for line in lines}
    names = dict(
        (
            await session.execute(
                select(Person.id, Person.name).where(Person.id.in_(person_ids))
            )
        ).all()
    )
    statuses = dict(
        (
            await session.execute(
                select(Assignment.id, Assignment.status).where(
                    Assignment.id.in_({line.assignment_id for line in lines})
                )
            )
        ).all()
    )
    reservations: dict[UUID, Allocation] = {}
    for allocation in (
        await session.execute(
            select(Allocation)
            .where(
                Allocation.budget_line_id.in_([line.id for line in lines]),
                Allocation.from_budget.is_(True),
            )
            .order_by(Allocation.created_at.desc(), Allocation.id)
        )
    ).scalars():
        reservations[allocation.budget_line_id] = allocation

    result: dict[UUID, LineIntent] = {}
    for line in lines:
        person_id = line.intended_person_id
        assert person_id is not None
        derived = (
            await derive(
                session,
                line.assignment_id,
                person_id,
                start_date=line.start_date,
                end_date=line.end_date,
                fte=line.fte,
                options=options,
            )
            if await _is_active(session, person_id)
            else None
        )
        notes = list(derived.notes) if derived else []
        if derived is None:
            notes.append("Deze persoon is niet meer actief.")
        reservation = reservations.get(line.id)
        if reservation is not None and reservation.person_id != person_id:
            reservation = None
        in_step = bool(
            reservation is not None
            and line.fte is not None
            and reservation.start_date == line.start_date
            and reservation.end_date == line.end_date
            and reservation.fte_pct == reservation_pct(line.fte)
        )
        if reservation is None:
            notes.append(
                "Voor deze persoon staat geen inzet op de regel. Dat gebeurt als "
                "een maand van de periode al is afgesloten, of als de inzet is "
                "verwijderd."
            )
        elif not in_step:
            notes.append(
                "De inzet van deze persoon wijkt af van de regel in periode of omvang."
            )
        differs = bool(
            derived
            and any(run.category != line.rate_category for run in derived.category_runs)
        )
        category_notes = list(derived.category_notes) if derived else []
        if (
            derived
            and derived.rate_category
            and derived.rate_category != line.rate_category
            and not derived.category_varies
        ):
            category_notes.append(
                f"Deze persoon declareert in categorie {derived.rate_category}; de "
                f"regel rekent met categorie {line.rate_category}."
            )
        result[line.id] = LineIntent(
            person_id=person_id,
            person_name=names.get(person_id, ""),
            allocation_id=reservation.id if reservation is not None else None,
            in_step=in_step,
            tentative=is_tentative(statuses[line.assignment_id]),
            notes=tuple(notes),
            category_differs=differs,
            implied_category=derived.rate_category if derived else None,
            category_notes=tuple(category_notes),
        )
    return result


async def _is_active(session: AsyncSession, person_id: UUID) -> bool:
    person = await session.get(Person, person_id)
    return bool(person is not None and person.is_active)
