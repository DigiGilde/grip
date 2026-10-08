from fastapi import APIRouter

from grip.api.routes.auth import router as auth_router
from grip.api.routes.health import router as health_router
from grip.api.routes.instance import router as instance_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(instance_router)
