import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
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
    only when asked for. Another record points here with a reference of the
    form ``stored_document:<id>``.
    """

    __tablename__ = "stored_document"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_not_negative"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="hash_format"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
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
