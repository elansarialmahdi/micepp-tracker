from fastapi import APIRouter, Request, Response, status

from app.core.config import Settings
from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.health import build_readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
async def live(request: Request) -> LivenessResponse:
    settings: Settings = request.app.state.settings
    return LivenessResponse(service=settings.app_name, version=settings.app_version)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    readiness = await build_readiness(
        request.app.state.database_engine,
        request.app.state.redis,
        request.app.state.settings,
    )
    if readiness.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness
