"""Following an assignment as client: progress, spending, final report."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from grip.core.audit import CREATE, record_audit
from grip.federation import terms
from grip.models.audit_log import AuditLog

from .conftest import CONTRACTOR_GRANT, example


def contractor(received, *, usage: httpx.Response | None = None):
    """A contractor instance that answers pulls for the received assignment."""
    remote_id = received.assignment.uri.rsplit("/", 1)[-1]

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["Fsc-Grant-Hash"] == CONTRACTOR_GRANT
        if request.url.path == f"/v1/opdrachten/{remote_id}/voortgang":
            return httpx.Response(
                200,
                json={**example("voortgang"), "opdracht_uri": received.assignment.uri},
            )
        if request.url.path == f"/v1/opdrachten/{remote_id}/uitputting":
            return usage or httpx.Response(
                200,
                json={**example("uitputting"), "opdracht_uri": received.assignment.uri},
            )
        return httpx.Response(404, json={"title": "Niet gevonden", "status": 404})

    return handle


async def test_progress_as_the_contractor_reports_it(
    client, cast, act_as, outway, received
):
    outway.handler = contractor(received)
    act_as(cast.requester)
    response = await client.get(
        f"/api/client/assignments/{received.assignment.id}/progress"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True and body["problem"] is None
    assert body["status"] == "in_progress" and body["as_of"] == "2026-09-30"
    assert body["summary"] == "Eerste versie opgeleverd."
    assert [m["state"] for m in body["milestones"]] == ["done", "planned"]
    assert body["delivered"] == ["Eerste versie"]

    # A planner reads assignment basics, and progress is that.
    act_as(cast.planner)
    allowed = await client.get(
        f"/api/client/assignments/{received.assignment.id}/progress"
    )
    assert allowed.status_code == 200
    act_as(cast.outsider)
    hidden = await client.get(
        f"/api/client/assignments/{received.assignment.id}/progress"
    )
    assert hidden.status_code == 404


async def test_progress_says_why_there_is_none(client, cast, act_as, outway, received):
    act_as(cast.requester)
    outway.handler = lambda _request: httpx.Response(503, text="down")
    body = (
        await client.get(f"/api/client/assignments/{received.assignment.id}/progress")
    ).json()
    assert body["available"] is False and "niet bereikbaar" in body["problem"]

    outway.handler = lambda _request: httpx.Response(404, json={"status": 404})
    body = (
        await client.get(f"/api/client/assignments/{received.assignment.id}/progress")
    ).json()
    assert "kent deze opdracht niet" in body["problem"]

    outway.handler = lambda _request: httpx.Response(200, json={"iets": "anders"})
    body = (
        await client.get(f"/api/client/assignments/{received.assignment.id}/progress")
    ).json()
    assert "niet aan het contract" in body["problem"]


async def test_spending_is_asked_explicitly_and_logged(
    client, db_session, cast, act_as, outway, received
):
    outway.handler = contractor(received)
    act_as(cast.requester)
    response = await client.post(
        f"/api/client/assignments/{received.assignment.id}/budget-usage",
        json={"year": 2026},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True and body["not_in_contract"] is False
    assert body["budgeted_cents"] == 125000000 and body["used_cents"] == 110000000
    assert body["available_cents"] == 15000000 and body["year"] == 2026
    (line,) = body["lines"]
    assert line["description"] == "Productmanager"
    assert line["available_cents"] == -720000
    assert body["fetched_at"]
    assert outway.requests[-1].url.params[terms.contract_parameter("year")] == "2026"

    logged = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.entity == "budget_usage_requested")
            )
        )
        .scalars()
        .all()
    )
    assert len(logged) == 1 and logged[0].actor_id == cast.requester.id
    assert logged[0].new_value["answered"] is True


async def test_spending_refused_by_the_contract_is_said_as_such(
    client, cast, act_as, outway, received
):
    outway.handler = contractor(
        received,
        usage=httpx.Response(
            403,
            json={"title": "Geen toegang", "status": 403},
            headers={"content-type": "application/problem+json"},
        ),
    )
    act_as(cast.requester)
    body = (
        await client.post(
            f"/api/client/assignments/{received.assignment.id}/budget-usage", json={}
        )
    ).json()
    assert body["available"] is False and body["not_in_contract"] is True
    assert "financiële inzage" in body["problem"]
    assert "budgeted_cents" not in body or body["budgeted_cents"] is None


async def test_who_may_ask_for_the_spending(client, cast, act_as, outway, received):
    outway.handler = contractor(received)
    url = f"/api/client/assignments/{received.assignment.id}/budget-usage"
    # Financial data: not for a planner or a tekenbevoegde, who read the basics
    # or the quote only.
    for person in (cast.planner, cast.signer):
        act_as(person)
        response = await client.post(url, json={})
        assert response.status_code in (403, 404), person.email
    act_as(cast.outsider)
    assert (await client.post(url, json={})).status_code == 404
    assert outway.requests == [], "nothing was asked from the contractor"

    for person in (cast.lezer, cast.beheerder):
        act_as(person)
        assert (await client.post(url, json={})).status_code == 200


async def test_final_report_when_it_came_in(client, db_session, cast, act_as, received):
    act_as(cast.requester)
    url = f"/api/client/assignments/{received.assignment.id}/final-report"
    empty = (await client.get(url)).json()
    assert empty["received"] is False and not empty.get("summary")

    report = terms.from_contract(example("eindrapport"))
    record_audit(
        db_session,
        actor=None,
        action=CREATE,
        entity="final_report_received",
        entity_id=received.assignment.id,
        new_value={"report_id": report["id"], "from_peer": "x", "report": report},
    )
    await db_session.flush()
    body = (await client.get(url)).json()
    assert body["received"] is True and body["summary"] == "Fictief eindrapport."
    assert body["delivered"] == ["Bouwsteen Alfa in productie"]
    assert body["not_delivered"] == [
        {
            "description": "Koppeling met register Beta",
            "reason": "Register was niet op tijd beschikbaar.",
        }
    ]
    assert body["total_cost_cents"] == 110000000
    assert body["period_start"] == "2026-07-01"

    # The cost is financial; a planner gets the report without it.
    act_as(cast.planner)
    body = (await client.get(url)).json()
    assert body["received"] is True and "total_cost_cents" not in body


async def test_inspection_is_only_for_assignments_this_instance_is_client_of(
    client, db_session, cast, act_as, outway
):
    from grip.services import assignments

    own_work = await assignments.create_assignment(
        db_session, name="Eigen werk", actor=cast.beheerder
    )
    act_as(cast.beheerder)
    for method, path in (
        ("get", "progress"),
        ("post", "budget-usage"),
        ("get", "final-report"),
    ):
        kwargs = {"json": {}} if method == "post" else {}
        response = await getattr(client, method)(
            f"/api/client/assignments/{own_work.id}/{path}", **kwargs
        )
        assert response.status_code == 404, path
    assert outway.requests == []
