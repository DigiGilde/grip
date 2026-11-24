"""Walking the path of an assignment through HTTP, as the real roles.

After every step the rows must equal the fold, and what a reader sees live is
kept. Afterwards every look-back must say what was seen then. All names and
amounts are fictional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from grip.chronicle.verify import differences
from grip.core import clock
from grip.core.auth import DEV_PERSON_COOKIE
from grip.models.person import Person
from grip.services import assignments, rates

YEAR = clock.today().year
RATES = {"A": 900000, "B": 1200000, "C": 1500000, "D": 1800000, "E": 2100000}
SCALES = {8: "A", 10: "B", 12: "C", 14: "D", 16: "E"}
# On the instance's calendar: a function granted today starts on that day.
START = datetime.combine(clock.today(), time(10), tzinfo=clock.zone())
PDF_BYTES = b"%PDF-1.4\n%voorbeeld\n"
STARTED = ("in_progress", "completed", "accounted")


def day(number: int) -> datetime:
    """A moment on the given day of the walk."""
    return START + timedelta(days=number)


def line_body(fte: str = "0.5", **changes: Any) -> dict[str, Any]:
    return {
        "kind": "personnel",
        "role": "Productmanager",
        "fte": fte,
        "rate_category": "D",
        "start_date": f"{YEAR}-01-01",
        "end_date": f"{YEAR}-12-31",
        **changes,
    }


@dataclass
class Cast:
    beheerder: Person
    owner: Person
    planner: Person
    reader: Person
    member: Person
    outsider: Person
    approver: Person
    signer: Person
    client_id: UUID


async def make_cast(
    db_session: AsyncSession, create_person: Any, *, with_rate_card: bool = True
) -> Cast:
    beheerder = await create_person(
        "beheerder@example.org", name="Bente Voorbeeld", functions=["beheerder"]
    )
    if with_rate_card:
        await add_rate_card(db_session, YEAR, beheerder)
    client = await assignments.upsert_organisation(
        db_session,
        name="Voorbeeldministerie",
        tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre9001",
    )
    member = await create_person("teamlid@example.org", name="Daan Voorbeeld")
    await rates.set_person_scale(
        db_session, member.id, date(YEAR, 1, 1), 14, actor=beheerder
    )
    await db_session.flush()
    return Cast(
        beheerder=beheerder,
        owner=await create_person(
            "eigenaar@example.org", name="Priya Voorbeeld", functions=["planner"]
        ),
        planner=await create_person(
            "planner@example.org", name="Pim Voorbeeld", functions=["planner"]
        ),
        reader=await create_person(
            "lezer@example.org", name="Lotte Voorbeeld", functions=["lezer"]
        ),
        member=member,
        outsider=await create_person("buiten@example.org", name="Olaf Voorbeeld"),
        approver=await create_person(
            "akkoord@example.org",
            name="Sem Voorbeeld",
            functions=["offertegoedkeurder"],
        ),
        signer=await create_person("tekenaar@voorbeeld.example", name="Tess Voorbeeld"),
        client_id=client.id,
    )


async def add_rate_card(db_session: AsyncSession, year: int, actor: Person) -> None:
    await rates.create_rate_card(db_session, year, actor=actor)
    for category, cents in RATES.items():
        await rates.set_rate_band(db_session, year, category, cents, actor=actor)
    for scale, category in SCALES.items():
        await rates.set_scale_band(db_session, year, scale, category, actor=actor)
    await rates.set_rate_card_status(db_session, year, "active", actor=actor)


def comparable(course: dict[str, Any] | None) -> dict[str, Any] | None:
    """What a look-back and a watcher must agree on. Not ids, days or who."""
    if course is None:
        return None
    told = course.get("next")
    return {
        "key": course["key"],
        "steps": [
            (step["key"], step["label"], step["state"], step.get("note"))
            for step in course["steps"]
        ],
        "current_key": course.get("current_key"),
        "position": course.get("position"),
        "ended": course.get("ended"),
        "next": told["headline"] if told else None,
    }


_LINE_FIELDS = (
    "id",
    "description",
    "kind",
    "position",
    "role",
    "fte",
    "start_date",
    "end_date",
    "rate_category",
    "amount_cents",
    "year",
    "budgeted_cents",
)
_QUOTE_FIELDS = (
    "id",
    "reference",
    "status",
    "total_cents",
    "valid_until",
    "snapshot_hash",
    "document_sha256",
    "issued_at",
    "content",
)


@dataclass
class Seen:
    """What the live routes said right after one step."""

    label: str
    seq: int
    course: dict[str, Any] | None
    budget: dict[str, Any]
    quotes: list[dict[str, Any]]
    assignment: dict[str, Any]
    started: bool


@dataclass
class Walk:
    client: AsyncClient
    db: AsyncSession
    cast: Cast
    assignment_id: str = ""
    seen: list[Seen] = field(default_factory=list)

    def as_person(self, person: Person) -> AsyncClient:
        self.client.cookies.set(DEV_PERSON_COOKIE, str(person.id))
        return self.client

    async def call(
        self, person: Person, method: str, path: str, **kwargs: Any
    ) -> dict[str, Any]:
        response: Response = await getattr(self.as_person(person), method)(
            path, **kwargs
        )
        assert response.status_code < 300, f"{path}: {response.text}"
        return response.json() if response.content else {}

    async def begin(self, on: int = 0, **changes: Any) -> str:
        with clock.at(day(on)):
            body = await self.call(
                self.cast.owner,
                "post",
                "/api/assignments",
                json={
                    "name": "Voorbeeldtraject",
                    "client_organisation_id": str(self.cast.client_id),
                    "start_date": f"{YEAR}-01-01",
                    "end_date": f"{YEAR}-12-31",
                    **changes,
                },
            )
            self.assignment_id = body["id"]
            await self.look("gemaakt")
        return self.assignment_id

    async def step(
        self,
        label: str,
        person: Person,
        method: str,
        path: str,
        *,
        on: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        with clock.at(day(on)):
            body = await self.call(person, method, path, **kwargs)
            await self.look(label)
        return body

    async def look(self, label: str) -> None:
        """Compare rows with the fold and keep what the live routes say."""
        aid = self.assignment_id
        await self.db.flush()
        report = await differences(self.db, UUID(aid))
        assert report.checked, f"{label}: {report.reason}"
        assert report.differences == [], (
            f"{label}: {[str(item) for item in report.differences]}"
        )
        watcher = self.cast.reader
        course = await self.call(
            watcher, "get", f"/api/tasks/cases/assignment/{aid}/course"
        )
        everything = self.cast.beheerder
        budget = await self.call(everything, "get", f"/api/assignments/{aid}/budget")
        listed = await self.call(everything, "get", f"/api/assignments/{aid}/quotes")
        quotes = [
            await self.call(everything, "get", f"/api/quotes/{quote['id']}")
            for quote in listed["quotes"]
        ]
        assignment = await self.call(everything, "get", f"/api/assignments/{aid}")
        moments = await self.moments(everything)
        self.seen.append(
            Seen(
                label=label,
                seq=moments[-1]["seq"],
                course=course.get("course"),
                budget=budget,
                quotes=quotes,
                assignment=assignment,
                started=assignment["status"]
                in ("in_progress", "completed", "accounted"),
            )
        )

    async def moments(self, person: Person) -> list[dict[str, Any]]:
        body = await self.call(
            person, "get", f"/api/assignments/{self.assignment_id}/chronicle"
        )
        return body["items"]

    async def stand(self, seq: int, person: Person | None = None) -> dict[str, Any]:
        return await self.call(
            person or self.cast.beheerder,
            "get",
            f"/api/assignments/{self.assignment_id}/chronicle/{seq}",
        )

    async def check_every_look_back(self) -> None:
        """Every look-back says what was seen live at that step."""
        assert self.seen, "nothing was walked"
        for seen in self.seen:
            stand = await self.stand(seen.seq)
            where = f"{seen.label} (moment {seen.seq})"
            assert stand["moment"]["seq"] == seen.seq, where
            assert stand["incomplete"] is False, where
            _same_course(stand, seen, where)
            _same_budget(stand, seen, where)
            _same_quotes(stand, seen, where)
            _same_assignment(stand, seen, where)


def _same_course(stand: dict[str, Any], seen: Seen, where: str) -> None:
    live, then = comparable(seen.course), comparable(stand["course"])
    if seen.started:
        # Whose turn it is after the start rests on what the chronicle has not.
        assert then is not None and then["next"] is None, where
        assert live is not None, where
        live = {**live, "next": None}
    assert then == live, where


def _same_budget(stand: dict[str, Any], seen: Seen, where: str) -> None:
    budget = stand["budget"]
    assert budget["total_budgeted_cents"] == seen.budget["total_budgeted_cents"], where
    assert budget["subtotals_by_year"] == seen.budget["subtotals_by_year"], where
    assert budget["pricing_error"] == seen.budget["pricing_error"], where
    lines = [
        {name: line.get(name) for name in _LINE_FIELDS} for line in budget["lines"]
    ]
    live = [
        {name: line.get(name) for name in _LINE_FIELDS} for line in seen.budget["lines"]
    ]
    assert lines == live, where


def _same_quotes(stand: dict[str, Any], seen: Seen, where: str) -> None:
    pick = [
        {name: quote.get(name) for name in _QUOTE_FIELDS} for quote in stand["quotes"]
    ]
    live = [{name: quote.get(name) for name in _QUOTE_FIELDS} for quote in seen.quotes]
    assert _instants(pick) == _instants(live), where
    for then, now in zip(stand["quotes"], seen.quotes, strict=True):
        assert [o["channel"] for o in then["offers"]] == [
            o["channel"] for o in now["offers"]
        ], where
        assert [o["recipient"] for o in then["offers"]] == [
            o["recipient"] for o in now["offers"]
        ], where
        assert [o["offered_by_name"] for o in then["offers"]] == [
            o["offered_by_name"] for o in now["offers"]
        ], where
        accepted, live_accepted = then["acceptance"], now["acceptance"]
        assert (accepted is None) == (live_accepted is None), where
        if accepted is not None:
            assert accepted["signer_name"] == live_accepted["signer_name"], where
            assert accepted["form"] == live_accepted["form"], where
            assert _instant(accepted["signed_at"]) == _instant(
                live_accepted["signed_at"]
            ), where
        rejected, live_rejected = then["rejection"], now["rejection"]
        assert (rejected is None) == (live_rejected is None), where
        if rejected is not None:
            assert rejected["reason"] == live_rejected["reason"], where


def _same_assignment(stand: dict[str, Any], seen: Seen, where: str) -> None:
    for name in (
        "name",
        "status",
        "kind",
        "start_date",
        "end_date",
        "notes",
        "quote_date",
        "verbal_agreement_note",
        "client_name",
    ):
        assert stand["assignment"][name] == seen.assignment[name], f"{where}: {name}"


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _instants(quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**quote, "issued_at": _instant(quote["issued_at"])} for quote in quotes]
