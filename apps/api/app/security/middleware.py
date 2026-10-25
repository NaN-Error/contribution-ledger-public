"""Bounded JSON requests and explicit browser-origin checks. CSRF is checked in dependencies."""
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope, Receive, Send
import re
from app.evidence.schemas import UPLOAD_JSON_LIMIT

UUID_PATH = r"[0-9a-fA-F-]{36}"
UPLOAD_PATH = re.compile(rf"^/api/v1/workspaces/{UUID_PATH}/projects/{UUID_PATH}/work-packages/{UUID_PATH}/evidence(?:/{UUID_PATH}/revisions)?$")


FINANCE_UPLOAD_PATH = re.compile(rf"^/api/v1/workspaces/{UUID_PATH}/projects/{UUID_PATH}/finance/periods/{UUID_PATH}/documents$")


class BrowserBoundaryMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: list[str], max_body_bytes: int = 65536):
        self.app, self.origins, self.limit = app, set(allowed_origins), max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))

        async def reject(status: int, code: str, message: str):
            await JSONResponse({"error": {"code": code, "message": message,
                "request_id": scope.get("state", {}).get("request_id", "unknown")}},
                status_code=status, headers={"Cache-Control": "no-store"})(scope, receive, send)

        if sum(key.lower()==b"host" for key,_ in scope.get("headers",[])) != 1:
            return await reject(400,"ambiguous_host","Exactly one Host header is required.")
        if scope["method"] in {"GET","HEAD","OPTIONS"}:
            if headers.get(b"transfer-encoding") or headers.get(b"content-length",b"0") not in {b"0",b""}:
                return await reject(400,"body_not_allowed","Read-only requests cannot carry a body.")
            return await self.app(scope, receive, send)
        webhook = scope['method'] == 'POST' and scope['path'] == '/api/v1/github/webhook'
        origin = headers.get(b"origin", b"").decode("latin1")
        if not webhook and (origin not in self.origins or headers.get(b"sec-fetch-site") == b"cross-site"):
            return await reject(403, "origin_rejected", "This browser origin is not authorized. Use the configured application address.")
        for header in (b"origin", b"x-csrf-token", b"content-type", b"content-length"):
            if sum(key.lower() == header for key, _ in scope.get("headers", [])) > 1:
                return await reject(400, "ambiguous_headers", "Duplicate security headers are not accepted.")
        if headers.get(b"content-type", b"").split(b";")[0].strip().lower() != b"application/json":
            return await reject(415, "json_required", "Send a JSON request body.")
        limit = 1048576 if webhook else UPLOAD_JSON_LIMIT if scope['method'] == 'POST' and (UPLOAD_PATH.fullmatch(scope['path']) or FINANCE_UPLOAD_PATH.fullmatch(scope['path'])) else self.limit
        declared = headers.get(b'content-length')
        if declared:
            try: size = int(declared)
            except ValueError: return await reject(400, 'invalid_length', 'The content length is invalid.')
            if size < 0: return await reject(400, 'invalid_length', 'The content length is invalid.')
            if size > limit: return await reject(413, 'request_too_large', 'This request exceeds the allowed size.')
        if headers.get(b'content-encoding', b'identity').lower() != b'identity':
            return await reject(415, 'encoding_rejected', 'Compressed request bodies are not accepted.')
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                return await reject(413, "request_too_large", "This request exceeds the allowed size.")
            if not message.get("more_body", False):
                break
        sent = False
        async def bounded_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, bounded_receive, send)
