"""A closed dossier offers no change on any tab: every write flag is off (ADR 0057).

The server refuses such a change anyway; these flags keep a screen from
offering it.
"""

from decimal import Decimal

import pytest

from grip.core import clock
from grip.services import assignments, costs, dossiers, quote_approval, quotes

from .conftest import by_id


@pytest.fixture
async def ended(db_session, world):
    """The world's assignment with an issued quote, completed, dossier open."""
    quote = await quotes.issue_quote(db_session, world.assignment.id, actor=world.owner)
    for step in ("accepted", "in_progress", "completed"):
        await assignments.transition(
            db_session, world.assignment.id, step, actor=world.owner
        )
    world.quote = quote
    return world


async def _close(db_session, world) -> None:
    await dossiers.close_dossier(
        db_session, world.assignment.id, actor=world.owner, closed_on=clock.today()
    )
    await db_session.flush()


def _url(world, path: str) -> str:
    return f"/api/assignments/{world.assignment.id}/{path}"


async def test_the_budget_offers_no_change(db_session, ended, as_person):
    client = as_person(ended.owner)
    assert (await client.get(_url(ended, "budget"))).json()["can_edit"] is True
    await _close(db_session, ended)
    assert (await client.get(_url(ended, "budget"))).json()["can_edit"] is False


async def test_the_staffing_offers_no_change(db_session, ended, as_person):
    owner = as_person(ended.owner)

    async def seen() -> tuple[list[bool], list[bool], list[bool], list[bool]]:
        listed = (
            await owner.get(
                "/api/allocations", params={"assignment_id": str(ended.assignment.id)}
            )
        ).json()["items"]
        staffing = (await owner.get(_url(ended, "staffing"))).json()
        board = (
            await owner.get("/api/allocations/board", params={"start": "2026-01"})
        ).json()
        bars = [
            bar["can_edit"]
            for person in board["persons"]
            for bar in person["bars"]
            if bar["assignment_id"] == str(ended.assignment.id)
        ]
        return (
            [item["can_edit"] for item in listed],
            [role["can_fill"] for role in staffing["roles"]],
            [bar["can_edit"] for role in staffing["roles"] for bar in role["bars"]],
            bars,
        )

    before = await seen()
    assert all(flags and all(flags) for flags in before), before
    await _close(db_session, ended)
    after = await seen()
    assert all(flags and not any(flags) for flags in after), after


async def test_no_new_quote_and_no_draft_text(db_session, ended, as_person):
    client = as_person(ended.owner)
    assert (await client.get(_url(ended, "quote-preview"))).json()["may_issue"] is True
    assert (await client.get(_url(ended, "quote-draft"))).json()["may_edit"] is True
    await _close(db_session, ended)
    assert (await client.get(_url(ended, "quote-preview"))).json()["may_issue"] is False
    assert (await client.get(_url(ended, "quote-draft"))).json()["may_edit"] is False


async def test_no_approval_is_asked_decided_or_withdrawn(
    db_session, ended, as_person, create_person
):
    approver = await create_person(
        "akkoord@example.org",
        name="Sam Akkoord",
        functions=[quote_approval.APPROVER_FUNCTION],
    )
    quote_id = ended.quote.id
    owner = as_person(ended.owner)
    state = (await owner.get(f"/api/quotes/{quote_id}/approval")).json()
    assert state["may_request_approval"] is True
    await quote_approval.request_approval(db_session, quote_id, actor=ended.owner)
    await db_session.flush()

    waiting = (await as_person(approver).get("/api/quote-approvals/waiting")).json()
    assert by_id(waiting["items"], "quote_id", quote_id)["may_decide"] is True
    owner = as_person(ended.owner)
    assert (await owner.get(f"/api/quotes/{quote_id}/approval")).json()[
        "may_withdraw"
    ] is True

    await _close(db_session, ended)
    state = (await owner.get(f"/api/quotes/{quote_id}/approval")).json()
    for name in ("may_request_approval", "may_decide_approval", "may_withdraw"):
        assert state[name] is False, name
    listed = (await owner.get(_url(ended, "quote-approvals"))).json()["items"]
    assert by_id(listed, "quote_id", quote_id)["may_withdraw"] is False
    for_approver = as_person(approver)
    waiting = (await for_approver.get("/api/quote-approvals/waiting")).json()
    assert by_id(waiting["items"], "quote_id", quote_id)["may_decide"] is False
    seen = (await for_approver.get(f"/api/quote-approvals/quotes/{quote_id}")).json()
    assert seen["approval"]["may_decide_approval"] is False


async def test_no_month_delivery_invoice_or_terms(db_session, ended, as_person):
    # Only the beheerder reopens a month.
    reopens = (await as_person(ended.beheerder).get(_url(ended, "billing"))).json()
    assert reopens["may_reopen"] is True
    client = as_person(ended.owner)
    assert (await client.get(_url(ended, "months"))).json()["may_close"] is True
    billing = (await client.get(_url(ended, "billing"))).json()
    for name in ("may_close", "may_deliver", "may_record_invoice", "may_edit_terms"):
        assert billing[name] is True, name
    status = (await client.get(_url(ended, "billing-status"))).json()
    assert status["may_record_invoice"] is True

    await _close(db_session, ended)
    reopens = (await as_person(ended.beheerder).get(_url(ended, "billing"))).json()
    assert reopens["may_reopen"] is False
    client = as_person(ended.owner)
    assert (await client.get(_url(ended, "months"))).json()["may_close"] is False
    month = (await client.get(_url(ended, "months/2026-01"))).json()
    assert month["may_close"] is False and month["may_reopen"] is False
    billing = (await client.get(_url(ended, "billing"))).json()
    for name in (
        "may_close",
        "may_reopen",
        "may_deliver",
        "may_record_invoice",
        "may_edit_terms",
    ):
        assert billing[name] is False, name
    status = (await client.get(_url(ended, "billing-status"))).json()
    assert status["may_record_invoice"] is False


async def test_no_cost_coverage_changes(db_session, ended, as_person):
    item = await costs.create_cost_item(
        db_session,
        description="Hostingcontract",
        budgeted_cents=1600000,
        actor=ended.beheerder,
    )
    await costs.set_coverage(
        db_session, item.id, ended.fixed_line.id, Decimal(30), actor=ended.beheerder
    )
    await db_session.flush()
    client = as_person(ended.owner)
    body = (await client.get(f"/api/costs/{item.id}")).json()
    assert [c["may_edit"] for c in body["coverages"]] == [True]
    options = (await client.get("/api/costs/coverage-options")).json()["items"]
    assert str(ended.assignment.id) in {o["assignment_id"] for o in options}

    await _close(db_session, ended)
    body = (await client.get(f"/api/costs/{item.id}")).json()
    assert [c["may_edit"] for c in body["coverages"]] == [False]
    listed = (await client.get("/api/costs")).json()["items"]
    assert [c["may_edit"] for c in by_id(listed, "id", item.id)["coverages"]] == [False]
    options = (await client.get("/api/costs/coverage-options")).json()["items"]
    assert str(ended.assignment.id) not in {o["assignment_id"] for o in options}
