"""How a task is told to the person reading it.

The plan says which work arises and what closes it. This module says what a
reader must hear about one task, in this order: what to do, or who must do
what and why the reader sees it; why the task is there; what comes after;
and the one action that does it, with the place where that is done.

The sentences are data (``grip/data/tasks/guidance.json``), one entry per
template key, for every version of the plan: a better sentence reaches the
cases that already run. The file can only use the names offered here, and a
test fails on a template of any known plan without an entry.

Nothing here decides access. A name of a person is only used where the
reader may change the case or the task is theirs; otherwise the role stands
in its place.
"""

from __future__ import annotations

import json
import string
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.core import clock
from grip.models.assignment import Assignment, AssignmentRole, BudgetLine
from grip.models.billing_correction import BillingCorrection
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.quote import Quote, QuoteApproval, QuoteRejection
from grip.models.role import PersonRole
from grip.models.task import Task
from grip.models.vacancy import Vacancy, VacancyText
from grip.services import billing_corrections
from grip.services.vacancies import service as vacancy_service
from grip.tasks import catalogue
from grip.tasks.cases import period_words
from grip.tasks.plan import Template, known_plans, plan_for

if TYPE_CHECKING:
    from grip.tasks.access import TaskAccess
    from grip.tasks.service import TaskView

GUIDANCE_FILE = Path(__file__).resolve().parents[1] / "data" / "tasks" / "guidance.json"

# What a sentence may name between braces.
VARIABLES = frozenset(
    {
        "opdracht",
        "opdrachtgever",
        "functie",
        "aanvrager",
        "ingediend_op",
        "wie",
        "kenmerk",
        "maand",
        "periode",
        "rol",
        "tekst",
        "gevraagd_door",
        "gevraagd_op",
        # A rejected quote: " op 8 okt 2026" and " De reden: ...", or nothing.
        "afgewezen_op",
        "reden_afwijzing",
        # A correction after delivery: the difference and why it arose.
        "bedrag",
        "oorzaak",
    }
)
# What stands in for a name the reader may not see or grip does not have.
# A variable without a stand-in makes the "why" sentence drop out.
_STAND_INS = {
    "opdracht": "de opdracht",
    "opdrachtgever": "de opdrachtgever",
    "functie": "deze functie",
    "aanvrager": "de aanvrager",
    "wie": "een ander",
    "rol": "deze rol",
    "tekst": "tekst",
    "maand": "de maand",
    "periode": "de periode",
    "kenmerk": "",
    "gevraagd_door": "de maker van de offerte",
    "bedrag": "nog niet berekend",
    "oorzaak": "de prijs van een aangeleverde maand is veranderd",
}
# What a destination may name between braces: ids the task itself carries.
DESTINATION_VARIABLES = frozenset(
    {"assignment_id", "vacancy_id", "subject_id", "repeat_key"}
)

# A stand that grip recognises and that changes what must be done.
#   unnamed: nobody is named yet for the advice or approval;
#   unnamed_recorder: the same, for a reader who may record it right away;
#   named_outside: the person named has no account, someone else records it;
#   incomplete: the request of the vacancy still misses something.
# Situations the telling works out itself, and any fact of the catalogue:
# a task is told in the words of the first such fact that holds for it.
_FACT_SITUATIONS = frozenset().union(
    *catalogue.CASE_FACTS.values(), *catalogue.SUBJECT_FACTS.values()
)
SITUATIONS = (
    frozenset({"unnamed", "unnamed_recorder", "named_outside", "incomplete"})
    | _FACT_SITUATIONS
)
_REQUIRED = ("title", "awaited", "do", "wait", "action", "why", "destination")
_TEXT_FIELDS = ("title", "awaited", "do", "wait", "action", "why", "then")
_SITUATION_FIELDS = frozenset({"title", "awaited", "do", "wait", "action"})

_ROLE_WORDS = {
    "owner": "de eigenaar van de opdracht",
    "manager": "de eigenaar of een manager van de opdracht",
    "planner": "een planner",
    "beheerder": "een beheerder",
    "tekenbevoegde": "een tekenbevoegde",
    "aanvrager": "een aanvrager",
    "offertegoedkeurder": "een interne goedkeurder van offertes",
}


def role_words(role: str | None) -> str:
    """Who holds a task that is nobody's in person, in words."""
    return _ROLE_WORDS.get(role or "", "een ander")


