from uuid import uuid4
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
import logging

logger = logging.getLogger("contribution_ledger")


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
    )


async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    messages = {404: ("not_found", "This endpoint does not exist."),
                405: ("method_not_allowed", "This method is not allowed."),
                403: ("forbidden", "This operation is not permitted.")}
    code, message = messages.get(exc.status_code, ("request_failed", "The request could not be completed."))
    return error_response(request, exc.status_code, code, message)


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Do not echo validation input, credentials, or exception detail to the browser.
    return error_response(request, 422, "invalid_request", "The request contains invalid data.")


async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("request_failed", extra={"event": "request_failed",
        "request_id": getattr(request.state, "request_id", "unknown"),
        "error_type": type(exc).__name__})
    return error_response(request, 500, "internal_error", "The request could not be completed.")


class ApiError(Exception):
    """Only fixed, public application messages belong here, never raw DB exceptions."""
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after
        super().__init__(code)


async def application_error(request: Request, exc: ApiError) -> JSONResponse:
    response = error_response(request, exc.status, exc.code, exc.message)
    if exc.retry_after is not None:
        response.headers["Retry-After"] = str(exc.retry_after)
    return response
