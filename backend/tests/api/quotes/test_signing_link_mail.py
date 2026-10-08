"""The signing link by mail: queued with the offer, sent by the worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from grip.core.config import get_settings
from grip.integrations.mail import outbox, transport
from grip.models.mail_outbox import MailOutbox
from grip.models.quote import QuoteInvitation
from grip.services import instance_settings, quotes, signing_mail


@pytest.fixture
def mail_on(monkeypatch):
    """An instance that can send mail, with a public address of its own."""
    settings = get_settings()
    monkeypatch.setattr(settings, "SMTP_HOST", "relay.example")
    monkeypatch.setattr(settings, "SMTP_FROM", "noreply+grip@voorbeeld.example")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://grip.voorbeeld.example")
    monkeypatch.setattr(settings, "ORGANISATION_NAME", "Voorbeeldgilde")
    return settings


class Relay:
    """Stands in for the relay: remembers what it got, or refuses."""

    def __init__(self) -> None:
        self.messages: list = []
        self.error: Exception | None = None

    def __call__(self, config, message, recipient) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append((recipient, message))


async def _issue(act_as, world) -> dict:
    response = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _offer(act_as, world, quote, email=None) -> dict:
    response = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/offers",
        json={"channel": "signing_link", "email": email or world.signer.email},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _mails(db_session) -> list[MailOutbox]:
    rows = await db_session.execute(select(MailOutbox).order_by(MailOutbox.created_at))
    return list(rows.scalars())


async def test_without_a_relay_nothing_is_mailed_and_offering_works(
    act_as, world, db_session, monkeypatch
):
    monkeypatch.setattr(get_settings(), "SMTP_HOST", "")
    quote = await _issue(act_as, world)
    body = await _offer(act_as, world, quote)
    assert body["signing_link_mail"] is False
    (offer,) = body["offers"]
    assert offer["invitation"]["signing_path"] == f"/tekenen/{quote['id']}"
    assert "mail" not in offer or offer["mail"] is None
    assert await _mails(db_session) == []
    # Nothing to resend either, and it says what to do instead.
    resend = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/invitations/{offer['invitation']['id']}/mail"
    )
    assert resend.status_code in (400, 422), resend.text
    assert "Kopieer de link" in resend.json()["detail"]


async def test_offering_queues_the_mail_and_says_so(act_as, world, db_session, mail_on):
    quote = await _issue(act_as, world)
    body = await _offer(act_as, world, quote)
    assert body["signing_link_mail"] is True
    (offer,) = body["offers"]
    assert offer["mail"]["state"] == "queued"
    assert offer["mail"]["sent_at"] is None and offer["mail"]["failed_reason"] is None

    (row,) = await _mails(db_session)
    assert row.kind == "signing_link" and row.status == "queued"
    assert row.recipient == world.signer.email
    assert row.reply_to == world.manager.email
    assert row.sender_name == "Voorbeeldgilde"
    assert row.assignment_id == world.assignment.id
    assert quote["reference"] in row.subject


async def test_the_mail_names_the_quote_and_how_to_check_it_and_no_amount(
    act_as, world, db_session, mail_on
):
    quote = await _issue(act_as, world)
    await _offer(act_as, world, quote)
    (row,) = await _mails(db_session)
    link = f"https://grip.voorbeeld.example/tekenen/{quote['id']}"
    for body in (row.text_body, row.html_body):
        assert link in body
        assert quote["reference"] in body
        assert "Voorbeeldgilde" in body and "Voorbeeldministerie" in body
        assert "Opdracht Alfa" in body
        assert world.signer.email in body
        # How a reader can tell the message is real.
        assert "begint met https://grip.voorbeeld.example" in body
        assert "nooit om een wachtwoord" in body
        # Mail is not a confidential channel: no money, in any notation.
        assert "€" not in body and "EUR" not in body
        assert "172" not in body and "18.000" not in body
    # Nothing is fetched from elsewhere and nothing tracks: the only address
    # in the HTML is the link itself, written out as its own text.
    html = row.html_body
    assert "<img" not in html and "<script" not in html and "<link" not in html
    assert html.count("http") == 3
    assert f'<a href="{link}">{link}</a>' in html

    names = (await db_session.execute(text("SELECT name FROM person"))).scalars().all()
    assert len(names) >= 6
    for name in names:
        assert name not in row.text_body and name not in row.html_body
        assert name not in row.subject


async def test_the_worker_sends_it_and_the_text_does_not_stay(
    act_as, world, db_session, mail_on
):
    quote = await _issue(act_as, world)
    await _offer(act_as, world, quote)
    relay = Relay()
    stats = await outbox.send_due(db_session, mail_on, sender=relay)
    assert (stats.sent, stats.retried, stats.failed) == (1, 0, 0)
    ((recipient, message),) = relay.messages
    assert recipient == world.signer.email
    assert message["Reply-To"] == world.manager.email
    assert "Voorbeeldgilde" in message["From"]

    (row,) = await _mails(db_session)
    assert row.status == "sent" and row.sent_at is not None
    assert row.text_body is None and row.html_body is None
    # A second pass sends nothing again.
    again = await outbox.send_due(db_session, mail_on, sender=relay)
    assert again.total == 0 and len(relay.messages) == 1

    shown = await act_as(world.manager).get(f"/api/quotes/{quote['id']}")
    (offer,) = shown.json()["offers"]
    assert offer["mail"]["state"] == "sent" and offer["mail"]["sent_at"]


async def test_a_busy_relay_is_tried_again_and_given_up_on_with_a_reason(
    act_as, world, db_session, mail_on, monkeypatch
):
    monkeypatch.setattr(mail_on, "MAIL_MAX_ATTEMPTS", 2)
    quote = await _issue(act_as, world)
    await _offer(act_as, world, quote)
    relay = Relay()
    relay.error = transport.TemporaryMailError(
        transport.RELAY_UNREACHABLE, "ConnectionRefusedError()"
    )
    first = await outbox.send_due(db_session, mail_on, sender=relay)
    (row,) = await _mails(db_session)
    assert first.retried == 1 and row.status == "queued" and row.attempts == 1
    assert row.next_attempt_at > datetime.now(UTC)
    assert row.text_body, "the text stays while the message still has to go"
    # Not due yet: nothing happens.
    assert (await outbox.send_due(db_session, mail_on, sender=relay)).total == 0

    row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()
    second = await outbox.send_due(db_session, mail_on, sender=relay)
    assert second.failed == 1
    assert row.status == "failed" and row.failure == transport.RELAY_UNREACHABLE
    assert row.text_body is None

    shown = await act_as(world.manager).get(f"/api/quotes/{quote['id']}")
    mail = shown.json()["offers"][0]["mail"]
    assert mail["state"] == "failed"
    assert mail["failed_reason"] == "de mailserver was niet bereikbaar"
    assert mail["attempts"] == 2


async def test_a_refused_address_fails_at_once(act_as, world, db_session, mail_on):
    quote = await _issue(act_as, world)
    await _offer(act_as, world, quote)
    relay = Relay()
    relay.error = transport.PermanentMailError(
        transport.RECIPIENT_REFUSED, "550 no such user"
    )
    stats = await outbox.send_due(db_session, mail_on, sender=relay)
    (row,) = await _mails(db_session)
    assert stats.failed == 1 and row.status == "failed" and row.attempts == 1
    assert signing_mail.state_of(row)["failed_reason"] == (
        "het adres is geweigerd door de mailserver"
    )


async def test_sending_again_is_idempotent_while_one_still_waits(
    act_as, world, db_session, mail_on
):
    quote = await _issue(act_as, world)
    body = await _offer(act_as, world, quote)
    invitation_id = body["offers"][0]["invitation"]["id"]
    manager = act_as(world.manager)
    url = f"/api/quotes/{quote['id']}/invitations/{invitation_id}/mail"

    # The first mail has not gone yet: asking again queues nothing new.
    for _ in range(2):
        response = await manager.post(url)
        assert response.status_code == 200, response.text
    assert len(await _mails(db_session)) == 1

    relay = Relay()
    await outbox.send_due(db_session, mail_on, sender=relay)
    # Now it has gone: "Stuur opnieuw" queues one more, and only one.
    for _ in range(2):
        response = await manager.post(url)
        assert response.status_code == 200, response.text
    rows = await _mails(db_session)
    assert [row.status for row in rows] == ["sent", "queued"]
    assert response.json()["offers"][0]["mail"]["state"] == "queued"
    await outbox.send_due(db_session, mail_on, sender=relay)
    assert len(relay.messages) == 2


async def test_an_expired_link_is_renewed_before_it_is_mailed_again(
    act_as, world, db_session, mail_on
):
    quote = await _issue(act_as, world)
    body = await _offer(act_as, world, quote)
    invitation_id = body["offers"][0]["invitation"]["id"]
    await outbox.send_due(db_session, mail_on, sender=Relay())
    invitation = await db_session.get(QuoteInvitation, invitation_id)
    invitation.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.flush()

    manager = act_as(world.manager)
    url = f"/api/quotes/{quote['id']}/invitations/{invitation_id}/mail"
    refused = await manager.post(url)
    assert refused.status_code in (400, 422), refused.text
    assert "verlopen" in refused.json()["detail"]
    renewed = await manager.post(url, json={"renew": True})
    assert renewed.status_code == 200, renewed.text
    offer = renewed.json()["offers"][0]
    assert offer["invitation"]["state"] in ("invited", "opened")
    assert offer["mail"]["state"] == "queued"
    rows = await _mails(db_session)
    # The new mail states the new end date.
    assert rows[-1].text_body and "geldig tot en met" in rows[-1].text_body


async def test_only_who_manages_sees_the_mail_and_may_send_it_again(
    act_as, world, db_session, mail_on
):
    quote = await _issue(act_as, world)
    body = await _offer(act_as, world, quote)
    invitation_id = body["offers"][0]["invitation"]["id"]
    url = f"/api/quotes/{quote['id']}/invitations/{invitation_id}/mail"

    for reader in (world.lezer, world.beheerder):
        shown = await act_as(reader).get(f"/api/quotes/{quote['id']}")
        assert shown.status_code == 200, shown.text
        (offer,) = shown.json()["offers"]
        assert offer.get("mail") is None
        assert offer.get("invitation") is None and offer.get("recipient") is None
        assert (await act_as(reader).post(url)).status_code == 403
    for stranger in (world.planner, world.member, world.outsider):
        assert (await act_as(stranger).post(url)).status_code in (403, 404)
    assert len(await _mails(db_session)) == 1


async def test_the_instance_can_switch_mailing_of_signing_links_off(
    act_as, world, db_session, mail_on
):
    assert await signing_mail.enabled(db_session) is True
    await instance_settings.set_values(
        db_session, {"mail.signing_link": False}, actor=world.beheerder
    )
    quote = await _issue(act_as, world)
    body = await _offer(act_as, world, quote)
    assert body["signing_link_mail"] is False
    assert body["offers"][0].get("mail") is None
    assert await _mails(db_session) == []


async def test_an_offer_that_is_undone_leaves_no_mail(world, db_session, mail_on):
    quote = await quotes.issue_quote(
        db_session, world.assignment.id, actor=world.manager
    )
    savepoint = await db_session.begin_nested()
    await quotes.offer_quote(
        db_session,
        quote.id,
        "signing_link",
        actor=world.manager,
        email=world.signer.email,
    )
    assert len(await _mails(db_session)) == 1
    await savepoint.rollback()
    db_session.expire_all()

    assert await _mails(db_session) == []
    relay = Relay()
    assert (await outbox.send_due(db_session, mail_on, sender=relay)).total == 0
    assert relay.messages == []


async def test_offering_again_to_the_same_person_mails_again(
    act_as, world, db_session, mail_on
):
    quote = await _issue(act_as, world)
    await _offer(act_as, world, quote)
    await outbox.send_due(db_session, mail_on, sender=Relay())
    body = await _offer(act_as, world, quote)
    assert len(body["offers"]) == 2
    rows = await _mails(db_session)
    assert [row.status for row in rows] == ["sent", "queued"]
    assert all(row.recipient == world.signer.email for row in rows)
