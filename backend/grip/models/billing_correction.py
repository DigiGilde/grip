"""A correction to deliver on a billing period that was delivered before."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base
from grip.models._columns import created_at, updated_at, uuid_pk


class BillingCorrection(Base):
    """What changed on a billing period after it was delivered (a
    "naverrekening"): the difference, why, and what became of it.

    Written in the transaction of the change that caused it (a billing scale
    or rate card with effect in the past), so nothing has to price every
    month to know that someone has something to deliver. Changes on the same
    period before it is delivered add up in one row; a change that is undone
    takes the row away again. Delivering the difference closes the row.
    """

    __tablename__ = "billing_correction"
    __table_args__ = (
        # One open correction per period: later changes add up in it.
        Index(
            "uq_billing_correction_open",
            "assignment_id",
            "period_key",
            unique=True,
            postgresql_where=text("delivered_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="RESTRICT"),
        index=True,
    )
    # "2026-Q3" or "2026-07", as on the delivery it follows.
    period_key: Mapped[str] = mapped_column(String(10))
    # Positive or negative: what the period costs now minus what was delivered.
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    # The same difference per month: {"2026-03": -240000}.
    months: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    # Why, in words, one entry per change: [{"cause", "at", "by_name"}].
    causes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    # The delivery of the period this is a difference on.
    follows_delivery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("billing_delivery.id", ondelete="SET NULL"),
        nullable=True,
    )
    arose_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    arose_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The delivery the difference went along with; NULL while it is open.
    delivered_delivery_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("billing_delivery.id", ondelete="SET NULL"),
        nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
