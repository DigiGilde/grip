"""Deciding with proof: the statement is the decision, and it can be checked.

Two ways through the same flow. Over HTTP in an instance without an
identity provider (how the tests and local development run): the decision is
made, and the statement says truthfully that nobody vouched for the
identity. And directly through the flow with a stand-in provider, where the
token is a real signed token: there the binding to the document, the
freshness and the identity are checked for real.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from grip.core.config import Settings
from grip.federation import registry
from grip.federation.signing import SigningKey
from grip.models.audit_log import AuditLog
from grip.models.decision_proof import DecisionEvidence, SigningIntent
from grip.models.quote import Quote, QuoteAcceptance, QuoteApproval, QuoteRejection
from grip.proof import flow
from grip.proof.decisions import execute
from grip.proof.statement import columns, parse_statement
from grip.proof.verify import verify_bundle
from grip.services import events as domain_events
from grip.services import instance_settings, quote_approval
from tests.proof.idp import StandInProvider

GUEST_EMAIL = "gast@opdrachtgever.example"


@pytest.fixture(autouse=True)
def _clean():
    registry.clear_registries()
    domain_events.clear_handlers()
    yield
    registry.clear_registries()
    domain_events.clear_handlers()


@pytest.fixture(scope="module")
def provider() -> StandInProvider:
    return StandInProvider()


@pytest.fixture(scope="module")
def instance_key() -> SigningKey:
    return SigningKey(
        private_key=ec.generate_private_key(ec.SECP256R1()), kid="instantie-test"
    )


def _oidc_settings(provider: StandInProvider) -> Settings:
    return Settings(
        _env_file=None,
        DEV_NO_AUTH=False,
        OIDC_ISSUER=provider.issuer,
        OIDC_CLIENT_ID=provider.client_id,
        SESSION_SECRET_KEY="s" * 40,
        INSTANCE_NAME="Grip test",
        INSTANCE_BASE_URI="https://grip.test.example",
    )


async def _issued(act_as, world) -> dict:
    response = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _invited(act_as, world, email: str) -> dict:
    quote = await _issued(act_as, world)
    response = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/invitations", json={"email": email}
    )
    assert response.status_code == 201, response.text
    return quote


def _result(response) -> dict[str, str]:
    """The query of the redirect back into the application."""
    assert response.status_code == 302, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return {key: values[0] for key, values in query.items()}


# --- over HTTP, without an identity provider ------------------------------------


async def test_signing_link_acceptance_is_made_from_its_statement(
    act_as, world, db_session
):
    quote = await _invited(act_as, world, world.signer.email)
    client = act_as(world.signer)
    created = await client.post(
        f"/api/signing/quotes/{quote['id']}/intents",
        json={
            "decision": "accept",
            "quote_hash": quote["snapshot_hash"],
            "signer_function": "Directeur",
            "confirm_mandate": True,
        },
    )
    assert created.status_code == 201, created.text
    intent = created.json()
    assert intent["authorize_url"] == f"/api/signing/intents/{intent['id']}/authorize"
    # No identity provider here: the screen can say so before the click.
    assert intent["reauthentication"] is False

    back = await client.get(intent["authorize_url"])
    result = _result(back)
    assert urlsplit(back.headers["location"]).path == f"/tekenen/{quote['id']}"
    evidence_id = result["bewijs"]

    acceptance = (
        await db_session.execute(
            select(QuoteAcceptance).where(
                QuoteAcceptance.quote_id == uuid.UUID(quote["id"])
            )
        )
    ).scalar_one()
    evidence = await db_session.get(DecisionEvidence, uuid.UUID(evidence_id))
    assert acceptance.evidence_id == evidence.id
    # The columns are what the statement says, read from the signed bytes.
    values = columns(parse_statement(bytes(evidence.statement)))
    assert acceptance.signer_name == values["signer_name"] == world.signer.name
    assert acceptance.signer_email == values["signer_email"]
    assert acceptance.signer_function == values["signer_function"] == "Directeur"
    assert acceptance.organisation == values["organisation"]
    assert acceptance.signed_at == values["decided_at"]
    assert acceptance.form == values["channel"] == "signing_link"

    statement = parse_statement(bytes(evidence.statement))
    assert statement["besluit"] == "akkoord"
    assert statement["offerte"]["vingerafdruk"] == quote["snapshot_hash"]
    # Truthful about what is missing.
    assert statement["hoe"]["id_token_sha256"] is None
    assert (
        "zonder identiteitsprovider"
        in statement["hoe"]["aanmelding"]["ontbreekt_omdat"]
    )
    assert statement["bevoegdheid"]["grondslag"] == "uitnodiging"
    assert statement["bevoegdheid"]["toegekend_door"] == world.manager.name
    assert statement["bevoegdheid"]["verklaring_ondertekenaar"] is True
    assert "mandaat" in statement["bevoegdheid"]["toelichting"]

    # The intent is used up.
    again = _result(await client.get(intent["authorize_url"]))
    assert again == {"besluit_fout": "verlopen"}


async def test_the_signer_gets_the_same_bundle_the_instance_keeps(
    act_as, world, db_session
):
    quote = await _invited(act_as, world, world.signer.email)
    client = act_as(world.signer)
    intent = (
        await client.post(
            f"/api/signing/quotes/{quote['id']}/intents",
            json={
                "decision": "accept",
                "quote_hash": quote["snapshot_hash"],
                "confirm_mandate": True,
            },
        )
    ).json()
    evidence_id = _result(await client.get(intent["authorize_url"]))["bewijs"]

    summary = (await client.get(f"/api/signing/evidence/{evidence_id}")).json()
    assert summary["sound"] is True and summary["wrong"] == []
    assert summary["has_identity_statement"] is False
    assert any(
        "geen verklaring van een identiteitsprovider" in t
        for t in summary["not_proven"]
    )
    assert any("mandaat" in t for t in summary["not_proven"])

    download = await client.get(f"/api/signing/evidence/{evidence_id}/bundle")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith(
        "application/vnd.grip.bewijs+json"
    )
    assert "attachment" in download.headers["content-disposition"]
    bundle = download.json()
    # Checked with nothing but the file.
    report = verify_bundle(bundle)
    assert report.sound
    stored = await db_session.get(Quote, uuid.UUID(quote["id"]))
    assert bundle["offerte"]["vingerafdruk"] == stored.snapshot_hash
    # What the manager downloads is the same file.
    kept = await act_as(world.manager).get(f"/api/proof/evidence/{evidence_id}/bundle")
    assert kept.status_code == 200 and kept.json() == bundle

    page = await act_as(world.signer).get(f"/api/signing/evidence/{evidence_id}/page")
    assert page.status_code == 200
    assert "Akkoordverklaring" in page.text and "Niet bewezen" in page.text

    # Nobody else's.
    assert (
        await act_as(world.outsider).get(f"/api/signing/evidence/{evidence_id}")
    ).status_code == 404
    assert (
        await act_as(world.outsider).get(f"/api/proof/evidence/{evidence_id}/bundle")
    ).status_code == 404

    listed = (
        await act_as(world.manager).get(f"/api/proof/quotes/{quote['id']}/evidence")
    ).json()["items"]
    assert [item["id"] for item in listed] == [evidence_id]

    checked = await act_as(world.manager).post(
        "/api/proof/verify", json={"bundle": bundle}
    )
    assert checked.json()["sound"] is True
    bundle["offerte"]["kenmerk"] = "iets-anders"
    bundle["offerte"]["vingerafdruk"] = "0" * 64
    checked = await act_as(world.manager).post(
        "/api/proof/verify", json={"bundle": bundle}
    )
    assert checked.json()["sound"] is False


async def test_rejection_through_the_signing_link(act_as, world, db_session):
    quote = await _invited(act_as, world, world.signer.email)
    client = act_as(world.signer)
    intent = (
        await client.post(
            f"/api/signing/quotes/{quote['id']}/intents",
            json={
                "decision": "reject",
                "quote_hash": quote["snapshot_hash"],
                "reason": "Het budget is er niet.",
            },
        )
    ).json()
    evidence_id = _result(await client.get(intent["authorize_url"]))["bewijs"]
    rejection = (
        await db_session.execute(
            select(QuoteRejection).where(
                QuoteRejection.quote_id == uuid.UUID(quote["id"])
            )
        )
    ).scalar_one()
    assert str(rejection.evidence_id) == evidence_id
    evidence = await db_session.get(DecisionEvidence, rejection.evidence_id)
    statement = parse_statement(bytes(evidence.statement))
    assert statement["besluit"] == "afwijzing"
    assert statement["toelichting"] == rejection.reason == "Het budget is er niet."


async def test_acceptance_needs_the_declaration_and_the_hash_that_was_shown(
    act_as, world
):
    quote = await _invited(act_as, world, world.signer.email)
    client = act_as(world.signer)
    url = f"/api/signing/quotes/{quote['id']}/intents"
    body = {"decision": "accept", "quote_hash": quote["snapshot_hash"]}
    assert (await client.post(url, json=body)).status_code == 422
    other = {"decision": "accept", "quote_hash": "0" * 64, "confirm_mandate": True}
    assert (await client.post(url, json=other)).status_code == 422
    # Someone who was not invited cannot even start.
    assert (
        await act_as(world.outsider).post(url, json={**body, "confirm_mandate": True})
    ).status_code == 404


async def test_an_intent_belongs_to_who_started_it(act_as, world):
    quote = await _invited(act_as, world, world.signer.email)
    intent = (
        await act_as(world.signer).post(
            f"/api/signing/quotes/{quote['id']}/intents",
            json={
                "decision": "accept",
                "quote_hash": quote["snapshot_hash"],
                "confirm_mandate": True,
            },
        )
    ).json()
    for person in (world.manager, world.outsider):
        response = await act_as(person).get(intent["authorize_url"])
        assert response.status_code == 404, person.name
    # And not through the other prefix.
    assert (
        await act_as(world.signer).get(f"/api/proof/intents/{intent['id']}/authorize")
    ).status_code == 404


# --- internal approval -----------------------------------------------------------


@pytest.fixture
async def approver(create_person):
    return await create_person(
        "goedkeurder@example.org",
        name="Goedkeurder Voorbeeld",
        functions=[quote_approval.APPROVER_FUNCTION],
    )


async def test_internal_approval_states_the_right_it_relied_on(
    act_as, world, db_session, approver
):
    await instance_settings.set_values(
        db_session, {"quote_approval.mode": "always"}, actor=world.beheerder
    )
    quote = await _issued(act_as, world)
    path = f"/api/quotes/{quote['id']}/approval"
    asked = await act_as(world.manager).post(f"{path}/request", json={})
    assert asked.status_code == 201, asked.text

    seen: list[tuple[str, dict]] = []

    async def remember(_db, name, payload):
        seen.append((name, payload))

    domain_events.register_handler(domain_events.QUOTE_APPROVAL_APPROVED, remember)

    client = act_as(approver)
    created = await client.post(
        "/api/proof/intents",
        json={
            "kind": "approve",
            "quote_id": quote["id"],
            "quote_hash": quote["snapshot_hash"],
        },
    )
    assert created.status_code == 201, created.text
    back = await client.get(created.json()["authorize_url"])
    evidence_id = _result(back)["bewijs"]

    approval = (
        await db_session.execute(
            select(QuoteApproval).where(
                QuoteApproval.quote_id == uuid.UUID(quote["id"])
            )
        )
    ).scalar_one()
    assert approval.status == "approved"
    assert str(approval.evidence_id) == evidence_id
    evidence = await db_session.get(DecisionEvidence, approval.evidence_id)
    statement = parse_statement(bytes(evidence.statement))
    assert statement["besluit"] == "goedkeuring"
    assert statement["hoe"]["kanaal"] == "intern"
    assert approval.decided_at == columns(statement)["decided_at"]
    authority = statement["bevoegdheid"]
    assert authority["grondslag"] == "recht"
    assert authority["recht"] == "offertegoedkeurder"
    assert authority["sinds"] is not None and authority["toegekend_door"]

    # The event points at the statement by its hash, and carries nothing of it.
    assert len(seen) == 1
    payload = seen[0][1]
    assert payload["statement_hash"] == evidence.statement_hash
    text = json.dumps(payload)
    assert approver.name not in text and approver.email not in text
    # So does the audit row.
    audit = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity == "quote_approval",
                    AuditLog.entity_id == str(approval.id),
                    AuditLog.action == "update",
                )
            )
        )
        .scalars()
        .all()
    )
    assert any(
        (row.new_value or {}).get("statement_hash") == evidence.statement_hash
        for row in audit
    )


async def test_without_the_right_nobody_starts_an_approval(act_as, world, db_session):
    await instance_settings.set_values(
        db_session, {"quote_approval.mode": "always"}, actor=world.beheerder
    )
    quote = await _issued(act_as, world)
    await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/approval/request", json={}
    )
    for person in (world.manager, world.lezer, world.outsider):
        response = await act_as(person).post(
            "/api/proof/intents",
            json={
                "kind": "approve",
                "quote_id": quote["id"],
                "quote_hash": quote["snapshot_hash"],
            },
        )
        assert response.status_code in (403, 404), person.name


async def test_sending_back_needs_a_note(act_as, world, db_session, approver):
    await instance_settings.set_values(
        db_session, {"quote_approval.mode": "always"}, actor=world.beheerder
    )
    quote = await _issued(act_as, world)
    await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/approval/request", json={}
    )
    body = {
        "kind": "send_back",
        "quote_id": quote["id"],
        "quote_hash": quote["snapshot_hash"],
    }
    assert (
        await act_as(approver).post("/api/proof/intents", json=body)
    ).status_code == 422
    created = await act_as(approver).post(
        "/api/proof/intents", json={**body, "note": "Het tarief klopt niet."}
    )
    evidence_id = _result(await act_as(approver).get(created.json()["authorize_url"]))[
        "bewijs"
    ]
    evidence = await db_session.get(DecisionEvidence, uuid.UUID(evidence_id))
    statement = parse_statement(bytes(evidence.statement))
    assert statement["besluit"] == "teruggestuurd"
    assert statement["toelichting"] == "Het tarief klopt niet."


# --- with an identity provider: the token is checked for real ---------------------


async def _guest_intent(act_as, world, db_session, action="accept") -> SigningIntent:
    quote = await _invited(act_as, world, GUEST_EMAIL)
    stored = await db_session.get(Quote, uuid.UUID(quote["id"]))
    return await flow.create_intent(
        db_session,
        action=action,
        channel="signing_link",
        quote=stored,
        quote_hash=stored.snapshot_hash,
        person=None,
        email=GUEST_EMAIL,
        params={
            "signer_name": "Gast Tekenaar",
            "signer_function": "Directeur",
            "confirm_mandate": True,
            "organisation": {"name": "Voorbeeldministerie"},
        },
    )


async def _complete(db_session, intent, provider, key, token, **overrides):
    return await flow.complete_intent(
        db_session,
        intent,
        settings=_oidc_settings(provider),
        signing_key=key,
        instance_jwks={"keys": [key.public_jwk]},
        execute=execute,
        id_token=token,
        provider=flow.IdentityProvider(
            issuer=provider.issuer,
            client_id=provider.client_id,
            jwks=provider.jwks,
            discovery=provider.discovery,
        ),
        **overrides,
    )


async def test_a_fresh_authentication_bound_to_the_quote_is_proven(
    act_as, world, db_session, provider, instance_key
):
    intent = await _guest_intent(act_as, world, db_session)
    params = flow.authorization_params(intent)
    # What the provider is asked: log in now, for this nonce.
    assert params == {"prompt": "login", "max_age": 0, "nonce": intent.nonce}

    token = provider.id_token(
        nonce=intent.nonce, email=GUEST_EMAIL, auth_age=7, acr="1", amr=["pwd"]
    )
    completed = await _complete(db_session, intent, provider, instance_key, token)
    evidence = completed.evidence
    assert evidence.id_token == token
    assert evidence.idp_jwks == provider.jwks
    assert evidence.idp_discovery == provider.discovery

    statement = completed.statement
    assert statement["wie"]["subject"] == "sub-tekenaar"
    assert statement["wie"]["uitgever"] == provider.issuer
    assert statement["hoe"]["aanmelding"]["vers"] is True
    assert statement["hoe"]["aanmelding"]["gevraagd"] == {
        "prompt": "login",
        "max_age": 0,
    }
    assert statement["hoe"]["aanmelding"]["amr"] == ["pwd"]
    assert statement["hoe"]["nonce"] == intent.nonce_inputs

    bundle = await flow.bundle_of(db_session, evidence, _oidc_settings(provider))
    report = verify_bundle(bundle)
    assert report.sound
    proven = " ".join(report.of("bewezen"))
    assert "nonce" in proven and "seconden voor het besluit" in proven
    assert "acr=1" in proven

    acceptance = (
        await db_session.execute(
            select(QuoteAcceptance).where(QuoteAcceptance.quote_id == intent.quote_id)
        )
    ).scalar_one()
    assert acceptance.evidence_id == evidence.id
    assert acceptance.signer_email == GUEST_EMAIL


async def test_a_token_obtained_for_another_decision_is_refused(
    act_as, world, db_session, provider, instance_key
):
    intent = await _guest_intent(act_as, world, db_session)
    quote = await db_session.get(Quote, intent.quote_id)
    # The same person, the same quote, but authenticated to reject it.
    other = await flow.create_intent(
        db_session,
        action="reject",
        channel="signing_link",
        quote=quote,
        quote_hash=quote.snapshot_hash,
        person=None,
        email=GUEST_EMAIL,
    )
    assert other.nonce != intent.nonce
    token = provider.id_token(nonce=other.nonce, email=GUEST_EMAIL)
    with pytest.raises(flow.ProofRefusedError) as refused:
        await _complete(db_session, intent, provider, instance_key, token)
    assert refused.value.code == "token_ongeldig"
    assert "nonce" in refused.value.message
    # Nothing was decided and nothing was stored.
    assert quote.status == "issued"
    assert (await db_session.execute(select(DecisionEvidence))).scalars().all() == []


async def test_a_token_for_the_same_decision_on_another_quote_is_refused(
    act_as, world, db_session, provider, instance_key
):
    first = await _guest_intent(act_as, world, db_session)
    # Issuing again supersedes the first quote: a different document.
    second = await _guest_intent(act_as, world, db_session)
    assert first.quote_hash != second.quote_hash or first.quote_id != second.quote_id
    token = provider.id_token(nonce=first.nonce, email=GUEST_EMAIL)
    with pytest.raises(flow.ProofRefusedError) as refused:
        await _complete(db_session, second, provider, instance_key, token)
    assert refused.value.code == "token_ongeldig"


async def test_a_stale_authentication_is_recorded_as_weaker(
    act_as, world, db_session, provider, instance_key
):
    intent = await _guest_intent(act_as, world, db_session)
    token = provider.id_token(nonce=intent.nonce, email=GUEST_EMAIL, auth_age=4 * 3600)
    completed = await _complete(db_session, intent, provider, instance_key, token)
    login = completed.statement["hoe"]["aanmelding"]
    assert login["vers"] is False
    assert login["leeftijd_seconden"] >= 4 * 3600
    report = verify_bundle(
        await flow.bundle_of(db_session, completed.evidence, _oidc_settings(provider))
    )
    assert report.sound
    assert any("niet vers" in text for text in report.of("niet_bewezen"))


async def test_an_instance_can_refuse_a_stale_authentication(
    act_as, world, db_session, provider, instance_key
):
    await instance_settings.set_values(
        db_session, {"proof.stale_authentication": "refuse"}, actor=world.beheerder
    )
    intent = await _guest_intent(act_as, world, db_session)
    token = provider.id_token(nonce=intent.nonce, email=GUEST_EMAIL, auth_age=4 * 3600)
    with pytest.raises(flow.ProofRefusedError) as refused:
        await _complete(db_session, intent, provider, instance_key, token)
    assert refused.value.code == "aanmelding_niet_vers"
    quote = await db_session.get(Quote, intent.quote_id)
    assert quote.status == "issued"
    # A provider that leaves the time out is treated the same.
    token = provider.id_token(nonce=intent.nonce, email=GUEST_EMAIL, auth_age=None)
    with pytest.raises(flow.ProofRefusedError) as refused:
        await _complete(db_session, intent, provider, instance_key, token)
    assert refused.value.code == "aanmelding_niet_vers"


async def test_someone_else_at_the_provider_is_refused(
    act_as, world, db_session, provider, instance_key
):
    intent = await _guest_intent(act_as, world, db_session)
    for token in (
        provider.id_token(nonce=intent.nonce, email="ander@elders.example"),
        provider.id_token(nonce=intent.nonce, email=GUEST_EMAIL, email_verified=False),
    ):
        with pytest.raises(flow.ProofRefusedError) as refused:
            await _complete(db_session, intent, provider, instance_key, token)
        assert refused.value.code == "andere_persoon"

    # A person of the instance is known by the subject they are bound to.
    quote = await db_session.get(Quote, intent.quote_id)
    await act_as(world.manager).post(
        f"/api/quotes/{quote.id}/invitations", json={"email": world.signer.email}
    )
    world.signer.oidc_subject = "sub-van-de-tekenaar"
    await db_session.flush()
    own = await flow.create_intent(
        db_session,
        action="accept",
        channel="signing_link",
        quote=quote,
        quote_hash=quote.snapshot_hash,
        person=world.signer,
        email=world.signer.email,
        params={
            "confirm_mandate": True,
            "organisation": {"name": "Voorbeeldministerie"},
        },
    )
    stranger = provider.id_token(
        nonce=own.nonce, sub="sub-van-iemand-anders", email=world.signer.email
    )
    with pytest.raises(flow.ProofRefusedError) as refused:
        await _complete(db_session, own, provider, instance_key, stranger)
    assert refused.value.code == "andere_persoon"


async def test_with_a_provider_a_decision_without_a_token_is_refused(
    act_as, world, db_session, provider, instance_key
):
    intent = await _guest_intent(act_as, world, db_session)
    with pytest.raises(flow.ProofRefusedError) as refused:
        await flow.complete_intent(
            db_session,
            intent,
            settings=_oidc_settings(provider),
            signing_key=instance_key,
            instance_jwks={"keys": [instance_key.public_jwk]},
            execute=execute,
        )
    assert refused.value.code == "geen_aanmelding"


async def test_an_intent_expires_and_is_used_once(
    act_as, world, db_session, provider, instance_key
):
    intent = await _guest_intent(act_as, world, db_session)
    token = provider.id_token(nonce=intent.nonce, email=GUEST_EMAIL)
    late = datetime.now(UTC) + flow.INTENT_TTL + flow.INTENT_TTL
    with pytest.raises(flow.ProofRefusedError) as refused:
        await _complete(db_session, intent, provider, instance_key, token, now=late)
    assert refused.value.code == "verlopen"

    await _complete(db_session, intent, provider, instance_key, token)
    with pytest.raises(flow.ProofRefusedError) as refused:
        await _complete(db_session, intent, provider, instance_key, token)
    assert refused.value.code == "al_gebruikt"


async def test_an_abandoned_decision_does_not_capture_a_later_login():
    """The callback is the login callback; only the state tells them apart."""
    from starlette.requests import Request

    from grip.api.routes.proof import PROOF_SESSION_KEY, pending_intent

    def request(state: str | None, session: dict) -> Request:
        query = f"state={state}&code=c" if state else "code=c"
        return Request(
            {
                "type": "http",
                "query_string": query.encode(),
                "session": session,
                "headers": [],
            }
        )

    pending = {"intent": str(uuid.uuid4()), "state": "state-of-the-decision"}
    assert pending_intent(
        request("state-of-the-decision", {PROOF_SESSION_KEY: pending})
    )
    assert (
        pending_intent(request("state-of-a-login", {PROOF_SESSION_KEY: pending}))
        is None
    )
    assert pending_intent(request(None, {PROOF_SESSION_KEY: pending})) is None
    assert pending_intent(request("state-of-the-decision", {})) is None


async def test_a_bundle_is_checked_for_a_signer_within_a_size_limit(
    act_as, world, monkeypatch
):
    from grip.api.routes import proof as proof_routes

    quote = await _invited(act_as, world, world.signer.email)
    client = act_as(world.signer)
    intent = (
        await client.post(
            f"/api/signing/quotes/{quote['id']}/intents",
            json={
                "decision": "accept",
                "quote_hash": quote["snapshot_hash"],
                "confirm_mandate": True,
            },
        )
    ).json()
    evidence_id = _result(await client.get(intent["authorize_url"]))["bewijs"]
    bundle = (await client.get(f"/api/signing/evidence/{evidence_id}/bundle")).json()

    checked = await client.post("/api/signing/verify", json={"bundle": bundle})
    assert checked.status_code == 200, checked.text
    assert checked.json()["sound"] is True
    assert checked.json()["statement"]["besluit"] == "akkoord"

    for body in ({}, {"bundle": "geen object"}, []):
        assert (
            await client.post("/api/signing/verify", json=body)
        ).status_code == 422, body
    not_json = await client.post(
        "/api/signing/verify",
        content=b"{",
        headers={"Content-Type": "application/json"},
    )
    assert not_json.status_code == 422

    # Far larger than any bundle: refused before it is parsed.
    monkeypatch.setattr(proof_routes, "MAX_BUNDLE_BYTES", 2000)
    for path in ("/api/signing/verify", "/api/proof/verify"):
        too_big = await act_as(world.manager).post(path, json={"bundle": bundle})
        assert too_big.status_code == 413, path
        assert "te groot" in too_big.json()["detail"]