_DECISION_WORDS = {
    "hr_advice": "de HR-adviseur",
    "control_advice": "de controller",
    "approval": "wie akkoord moet geven",
}
_MONTHS_SHORT = (
    "jan",
    "feb",
    "mrt",
    "apr",
    "mei",
    "jun",
    "jul",
    "aug",
    "sep",
    "okt",
    "nov",
    "dec",
)
_MONTHS = (
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
_TEXT_WORDS = {"vacancy_text": "vacaturetekst", "motivation": "motivatie"}


class GuidanceError(ValueError):
    """The guidance names something this module does not offer."""


@dataclass(frozen=True)
class Guide:
    title: str
    awaited: str
    do: str
    wait: str
    action: str
    why: str
    destination: str
    then: str | None = None
    situations: dict[str, dict[str, str]] = field(default_factory=dict)

    def in_situation(self, situation: str | None) -> Guide:
        override = self.situations.get(situation or "")
        if not override:
            return self
        return Guide(
            title=override.get("title", self.title),
            awaited=override.get("awaited", self.awaited),
            do=override.get("do", self.do),
            wait=override.get("wait", self.wait),
            action=override.get("action", self.action),
            why=self.why,
            destination=self.destination,
            then=self.then,
        )


@dataclass(frozen=True)
class Guidance:
    destinations: dict[str, str]
    templates: dict[str, Guide]


def _names_in(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def parse_guidance(data: dict[str, Any]) -> Guidance:
    """Check the guidance against what this module offers and return it."""
    destinations = dict(data.get("destinations") or {})
    for name, path in destinations.items():
        unknown = _names_in(path) - DESTINATION_VARIABLES
        if unknown or not path.startswith("/"):
            raise GuidanceError(f"Bestemming {name}: onbekend in '{path}'.")
    templates: dict[str, Guide] = {}
    for key, raw in (data.get("templates") or {}).items():

        def fail(message: str, key: str = key) -> GuidanceError:
            return GuidanceError(f"Taak {key}: {message}")

        for name in _REQUIRED:
            if not isinstance(raw.get(name), str) or not raw[name].strip():
                raise fail(f"'{name}' ontbreekt")
        if raw["destination"] not in destinations:
            raise fail(f"onbekende bestemming '{raw['destination']}'")
        unknown_keys = set(raw) - set(_TEXT_FIELDS) - {"destination", "situations"}
        if unknown_keys:
            raise fail(f"onbekende instelling {sorted(unknown_keys)}")
        situations = raw.get("situations") or {}
        texts = [raw[name] for name in _TEXT_FIELDS if raw.get(name)]
        for situation, override in situations.items():
            if situation not in SITUATIONS:
                raise fail(f"onbekende stand '{situation}'")
            if set(override) - _SITUATION_FIELDS:
                raise fail(f"stand '{situation}' kan dit niet vervangen")
            texts.extend(override.values())
        for text in texts:
            unknown = _names_in(text) - VARIABLES
            if unknown:
                raise fail(f"onbekende naam {sorted(unknown)} in '{text}'")
        templates[key] = Guide(
            title=raw["title"],
            awaited=raw["awaited"],
            do=raw["do"],
            wait=raw["wait"],
            action=raw["action"],
            why=raw["why"],
            destination=raw["destination"],
            then=raw.get("then"),
            situations={name: dict(value) for name, value in situations.items()},
        )
    return Guidance(destinations=destinations, templates=templates)


@lru_cache(maxsize=1)
def guidance() -> Guidance:
    return parse_guidance(json.loads(GUIDANCE_FILE.read_text(encoding="utf-8")))


def templates_without_guidance() -> list[str]:
    """Template keys of any known plan that the guidance does not cover."""
    known = guidance().templates
    missing = {
        template.key
        for plan in known_plans().values()
        for templates in plan.templates.values()
        for template in templates
        if template.key not in known
    }
    return sorted(missing)


@dataclass(frozen=True)
class ChecklistItem:
    text: str
    done: bool


@dataclass
class Telling:
    """One task as one reader must hear it."""

    # The task in a few words: what to do, or what is waited for.
    headline: str
    # What must happen, whoever reads it: the words for a line that says
    # where a track stands.
    title: str
    # The sentence addressed to this reader.
    instruction: str
    # The reader must act now; false when the reader waits or only looks on.
    needs_me: bool
    why: str | None = None
    then: str | None = None
    # The one action, and the place where it is done. The text is absent
    # when the reader has nothing to do there now.
    action_text: str | None = None
    work_href: str | None = None
    # Who is waited on, when that is not the reader.
    waits_on: str | None = None
    # Nobody can do this until something outside the task changes.
    blocked: str | None = None
    checklist: list[ChecklistItem] = field(default_factory=list)


def day(value: date) -> str:
    return f"{value.day} {_MONTHS_SHORT[value.month - 1]} {value.year}"


def _euros(cents: int) -> str:
    """An amount in a sentence: "€ 2.400" or "-€ 2.400"."""
    sign = "-" if cents < 0 else ""
    whole = f"{abs(cents) // 100:,}".replace(",", ".")
    rest = abs(cents) % 100
    return f"{sign}€ {whole}" + (f",{rest:02d}" if rest else "")


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _fill(text: str, values: dict[str, str], *, strict: bool = False) -> str | None:
    """A sentence with its names filled in; None when a name has no value."""
    names = _names_in(text)
    used: dict[str, str] = {}
    for name in names:
        value = values.get(name)
        if not value:
            if strict and name not in _STAND_INS:
                return None
            value = _STAND_INS.get(name, "")
        used[name] = value
    return _capital(" ".join(text.format(**used).split()))


@dataclass
class _Context:
    assignments: dict[UUID, Assignment] = field(default_factory=dict)
    clients: dict[UUID, str] = field(default_factory=dict)
    owners: dict[UUID, str] = field(default_factory=dict)
    vacancies: dict[UUID, Vacancy] = field(default_factory=dict)
    vacancy_assignment: dict[UUID, UUID] = field(default_factory=dict)
    people: dict[UUID, str] = field(default_factory=dict)
    quotes: dict[str, Quote] = field(default_factory=dict)
    approvals: dict[str, QuoteApproval] = field(default_factory=dict)
    corrections: dict[str, BillingCorrection] = field(default_factory=dict)
    rejections: dict[str, QuoteRejection] = field(default_factory=dict)
    lines: dict[str, BudgetLine] = field(default_factory=dict)
    # Vacancies whose motivation for the request is settled.
    motivated: set[UUID] = field(default_factory=set)
    # Rights in grip that nobody holds today.
    unheld: set[str] = field(default_factory=set)


def _as_uuid(value: str | None) -> UUID | None:
    try:
        return UUID(value) if value else None
    except ValueError:
        return None


async def _load_context(
    db: AsyncSession, tasks: list[Task], *, today: date
) -> _Context:
    context = _Context()
    assignment_ids = {t.assignment_id for t in tasks if t.assignment_id}
    vacancy_ids = {t.vacancy_id for t in tasks if t.vacancy_id}
    person_ids: set[UUID] = set()

    if vacancy_ids:
        vacancies = (
            await db.scalars(
                select(Vacancy)
                .where(Vacancy.id.in_(vacancy_ids))
                .options(selectinload(Vacancy.decisions))
            )
        ).all()
        context.vacancies = {vacancy.id: vacancy for vacancy in vacancies}
        context.motivated = set(
            await db.scalars(
                select(VacancyText.vacancy_id).where(
                    VacancyText.vacancy_id.in_(vacancy_ids),
                    VacancyText.kind == "motivation",
                    VacancyText.established_at.is_not(None),
                )
            )
        )
        person_ids |= {v.requester_id for v in vacancies if v.requester_id}
        line_ids = {v.budget_line_id for v in vacancies if v.budget_line_id}
        if line_ids:
            rows = await db.execute(
                select(BudgetLine.id, BudgetLine.assignment_id).where(
                    BudgetLine.id.in_(line_ids)
                )
            )
            of_line = {row[0]: row[1] for row in rows}
            context.vacancy_assignment = {
                v.id: of_line[v.budget_line_id]
                for v in vacancies
                if v.budget_line_id in of_line
            }

    if assignment_ids:
        assignments = (
            await db.scalars(
                select(Assignment).where(Assignment.id.in_(assignment_ids))
            )
        ).all()
        context.assignments = {a.id: a for a in assignments}
        organisation_ids = {
            a.client_organisation_id for a in assignments if a.client_organisation_id
        }
        if organisation_ids:
            rows = await db.execute(
                select(Organisation.id, Organisation.name).where(
                    Organisation.id.in_(organisation_ids)
                )
            )
            names = {row[0]: row[1] for row in rows}
            context.clients = {
                a.id: names[a.client_organisation_id]
                for a in assignments
                if a.client_organisation_id in names
            }
        rows = await db.execute(
            select(AssignmentRole.assignment_id, Person.name)
            .join(Person, Person.id == AssignmentRole.person_id)
            .where(
                AssignmentRole.assignment_id.in_(assignment_ids),
                AssignmentRole.role == "owner",
            )
        )
        context.owners = {row[0]: row[1] for row in rows}

    quote_ids = {
        _as_uuid(t.subject_id)
        for t in tasks
        if t.subject_kind
        in (
            "quote_round",
            "rejected_quote",
            "received_quote",
            "quote_approval",
            "sent_back_quote",
        )
    } - {None}
    if quote_ids:
        quotes = (await db.scalars(select(Quote).where(Quote.id.in_(quote_ids)))).all()
        context.quotes = {str(quote.id): quote for quote in quotes}
        rejections = (
            await db.scalars(
                select(QuoteRejection).where(QuoteRejection.quote_id.in_(quote_ids))
            )
        ).all()
        context.rejections = {str(r.quote_id): r for r in rejections}
    correction_ids = {
        _as_uuid(t.subject_id) for t in tasks if t.subject_kind == "period_correction"
    } - {None}
    if correction_ids:
        corrections = (
            await db.scalars(
                select(BillingCorrection).where(
                    BillingCorrection.id.in_(correction_ids)
                )
            )
        ).all()
        context.corrections = {str(c.id): c for c in corrections}
    approval_ids = {
        _as_uuid(t.repeat_key)
        for t in tasks
        if t.subject_kind in ("quote_approval", "sent_back_quote")
    } - {None}
    if approval_ids:
        approvals = (
            await db.scalars(
                select(QuoteApproval).where(QuoteApproval.id.in_(approval_ids))
            )
        ).all()
        context.approvals = {str(a.id): a for a in approvals}
        person_ids |= {a.requested_by_id for a in approvals if a.requested_by_id}
    line_ids = {
        _as_uuid(t.subject_id) for t in tasks if t.subject_kind == "open_role"
    } - {None}
    if line_ids:
        lines = (
            await db.scalars(select(BudgetLine).where(BudgetLine.id.in_(line_ids)))
        ).all()
        context.lines = {str(line.id): line for line in lines}

    if person_ids:
        rows = await db.execute(
            select(Person.id, Person.name).where(Person.id.in_(person_ids))
        )
        context.people = {row[0]: row[1] for row in rows}

    asked = {
        t.assignee_role
        for t in tasks
        if t.assignee_person_id is None and t.assignee_role in catalogue.FUNCTION_ROLES
    }
    if asked:
        rows = await db.execute(
            select(PersonRole.role_id)
            .join(Person, Person.id == PersonRole.person_id)
            .where(
                PersonRole.role_id.in_(asked),
                PersonRole.start_date <= today,
                or_(PersonRole.end_date.is_(None), PersonRole.end_date >= today),
                Person.is_active.is_(True),
            )
            .distinct()
        )
        context.unheld = {role for role in asked if role} - {row[0] for row in rows}
    return context


def _month_words(key: str) -> str | None:
    try:
        year, month = key.split("-")
        return f"{_MONTHS[int(month) - 1]} {int(year)}"
    except (ValueError, IndexError):
        return None


def _template(task: Task) -> Template | None:
    if task.template_key is None:
        return None
    return plan_for(task.plan_version).template(task.template_key)


def _decision_kind(template: Template | None) -> str | None:
    if template is not None and template.assignee.startswith("decision:"):
        return template.assignee.split(":", 1)[1]
    return None


def _named(vacancy: Vacancy, kind: str) -> tuple[str | None, bool]:
    """The name on the vacancy for this decision, and whether it has an account."""
    decision = next((d for d in vacancy.decisions if d.kind == kind), None)
    if decision is not None and decision.person_name:
        return decision.person_name, decision.person_id is not None
    if kind == "approval" and vacancy.addressee_name:
        return vacancy.addressee_name, vacancy.addressee_id is not None
    return None, False


def _missing_request_fields(vacancy: Vacancy, motivated: bool) -> list[ChecklistItem]:
    """What the request needs before it can be made, from the one list the
    vacancies service keeps: the fields of the form and a settled motivation."""
    return [
        *(
            ChecklistItem(
                text=_capital(text), done=getattr(vacancy, name) not in (None, "")
            )
            for name, text in vacancy_service.REQUEST_FIELDS
        ),
        ChecklistItem(
            text=_capital(vacancy_service.MOTIVATION_MISSING), done=motivated
        ),
    ]


def work_href(task: Task) -> str | None:
    """Where the work of a task is done, from its guidance or else its plan."""
    guide = guidance().templates.get(task.template_key or "")
    if guide is None:
        return task.link
    values = {
        "assignment_id": str(task.assignment_id or ""),
        "vacancy_id": str(task.vacancy_id or ""),
        "subject_id": task.subject_id or "",
        "repeat_key": task.repeat_key or "",
    }
    path = guidance().destinations[guide.destination]
    if any(not values[name] for name in _names_in(path)):
        return task.link
    return path.format(**values)


async def tell(
    db: AsyncSession,
    access: TaskAccess,
    views: list[TaskView],
    *,
    today: date,
) -> None:
    """Give every view its telling for this reader."""
    if not views:
        return
    context = await _load_context(db, [view.task for view in views], today=today)
    for view in views:
        view.telling = await _tell_one(access, view, context)


async def _tell_one(access: TaskAccess, view: TaskView, context: _Context) -> Telling:
    task = view.task
    guide = guidance().templates.get(task.template_key or "")
    rights = await access.of_task(task)
    mine = view.is_mine
    # A name of a person only where the reader runs the case or does the work.
    may_name = rights.edit or mine
    href = work_href(task)

    if not task.is_open:
        closed = _closed_headline(task, guide, view, context, may_name)
        return Telling(
            headline=closed,
            title=closed,
            instruction="Deze taak is afgerond."
            if task.status == "done"
            else "Deze taak is vervallen.",
            needs_me=False,
            work_href=href,
        )

    if guide is None:
        # A task someone added by hand, or a template without guidance yet.
        needs_me = mine and task.status != "waiting"
        who = view.assignee_label
        if needs_me:
            instruction = (
                "Doe dit en rond de taak daarna af."
                if view.can_complete
                else "Deze taak is van jou."
            )
        elif mine:
            instruction = "Deze taak is van jou en wacht op een ander."
        else:
            instruction = f"Deze taak is van {who}. Jij hoeft nu niets te doen."
        return Telling(
            headline=task.title,
            title=task.title,
            instruction=instruction,
            needs_me=needs_me,
            work_href=href,
            waits_on=None if needs_me else (task.waiting_on or who),
        )

    template = _template(task)
    values = _values(task, view, context, may_name, access.subject.person_id)
    situation: str | None = None
    can_act = mine and task.status != "waiting"
    checklist: list[ChecklistItem] = []
    vacancy = context.vacancies.get(task.vacancy_id) if task.vacancy_id else None

    kind = _decision_kind(template)
    if kind is not None and vacancy is not None:
        name, has_account = _named(vacancy, kind)
        role_words = _DECISION_WORDS[kind]
        may_record = await access.may_record_decision(
            vacancy, context.vacancy_assignment.get(vacancy.id), kind
        )
        if name is None:
            # Whoever may record does so with the name in one go; whoever
            # only runs the vacancy names the person, who then gets the task.
            situation = "unnamed_recorder" if mine and may_record else "unnamed"
            can_act = mine and (may_record or rights.edit)
            values["wie"] = role_words
        elif not has_account:
            situation = "named_outside"
            can_act = mine and may_record
            values["wie"] = name if may_name else role_words
        elif not mine:
            values["wie"] = name if may_name else role_words
    elif (
        template is not None
        and template.done_when == "requested"
        and vacancy is not None
        and vacancy.status == "draft"
    ):
        checklist = _missing_request_fields(vacancy, vacancy.id in context.motivated)
        if any(not item.done for item in checklist):
            situation = "incomplete"
        else:
            checklist = []

    # No situation of the kinds above: the one the facts gave the task.
    if situation is None:
        situation = task.situation
    told = guide.in_situation(situation)
    blocked = None
    if (
        task.assignee_person_id is None
        and task.assignee_role in context.unheld
        and not mine
    ):
        label = catalogue.ROLE_LABELS.get(task.assignee_role or "", "dit recht")
        blocked = (
            f"Niemand heeft het recht {label} in grip. Een beheerder geeft dat "
            "recht bij Team, op de pagina van een persoon."
        )
    if can_act:
        instruction = _fill(told.do, values) or told.do
        headline = _fill(told.title, values) or told.title
    else:
        instruction = _fill(told.wait, values) or told.wait
        headline = _fill(told.awaited, values) or told.awaited
    return Telling(
        headline=headline,
        title=_fill(told.title, values) or told.title,
        instruction=instruction,
        needs_me=can_act,
        why=_fill(told.why, values, strict=True),
        then=_fill(told.then, values) if told.then else None,
        action_text=(_fill(told.action, values) or told.action) if can_act else None,
        work_href=href,
        waits_on=None if can_act else values.get("wie"),
        blocked=blocked,
        checklist=checklist,
    )


def _closed_headline(
    task: Task,
    guide: Guide | None,
    view: TaskView,
    context: _Context,
    may_name: bool,
) -> str:
    if guide is None:
        return task.title
    values = _values(task, view, context, may_name)
    return _fill(guide.title, values) or task.title


def _values(
    task: Task,
    view: TaskView,
    context: _Context,
    may_name: bool,
    reader_id: UUID | None = None,
) -> dict[str, str]:
    """The names a sentence about this task may use, as far as they are known."""
    values: dict[str, str] = {}
    if view.assignment_name:
        values["opdracht"] = view.assignment_name
        if task.assignment_id in context.clients:
            values["opdrachtgever"] = context.clients[task.assignment_id]
    if view.vacancy_title:
        values["functie"] = view.vacancy_title
    vacancy = context.vacancies.get(task.vacancy_id) if task.vacancy_id else None
    if vacancy is not None:
        if vacancy.requested_on:
            values["ingediend_op"] = day(vacancy.requested_on)
        requester = (
            context.people.get(vacancy.requester_id) if vacancy.requester_id else None
        )
        if vacancy.requester_id is not None and vacancy.requester_id == reader_id:
            values["aanvrager"] = "jou"
        elif requester and may_name:
            values["aanvrager"] = requester

    # Who does the work, for a reader who waits.
    if view.assignee_name:
        values["wie"] = view.assignee_name
    elif task.status == "waiting" and task.waiting_on:
        # The plan says "de opdrachtgever"; the reader knows which one.
        named_client = values.get("opdrachtgever")
        values["wie"] = (
            named_client
            if named_client and task.waiting_on == "de opdrachtgever"
            else task.waiting_on
        )
    elif (
        task.assignee_role in ("owner", "manager")
        and task.assignment_id in context.owners
    ):
        owner = context.owners[task.assignment_id]
        values["wie"] = (
            owner
            if task.assignee_role == "owner"
            else f"{owner} of een manager van de opdracht"
        )
    elif task.assignee_role:
        values["wie"] = _ROLE_WORDS.get(task.assignee_role, "een ander")

    kind = task.subject_kind
    if kind in ("month_to_close", "closed_month", "correction_month"):
        words = _month_words(task.repeat_key or "")
        if words:
            values["maand"] = words
            # A month is also a billing period, for a task of an older plan.
            values["periode"] = words
    elif kind in ("billing_period", "period_correction"):
        try:
            values["periode"] = period_words(task.repeat_key or "")
        except (ValueError, IndexError):
            pass
        correction = context.corrections.get(task.subject_id or "")
        if correction is not None:
            # Whole euros: the exact amount is on the page it leads to.
            values["bedrag"] = _euros(correction.amount_cents)
            cause = billing_corrections.causes_text(correction)
            if cause:
                values["oorzaak"] = cause
    elif kind == "open_role":
        line = context.lines.get(task.subject_id or "")
        if line is not None:
            values["rol"] = line.description or line.role or "rol"
    elif kind in ("text", "text_review"):
        word = _TEXT_WORDS.get((task.repeat_key or "").split(":", 1)[0])
        if word:
            values["tekst"] = word
    quote = context.quotes.get(task.subject_id or "")
    if quote is not None and quote.reference:
        values["kenmerk"] = quote.reference
    rejection = context.rejections.get(task.subject_id or "")
    if rejection is not None:
        values["afgewezen_op"] = f" op {day(clock.local_date(rejection.rejected_at))}"
        # The reason is about the quote: only for who runs the case.
        if rejection.reason and may_name:
            reason = " ".join(rejection.reason.split()).rstrip(".")
            values["reden_afwijzing"] = f' De reden: "{reason}".'
    approval = context.approvals.get(task.repeat_key or "")
    if approval is not None:
        values["gevraagd_op"] = day(clock.local_date(approval.requested_at))
        asker = (
            context.people.get(approval.requested_by_id)
            if approval.requested_by_id
            else None
        )
        if (
            approval.requested_by_id is not None
            and approval.requested_by_id == reader_id
        ):
            values["gevraagd_door"] = "jou"
        elif asker:
            values["gevraagd_door"] = asker
    return values
