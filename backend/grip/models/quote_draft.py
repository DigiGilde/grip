"""The quote in preparation: the text of a quote before it is made.

The budget is the draft of the numbers; this is the draft of the words. One
per assignment. When a quote is made the text is frozen into its content;
the draft stays, as the start of a next quote.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base


class QuoteDraft(Base):
    __tablename__ = "quote_draft"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Subject, addressee, salutation, opening, closing, the signatory of the
    # client, and the sections with where each text came from
    # (grip.services.quote_drafts describes the shape).
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
