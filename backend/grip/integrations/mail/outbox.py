"""Mail to send: queue it with the change, send it from the worker, retry it.

The pattern of the federation outbox with its own table: a caller queues a
message in the transaction of its own change, so a message exists if and
only if the change does. The worker claims due rows with SKIP LOCKED and
hands them to the relay. A temporary refusal is retried with a growing
pause; a permanent one, or too many attempts, ends as ``failed`` with the
reason.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from grip.core.audit import UPDATE, record_audit
from grip.core.config import Settings
from grip.integrations.mail import transport
from grip.integrations.mail.config import MailConfig, display_name, mail_config
from grip.models.mail_outbox import MAIL_FAILED, MAIL_QUEUED, MAIL_SENT, MailOutbox

logger = logging.getLogger(__name__)

_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 3600
_MAX_ERROR_LENGTH = 1000
GAVE_UP = "gave_up"

Sender = Callable[[MailConfig, EmailMessage, str], None]


@dataclass(frozen=True)
class Content:
    subject: str
    text: str
    html: str | None = None


async def enqueue(
    db: AsyncSession,
    *,
    kind: str,
    dedupe_key: str,
    subject_kind: str,
    subject_id: UUID,
    recipient: str,
    content: Content,
    sender_name: str | None = None,
    reply_to: str | None = None,
    assignment_id: UUID | None = None,
    created_by_id: UUID | None = None,
) -> MailOutbox:
    """Queue one message. The caller commits; the same key queues nothing new."""
    existing = (
        await db.execute(select(MailOutbox).where(MailOutbox.dedupe_key == dedupe_key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = MailOutbox(
        kind=kind,
        dedupe_key=dedupe_key,
        subject_kind=subject_kind,
        subject_id=subject_id,
        assignment_id=assignment_id,
        recipient=recipient.strip(),
        reply_to=reply_to.strip() if reply_to and reply_to.strip() else None,
        sender_name=display_name(sender_name) if sender_name else None,
        subject=" ".join(content.subject.split())[:300],
        text_body=content.text,
        html_body=content.html,
        status=MAIL_QUEUED,
        attempts=0,
        next_attempt_at=datetime.now(UTC),
        created_by_id=created_by_id,
    )
    db.add(row)
    await db.flush()
    return row


async def latest_for(
    db: AsyncSession, subject_kind: str, subject_ids: set[UUID]
) -> dict[UUID, MailOutbox]:
    """Per subject its most recent message."""
    if not subject_ids:
        return {}
    rows = (
        await db.execute(
            select(MailOutbox)
            .where(
                MailOutbox.subject_kind == subject_kind,
                MailOutbox.subject_id.in_(subject_ids),
            )
            .order_by(MailOutbox.created_at, MailOutbox.next_attempt_at)
        )
    ).scalars()
    latest: dict[UUID, MailOutbox] = {}
    for row in rows:
        latest[row.subject_id] = row
    return latest


async def count_for(db: AsyncSession, subject_kind: str, subject_id: UUID) -> int:
    rows = await db.execute(
        select(MailOutbox.id).where(
            MailOutbox.subject_kind == subject_kind,
            MailOutbox.subject_id == subject_id,
        )
    )
    return len(rows.all())


def build_message(row: MailOutbox, config: MailConfig) -> EmailMessage:
    """The message as it goes to the relay.

    Text with a plain HTML alternative, nothing fetched from elsewhere and
    nothing that tracks. The platform relay replaces From with the address
    and name of the project; Reply-To stays as set here.
    """
    message = EmailMessage()
    message["From"] = formataddr((row.sender_name or "", config.from_address))
    message["To"] = row.recipient
    message["Subject"] = row.subject
    message["Date"] = format_datetime(datetime.now(UTC))
    domain = config.from_address.rsplit("@", 1)[-1] or None
    message["Message-ID"] = make_msgid(idstring=str(row.id), domain=domain)
    if row.reply_to:
        message["Reply-To"] = row.reply_to
    # Sent by a system on an event: a vacation responder should stay quiet.
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(row.text_body or "")
    if row.html_body:
        message.add_alternative(row.html_body, subtype="html")
    return message


def backoff_seconds(attempts: int) -> int:
    return min(_BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), _BACKOFF_MAX_SECONDS)


@dataclass
class SendStats:
    sent: int = 0
    retried: int = 0
    failed: int = 0

    @property
    def total(self) -> int:
        return self.sent + self.retried + self.failed


def _close(db: AsyncSession, row: MailOutbox, status: str) -> None:
    """End a message: the text goes, the fact stays and is recorded."""
    row.status = status
    row.text_body = None
    row.html_body = None
    record_audit(
        db,
        actor=None,
        action=UPDATE,
        entity="mail_outbox",
        entity_id=row.id,
        new_value={
            "status": status,
            "kind": row.kind,
            "failure": row.failure,
            "attempts": row.attempts,
        },
        assignment_id=row.assignment_id,
    )


async def _send_one(
    db: AsyncSession,
    row: MailOutbox,
    config: MailConfig,
    settings: Settings,
    sender: Sender,
    stats: SendStats,
) -> None:
    row.attempts += 1
    try:
        message = build_message(row, config)
        await asyncio.to_thread(sender, config, message, row.recipient)
    except transport.PermanentMailError as exc:
        row.failure = exc.code
        row.last_error = exc.detail[:_MAX_ERROR_LENGTH]
        _close(db, row, MAIL_FAILED)
        stats.failed += 1
        logger.warning("Mail %s (%s) was refused: %s", row.id, row.kind, exc.code)
        return
    except transport.TemporaryMailError as exc:
        row.failure = exc.code
        row.last_error = exc.detail[:_MAX_ERROR_LENGTH]
        if row.attempts >= settings.MAIL_MAX_ATTEMPTS:
            _close(db, row, MAIL_FAILED)
            stats.failed += 1
            logger.error(
                "Mail %s (%s) gave up after %d attempts: %s",
                row.id,
                row.kind,
                row.attempts,
                exc.code,
            )
            return
        row.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=backoff_seconds(row.attempts)
        )
        stats.retried += 1
        return
    row.failure = None
    row.last_error = None
    row.sent_at = datetime.now(UTC)
    _close(db, row, MAIL_SENT)
    stats.sent += 1


async def send_due(
    db: AsyncSession,
    settings: Settings,
    *,
    sender: Sender = transport.send,
    limit: int = 20,
) -> SendStats:
    """Send the messages that are due. The caller commits.

    Without a configured relay nothing is claimed: queued messages wait.
    """
    stats = SendStats()
    config = mail_config(settings)
    if config is None:
        return stats
    rows = (
        (
            await db.execute(
                select(MailOutbox)
                .where(
                    MailOutbox.status == MAIL_QUEUED,
                    MailOutbox.next_attempt_at <= datetime.now(UTC),
                )
                .order_by(MailOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        await _send_one(db, row, config, settings, sender, stats)
    await db.flush()
    return stats


async def run_mail_loop(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    """Send due mail forever. Started by the worker."""
    while True:
        try:
            async with session_factory() as db:
                stats = await send_due(db, settings)
                await db.commit()
            if stats.total:
                logger.info("Mail: %s", stats)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Mail loop failed; trying again later")
        await asyncio.sleep(settings.MAIL_OUTBOX_INTERVAL_SECONDS)
