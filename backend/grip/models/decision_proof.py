import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, uuid_pk

DECISION_ACTIONS = ("accept", "reject", "approve", "send_back")
DECISION_CHANNELS = ("signing_link", "own_instance", "internal", "uploaded_pdf")


class SigningIntent(Base):
    """Someone is about to decide and is being authenticated for it.

    Made when a person presses the button, used once when the identity
    provider sends them back, and gone stale after a few minutes. It holds
    the random value of the nonce: the token that comes back only counts
    when it carries the nonce computed from this row.
    """

    __tablename__ = "signing_intent"
    __table_args__ = (
        CheckConstraint(
            "action IN ('accept', 'reject', 'approve', 'send_back')",
            name="action_valid",
        ),
        CheckConstraint(
            "channel IN ('signing_link', 'own_instance', 'internal')",
            name="channel_valid",
        ),
        CheckConstraint("quote_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        Index("ix_signing_intent_expires", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    action: Mapped[str] = mapped_column(String(12))
    channel: Mapped[str] = mapped_column(String(20))
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote.id", ondelete="CASCADE"), index=True
    )
    quote_hash: Mapped[str] = mapped_column(String(64))
    # The inputs of the nonce, exactly as they go into the statement.
    nonce_inputs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    nonce: Mapped[str] = mapped_column(String(64), unique=True)
    # Who started it: a person of this instance, or an invited guest known
    # by the email address the identity provider vouched for at login.
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String(320))
    # What the person filled in with the decision (function, note, the
    # declaration of being authorised), kept until the provider sends them
    # back.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Where in the application to send the person afterwards.
    return_path: Mapped[str] = mapped_column(String(500), default="/")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decision_evidence.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The assertion of a passkey the person made for this decision, checked
    # when it came in; None when no passkey was used (grip.proof.passkey).
    passkey: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Why it ended without a decision, in a code the screen can explain.
    failure: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = created_at()


class DecisionEvidence(Base):
    """What a decision rests on: the statement and everything that verifies it.

    The statement is the decision (see ``grip.proof.statement``). Next to it
    are kept, as issued and never touched again: the ID token the identity
    provider signed for this decision, the keys that verify that token at
    that moment (keys rotate), the provider's discovery document, the keys
    of this instance, and an optional timestamp of a time-stamping
    authority. A bundle is assembled from this row and the quote.
    """

    __tablename__ = "decision_evidence"
    __table_args__ = (
        CheckConstraint(
            "action IN ('accept', 'reject', 'approve', 'send_back')",
            name="action_valid",
        ),
        CheckConstraint(
            "channel IN ('signing_link', 'own_instance', 'internal', 'uploaded_pdf')",
            name="channel_valid",
        ),
        CheckConstraint("quote_hash ~ '^[0-9a-f]{64}$'", name="hash_format"),
        # The hash is the hash of the stored bytes: the statement can be
        # referred to by it, and the row cannot say otherwise.
        CheckConstraint(
            "statement_hash = encode(sha256(statement), 'hex')",
            name="hash_of_statement",
        ),
        Index("ix_decision_evidence_quote", "quote_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    action: Mapped[str] = mapped_column(String(12))
    channel: Mapped[str] = mapped_column(String(20))
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quote.id", ondelete="RESTRICT")
    )
    quote_hash: Mapped[str] = mapped_column(String(64))
    # The statement as canonical JSON (RFC 8785), the bytes that were signed.
    statement: Mapped[bytes] = mapped_column(LargeBinary)
    statement_hash: Mapped[str] = mapped_column(String(64), unique=True)
    statement_jws: Mapped[str] = mapped_column(Text)
    # NULL when no identity provider was involved; the statement says why.
    id_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    idp_jwks: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    idp_discovery: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    instance_jwks: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # The passkey assertion made for this decision, as the browser sent it.
    passkey: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    timestamp_reply: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    timestamp_authority: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Who the statement is about, to find it again without parsing it:
    # a person of this instance, and always the address.
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    created_at: Mapped[datetime] = created_at()
