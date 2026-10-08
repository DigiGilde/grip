"""How a task is told to its reader: the guidance, and what each reader hears."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pytest

from grip.models.person import Person
from grip.models.vacancy import Vacancy
from grip.tasks import telling
from grip.tasks.plan import known_plans

FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "src"


# --- the guidance ------------------------------------------------------------


def test_every_template_of_every_plan_has_guidance():
    """A new template without guidance fails here, with its key."""
    assert telling.templates_without_guidance() == []


def test_guidance_has_everything_the_screen_needs():
    guidance = telling.guidance()
    for key, guide in guidance.templates.items():
        for name in ("title", "awaited", "do", "wait", "action", "why"):
            assert getattr(guide, name).strip(), f"{key}: {name}"
        assert guide.destination in guidance.destinations, key
        # The waiter is never told to do the doer's work.
        assert guide.wait != guide.do, key


def test_sentences_follow_the_house_rules():
    for key, guide in telling.guidance().templates.items():
        texts = [guide.title, guide.awaited, guide.do, guide.wait, guide.action]
        texts += [guide.why, guide.then or ""]
        for override in guide.situations.values():
            texts += list(override.values())
        for text in texts:
            assert chr(0x2014) not in text, f"{key}: no dash as punctuation"
            assert "sluit vanzelf" not in text.lower(), f"{key}: explains the system"


def _routes() -> list[re.Pattern[str]]:
    """Every address the frontend serves, as a pattern."""
    paths = re.findall(r":\s*'(/[^']*)'", (FRONTEND / "paths.ts").read_text())
    for folder, base in (
        ("vacancies", "/vacatures/:id"),
        ("assignments", "/opdrachten/:id"),
    ):
        source = (FRONTEND / "features" / folder / "paths.ts").read_text()
        block = source.split("TAB_SEGMENTS = {", 1)[1].split("}", 1)[0]
        for segment in re.findall(r":\s*'([^']*)'", block):
            paths.append(f"{base}/{segment}" if segment else base)
    return [re.compile("^" + re.sub(r":\w+", "[^/]+", path) + "$") for path in paths]


@pytest.mark.skipif(not (FRONTEND / "paths.ts").exists(), reason="no frontend here")
def test_every_destination_is_a_page_that_exists():
    routes = _routes()
    for name, path in telling.guidance().destinations.items():
        address = re.sub(r"\{\w+\}", "x", path).split("?", 1)[0]
        assert any(route.match(address) for route in routes), f"{name}: {address}"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"do": "Doe iets met {onbekend}."}, "onbekende naam"),
        ({"destination": "nergens"}, "onbekende bestemming"),
        ({"situations": {"verzonnen": {"do": "x"}}}, "onbekende stand"),
        ({"situations": {"unnamed": {"why": "x"}}}, "kan dit niet vervangen"),
        ({"action": ""}, "ontbreekt"),
        ({"knop": "x"}, "onbekende instelling"),
    ],
)
def test_guidance_that_reaches_past_what_is_offered_is_refused(change, message):
    entry = {
        "title": "Doe iets",
        "awaited": "Iets",
        "do": "Doe iets voor {opdracht}.",
        "wait": "Je wacht op {wie}.",
        "action": "Doe het",
        "why": "Er gebeurde iets.",
        "destination": "hier",
    }
    data = {"destinations": {"hier": "/opdrachten/{assignment_id}"}}
    with pytest.raises(telling.GuidanceError, match=message):
        telling.parse_guidance({**data, "templates": {"x": {**entry, **change}}})


def test_plans_known_here_include_the_running_ones():
    assert len(known_plans()) >= 2


# --- what a reader hears ---------------------------------------------------------


@dataclass
class World:
    beheerder: Person
    planner: Person
    owner: Person
    requester: Person
    adviser: Person
    vacancy: Vacancy


@pytest.fixture
async def world(build, create_person) -> World:
    beheerder = await create_person("beheer@example.org", functions=["beheerder"])
    planner = await create_person("planner@example.org", functions=["planner"])
    owner = await create_person("eigenaar@example.org", name="Eva Eigenaar")
    requester = await create_person(
        "vraag@example.org", name="Vera Vraag", functions=["planner"]
    )
    adviser = await create_person("advies@example.org", name="Ad Advies")
    client = await build.organisation("Voorbeeldministerie")
    start = date.today().replace(day=1)
    assignment = await build.assignment(
        status="accepted",
        owner=owner,
        client=client,
        start=start,
        end=start + timedelta(days=200),
    )
    await build.line(assignment, "Ontwerper")
    vacancy = await build.vacancy(status="requested", requester=requester)
    return World(
        beheerder=beheerder,
        planner=planner,
        owner=owner,
        requester=requester,
        adviser=adviser,
        vacancy=vacancy,
    )


async def mine(client) -> dict:
    return (await client.get("/api/tasks/mine")).json()


def by_headline(body: dict, group: str = "items") -> dict[str, dict]:
    return {task["headline"]: task for task in body.get(group, [])}


async def test_the_doer_hears_what_to_do_and_where(as_person, world):
    body = await mine(as_person(world.owner))
    task = by_headline(body)["Zet de opdracht in uitvoering"]
    assert task["needs_me"] is True
    assert task["instruction"].startswith("Er is akkoord op Opdracht Alfa 2026.")
    assert task["action_text"] == "Zet in uitvoering"
    assert task["work_href"] == f"/opdrachten/{task['assignment_id']}"
    assert task["why"] == "Er is akkoord gegeven op de offerte voor Opdracht Alfa 2026."
    assert task["then"]
    assert "waits_on" not in task or task["waits_on"] is None


async def test_the_owner_sees_what_others_must_do_on_the_assignment(as_person, world):
    body = await mine(as_person(world.owner))
    waited = by_headline(body, "awaited")["De invulling van de rol Ontwerper"]
    assert waited.get("needs_me", False) is False
    assert waited["instruction"].startswith("Je wacht op een planner")
    assert waited["instruction"].endswith("Jij hoeft nu niets te doen.")
    assert waited.get("action_text") is None
    assert waited["waits_on"] == "een planner"
    # It is the planner's to do, in the planner's own words.
    planner = by_headline(await mine(as_person(world.planner)))
    assert planner["Vul de rol Ontwerper in"]["needs_me"] is True
    # Nothing of the owner's own list is repeated under what is waited for.
    own = {task["id"] for task in body["items"]}
    assert not own & {task["id"] for task in body["awaited"]}


async def test_the_badge_counts_only_what_needs_me(as_person, world):
    owner = (await as_person(world.owner).get("/api/tasks/count")).json()
    assert owner["to_do"] == 1
    # The requester has two advices to wait for, and nothing else to do on
    # them than naming who gives them.
    requester = await mine(as_person(world.requester))
    assert requester["counts"]["to_do"] == sum(
        1 for task in requester["items"] if task.get("needs_me")
    )


async def test_advice_nobody_is_named_for_asks_the_requester_to_name_someone(
    as_person, world
):
    tasks = by_headline(await mine(as_person(world.requester)))
    task = tasks["Noem wie het advies van concern control geeft"]
    assert task["needs_me"] is True
    assert task["action_text"] == "Noem iemand"
    assert task["work_href"] == f"/vacatures/{world.vacancy.id}/advies"
    assert "door jou" in task["why"]


async def test_advice_from_someone_with_an_account_is_theirs(as_person, world, build):
    await build.decision(world.vacancy, "control_advice", person=world.adviser)
    adviser = by_headline(await mine(as_person(world.adviser)))
    task = adviser["Geef het advies van concern control"]
    assert task["needs_me"] is True and task["action_text"] == "Leg het advies vast"
    assert "Vera Vraag" in task["why"]
    # The requester waits, and is told for whom.
    requester = await mine(as_person(world.requester))
    waited = by_headline(requester, "awaited")["Het advies van concern control"]
    assert waited.get("needs_me", False) is False
    assert waited["instruction"] == (
        "Je wacht op het advies van concern control van Ad Advies. "
        "Jij hoeft nu niets te doen."
    )


async def test_advice_from_someone_without_an_account_waits_on_a_beheerder(
    as_person, world, build
):
    await build.decision(world.vacancy, "control_advice")
    requester = by_headline(await mine(as_person(world.requester)))
    task = requester["Het advies van concern control"]
    assert task.get("needs_me", False) is False
    assert "alleen een beheerder" in task["instruction"]
    assert task.get("action_text") is None


async def test_a_role_nobody_holds_says_who_can_fix_that(as_person, world, db_session):
    # Take the right away from every planner.
    from sqlalchemy import delete

    from grip.models.role import PersonRole

    await db_session.execute(delete(PersonRole).where(PersonRole.role_id == "planner"))
    await db_session.flush()
    body = await mine(as_person(world.owner))
    waited = by_headline(body, "awaited")["De invulling van de rol Ontwerper"]
    assert waited["blocked"].startswith("Niemand heeft het recht Planner")
    assert "beheerder" in waited["blocked"]


async def test_a_request_that_misses_something_lists_what(as_person, world, build):
    draft = await build.vacancy(requester=world.requester, title="Ontwerper")
    tasks = by_headline(await mine(as_person(world.requester)))
    task = tasks["Vraag de vacature aan"]
    assert task["action_text"] == "Bereid aanvraag voor"
    assert task["work_href"] == f"/vacatures/{draft.id}"
    assert [item["text"] for item in task["checklist"]] == [
        "Functienaam uit het functiegebouw",
        "Schaal",
        "Soort contract",
        "Aan wie de aanvraag is gericht",
        "Vastgestelde aanleiding en motivatie",
    ]
    assert not any(item.get("done") for item in task["checklist"])


async def test_a_name_is_only_told_to_who_runs_the_case(as_person, world, build):
    """A reader of the vacancy without rights on it gets the role, not the name."""
    await build.decision(world.vacancy, "control_advice")
    body = (
        await as_person(world.beheerder).get(
            f"/api/tasks/cases/vacancy/{world.vacancy.id}"
        )
    ).json()
    told = [task for track in body["tracks"] for task in track["tasks"]]
    assert told, "the beheerder reads the tasks of the vacancy"
    # The beheerder runs every vacancy, so the name is there for them.
    control = next(task for task in told if "concern control" in task["headline"])
    assert "Iemand zonder account" in control["instruction"]


async def test_what_a_person_must_do_now_can_be_read_for_a_notification(
    world, db_session
):
    """``to_do_of`` is what a notifier reads: to do, never what is waited on."""
    from grip.access import Subject
    from grip.access.deps import get_decider, get_relation_source
    from grip.core.config import get_settings
    from grip.tasks import engine, service
    from grip.tasks.access import TaskAccess

    settings = get_settings()
    await engine.evaluate_all(
        db_session, today=date.today(), instance_base_uri=settings.INSTANCE_BASE_URI
    )
    decider = get_decider(get_relation_source(db_session, settings))
    owner = Subject.for_person(world.owner.id, frozenset())
    items = await service.to_do_of(
        db_session, TaskAccess(db_session, decider, owner), today=date.today()
    )
    assert [(item.kind, item.headline) for item in items] == [
        ("uitvoering.starten", "Zet de opdracht in uitvoering")
    ]
    assert items[0].href and items[0].href.startswith("/opdrachten/")
