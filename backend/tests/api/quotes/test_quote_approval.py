"""Internal approval of a quote before it may be offered (optional per instance)."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from grip.federation import registry
from grip.federation.events import EVENT_HANDLERS, register_event_handlers
from grip.federation.models import FederationOutbox
from grip.models.assignment import Assignment
from grip.models.audit_log import AuditLog
from grip.models.quote import Quote, QuoteApproval, QuoteOffer
from grip.services import events as domain_events
from grip.services import instance_settings, quote_approval, terms
from grip.services.quote_content import check_content

TOTAL_CENTS = 17_280_000  # 0.8 FTE, category D, twelve months of 2026


@pytest.fixture(autouse=True)
def _clean():
    registry.clear_registries()
    domain_events.clear_handlers()
    yield
    registry.clear_registries()
    domain_events.clear_handlers()


@pytest.fixture
async def approver(create_person):
    return await create_person(
        "goedkeurder@example.org",
        name="Goedkeurder Voorbeeld",
        functions=[quote_approval.APPROVER_FUNCTION],
    )


@pytest.fixture
def configure(db_session, world):
    async def _set(**values):
        await instance_settings.set_values(
            db_session,
            {f"quote_approval.{key}": value for key, value in values.items()},
            actor=world.beheerder,
        )

    return _set


async def _make(act_as, world) -> dict:
    response = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _state(client, quote_id) -> dict:
    response = await client.get(f"/api/quotes/{quote_id}/approval")
    assert response.status_code == 200, response.text
    return response.json()


async def _offer(client, quote_id, **body):
    return await client.post(
        f"/api/quotes/{quote_id}/offers", json={"channel": "document", **body}
    )


# --- required or not ---------------------------------------------------------


async def test_by_default_nothing_changes(act_as, world, db_session):
    quote = await _make(act_as, world)
    manager = act_as(world.manager)
    state = await _state(manager, quote["id"])
    assert state["approval_required"] is False and state["approval_reason"] is None
    assert state["status"] == "none" and state["may_offer"] is True
    assert state["blocked_message"] is None
    assert (await _offer(manager, quote["id"])).status_code == 201
    assert (await db_session.execute(select(QuoteApproval))).scalars().all() == []


async def test_required_blocks_every_channel_until_approved(
    act_as, world, db_session, configure, approver
):
    await configure(mode="always")
    quote = await _make(act_as, world)
    manager = act_as(world.manager)
    state = await _state(manager, quote["id"])
    assert state["approval_required"] is True and state["may_offer"] is False
    assert state["may_request_approval"] is True and state["approver_available"] is True

    for body in (
        {"channel": "document"},
        {"channel": "signing_link", "email": world.signer.email},
        {"channel": "client_instance"},
    ):
        refused = await manager.post(f"/api/quotes/{quote['id']}/offers", json=body)
        assert refused.status_code in (400, 409, 422), body
        assert "intern worden goedgekeurd" in refused.json()["detail"], body
    # The older way to invite a signer is an offer too.
    invited = await manager.post(
        f"/api/quotes/{quote['id']}/invitations", json={"email": world.signer.email}
    )
    assert invited.status_code in (400, 409, 422)
    assert (await db_session.execute(select(QuoteOffer))).scalars().all() == []

    asked = await manager.post(
        f"/api/quotes/{quote['id']}/approval/request",
        json={"note": "Graag voor vrijdag."},
    )
    assert asked.status_code == 201, asked.text
    assert asked.json()["status"] == "requested"
    assert asked.json()["current"]["request_note"] == "Graag voor vrijdag."
    waiting = await _offer(manager, quote["id"])
    assert "wacht op interne goedkeuring" in waiting.json()["detail"]

    decided = await act_as(approver).post(
        f"/api/quotes/{quote['id']}/approval/decision",
        json={"decision": "approve", "quote_hash": quote["snapshot_hash"]},
    )
    assert decided.status_code == 201, decided.text
    assert decided.json()["status"] == "approved"
    assert decided.json()["current"]["decided_by_name"] == "Goedkeurder Voorbeeld"

    manager = act_as(world.manager)
    state = await _state(manager, quote["id"])
    assert state["may_offer"] is True and state["blocked_message"] is None
    assert (await _offer(manager, quote["id"])).status_code == 201
    # The quote and the assignment read to others as before.
    detail = (await manager.get(f"/api/quotes/{quote['id']}")).json()
    assert detail["status"] == "issued"


@pytest.mark.parametrize(
    "threshold,required", [(TOTAL_CENTS + 1, False), (TOTAL_CENTS, True), (100, True)]
)
async def test_from_an_amount_upward(act_as, world, configure, threshold, required):
    await configure(mode="from_amount", threshold_cents=threshold)
    quote = await _make(act_as, world)
    manager = act_as(world.manager)
    state = await _state(manager, quote["id"])
    assert state["approval_required"] is required
    offered = await _offer(manager, quote["id"])
    if required:
        assert offered.status_code in (400, 409, 422)
    else:
        assert offered.status_code == 201, offered.text
    if required:
        assert state["approval_reason"].startswith("vanaf € ")
    else:
        assert state["approval_reason"] is None


async def test_reason_reads_as_an_amount(db_session, world, configure):
    await configure(mode="from_amount", threshold_cents=10_000_000)
    quote = Quote(total_cents=10_000_000)
    assert (await quote_approval.requirement_for(db_session, quote)).reason == (
        "vanaf € 100.000"
    )


# --- who approves -------------------------------------------------------------


async def test_four_eyes_unless_the_instance_allows_one_person(
    act_as, world, db_session, configure, create_person
):
    await configure(mode="always")
    # The manager of the assignment also holds the right to approve.
    from grip.models.role import PersonRole

    db_session.add(
        PersonRole(person_id=world.manager.id, role_id=quote_approval.APPROVER_FUNCTION)
    )
    await db_session.flush()
    quote = await _make(act_as, world)
    manager = act_as(world.manager)
    await manager.post(f"/api/quotes/{quote['id']}/approval/request", json={})
    state = await _state(manager, quote["id"])
    assert state["may_decide_approval"] is False, "not the own request"
    body = {"decision": "approve", "quote_hash": quote["snapshot_hash"]}
    refused = await manager.post(
        f"/api/quotes/{quote['id']}/approval/decision", json=body
    )
    assert refused.status_code in (400, 409, 422)
    assert "niet zelf" in refused.json()["detail"]
    # Sending the own request back is not approving and stays possible.

    await configure(allow_self_approval=True)
    state = await _state(manager, quote["id"])
    assert state["may_decide_approval"] is True
    allowed = await manager.post(
        f"/api/quotes/{quote['id']}/approval/decision", json=body
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["current"]["self_approved"] is True
    audit = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.entity == "quote_approval")
            )
        )
        .scalars()
        .all()
    )
    assert any((row.new_value or {}).get("self_approved") is True for row in audit)


async def test_nobody_holds_the_right(act_as, world, configure):
    await configure(mode="always")
    quote = await _make(act_as, world)
    manager = act_as(world.manager)
    state = await _state(manager, quote["id"])
    assert state["approver_available"] is False
    assert "Interne goedkeurder van offertes" in state["blocked_message"]
    assert "beheerder" in state["blocked_message"]
    refused = await _offer(manager, quote["id"])
    assert refused.status_code in (400, 409, 422)
    assert "Niemand heeft het recht" in refused.json()["detail"]


async def test_only_the_holder_of_the_right_decides_and_only_a_manager_asks(
    act_as, world, configure, approver
):
    await configure(mode="always")
    quote = await _make(act_as, world)
    # The approver has no relation with the assignment and cannot ask.
    asked = await act_as(approver).post(
        f"/api/quotes/{quote['id']}/approval/request", json={}
    )
    assert asked.status_code in (403, 404)
    await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/approval/request", json={}
    )
    body = {"decision": "approve", "quote_hash": quote["snapshot_hash"]}
    for person in (world.manager, world.planner, world.lezer, world.outsider):
        response = await act_as(person).post(
            f"/api/quotes/{quote['id']}/approval/decision", json=body
        )
        assert response.status_code in (403, 404), person.email


# --- send back, other bytes, withdraw ------------------------------------------


async def test_send_back_then_a_new_quote(
    act_as, world, db_session, configure, approver
):
    await configure(mode="always")
    first = await _make(act_as, world)
    await act_as(world.manager).post(
        f"/api/quotes/{first['id']}/approval/request", json={}
    )
    without_note = await act_as(approver).post(
        f"/api/quotes/{first['id']}/approval/decision",
        json={"decision": "send_back", "quote_hash": first["snapshot_hash"]},
    )
    assert without_note.status_code in (400, 422), "the maker must know what to change"
    sent_back = await act_as(approver).post(
        f"/api/quotes/{first['id']}/approval/decision",
        json={
            "decision": "send_back",
            "quote_hash": first["snapshot_hash"],
            "note": "De looptijd klopt niet met de afspraak.",
        },
    )
    assert sent_back.status_code == 201, sent_back.text
    assert sent_back.json()["status"] == "sent_back"

    manager = act_as(world.manager)
    blocked = await _offer(manager, first["id"])
    assert "teruggestuurd" in blocked.json()["detail"]
    # Sending back changed nothing about the quote itself.
    stored = await db_session.get(Quote, uuid.UUID(first["id"]))
    assert stored.snapshot_hash == first["snapshot_hash"] and stored.status == "issued"

    second = await _make(act_as, world)
    manager = act_as(world.manager)
    await db_session.refresh(stored)
    assert stored.status == "superseded"
    old = await _state(manager, first["id"])
    assert (
        old["history"][0]["decision_note"] == "De looptijd klopt niet met de afspraak."
    )
    assert old["may_request_approval"] is False, "a superseded quote is closed"
    new = await _state(manager, second["id"])
    assert new["status"] == "none" and new["may_offer"] is False
    assert new["may_request_approval"] is True


async def test_an_approval_is_about_exactly_those_bytes(
    act_as, world, db_session, configure, approver
):
    await configure(mode="always")
    quote = await _make(act_as, world)
    await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/approval/request", json={}
    )
    other_version = await act_as(approver).post(
        f"/api/quotes/{quote['id']}/approval/decision",
        json={"decision": "approve", "quote_hash": "0" * 64},
    )
    assert other_version.status_code in (400, 409, 422)
    assert "andere versie" in other_version.json()["detail"]

    # An approval on record that cites another hash approves nothing.
    approval = await db_session.scalar(select(QuoteApproval))
    approval.status = "approved"
    approval.decided_by_id = approver.id
    approval.quote_hash = "1" * 64
    await db_session.flush()
    manager = act_as(world.manager)
    state = await _state(manager, quote["id"])
    assert state["status"] != "approved" and state["may_offer"] is False
    assert state["history"][0]["for_this_version"] is False
    assert (await _offer(manager, quote["id"])).status_code in (400, 409, 422)


async def test_withdraw_a_request_and_an_approval_until_offered(
    act_as, world, configure, approver
):
    await configure(mode="always")
    quote = await _make(act_as, world)
    path = f"/api/quotes/{quote['id']}/approval"
    manager = act_as(world.manager)
    nothing = await manager.post(f"{path}/withdrawal")
    assert nothing.status_code in (400, 403, 409, 422)

    await manager.post(f"{path}/request", json={})
    # The approver cannot take back the maker's request; the maker can.
    assert (await act_as(approver).post(f"{path}/withdrawal")).status_code in (403, 404)
    taken_back = await act_as(world.manager).post(f"{path}/withdrawal")
    assert taken_back.status_code == 200, taken_back.text
    assert taken_back.json()["status"] == "withdrawn"
    assert taken_back.json()["may_request_approval"] is True

    await act_as(world.manager).post(f"{path}/request", json={})
    body = {"decision": "approve", "quote_hash": quote["snapshot_hash"]}
    await act_as(approver).post(f"{path}/decision", json=body)
    # The maker cannot take back someone's approval; the approver can.
    assert (await act_as(world.manager).post(f"{path}/withdrawal")).status_code in (
        403,
        404,
    )
    undone = await act_as(approver).post(f"{path}/withdrawal")
    assert undone.status_code == 200 and undone.json()["status"] == "withdrawn"
    assert (await _offer(act_as(world.manager), quote["id"])).status_code != 201

    await act_as(world.manager).post(f"{path}/request", json={})
    await act_as(approver).post(f"{path}/decision", json=body)
    assert (await _offer(act_as(world.manager), quote["id"])).status_code == 201
    too_late = await act_as(approver).post(f"{path}/withdrawal")
    assert too_late.status_code in (400, 409, 422)
    assert "al aangeboden" in too_late.json()["detail"]


# --- what the approver sees ---------------------------------------------------


async def test_approver_reads_the_quote_in_full_and_nothing_else(
    act_as, world, configure, approver
):
    await configure(mode="always")
    quote = await _make(act_as, world)
    stranger = act_as(approver)
    # Nobody asked yet: the quote is not there for the approver.
    assert (
        await stranger.get(f"/api/quote-approvals/quotes/{quote['id']}")
    ).status_code == 404
    assert (await stranger.get("/api/quote-approvals/waiting")).json()["items"] == []

    await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/approval/request", json={"note": "Spoed."}
    )
    stranger = act_as(approver)
    (row,) = (await stranger.get("/api/quote-approvals/waiting")).json()["items"]
    assert row["quote_id"] == quote["id"] and row["assignment_name"] == "Opdracht Alfa"
    assert row["total_cents"] == TOTAL_CENTS and row["request_note"] == "Spoed."
    assert row["requested_by_name"] == world.manager.name and row["may_decide"] is True

    full = await stranger.get(f"/api/quote-approvals/quotes/{quote['id']}")
    assert full.status_code == 200, full.text
    body = full.json()
    assert body["snapshot_hash"] == quote["snapshot_hash"]
    assert body["content"]["lines"][0]["description"] == "Productmanager"
    assert body["approval"]["may_decide_approval"] is True
    document = await stranger.get(f"/api/quote-approvals/quotes/{quote['id']}/document")
    # The same page the client gets. What it prints of the hash is the
    # document's own concern and is tested there.
    assert document.status_code == 200 and "Productmanager" in document.text

    # Nothing else of the assignment opens up.
    for path in (
        f"/api/assignments/{world.assignment.id}",
        f"/api/assignments/{world.assignment.id}/quotes",
        f"/api/assignments/{world.assignment.id}/quote-approvals",
    ):
        assert (await stranger.get(path)).status_code in (403, 404), path

    # Someone without the right has no such list.
    assert (
        await act_as(world.manager).get("/api/quote-approvals/waiting")
    ).status_code in (403, 404)


async def test_list_of_states_for_the_quote_list(act_as, world, configure):
    await configure(mode="always")
    await _make(act_as, world)
    second = await _make(act_as, world)
    manager = act_as(world.manager)
    items = (
        await manager.get(f"/api/assignments/{world.assignment.id}/quote-approvals")
    ).json()["items"]
    assert len(items) == 2 and items[0]["quote_id"] == second["id"]
    assert all(item["approval_required"] for item in items)
    assert (
        await act_as(world.outsider).get(
            f"/api/assignments/{world.assignment.id}/quote-approvals"
        )
    ).status_code in (403, 404)


# --- nothing leaves the organisation -------------------------------------------


async def test_events_carry_ids_and_the_reference_and_no_amounts(
    act_as, world, db_session, configure, approver
):
    await configure(mode="always")
    seen: list[tuple[str, dict]] = []

    async def record(_db, event_type, payload):
        seen.append((event_type, payload))

    for event_type in (
        quote_approval.EVENT_REQUESTED,
        quote_approval.EVENT_APPROVED,
        quote_approval.EVENT_SENT_BACK,
        quote_approval.EVENT_WITHDRAWN,
    ):
        domain_events.register_handler(event_type, record)

    quote = await _make(act_as, world)
    path = f"/api/quotes/{quote['id']}/approval"
    await act_as(world.manager).post(f"{path}/request", json={"note": "Zie bijlage."})
    await act_as(approver).post(
        f"{path}/decision",
        json={"decision": "approve", "quote_hash": quote["snapshot_hash"]},
    )
    assert [name for name, _ in seen] == [
        "quote_approval.requested",
        "quote_approval.approved",
    ]
    stored = await db_session.get(Quote, uuid.UUID(quote["id"]))
    for _, payload in seen:
        assert set(payload) == {
            "approval_id",
            "quote_id",
            "quote_reference",
            "assignment_id",
            "requested_by_id",
            "decided_by_id",
            "origin",
        }
        assert payload["quote_reference"] == stored.reference
        assert payload["requested_by_id"] == str(world.manager.id)
        text = json.dumps(payload)
        assert str(TOTAL_CENTS) not in text and "Zie bijlage" not in text
    assert seen[1][1]["decided_by_id"] == str(approver.id)


async def test_nothing_about_approval_reaches_another_instance(
    act_as, world, db_session, configure, approver
):
    await configure(mode="always")
    # No approval event has a route to another instance.
    assert not any(name.startswith("quote_approval") for name in EVENT_HANDLERS)
    register_event_handlers()
    quote = await _make(act_as, world)
    path = f"/api/quotes/{quote['id']}/approval"
    await act_as(world.manager).post(f"{path}/request", json={"note": "Intern."})
    await act_as(approver).post(
        f"{path}/decision",
        json={"decision": "approve", "quote_hash": quote["snapshot_hash"]},
    )
    assert (await db_session.execute(select(FederationOutbox))).scalars().all() == []

    # Approval is not content of the quote: the bytes are as they were made,
    # and the content check has no place for it.
    stored = await db_session.get(Quote, uuid.UUID(quote["id"]))
    assert stored.snapshot_hash == quote["snapshot_hash"]
    canonical = bytes(stored.canonical).decode()
    for word in ("approval", "goedkeur", "Intern.", "akkoord_intern"):
        assert word not in canonical, word
    with pytest.raises(Exception, match="approval"):
        check_content({**stored.snapshot, "approval": {"status": "approved"}})
    assert (
        "approval" not in terms.PROPERTIES and "approved" not in terms.VALUES["status"]
    )

    # The status others see did not move.
    assignment = await db_session.get(Assignment, world.assignment.id)
    assert assignment.status == "quoted" and stored.status == "issued"
    # What goes out when the quote is offered and decided cites the quote
    # only; the document the client gets does not mention the approval.
    document = await act_as(world.manager).get(f"/api/quotes/{quote['id']}/document")
    assert "goedkeur" not in document.text.lower()


# --- settings -------------------------------------------------------------------


async def test_instance_settings_are_for_the_beheerder(act_as, world, db_session):
    assert (
        await act_as(world.manager).get("/api/instance-settings")
    ).status_code == 403
    beheerder = act_as(world.beheerder)
    items = (await beheerder.get("/api/instance-settings")).json()["items"]
    by_key = {item["key"]: item for item in items}
    assert by_key["quote_approval.mode"]["value"] == "never"
    assert by_key["quote_approval.allow_self_approval"]["default"] is False

    changed = await beheerder.patch(
        "/api/instance-settings",
        json={
            "values": {
                "quote_approval.mode": "from_amount",
                "quote_approval.threshold_cents": 10_000_000,
            }
        },
    )
    assert changed.status_code == 200, changed.text
    assert (
        await instance_settings.get(db_session, "quote_approval.mode") == "from_amount"
    )
    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.entity == "instance_setting")
    )
    assert audit.old_value["quote_approval.mode"] == "never"
    assert audit.actor_id == world.beheerder.id

    for values in (
        {"quote_approval.mode": "soms"},
        {"quote_approval.threshold_cents": -1},
        {"quote_approval.allow_self_approval": "ja"},
        {"bestaat.niet": 1},
    ):
        refused = await beheerder.patch(
            "/api/instance-settings", json={"values": values}
        )
        assert refused.status_code in (400, 422), values
    assert (
        await instance_settings.get(db_session, "quote_approval.mode") == "from_amount"
    )
    assert (
        await act_as(world.manager).patch("/api/instance-settings", json={"values": {}})
    ).status_code == 403
