"""Walk an example assignment along the path, step by step, to look back at it.

For a local demo, on a database the seed filled. Run from ``backend/``::

    uv run python -m grip.dev.chronicle_walk new
    uv run python -m grip.dev.chronicle_walk next <id>
    uv run python -m grip.dev.chronicle_walk run <id> --to tekenen
    uv run python -m grip.dev.chronicle_walk rebuild <id>

or ``just kroniek-nieuw``, ``just kroniek-stap <id>``, ``just kroniek-check`` and
``just kroniek-herstel <id>`` from the repo root.

Each step goes through the real services as the right example person, with a
commit of its own, and is chosen from the same facts and course the screens
read. ``--days N`` lays the facts N days apart, so the history has a time axis:
``new --days N`` starts far enough back for a whole walk to end about today.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.chronicle import words
from grip.chronicle.facts import FACTS
from grip.chronicle.verify import rebuild
from grip.chronicle.writer import plan_version_of
from grip.core import clock
from grip.core.config import get_settings
from grip.dev.seed import EMAIL_DOMAIN, EXAMPLE_TOOI, ensure_local_instance
from grip.dev.seed import SeedRefusedError as RefusedError
from grip.events import context
from grip.events.stream import recording_at
from grip.models.assignment import ROLE_OWNER, Assignment, AssignmentRole
from grip.models.person import Person
from grip.models.quote import Quote
from grip.repositories.chronicle import ChronicleRepository
from grip.services import (
    assignments,
    budget_intent,
    instance_settings,
    quote_approval,
    quote_budget,
    quote_views,
    quotes,
)
from grip.services.errors import DomainError
from grip.tasks import course, engine
from grip.tasks.cases import CaseSnapshot, load_assignment_cases
from grip.tasks.handlers import register_task_handlers
from grip.tasks.plan import plan_for

BUDGET = "begroting"
QUOTE = "offerte"
ASK = "vragen"
APPROVE = "goedkeuren"
OFFER = "aanbieden"
SIGN = "tekenen"
START = "starten"
STEPS = (BUDGET, QUOTE, ASK, APPROVE, OFFER, SIGN, START)

_OWNER = "priya.product"
_APPROVER = "sem.senior"
_SIGNER = "tess.teken"
_BEHEERDER = "bente.beheer"


class WalkError(Exception):
    """The walk cannot go on. The message says why, in Dutch."""


@contextmanager
def _on(moment: datetime | None) -> Iterator[None]:
    """Everything in this block happens at this moment, when one is given."""
    if moment is None:
        yield
        return
    with clock.at(moment), recording_at(moment):
        yield


async def _person(db: AsyncSession, key: str) -> Person:
    person = await db.scalar(
        select(Person).where(Person.email == f"{key}@{EMAIL_DOMAIN}")
    )
    if person is None:
        raise WalkError(f"{key} ontbreekt. Laad eerst de voorbeeldgegevens: just seed")
    return person


async def _assignment(db: AsyncSession, assignment_id: UUID) -> Assignment:
    assignment = await db.get(Assignment, assignment_id)
    if assignment is None:
        raise WalkError(f"Er is geen opdracht met id {assignment_id}.")
    return assignment


async def _owner(db: AsyncSession, assignment_id: UUID) -> Person:
    person = await db.scalar(
        select(Person)
        .join(AssignmentRole, AssignmentRole.person_id == Person.id)
        .where(
            AssignmentRole.assignment_id == assignment_id,
            AssignmentRole.role == ROLE_OWNER,
        )
    )
    return person if person is not None else await _person(db, _OWNER)


async def _quote_in_force(db: AsyncSession, assignment_id: UUID) -> Quote:
    quote = await quote_budget.quote_in_force(db, assignment_id)
    if quote is None:
        raise WalkError("Deze opdracht heeft geen offerte om mee verder te gaan.")
    return quote


def _address(assignment_id: UUID, seq: int | None = None) -> str:
    base = get_settings().FRONTEND_URL.rstrip("/")
    moment = f"?moment={seq}" if seq is not None else ""
    return f"{base}/opdrachten/{assignment_id}/geschiedenis{moment}"


# -- which step is next --------------------------------------------------------


async def _facts_now(
    db: AsyncSession, assignment_id: UUID
) -> tuple[CaseSnapshot, str | None]:
    """The facts of the case and the step of the course it is at."""
    [snapshot] = await load_assignment_cases(
        db,
        {assignment_id},
        today=clock.today(),
        instance_base_uri=get_settings().INSTANCE_BASE_URI,
    )
    plan = plan_for(await plan_version_of(db, assignment_id))
    views = course.at_moment(snapshot, plan, engine.asked_for(snapshot, plan))
    own = next((view for view in views if view.subject == "case"), None)
    return snapshot, own.current_key if own is not None else None


async def next_step(db: AsyncSession, assignment_id: UUID) -> str | None:
    """The step this walk can take now. None once the case has started."""
    snapshot, current = await _facts_now(db, assignment_id)
    if current == "goedkeuring":
        return APPROVE if course.holds("approval_asked", snapshot) else ASK
    return {
        "begroting": BUDGET,
        "offerte": QUOTE,
        "aanbieden": OFFER,
        "akkoord": SIGN,
        "starten": START,
    }.get(current or "")


# -- the steps -----------------------------------------------------------------


async def _do_budget(
    db: AsyncSession, assignment: Assignment, moment: datetime | None
) -> None:
    await budget_intent.add_line(
        db,
        assignment.id,
        actor=await _owner(db, assignment.id),
        description="",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("0.8"),
        rate_category="D",
        start_date=assignment.start_date,
        end_date=assignment.end_date,
    )


async def _do_quote(
    db: AsyncSession, assignment: Assignment, moment: datetime | None
) -> None:
    await quotes.issue_quote(
        db,
        assignment.id,
        actor=await _owner(db, assignment.id),
        valid_until=clock.today() + timedelta(days=60),
        issued_at=moment,
    )


async def _do_ask(
    db: AsyncSession, assignment: Assignment, moment: datetime | None
) -> None:
    quote = await _quote_in_force(db, assignment.id)
    await quote_approval.request_approval(
        db,
        quote.id,
        actor=await _owner(db, assignment.id),
        note="Graag nakijken voor het aanbieden.",
    )


async def _do_approve(
    db: AsyncSession, assignment: Assignment, moment: datetime | None
) -> None:
    quote = await _quote_in_force(db, assignment.id)
    await quote_approval.decide(
        db,
        quote.id,
        approve=True,
        actor=await _person(db, _APPROVER),
        quote_hash=quote.snapshot_hash,
        decided_at=moment,
    )


async def _do_offer(
    db: AsyncSession, assignment: Assignment, moment: datetime | None
) -> None:
    quote = await _quote_in_force(db, assignment.id)
    signer = await _person(db, _SIGNER)
    await quotes.offer_quote(
        db,
        quote.id,
        "signing_link",
        actor=await _owner(db, assignment.id),
        email=signer.email,
    )


async def _do_sign(
    db: AsyncSession, assignment: Assignment, moment: datetime | None
) -> None:
    quote = await _quote_in_force(db, assignment.id)
    signer = await _person(db, _SIGNER)
    await quotes.accept_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name=signer.name,
        signer_email=f"{_SIGNER}@{EMAIL_DOMAIN}",
        signer_person_id=signer.id,
        organisation=await quote_views.client_reference(db, assignment),
        form="signing_link",
        actor=signer,
        signed_at=moment,
        declared_mandate=True,
    )


async def _do_start(
    db: AsyncSession, assignment: Assignment, moment: datetime | None
) -> None:
    await assignments.transition(
        db, assignment.id, "in_progress", actor=await _owner(db, assignment.id)
    )


_ACTIONS = {
    BUDGET: _do_budget,
    QUOTE: _do_quote,
    ASK: _do_ask,
    APPROVE: _do_approve,
    OFFER: _do_offer,
    SIGN: _do_sign,
    START: _do_start,
}


# -- the commands ----------------------------------------------------------------


async def create(db: AsyncSession, *, approval: bool) -> Assignment:
    """A fresh example assignment, owned by a seeded person."""
    owner = await _person(db, _OWNER)
    if approval:
        await instance_settings.set_values(
            db,
            {quote_approval.MODE.key: quote_approval.MODE_ALWAYS},
            actor=await _person(db, _BEHEERDER),
        )
    client = await assignments.upsert_organisation(
        db,
        name="Voorbeeldministerie",
        tooi_uri=f"{EXAMPLE_TOOI}/ministerie/mnre9001",
    )
    count = await db.scalar(
        select(func.count())
        .select_from(Assignment)
        .where(Assignment.name.like("Voorbeeldtraject %"))
    )
    year = clock.today().year
    return await assignments.create_assignment(
        db,
        name=f"Voorbeeldtraject {(count or 0) + 1}",
        actor=owner,
        client_organisation_id=client.id,
        client_contact="Afdeling Voorbeeld",
        start_date=date(year, 1, 1),
        end_date=date(year, 12, 31),
    )


async def _new(approval: bool, days: int) -> None:
    from grip.core.database import async_session

    moment = clock.now() - timedelta(days=days * (len(STEPS) + 1)) if days > 0 else None
    async with async_session() as db:
        with context.scope(), _on(moment):
            assignment = await create(db, approval=approval)
            await db.commit()
    print(f"Opdracht toegevoegd: {assignment.name}")
    print(f"Id: {assignment.id}")
    print(f"Interne goedkeuring: {'altijd' if approval else 'zoals ingesteld'}")
    print(f"Bekijk: {_address(assignment.id)}")
    print(f"Volgende stap: just kroniek-stap {assignment.id}")


async def _take_step(assignment_id: UUID, days: int) -> str | None:
    """Do the next step in a transaction of its own. Returns which it was."""
    from grip.core.database import async_session

    async with async_session() as db:
        repository = ChronicleRepository(db)
        grams = await repository.grams(assignment_id)
        last = grams[-1] if grams else None
        moment = (
            last.occurred_at + timedelta(days=days)
            if days > 0 and last is not None
            else None
        )
        with context.scope(), _on(moment):
            assignment = await _assignment(db, assignment_id)
            step = await next_step(db, assignment_id)
            if step is None:
                print(f"Niets meer te doen op dit pad: {assignment.name}.")
                return None
            await _ACTIONS[step](db, assignment, moment)
            await db.commit()
        made = [
            gram
            for gram in await repository.grams(assignment_id)
            if (last is None or gram.seq > last.seq) and FACTS[gram.fact].moment
        ]
        names = await quote_views.person_names(
            db, {gram.actor_person_id for gram in made if gram.actor_person_id}
        )
        print(f"Stap: {step}")
        for gram in made:
            who = names.get(gram.actor_person_id)
            sentence = words.statement(gram.fact, gram.fields, actor=who)
            print(f"Vastgelegd: {sentence}")
            print(
                f"  door {who or 'het systeem'}, op {words.day_words(gram.occurred_at)}"
            )
        if made:
            print(f"Bekijk: {_address(assignment_id, made[-1].seq)}")
    return step


async def _next(assignment_id: UUID, days: int) -> None:
    await _take_step(assignment_id, days)


async def _run(assignment_id: UUID, to: str, days: int) -> None:
    while True:
        from grip.core.database import async_session

        async with async_session() as db:
            with context.scope():
                upcoming = await next_step(db, assignment_id)
        if upcoming is None or STEPS.index(upcoming) > STEPS.index(to):
            print(f"Tot {to} is er niets meer te doen.")
            return
        step = await _take_step(assignment_id, days)
        if step == to or step is None:
            return


async def _rebuild(assignment_id: UUID) -> None:
    from grip.core.database import async_session

    async with async_session() as db:
        with context.scope():
            await _assignment(db, assignment_id)
            try:
                changed = await rebuild(db, assignment_id)
            except ValueError as exc:
                raise WalkError(str(exc)) from exc
            await db.commit()
    if changed:
        print(f"{changed} verschillen hersteld uit de kroniek.")
    else:
        print("Geen verschillen: de tabellen zeggen wat de kroniek zegt.")


async def _main(args: argparse.Namespace) -> int:
    from grip.core.database import close_db

    try:
        ensure_local_instance(get_settings())
        register_task_handlers()
        if args.command == "new":
            await _new(not args.geen_goedkeuring, args.days)
        elif args.command == "next":
            await _next(args.id, args.days)
        elif args.command == "run":
            await _run(args.id, args.to, args.days)
        else:
            await _rebuild(args.id)
        return 0
    except (RefusedError, WalkError, DomainError) as exc:
        print(f"Geweigerd: {exc}")
        return 1
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Loop een voorbeeldopdracht stap voor stap langs het pad."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="maak een nieuwe voorbeeldopdracht")
    new.add_argument(
        "--geen-goedkeuring",
        action="store_true",
        help="zet interne goedkeuring niet aan",
    )
    step = commands.add_parser("next", help="zet de volgende stap")
    step.add_argument("id", type=UUID)
    run = commands.add_parser("run", help="zet stappen tot en met een stap")
    run.add_argument("id", type=UUID)
    run.add_argument("--to", choices=STEPS, default=START)
    for command in (new, step, run):
        command.add_argument(
            "--days",
            type=int,
            default=0,
            help="aantal dagen tussen de feiten (0: nu)",
        )
    again = commands.add_parser("rebuild", help="herstel een opdracht uit de kroniek")
    again.add_argument("id", type=UUID)
    raise SystemExit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
