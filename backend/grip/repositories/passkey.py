from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.passkey import PasskeyCredential


class PasskeyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, passkey_id: UUID) -> PasskeyCredential | None:
        return await self.db.get(PasskeyCredential, passkey_id)

    async def by_credential_id(self, credential_id: bytes) -> PasskeyCredential | None:
        result = await self.db.execute(
            select(PasskeyCredential).where(
                PasskeyCredential.credential_id == credential_id
            )
        )
        return result.scalar_one_or_none()

    async def of_person(
        self, person_id: UUID, *, include_revoked: bool = False
    ) -> list[PasskeyCredential]:
        query = select(PasskeyCredential).where(
            PasskeyCredential.person_id == person_id
        )
        if not include_revoked:
            query = query.where(PasskeyCredential.revoked_at.is_(None))
        result = await self.db.execute(
            query.order_by(PasskeyCredential.created_at.desc())
        )
        return list(result.scalars())

    async def count_of_person(self, person_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(PasskeyCredential)
            .where(
                PasskeyCredential.person_id == person_id,
                PasskeyCredential.revoked_at.is_(None),
            )
        )
        return int(result.scalar() or 0)
