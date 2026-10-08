from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from grip.core.database import Base


class HttpSession(Base):
    """Server-side session; the browser cookie only holds the signed id."""

    __tablename__ = "http_session"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Fernet-encrypted JSON (see core.session_store).
    data: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
