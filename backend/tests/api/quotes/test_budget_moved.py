"""Whether the budget moved since the quote in force, by content."""

from __future__ import annotations

from decimal import Decimal

from grip.services import assignments
from grip.services.quote_budget import budget_fingerprint


async def _issue(client, world) -> dict:
    response = await client.post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _list(client, world) -> dict:
    response = await client.get(f"/api/assignments/{world.assignment.id}/quotes")
    assert response.status_code == 200, response.text
    return response.json()


async def test_nothing_to_compare_without_a_quote(act_as, world):
    listed = await _list(act_as(world.manager), world)
    assert listed.get("budget_moved") is None
    assert listed.get("budget_compared_quote_id") is None


async def test_a_fresh_quote_matches_the_budget(act_as, world):
    client = act_as(world.manager)
    quote = await _issue(client, world)
    listed = await _list(client, world)
    assert listed["budget_moved"] is False
    assert listed["budget_compared_quote_id"] == quote["id"]


async def test_a_change_that_keeps_the_total_still_counts(act_as, world, db_session):
    client = act_as(world.manager)
    quote = await _issue(client, world)
    before = (await _list(client, world))["quotes"][0]["total_cents"]

    # Another role for the same money: the total stays, the content does not.
    await assignments.update_budget_line(
        db_session,
        world.line.id,
        actor=world.manager,
        description="Productowner",
        role="Productowner",
    )
    await db_session.flush()

    preview = await client.get(f"/api/assignments/{world.assignment.id}/quote-preview")
    assert preview.json()["content"]["total_cents"] == before
    listed = await _list(client, world)
    assert listed["budget_moved"] is True
    assert listed["budget_compared_quote_id"] == quote["id"]


async def test_a_change_of_the_total_counts(act_as, world, db_session):
    client = act_as(world.manager)
    await _issue(client, world)
    await assignments.update_budget_line(
        db_session, world.line.id, actor=world.manager, fte=Decimal("0.6")
    )
    await db_session.flush()
    assert (await _list(client, world))["budget_moved"] is True


async def test_the_fact_is_financial(act_as, world):
    await _issue(act_as(world.manager), world)
    # A team member reads the assignment but not its money.
    listed = await act_as(world.member).get(
        f"/api/assignments/{world.assignment.id}/quotes"
    )
    if listed.status_code == 200:
        assert "budget_moved" not in listed.json()
        assert "budget_compared_quote_id" not in listed.json()


def test_what_belongs_to_the_quote_is_no_part_of_the_budget():
    line = {"position": 1, "description": "Rol", "amount": {"amount_cents": 100}}
    budget = {"lines": [line], "subtotals_per_year": [], "total": {"amount_cents": 100}}
    quote = {
        **budget,
        "lines": [{**line, "scales": [14, 15]}],
        "reference": "VG-2026-0007",
        "valid_until": "2026-12-31",
        "conditions": "Betaling per maand.",
        "sender": "Voorbeeldgilde",
    }
    assert budget_fingerprint(budget) == budget_fingerprint(quote)
    moved = {**budget, "lines": [{**line, "description": "Andere rol"}]}
    assert budget_fingerprint(budget) != budget_fingerprint(moved)
