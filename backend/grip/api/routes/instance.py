"""Which instance this is."""

from fastapi import APIRouter, Depends

from grip.core.config import Settings, get_settings
from grip.schema.instance import InstanceInfo

router = APIRouter(prefix="/instance", tags=["instance"])


@router.get("", response_model=InstanceInfo)
async def get_instance(
    settings: Settings = Depends(get_settings),
) -> InstanceInfo:
    """Name and base URI of this instance.

    Public on purpose: the login page shows the name before anyone is
    logged in. Nothing else about the instance belongs here.
    """
    return InstanceInfo(
        name=settings.INSTANCE_NAME,
        base_uri=settings.INSTANCE_BASE_URI.rstrip("/"),
        example=settings.is_example,
    )
