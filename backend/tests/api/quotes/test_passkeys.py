"""Passkeys: a person's own keys, logging in, and confirming a decision.

The ceremonies run for real against an authenticator in software
(``tests/software_authenticator.py``): what the server checks here is what
it checks for a device. All names are fictional.
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from grip.core.auth import (
    PASSKEY_SESSION_KEY,
    is_passkey_session,
    passkey_session_expired,
    start_passkey_session,
)
from grip.core.config import Settings, get_settings
from grip.models.audit_log import AuditLog
from grip.models.decision_proof import DecisionEvidence, SigningIntent
from grip.models.passkey import PasskeyCredential
from grip.proof import flow
from grip.proof.passkey import compute_challenge
from grip.proof.statement import parse_statement
from grip.proof.verify import NOT_PROVEN, PROVEN, WRONG, verify_bundle
from grip.services import instance_settings, passkeys, quote_approval
from tests.software_authenticator import SoftwareAuthenticator


@pytest.fixture
def device() -> SoftwareAuthenticator:
    settings = get_settings()
    return SoftwareAuthenticator(
        rp_id=settings.PASSKEY_RP_ID, origin=settings.PASSKEY_ORIGIN
    )


async def _register(client, device, label="Laptop"):
    options = await client.post("/api/passkeys/register/options")
    assert options.status_code == 200, options.text
    return await client.post(
        "/api/passkeys/register/verify",
        json={
            "credential": device.register(options.json()["options_json"]),
            "label": label,
        },
    )


# --- a person's own passkeys -----------------------------------------------------


async def test_a_person_registers_lists_and_withdraws_a_passkey(
    act_as, world, db_session, device
):
    client = act_as(world.manager)
    empty = (await client.get("/api/passkeys")).json()
    assert empty["available"] is True and empty["items"] == []
    assert empty["may_register"] is True

    made = await _register(client, device)
    assert made.status_code == 201, made.text
    assert made.json()["label"] == "Laptop"
    # Nothing of the key itself goes back to the screen.
    assert set(made.json()) == {
        "id",
        "label",
        "created_at",
        "last_used_at",
        "device_type",
        "backed_up",
    }

    stored = await db_session.get(PasskeyCredential, uuid.UUID(made.json()["id"]))
    assert stored.person_id == world.manager.id
    assert bytes(stored.credential_id) == device.credential_id
    # The registration record says what the session rested on: here nothing,
    # and it says so.
    login = stored.registration["aanmelding"]
    assert (
        login["uitgever"] is None and "lokale ontwikkeling" in login["ontbreekt_omdat"]
    )

    listed = (await client.get("/api/passkeys")).json()["items"]
    assert [item["id"] for item in listed] == [made.json()["id"]]

    gone = await client.delete(f"/api/passkeys/{made.json()['id']}")
    assert gone.status_code == 204
    assert (await client.get("/api/passkeys")).json()["items"] == []
    # Withdrawn, not removed: what was confirmed with it stays checkable.
    await db_session.refresh(stored)
    assert stored.revoked_at is not None and stored.revoked_by_id == world.manager.id

    events = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.entity == "passkey_credential")
            )
        )
        .scalars()
        .all()
    )
    assert [e.action for e in events] == ["create", "update"]
    # No key material in the stream.
    text = json.dumps([e.new_value for e in events])
    assert "public_key" not in text


async def test_the_same_key_is_not_registered_twice(act_as, world, device):
    client = act_as(world.manager)
    assert (await _register(client, device)).status_code == 201
    options = await client.post("/api/passkeys/register/options")
    # The server tells the device which keys it already knows.
    exclude = json.loads(options.json()["options_json"])["excludeCredentials"]
    assert len(exclude) == 1
    again = await client.post(
        "/api/passkeys/register/verify",
        json={"credential": device.register(options.json()["options_json"])},
    )
    assert again.status_code == 422, again.text


async def test_a_registration_needs_its_own_challenge_and_user_verification(
    act_as, world, device
):
    client = act_as(world.manager)
    options = await client.post("/api/passkeys/register/options")
    answer = device.register(options.json()["options_json"])
    # The challenge is used once.
    assert (
        await client.post("/api/passkeys/register/verify", json={"credential": answer})
    ).status_code == 201
    replay = await client.post(
        "/api/passkeys/register/verify", json={"credential": answer}
    )
    assert replay.status_code == 400

    settings = get_settings()
    lazy = SoftwareAuthenticator(
        rp_id=settings.PASSKEY_RP_ID,
        origin=settings.PASSKEY_ORIGIN,
        user_verification=False,
    )
    refused = await _register(client, lazy)
    assert refused.status_code == 400

    elsewhere = SoftwareAuthenticator(
        rp_id=settings.PASSKEY_RP_ID, origin="https://grip.elders.example"
    )
    assert (await _register(client, elsewhere)).status_code == 400


async def test_nobody_touches_someone_elses_passkey_but_the_beheerder_withdraws(
    act_as, world, db_session, device
):
    made = (await _register(act_as(world.manager), device)).json()

    other = act_as(world.planner)
    assert (await other.delete(f"/api/passkeys/{made['id']}")).status_code == 404
    path = f"/api/people/{world.manager.id}/passkeys"
    assert (await other.get(path)).status_code == 403
    assert (await other.delete(f"{path}/{made['id']}")).status_code == 403

    beheerder = act_as(world.beheerder)
    seen = await beheerder.get(path)
    assert seen.status_code == 200 and [p["id"] for p in seen.json()] == [made["id"]]
    assert (await beheerder.delete(f"{path}/{made['id']}")).status_code == 204
    stored = await db_session.get(PasskeyCredential, uuid.UUID(made["id"]))
    assert stored.revoked_by_id == world.beheerder.id
    # There is no route by which the beheerder makes a passkey for someone.
    assert (await beheerder.post(f"{path}/register/options")).status_code in (404, 405)


async def test_a_person_has_at_most_ten_passkeys(act_as, world, monkeypatch):
    monkeypatch.setattr(passkeys, "MAX_PASSKEYS_PER_PERSON", 1)
    settings = get_settings()
    client = act_as(world.manager)
    first = SoftwareAuthenticator(
        rp_id=settings.PASSKEY_RP_ID, origin=settings.PASSKEY_ORIGIN
    )
    assert (await _register(client, first)).status_code == 201
    more = await client.post("/api/passkeys/register/options")
    assert more.status_code == 422


# --- logging in --------------------------------------------------------------------


def _oidc_settings(**overrides) -> Settings:
    values = dict(
        _env_file=None,
        DEV_NO_AUTH=False,
        OIDC_ISSUER="https://idp.test.example/realms/test",
        SESSION_SECRET_KEY="s" * 40,
        FRONTEND_URL="https://grip.test.example",
    )
    values.update(overrides)
    return Settings(**values)


async def _registered(db_session, person, settings, *, seen: datetime | None):
    device = SoftwareAuthenticator(
        rp_id=settings.PASSKEY_RP_ID, origin=settings.PASSKEY_ORIGIN
    )
    options_json, challenge = await passkeys.registration_options(
        db_session, person, settings
    )
    passkey = await passkeys.register(
        db_session,
        person,
        settings,
        credential=device.register(options_json),
        challenge_hex=challenge,
        label="Telefoon",
        login={
            "uitgever": settings.OIDC_ISSUER,
            "subject": "sub-1",
            "aangemeld_op": "2026-10-01T09:00:00+00:00",
        },
        now=seen,
    )
    return device, passkey


async def test_a_passkey_logs_in_for_a_while_after_the_identity_provider(
    world, db_session
):
    settings = _oidc_settings()
    assert settings.PASSKEY_RP_ID == "grip.test.example"
    now = datetime.now(UTC)
    device, passkey = await _registered(
        db_session, world.manager, settings, seen=now - timedelta(days=3)
    )
    options_json, challenge = passkeys.login_options(settings)
    # No credential is named: nothing on the login page says who has one.
    assert not json.loads(options_json).get("allowCredentials")

    person = await passkeys.login(
        db_session,
        settings,
        credential=device.assert_(options_json),
        challenge_hex=challenge,
    )
    assert person.id == world.manager.id
    assert passkey.last_used_at is not None and passkey.sign_count == 1


async def test_a_passkey_does_not_outlive_the_identity_provider(world, db_session):
    settings = _oidc_settings()
    now = datetime.now(UTC)
    device, passkey = await _registered(
        db_session, world.manager, settings, seen=now - timedelta(days=31)
    )

    async def attempt():
        options_json, challenge = passkeys.login_options(settings)
        return await passkeys.login(
            db_session,
            settings,
            credential=device.assert_(options_json),
            challenge_hex=challenge,
        )

    with pytest.raises(passkeys.PasskeyRefusedError) as stale:
        await attempt()
    assert "gewone weg" in stale.value.message

    # Logging in through the provider again makes it usable again.
    await passkeys.note_oidc_login(db_session, world.manager)
    assert (await attempt()).id == world.manager.id

    world.manager.is_active = False
    await db_session.flush()
    with pytest.raises(passkeys.PasskeyRefusedError):
        await attempt()
    world.manager.is_active = True

    await passkeys.revoke(db_session, passkey, actor=world.manager)
    with pytest.raises(passkeys.PasskeyRefusedError):
        await attempt()


async def test_an_assertion_for_another_challenge_or_host_is_refused(world, db_session):
    settings = _oidc_settings()
    device, _ = await _registered(
        db_session, world.manager, settings, seen=datetime.now(UTC)
    )
    options_json, _challenge = passkeys.login_options(settings)
    _other_options, other_challenge = passkeys.login_options(settings)
    with pytest.raises(passkeys.PasskeyRefusedError):
        await passkeys.login(
            db_session,
            settings,
            credential=device.assert_(options_json),
            challenge_hex=other_challenge,
        )
    # A page on another host that got the person to use the key.
    device.origin = "https://grip.nagemaakt.example"
    options_json, challenge = passkeys.login_options(settings)
    with pytest.raises(passkeys.PasskeyRefusedError):
        await passkeys.login(
            db_session,
            settings,
            credential=device.assert_(options_json),
            challenge_hex=challenge,
        )


async def test_logging_in_with_a_passkey_can_be_switched_off(world, db_session):
    assert passkeys.login_enabled(_oidc_settings()) is True
    assert passkeys.login_enabled(_oidc_settings(PASSKEY_LOGIN_MAX_AGE_DAYS=0)) is False
    # Without an identity provider there is no login to speak of.
    assert passkeys.login_enabled(get_settings()) is False


async def test_the_login_routes_are_closed_where_login_is_off(client):
    assert (await client.post("/api/auth/passkey/options")).status_code == 501
    status = (await client.get("/api/auth/status")).json()
    assert status["passkey_login"] is False and status["passkey_session"] is False


def test_a_passkey_session_holds_no_tokens_and_ends_sooner(world):
    settings = _oidc_settings(PASSKEY_SESSION_TTL_SECONDS=60)
    session: dict = {"access_token": "x", "csrf_token": "y", "guest": {"email": "a"}}
    start_passkey_session(session, world.manager)
    assert is_passkey_session(session)
    assert set(session) == {PASSKEY_SESSION_KEY, "person_id", "_rotate"}
    assert passkey_session_expired(session, settings) is False
    session[PASSKEY_SESSION_KEY]["created_at"] = time.time() - 61
    assert passkey_session_expired(session, settings) is True
    assert is_passkey_session({"person_id": "1", "access_token": "x"}) is False


# --- confirming a decision -----------------------------------------------------------


@pytest.fixture
async def approver(create_person):
    return await create_person(
        "goedkeurder@example.org",
        name="Goedkeurder Voorbeeld",
        functions=[quote_approval.APPROVER_FUNCTION],
    )


async def _awaiting_approval(act_as, world, db_session) -> dict:
    await instance_settings.set_values(
        db_session, {"quote_approval.mode": "always"}, actor=world.beheerder
    )
    made = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert made.status_code == 201, made.text
    quote = made.json()
    asked = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/approval/request", json={}
    )
    assert asked.status_code == 201, asked.text
    return quote


async def _intent(client, quote) -> dict:
    created = await client.post(
        "/api/proof/intents",
        json={
            "kind": "approve",
            "quote_id": quote["id"],
            "quote_hash": quote["snapshot_hash"],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def _result(response) -> dict[str, str]:
    assert response.status_code == 302, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return {key: values[0] for key, values in query.items()}


async def test_without_a_passkey_a_decision_goes_as_before(
    act_as, world, db_session, approver
):
    quote = await _awaiting_approval(act_as, world, db_session)
    client = act_as(approver)
    intent = await _intent(client, quote)
    assert intent["passkey"] is None
    evidence_id = _result(await client.get(intent["authorize_url"]))["bewijs"]
    evidence = await db_session.get(DecisionEvidence, uuid.UUID(evidence_id))
    assert evidence.passkey is None
    # A statement without a passkey has no member for it.
    assert "passkey" not in parse_statement(bytes(evidence.statement))["hoe"]
    bundle = await flow.bundle_of(db_session, evidence, get_settings())
    assert "passkey" not in bundle
    assert not any("passkey" in text for _, text in verify_bundle(bundle).findings)


async def test_a_passkey_signs_for_exactly_this_decision_and_the_bundle_proves_it(
    act_as, world, db_session, approver, device
):
    quote = await _awaiting_approval(act_as, world, db_session)
    client = act_as(approver)
    assert (await _register(client, device)).status_code == 201

    intent = await _intent(client, quote)
    assert intent["passkey"] is not None
    options = await client.post(intent["passkey"]["options_url"])
    assert options.status_code == 200, options.text
    request = json.loads(options.json()["options_json"])
    assert request["userVerification"] == "required"
    # The challenge is computed from the decision, not drawn at random.
    stored = await db_session.get(SigningIntent, uuid.UUID(intent["id"]))
    assert request["challenge"] == _b64(compute_challenge(stored.nonce_inputs))

    confirmed = await client.post(
        intent["passkey"]["verify_url"],
        json={"credential": device.assert_(options.json()["options_json"])},
    )
    assert confirmed.status_code == 200, confirmed.text

    evidence_id = _result(await client.get(intent["authorize_url"]))["bewijs"]
    evidence = await db_session.get(DecisionEvidence, uuid.UUID(evidence_id))
    statement = parse_statement(bytes(evidence.statement))
    stated = statement["hoe"]["passkey"]
    assert stated["uitdaging"]["vingerafdruk"] == quote["snapshot_hash"]
    assert stated["uitdaging"]["besluit"] == "goedkeuring"
    assert stated["rp_id"] == get_settings().PASSKEY_RP_ID
    assert stated["registratie"]["geregistreerd_op"]

    bundle = await flow.bundle_of(db_session, evidence, get_settings())
    # The bundle survives being written to a file and read back.
    bundle = json.loads(json.dumps(bundle, default=str))
    report = verify_bundle(bundle)
    assert report.sound, report.of(WRONG)
    proven = " ".join(report.of(PROVEN))
    assert "Een passkey tekende voor precies dit besluit" in proven
    assert "gebruiker heeft geverifieerd" in proven
    unproven = " ".join(report.of(NOT_PROVEN))
    assert "Welke mens het apparaat bediende is hiermee niet bewezen" in unproven
    # Facts, not a judgement of strength.
    everything = " ".join(text for _, text in report.findings).lower()
    assert "zwakker" not in everything and "sterker" not in everything

    # The event names the use, not the key or the person.
    used = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity == "passkey_credential", AuditLog.action == "update"
                )
            )
        )
        .scalars()
        .all()
    )
    assert any((e.new_value or {}).get("used_for") == "decision" for e in used)

    # Any change to what the device signed, or to what it signed for, shows.
    tampered = copy.deepcopy(bundle)
    tampered["passkey"]["assertion"]["response"]["signature"] = _b64(b"\x30\x00")
    assert not verify_bundle(tampered).sound
    missing = copy.deepcopy(bundle)
    del missing["passkey"]
    report = verify_bundle(missing)
    assert report.sound and any("niet na te gaan" in t for t in report.of(NOT_PROVEN))


async def test_an_assertion_for_another_decision_is_refused(
    act_as, world, db_session, approver, device
):
    quote = await _awaiting_approval(act_as, world, db_session)
    client = act_as(approver)
    assert (await _register(client, device)).status_code == 201
    first = await _intent(client, quote)
    second = await _intent(client, quote)
    options = await client.post(first["passkey"]["options_url"])
    assertion = device.assert_(options.json()["options_json"])
    # Same quote, same person, same decision: another random value, so
    # another challenge.
    refused = await client.post(
        second["passkey"]["verify_url"], json={"credential": assertion}
    )
    assert refused.status_code == 400
    stored = await db_session.get(SigningIntent, uuid.UUID(second["id"]))
    assert stored.passkey is None


async def test_only_who_started_a_decision_confirms_it_with_their_own_passkey(
    act_as, world, db_session, approver, device, create_person
):
    quote = await _awaiting_approval(act_as, world, db_session)
    client = act_as(approver)
    assert (await _register(client, device)).status_code == 201
    intent = await _intent(client, quote)

    other = await create_person(
        "tweede@example.org",
        name="Tweede Goedkeurder",
        functions=[quote_approval.APPROVER_FUNCTION],
    )
    settings = get_settings()
    theirs = SoftwareAuthenticator(
        rp_id=settings.PASSKEY_RP_ID, origin=settings.PASSKEY_ORIGIN
    )
    assert (await _register(act_as(other), theirs)).status_code == 201
    assert (
        await act_as(other).post(intent["passkey"]["options_url"])
    ).status_code == 404

    # The other person's key signing the right challenge is still not theirs
    # to use on this decision.
    stored = await db_session.get(SigningIntent, uuid.UUID(intent["id"]))
    forged = theirs.assertion(_b64(compute_challenge(stored.nonce_inputs)))
    refused = await act_as(approver).post(
        intent["passkey"]["verify_url"], json={"credential": json.dumps(forged)}
    )
    assert refused.status_code == 400
    # And the decision is still possible without a passkey.
    back = await act_as(approver).get(intent["authorize_url"])
    assert "bewijs" in _result(back)


def _b64(data: bytes) -> str:
    from grip.proof.jose import b64url

    return b64url(data)
