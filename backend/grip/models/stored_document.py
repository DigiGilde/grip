import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, uuid_pk


class StoredDocument(Base):
    """A file kept in the database, such as a signed quote.

    Meant for small documents that belong to a record. The content is loaded
    only when asked for.

    A document belongs to exactly one owning object, named by ``owner_kind``
    and ``owner_id`` (a signed quote to its acceptance, a received invoice to
    its invoice line). Who may see or remove a document is decided through
    that owner, never on the document itself. The owner is not a foreign key,
    because it can be a row of several tables: whoever deletes an owner
    deletes its documents (see ``services.stored_documents``).
    """

    __tablename__ = "stored_document"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_not_negative"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="hash_format"),
        CheckConstraint(
            "(owner_kind IS NULL) = (owner_id IS NULL)", name="owner_complete"
        ),
        Index("ix_stored_document_owner", "owner_kind", "owner_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Null only between storing a file and recording what it belongs to, in
    # the same transaction.
    owner_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()
