import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, uuid_pk


class PasskeyCredential(Base):
    """A passkey a person registered: a public key, and how it came to be theirs.

    The private key never leaves the person's device. Grip keeps the public
    key and the record of the registration: when it happened and which
    login the session rested on at that moment. That record is what ties
    the key to the person; an assertion made with the key later is checked
    against the public key alone.

    A passkey that is withdrawn keeps its row (``revoked_at``): a decision
    that was confirmed with it must stay verifiable.
    """

    __tablename__ = "passkey_credential"

    id: Mapped[uuid.UUID] = uuid_pk()
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        index=True,
    )
    # The id the authenticator gave the credential.
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    # The public key as the authenticator delivered it (COSE).
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    # What the person calls it ("Laptop", "Telefoon").
    label: Mapped[str] = mapped_column(String(100))
    # What the authenticator said about itself at registration.
    aaguid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    backed_up: Mapped[bool | None] = mapped_column(nullable=True)
    # The registration record: the relying party, the origin, and the login
    # the session rested on when the key was registered (issuer, subject,
    # time of authentication), or why there was none.
    registration: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # When the person last logged in through the identity provider. Logging
    # in with the passkey alone is only possible for a while after that.
    oidc_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at()
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
