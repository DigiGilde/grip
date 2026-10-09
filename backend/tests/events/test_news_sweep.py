"""Every kind of news against every kind of reader.

One invariant, checked over the whole list instead of a chosen day: a reader
never gets an item, in "Wat is er gebeurd" or in the history, about an
assignment, a vacancy or a person they could not open. Every rule of
``news.NEWS`` is made to happen on an assignment the readers are part of,
on one they are not, on a vacancy of someone else, and about a person; a new
rule that cannot be made to happen here fails the test, so it gets swept too.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from grip.events import news, stream
from grip.models.vacancy import Vacancy

_VERB_ACTION = {"created": "create", "updated": "update", "deleted": "delete"}
_STATUSES = (
    "active",
    "cancelled",
    "completed",
    "filled",
    "in_progress",
    "open",
    "requested",
)
_CANDIDATES: tuple[dict, ...] = (
    {},
    {"established": True},
    *({"status": status} for status in _STATUSES),
    *(
        {"kind": kind, "agreed": agreed}
        for kind in ("approval", "hr_advice", "control_advice")
        for agreed in (True, False)
    ),
)
_OPEN = {
    "opdrachten": "/api/assignments/{id}",
    "vacatures": "/api/vacancies/{id}",
    "team": "/api/people/{id}",
}
_ID = re.compile(r"^/(opdrachten|vacatures|team)/([0-9a-f-]{36})")


def _values_for(rule: news.News, event_type: str) -> dict:
    """Values that make an event of this type fall under this rule."""
    for values in _CANDIDATES:
        probe = SimpleNamespace(type=event_type, new_value=values, old_value=None)
        if news.rule_for(probe) is rule:  # type: ignore[arg-type]
            return values
    raise AssertionError(
        f"De regel {rule.key} ({event_type}) is hier niet na te maken: vul "
        "_CANDIDATES aan, zodat ook deze regel wordt nagelopen."
    )


def _happen(
    db, rule: news.News, event_type: str, values: dict, subject=None, **where
) -> None:
    kind, _, verb = event_type.partition(".")
    action = _VERB_ACTION.get(verb)
    stream.append(
        db,
        None if action else event_type,
        subject=(kind, subject or uuid.uuid4()),
        action=action,
        new=values,
        **where,
    )


async def _all_items(client, url: str, cursor: str, **params) -> list[dict]:
    items: list[dict] = []
    after = None
    for _ in range(40):
        answer = await client.get(
            url, params={**params, **({cursor: after} if after else {})}
        )
        assert answer.status_code == 200, answer.text
        body = answer.json()
        items += body["items"]
        after = body.get("next") or body.get("next_before")
        if not after:
            break
    return items


async def test_nobody_gets_news_about_what_they_cannot_open(
    client, as_person, world, create_person, db_session
):
    db = db_session
    requester = await create_person(
        "aanvraag@example.org", name="Aaf Aanvraag", functions=["aanvrager"]
    )
    signatory = await create_person(
        "teken@example.org", name="Tes Teken", functions=["tekenbevoegde"]
    )
    approver = await create_person(
        "keur@example.org", name="Kee Keur", functions=["offertegoedkeurder"]
    )
    vacancy = Vacancy(
        function_title="Developer",
        fte=Decimal("1"),
        declarable=False,
        vacancy_type="regulier",
        status="requested",
        requester_id=world.owner.id,
        requested_on=date(2026, 10, 1),
    )
    db.add(vacancy)
    await db.flush()

    made = 0
    for rule in news.NEWS:
        for event_type in rule.types:
            values = _values_for(rule, event_type)
            if rule.object_is_subject:
                # The assignment itself is the subject, without a case.
                for assignment in (world.assignment, world.other_assignment):
                    _happen(db, rule, event_type, values, subject=assignment.id)
                    made += 1
                continue
            for where in (
                {"assignment_id": world.assignment.id},
                {"assignment_id": world.other_assignment.id},
                {"vacancy_id": vacancy.id},
                {"person_id": world.colleague.id},
                {"assignment_id": world.assignment.id, "person_id": world.member.id},
            ):
                # An event about an assignment or a vacancy itself names a
                # real one; anything else is a new thing of its kind.
                itself = {
                    "assignment": where.get("assignment_id", world.assignment.id),
                    "vacancy": vacancy.id,
                    "person": where.get("person_id", world.colleague.id),
                }.get(event_type.partition(".")[0])
                _happen(db, rule, event_type, values, subject=itself, **where)
                made += 1
    await db.flush()
    assert made >= 4 * len(news.NEWS)

    readers = {
        "beheerder": world.beheerder,
        "lezer": world.lezer,
        "planner": world.planner,
        "owner": world.owner,
        "member": world.member,
        "colleague": world.colleague,
        "outsider": world.outsider,
        "aanvrager": requester,
        "tekenbevoegde": signatory,
        "offertegoedkeurder": approver,
    }
    got: dict[str, int] = {}
    for name, person in readers.items():
        reader = as_person(person)
        feed = await _all_items(reader, "/api/updates", "na", limiet=50)
        got[name] = len(feed)
        targets = {
            match.groups()
            for item in feed
            for part in item.get("parts", [])
            if part.get("href") and (match := _ID.match(part["href"]))
        }
        history = await _all_items(reader, "/api/events", "before", limit=200)
        targets |= {
            (
                "opdrachten" if event["case_kind"] == "assignment" else "vacatures",
                event["case_id"],
            )
            for event in history
            if event.get("case_id")
        }
        targets |= {
            ("team", event["person_id"]) for event in history if event.get("person_id")
        }
        source = {
            (
                ("opdrachten" if e["case_kind"] == "assignment" else "vacatures"),
                e["case_id"],
            ): e["type"]
            for e in history
            if e.get("case_id")
        }
        names = {
            str(world.assignment.id): "own",
            str(world.other_assignment.id): "other",
        }
        for place, target in sorted(targets):
            opened = await as_person(person).get(_OPEN[place].format(id=target))
            assert opened.status_code == 200, (
                f"{name} leest nieuws of geschiedenis over {place}/{target} "
                f"en kan dat niet openen ({opened.status_code}); "
                f"{names.get(target, '?')}, "
                f"uit de geschiedenis: {source.get((place, target))}"
            )

    # Who has no part in anything and no function for the whole instance
    # reads nothing; who reads the whole instance reads a lot.
    for nobody in ("outsider", "aanvrager", "tekenbevoegde", "offertegoedkeurder"):
        assert got[nobody] == 0, (nobody, got[nobody])
    assert got["beheerder"] > 20 and got["owner"] > 5
