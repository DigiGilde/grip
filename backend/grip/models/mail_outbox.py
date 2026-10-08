"""A mail to send: queued with the change that causes it, sent by the worker."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, uuid_pk

MAIL_QUEUED = "queued"
MAIL_SENT = "sent"
MAIL_FAILED = "failed"
MAIL_STATUSES = (MAIL_QUEUED, MAIL_SENT, MAIL_FAILED)


class MailOutbox(Base):
    """One message to one recipient.

    ``sent`` means the relay accepted the message, not that it reached a
    mailbox: a bounce comes back later as mail, and grip receives none.
    The text is kept until the message is sent or given up on, and removed
    then; what stays is that a message of this kind went to this address.
    """

    __tablename__ = "mail_outbox"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'sent', 'failed')", name="status_valid"),
        Index("ix_mail_outbox_due", "status", "next_attempt_at"),
        Index("ix_mail_outbox_subject", "subject_kind", "subject_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # What the message is, e.g. "signing_link".
    kind: Mapped[str] = mapped_column(String(40))
    # Queueing a message with a key that exists returns the existing row.
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    # What the message is about, e.g. ("quote_invitation", id).
    subject_kind: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    recipient: Mapped[str] = mapped_column(String(320))
    reply_to: Mapped[str | None] = mapped_column(String(320), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject: Mapped[str] = mapped_column(String(300))
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default=MAIL_QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Why the last attempt did not send: a short code and what the relay said.
    failure: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at()
