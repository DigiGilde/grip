import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grip.core.database import Base


class Person(Base):
    """Someone who can log in to this instance or be staffed on an opdracht.

    Access is pre-provisioned: a login only succeeds for an active Person.
    ``oidc_subject`` is bound on the first login, matched on verified email.
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
    email: Mapped[str] = mapped_column(String(320))
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
