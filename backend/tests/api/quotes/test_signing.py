"""The signing link: one invited person, one quote."""

from datetime import UTC, datetime, timedelta

from grip.access.guest_deps import signer_from_guest_session
from grip.access.types import SubjectKind


async def _issued_and_invited(act_as, world, **invite) -> dict:
    client = act_as(world.manager)
    quote = (
        await client.post(f"/api/assignments/{world.assignment.id}/quotes", json={})
    ).json()
    response = await client.post(
        f"/api/quotes/{quote['id']}/invitations",
        json={"email": world.signer.email, **invite},
    )
    assert response.status_code == 201, response.text
    return quote


async def test_signer_sees_the_invited_quote(act_as, world):
    quote = await _issued_and_invited(act_as, world)
    client = act_as(world.signer)

    listed = (await client.get("/api/signing/invitations")).json()
    assert [i["quote_id"] for i in listed["invitations"]] == [quote["id"]]
    assert listed["invitations"][0]["assignment_name"] == "Opdracht Alfa"

    body = (await client.get(f"/api/signing/quotes/{quote['id']}")).json()
    assert body["status"] == "issued"
    assert body["snapshot_hash"] == quote["snapshot_hash"]
    assert body["client_name"] == "Voorbeeldministerie"
    assert body["content"]["total_cents"] == quote["total_cents"]

    document = await client.get(f"/api/signing/quotes/{quote['id']}/document")
    assert document.status_code == 200
    assert quote["snapshot_hash"] in document.text


async def test_signer_reaches_nothing_else(act_as, world):
    quote = await _issued_and_invited(act_as, world)
    client = act_as(world.signer)
    aid = world.assignment.id
    for path in (
        f"/api/quotes/{quote['id']}/invitations",
        f"/api/assignments/{aid}/quote-preview",
        f"/api/assignments/{aid}/quotes",
        f"/api/assignments/{aid}/months",
        f"/api/assignments/{aid}/months/2026-01",
        f"/api/assignments/{aid}/months/2026-01/billing-data",
        f"/api/assignments/{aid}/billing-exports",
    ):
        response = await client.get(path)
        assert response.status_code in (403, 404), path


async def test_uninvited_person_gets_404(act_as, world):
    quote = await _issued_and_invited(act_as, world)
    client = act_as(world.outsider)
    assert (await client.get("/api/signing/invitations")).json() == {"invitations": []}
    for method, path, payload in (
        ("get", f"/api/signing/quotes/{quote['id']}", None),
        ("get", f"/api/signing/quotes/{quote['id']}/document", None),
        (
            "post",
            f"/api/signing/quotes/{quote['id']}/accept",
            {"quote_hash": quote["snapshot_hash"], "confirm_mandate": True},
        ),
        (
            "post",
            f"/api/signing/quotes/{quote['id']}/reject",
            {"quote_hash": quote["snapshot_hash"]},
        ),
    ):
        response = (
            await client.get(path)
            if method == "get"
            else await client.post(path, json=payload)
        )
        assert response.status_code == 404, path


async def test_accept_records_who_signed(act_as, world):
    quote = await _issued_and_invited(act_as, world)
    client = act_as(world.signer)
    response = await client.post(
        f"/api/signing/quotes/{quote['id']}/accept",
        json={
            "quote_hash": quote["snapshot_hash"],
            "signer_function": "Directeur",
            "confirm_mandate": True,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "accepted"
    assert response.json()["decided_at"] is not None

    client = act_as(world.manager)
    seen = (await client.get(f"/api/quotes/{quote['id']}")).json()
    assert seen["status"] == "accepted"
    assert seen["acceptance"]["form"] == "signing_link"
    assert seen["acceptance"]["signer_name"] == "Tekenaar Voorbeeld"
    assert seen["acceptance"]["signer_function"] == "Directeur"
    assert seen["acceptance"]["organisation_name"] == "Voorbeeldministerie"
    invitations = (await client.get(f"/api/quotes/{quote['id']}/invitations")).json()[
        "invitations"
    ]
    assert invitations[0]["used_at"] is not None


async def test_accept_needs_the_mandate_confirmation(act_as, world):
    quote = await _issued_and_invited(act_as, world)
    client = act_as(world.signer)
    response = await client.post(
        f"/api/signing/quotes/{quote['id']}/accept",
        json={"quote_hash": quote["snapshot_hash"], "confirm_mandate": False},
    )
    assert response.status_code == 422
    assert (await client.get(f"/api/signing/quotes/{quote['id']}")).json()[
        "status"
    ] == "issued"


async def test_accept_refuses_another_hash(act_as, world):
    quote = await _issued_and_invited(act_as, world)
    client = act_as(world.signer)
    response = await client.post(
        f"/api/signing/quotes/{quote['id']}/accept",
        json={"quote_hash": "0" * 64, "confirm_mandate": True},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "QuoteHashMismatchError"


async def test_a_decided_quote_cannot_be_signed_again(act_as, world):
    quote = await _issued_and_invited(act_as, world)
    client = act_as(world.signer)
    payload = {"quote_hash": quote["snapshot_hash"], "confirm_mandate": True}
    first = await client.post(f"/api/signing/quotes/{quote['id']}/accept", json=payload)
    assert first.status_code == 201
    again = await client.post(f"/api/signing/quotes/{quote['id']}/accept", json=payload)
    assert again.status_code == 409


async def test_reject_with_a_reason(act_as, world):
    quote = await _issued_and_invited(act_as, world)
    client = act_as(world.signer)
    response = await client.post(
        f"/api/signing/quotes/{quote['id']}/reject",
        json={
            "quote_hash": quote["snapshot_hash"],
            "reason": "Past niet in het jaarplan",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "rejected"
    client = act_as(world.manager)
    seen = (await client.get(f"/api/quotes/{quote['id']}")).json()
    assert seen["rejection"]["reason"] == "Past niet in het jaarplan"


async def test_expired_invitation_grants_nothing(act_as, world):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    quote = await _issued_and_invited(act_as, world, expires_at=past)
    client = act_as(world.signer)
    assert (await client.get("/api/signing/invitations")).json() == {"invitations": []}
    assert (await client.get(f"/api/signing/quotes/{quote['id']}")).status_code == 404


async def test_manager_cannot_sign_the_own_quote(act_as, world):
    """Issuing and accepting are different hands."""
    quote = await _issued_and_invited(act_as, world)
    client = act_as(world.manager)
    response = await client.post(
        f"/api/signing/quotes/{quote['id']}/accept",
        json={"quote_hash": quote["snapshot_hash"], "confirm_mandate": True},
    )
    assert response.status_code == 404


def test_guest_session_needs_a_verified_email():
    signer = signer_from_guest_session(
        {
            "guest": {
                "email": "Gast@Voorbeeld.example",
                "name": "Gast",
                "email_verified": True,
            }
        }
    )
    assert signer is not None
    assert signer.subject.kind is SubjectKind.GUEST
    assert signer.email == "gast@voorbeeld.example"
    assert signer.person_id is None

    for session in (
        {},
        {"guest": "gast@voorbeeld.example"},
        {"guest": {"email": "gast@voorbeeld.example"}},
        {"guest": {"email": "gast@voorbeeld.example", "email_verified": False}},
        {"guest": {"email": " ", "email_verified": True}},
    ):
        assert signer_from_guest_session(session) is None
