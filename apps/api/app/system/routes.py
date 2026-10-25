from datetime import datetime, timezone
from fastapi import APIRouter, Request, Response
from app.core.config import BUILD_VERSION
from app.system.schemas import SystemStatus
from app.system.service import system_status

router = APIRouter()


@router.get("/health/live", tags=["health"])
def live() -> dict:
    return {"status": "ok", "service": "contribution-ledger-api", "version": BUILD_VERSION,
            "checked_at": datetime.now(timezone.utc).isoformat()}


@router.get("/health/ready", response_model=SystemStatus, tags=["health"], responses={503: {"model": SystemStatus}})
@router.get("/api/v1/system/status", response_model=SystemStatus, tags=["system"], responses={503: {"model": SystemStatus}})
def status(request: Request, response: Response) -> SystemStatus:
    if request.app.state.settings.environment == "staging" and request.url.path.startswith("/api/"):
        from app.auth.dependencies import find_identity
        from app.core.errors import ApiError
        with request.app.state.database.session() as db:
            identity=find_identity(request,db)
            if not identity or not identity.user:raise ApiError(401,"authentication_required","Finish signing in to inspect application status.")
    result = system_status(request.app.state.database)
    if result.status != "ready":
        response.status_code = 503
    return result
