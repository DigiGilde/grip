"""Which instance this is."""

from fastapi import APIRouter, Depends

from grip.core.auth import CurrentPerson
from grip.core.config import Settings, get_settings
from grip.schema.instance import InstanceInfo

router = APIRouter(prefix="/instance", tags=["instance"])


@router.get("", response_model=InstanceInfo)
async def get_instance(
    _person: CurrentPerson,
    settings: Settings = Depends(get_settings),
) -> InstanceInfo:
    return InstanceInfo(
        name=settings.INSTANCE_NAME,
        base_uri=settings.INSTANCE_BASE_URI.rstrip("/"),
    )
