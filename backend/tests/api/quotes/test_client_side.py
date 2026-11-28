"""On the client side of an assignment nobody makes a quote."""

from __future__ import annotations

import pytest

from grip.federation.bridge.organisations import own_organisation
from grip.services import assignments, quotes


@pytest.fixture
async def asked(world, db_session):
    """An assignment this instance asked another one for, with a quote in."""
    own = await own_organisation(db_session)
    contractor = await assignments.upsert_organisation(
        db_session, name="Voorbeeldleverancier"
    )
    assignment, _ = await assignments.create_assignment_request(
        db_session,
        name="Aanvraag Zeta 2026",
        contractor_organisation_id=contractor.id,
        client_organisation_id=own.id,
        actor=world.manager,
    )
    await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Regel",
        kind="fixed",
        amount_cents=100000,
        year=2026,
        actor=world.manager,
    )
    quote = await quotes.issue_quote(db_session, assignment.id, actor=world.manager)
    return assignment, quote


async def test_the_client_side_may_not_make_a_quote(world, asked, act_as):
    assignment, quote = asked
    owner = act_as(world.manager)
    base = f"/api/assignments/{assignment.id}"

    preview = (await owner.get(f"{base}/quote-preview")).json()
    assert preview["may_issue"] is False
    listed = (await owner.get(f"{base}/quotes")).json()
    assert listed["may_manage"] is False
    assert (await owner.get(f"{base}/quote-draft")).json()["may_edit"] is False
    assert (await owner.get(f"/api/quotes/{quote.id}")).status_code == 200

    writes = [
        ("post", f"{base}/quotes", {"json": {}}),
        ("patch", f"{base}/quote-draft", {"json": {"subject": "Onderwerp"}}),
        ("post", f"/api/quotes/{quote.id}/offers", {"json": {"channel": "document"}}),
        ("post", f"/api/quotes/{quote.id}/invitations", {"json": {"email": "a@b.nl"}}),
    ]
    for method, url, kwargs in writes:
        response = await getattr(owner, method)(url, **kwargs)
        assert response.status_code == 403, (method, url, response.text)


async def test_the_contractor_side_still_may(world, act_as):
    owner = act_as(world.manager)
    base = f"/api/assignments/{world.assignment.id}"
    assert (await owner.get(f"{base}/quote-preview")).json()["may_issue"] is True
    assert (await owner.get(f"{base}/quotes")).json()["may_manage"] is True
    assert (await owner.get(f"{base}/quote-draft")).json()["may_edit"] is True
    assert (await owner.post(f"{base}/quotes", json={})).status_code == 201
