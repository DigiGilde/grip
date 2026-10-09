"""Column helpers shared by the domain models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Versioned:
    """A record people edit in forms: it counts its own changes.

    ``version`` goes up with every update of the row. A form reads it with
    the record and sends it back with the save, so a save on top of someone
    else's change is refused instead of silently overwriting it
    (``grip.services.stale``). The database also refuses two updates that
    started from the same version.
    """

    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, object]:  # noqa: N805
        return {"version_id_col": cls.version}


class EditCounted:
    """A record that both people and the system write to: it counts only what
    people change.

    A login, a sync or the task engine updates such a row all the time; if
    every update raised the version, a person's form would be stale before
    they finished typing. So ``version`` goes up only when a service that
    carries a person's edit says so (``grip.services.stale.touch``). The
    check itself is the same as for ``Versioned``.
    """

    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
