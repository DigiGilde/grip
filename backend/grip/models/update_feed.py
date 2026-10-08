"""When a person last looked at the feed of updates."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base


class UpdateFeedMarker(Base):
    """One row per person: the position in the stream they have seen up to.

    There is no bookkeeping per item: what lies after the marker is new.
    """

    __tablename__ = "update_feed_marker"

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seen_seq: Mapped[int] = mapped_column(BigInteger)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
