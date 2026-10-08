"""The mail that carries a signing link to the person invited to sign.

Offering a quote "met een tekenlink" queues this mail in the same
transaction, when the instance can send mail and has not switched it off.
The message names the quote and says how to check that it is real; it holds
no amount and no name of staff, because mail is not a confidential channel.
The link opens only for the invited address, after logging in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.audit import CREATE, record_audit
from grip.core.config import get_settings
from grip.integrations.mail import outbox
from grip.integrations.mail.config import is_configured
from grip.models.mail_outbox import MAIL_FAILED, MAIL_QUEUED, MailOutbox
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.quote import Quote, QuoteInvitation
from grip.services import instance_settings
from grip.services.errors import DomainValidationError

KIND = "signing_link"
SUBJECT_KIND = "quote_invitation"

ENABLED = instance_settings.declare(
    "mail.signing_link",
    True,
    instance_settings.boolean,
    "Of grip de tekenlink mailt aan wie wordt uitgenodigd om een offerte te "
    "tekenen. Werkt alleen als de instantie e-mail kan versturen.",
)

_MONTHS = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)
_AMSTERDAM = ZoneInfo("Europe/Amsterdam")

# Why a message was not sent, for whoever manages the assignment.
_REASONS = {
    "recipient_refused": "het adres is geweigerd door de mailserver",
    "message_refused": "de mailserver weigerde het bericht",
    "limit_reached": "de daglimiet voor e-mail is bereikt",
    "login_refused": "de mailserver weigerde de aanmelding van grip",
    "relay_unreachable": "de mailserver was niet bereikbaar",
    "relay_busy": "de mailserver nam het bericht niet aan",
}


async def enabled(db: AsyncSession) -> bool:
    """Whether offering with a signing link mails the link."""
    return is_configured() and bool(await instance_settings.get(db, ENABLED.key))


def _day(moment: datetime) -> str:
    local = moment.astimezone(_AMSTERDAM)
    return f"{local.day} {_MONTHS[local.month - 1]} {local.year}"


@dataclass(frozen=True)
class SigningLinkFacts:
    """Everything the message says. No amount, no name of staff."""

    organisation: str
    client: str | None
    reference: str | None
    title: str | None
    link: str
    origin: str
    email: str
    valid_until: datetime | None
    can_reply: bool


def signing_link(quote_id: UUID) -> str:
    return f"{get_settings().FRONTEND_URL.rstrip('/')}/tekenen/{quote_id}"


def compose(facts: SigningLinkFacts) -> outbox.Content:
    """The message in plain text and in sober HTML, with the same words."""
    named = f"offerte {facts.reference}" if facts.reference else "een offerte"
    about = f" voor {facts.title}" if facts.title else ""
    to_client = f" aan {facts.client}" if facts.client else ""
    subject = (
        f"Offerte {facts.reference} van {facts.organisation} staat klaar om te tekenen"
        if facts.reference
        else f"Een offerte van {facts.organisation} staat klaar om te tekenen"
    )
    intro = (
        f"{facts.organisation} heeft {named}{about}{to_client} klaargezet. "
        "U bent uitgenodigd om de offerte te bekijken en er akkoord op te "
        "geven of haar af te wijzen."
    )
    conditions = f"De link werkt alleen voor {facts.email}, nadat u hebt ingelogd."
    if facts.valid_until is not None:
        conditions += f" De uitnodiging is geldig tot en met {_day(facts.valid_until)}."
    checks = [
        f"Het adres van de link begint met {facts.origin}. U kunt dat adres "
        "ook zelf in uw browser typen.",
        "U logt in bij uw eigen organisatie. Dit bericht vraagt u nooit om "
        "een wachtwoord.",
    ]
    if facts.reference:
        checks.insert(
            1,
            f"Het kenmerk van de offerte is {facts.reference}. U kunt dat "
            f"navragen bij {facts.organisation}.",
        )
    if facts.can_reply:
        checks.append(f"Een antwoord op dit bericht komt aan bij {facts.organisation}.")
    unexpected = (
        "Verwachtte u dit bericht niet? Dan hoeft u niets te doen. Zonder "
        "inloggen met dit adres opent de offerte niet."
    )

    text = "\n".join(
        [
            "Goedendag,",
            "",
            intro,
            "",
            "Open de offerte:",
            facts.link,
            "",
            conditions,
            "",
            "Zo controleert u dit bericht",
            *[f"- {check}" for check in checks],
            "",
            unexpected,
            "",
            "Met vriendelijke groet,",
            facts.organisation,
            "",
        ]
    )
    # The link is written out and points where it says: a reader can compare.
    link = escape(facts.link, quote=True)
    html = (
        '<!doctype html><html lang="nl"><body style="font-family:Verdana,'
        'Arial,sans-serif;font-size:15px;line-height:1.5;color:#1a1a1a">'
        "<p>Goedendag,</p>"
        f"<p>{escape(intro)}</p>"
        f'<p>Open de offerte:<br><a href="{link}">{link}</a></p>'
        f"<p>{escape(conditions)}</p>"
        "<p><strong>Zo controleert u dit bericht</strong></p><ul>"
        + "".join(f"<li>{escape(check)}</li>" for check in checks)
        + "</ul>"
        f"<p>{escape(unexpected)}</p>"
        f"<p>Met vriendelijke groet,<br>{escape(facts.organisation)}</p>"
        "</body></html>"
    )
    return outbox.Content(subject=subject, text=text, html=html)


async def _facts(
    db: AsyncSession, quote: Quote, invitation: QuoteInvitation, *, can_reply: bool
) -> SigningLinkFacts:
    # Imported here: the quote service queues this mail when it offers.
    from grip.services.assignments import get_assignment
    from grip.services.quotes import sender_name

    assignment = await get_assignment(db, quote.assignment_id)
    client = None
    if assignment.client_organisation_id is not None:
        organisation = await db.get(Organisation, assignment.client_organisation_id)
        client = organisation.name if organisation is not None else None
    link = signing_link(quote.id)
    parts = urlsplit(link)
    snapshot: dict[str, Any] = quote.snapshot or {}
    title = snapshot.get("name")
    return SigningLinkFacts(
        organisation=await sender_name(db, assignment),
        client=client,
        reference=quote.reference,
        title=title if isinstance(title, str) and title.strip() else None,
        link=link,
        origin=f"{parts.scheme}://{parts.netloc}",
        email=invitation.email,
        valid_until=invitation.expires_at,
        can_reply=can_reply,
    )


async def queue(
    db: AsyncSession,
    quote: Quote,
    invitation: QuoteInvitation,
    *,
    actor: Person | None,
    occasion: str,
) -> MailOutbox | None:
    """Queue the mail for an invitation, in the caller's transaction.

    ``occasion`` tells one sending from another (the offer it belongs to, or
    a numbered resend). While a message for this invitation is still waiting
    to be sent, that one is returned and nothing new is queued. Returns None
    when the instance does not mail signing links.
    """
    if not await enabled(db):
        return None
    waiting = (await outbox.latest_for(db, SUBJECT_KIND, {invitation.id})).get(
        invitation.id
    )
    if waiting is not None and waiting.status == MAIL_QUEUED:
        return waiting
    reply_to = actor.email if actor is not None and actor.email else None
    facts = await _facts(db, quote, invitation, can_reply=reply_to is not None)
    row = await outbox.enqueue(
        db,
        kind=KIND,
        dedupe_key=f"{KIND}:{invitation.id}:{occasion}",
        subject_kind=SUBJECT_KIND,
        subject_id=invitation.id,
        recipient=invitation.email,
        content=compose(facts),
        sender_name=facts.organisation,
        reply_to=reply_to,
        assignment_id=quote.assignment_id,
        created_by_id=actor.id if actor is not None else None,
    )
    # That a mail goes to this address is a fact about a person; the text of
    # the mail is not recorded.
    record_audit(
        db,
        actor=actor,
        action=CREATE,
        entity="mail_outbox",
        entity_id=row.id,
        new_value={
            "kind": KIND,
            "recipient": invitation.email,
            "quote_id": str(quote.id),
            "invitation_id": str(invitation.id),
        },
        assignment_id=quote.assignment_id,
    )
    return row


async def resend(
    db: AsyncSession,
    quote: Quote,
    invitation: QuoteInvitation,
    *,
    actor: Person | None,
) -> MailOutbox:
    """Mail the link of an open invitation again."""
    if not await enabled(db):
        raise DomainValidationError(
            "Deze instantie mailt geen tekenlinks. Kopieer de link en stuur hem zelf."
        )
    if invitation.used_at is not None:
        raise DomainValidationError("Met deze link is al getekend.")
    if invitation.withdrawn_at is not None:
        raise DomainValidationError("Deze link is ingetrokken. Verleng hem eerst.")
    if invitation.expires_at is not None and invitation.expires_at <= datetime.now(
        invitation.expires_at.tzinfo
    ):
        raise DomainValidationError("Deze link is verlopen. Verleng hem eerst.")
    number = await outbox.count_for(db, SUBJECT_KIND, invitation.id)
    row = await queue(db, quote, invitation, actor=actor, occasion=f"resend:{number}")
    assert row is not None
    return row


def state_of(row: MailOutbox) -> dict[str, Any]:
    """What whoever manages the assignment sees of a mail."""
    failed = row.status == MAIL_FAILED
    reason = None
    if failed:
        reason = _REASONS.get(
            row.failure or "", "het bericht kon niet worden verstuurd"
        )
    return {
        "state": row.status,
        "queued_at": row.created_at,
        "sent_at": row.sent_at,
        "failed_reason": reason,
        "attempts": row.attempts,
    }
