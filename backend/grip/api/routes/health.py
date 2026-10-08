"""Health endpoints. Public: the platform probes them without a session."""

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness() -> dict[str, str]:
    from grip.core.database import async_session

    async with async_session() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}
