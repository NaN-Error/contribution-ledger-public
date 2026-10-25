import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SafeJsonFormatter(logging.Formatter):
    """Allowlist fields. Never stringify exception messages or arbitrary request input."""
    def format(self, record: logging.LogRecord) -> str:
        data = {"time": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname, "event": getattr(record, "event", "application_event")}
        for key in ("request_id", "method", "status", "duration_ms", "error_type"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data, separators=(",", ":"))


def configure_logging() -> None:
    logger = logging.getLogger("contribution_ledger")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(SafeJsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    # Starlette re-raises handled 500s to the server. Uvicorn's default traceback
    # could otherwise disclose the original exception/DSN after our safe response.
    server_logger = logging.getLogger("uvicorn.error")
    server_logger.handlers.clear()
    server_handler = logging.StreamHandler()
    server_handler.setFormatter(SafeJsonFormatter())
    server_logger.addHandler(server_handler)
    server_logger.propagate = False


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        try:
            request_id = str(UUID(headers.get(b"x-request-id", b"").decode("ascii")))
        except (ValueError, UnicodeError):
            request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.monotonic()
        status = 500

        async def send_with_headers(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                outgoing = [(k, v) for k, v in message.get("headers", [])
                            if k.lower() not in {b"x-request-id", b"cache-control"}]
                outgoing.extend([(b"x-request-id", request_id.encode()),
                                 (b"cache-control", b"no-store"),
                                 (b"x-content-type-options", b"nosniff"),
                                 (b"referrer-policy", b"no-referrer"),
                                 (b"x-frame-options", b"DENY")])
                message["headers"] = outgoing
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            logging.getLogger("contribution_ledger").info("http_request", extra={
                "event": "http_request", "request_id": request_id,
                "method": scope["method"], "status": status,
                "duration_ms": round((time.monotonic() - started) * 1000, 2)})
