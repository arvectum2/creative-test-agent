from __future__ import annotations

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from src.shared.config.settings import get_settings
from src.shared.security.hardening import is_loopback_host


class RequestBodyTooLarge(Exception):
    pass


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
                headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
                headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
                headers.setdefault(
                    "Content-Security-Policy",
                    "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
                    "form-action 'self'; object-src 'none'; img-src 'self' data:; "
                    "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'",
                )
                if scope.get("scheme") == "https":
                    headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
                path = scope.get("path", "")
                if not path.startswith("/static/"):
                    headers["Cache-Control"] = "no-store"
                    headers["Pragma"] = "no-cache"
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length:
            try:
                declared = int(content_length)
            except ValueError:
                await self._reject(scope, receive, send, 400, "Invalid Content-Length header")
                return
            if declared < 0:
                await self._reject(scope, receive, send, 400, "Invalid Content-Length header")
                return
            if declared > self.max_bytes:
                await self._reject(
                    scope,
                    receive,
                    send,
                    413,
                    "Request body exceeds configured security limit",
                )
                return

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if response_started:
                raise
            await self._reject(
                scope,
                receive,
                send,
                413,
                "Request body exceeds configured security limit",
            )

    @staticmethod
    async def _reject(scope, receive, send, status_code: int, detail: str) -> None:
        response = JSONResponse(status_code=status_code, content={"detail": detail})
        await response(scope, receive, send)


class LocalOnlyRequestMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        settings = get_settings()
        if scope["type"] != "http" or not settings.local_only_mode:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        host_header = headers.get("host", "")
        host = host_header.rsplit(":", 1)[0].strip("[]") if host_header else ""
        if host not in {"test", "testserver"} and not is_loopback_host(host):
            response = JSONResponse(
                status_code=403,
                content={"detail": "Local-only mode rejected a non-loopback Host header"},
            )
            await response(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else ""
        if client_host and client_host not in {"test", "testclient"} and not is_loopback_host(client_host):
            response = JSONResponse(
                status_code=403,
                content={"detail": "Local-only mode rejected a non-loopback client address"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class BrowserOriginGuardMiddleware:
    _WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        settings = get_settings()
        if (
            scope["type"] != "http"
            or not settings.enable_auth
            or scope.get("method") not in self._WRITE_METHODS
        ):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if not origin:
            await self.app(scope, receive, send)
            return
        allowed = {
            _normalize_origin(value)
            for value in [*settings.cors_origins_list, settings.public_base_url]
            if value
        }
        if _normalize_origin(origin) not in allowed:
            response = JSONResponse(
                status_code=403,
                content={"detail": "Request origin is not allowed"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _normalize_origin(value: str) -> str:
    return value.strip().rstrip("/").lower()
