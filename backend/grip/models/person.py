import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, event, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base
from grip.models._columns import EditCounted


class Person(EditCounted, Base):
    """Someone who can log in to this instance or be staffed on an opdracht.

    Access is pre-provisioned: a login only succeeds for an active Person.
    ``oidc_subject`` is bound on the first login, matched on verified email.

    A person may exist before there is an email address: a prospective
    colleague is planned from the moment of hire. Such a person cannot log in
    until the address arrives. The ``uri`` is the key shared with other
    systems, minted by this instance; the email is not, because it comes
    later and can change.
    """

    __tablename__ = "person"
    __table_args__ = (
        # Email is unique regardless of case.
        Index("uq_person_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Minted on insert as {INSTANCE_BASE_URI}/id/persoon/{id}.
    uri: Mapped[str | None] = mapped_column(String(500), unique=True, nullable=True)
    # The public id of the colleague in Wies, once Wies knows this person.
    wies_public_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    # Which system is the source of name and email: grip until Wies knows the
    # person, Wies afterwards.
    identity_source: Mapped[str] = mapped_column(
        String(20), default="grip", server_default=text("'grip'")
    )
    oidc_subject: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    manager: Mapped["Person | None"] = relationship(
        remote_side="Person.id", foreign_keys=[manager_id]
    )


def person_uri(person_id: uuid.UUID) -> str:
    from grip.core.config import get_settings

    base = get_settings().INSTANCE_BASE_URI.rstrip("/")
    return f"{base}/id/persoon/{person_id}"


@event.listens_for(Person, "before_insert")
def _mint_uri(mapper, connection, target: Person) -> None:  # noqa: ARG001
    """Every person gets a URI, whoever creates the row."""
    if target.id is None:
        target.id = uuid.uuid4()
    if not target.uri:
        target.uri = person_uri(target.id)
