"""Application middleware assembly and write authorization."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.modules.pilot_workspace.scope_middleware import PilotWorkspaceScopeMiddleware
from src.shared.config.settings import Settings, get_settings
from src.shared.security.auth import get_current_user_from_request
from src.shared.security.config import security_headers_enabled, security_max_request_bytes
from src.shared.security.middleware import (
    BrowserOriginGuardMiddleware,
    LocalOnlyRequestMiddleware,
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_WRITE_ROLES = frozenset({"admin", "manager", "analyst"})
_AUTH_BYPASS_PATHS = frozenset({"/"})
_AUTH_BYPASS_PREFIXES = (
    "/auth/login",
    "/auth/logout",
    "/ui/login",
    "/ui/logout",
)


class WriteAuthorizationMiddleware:
    """Require an authenticated write-capable role for state-changing requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if not self._requires_authorization(scope):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        try:
            user = get_current_user_from_request(request)
        except HTTPException as exc:
            response = JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
            await response(scope, receive, send)
            return

        role = str(user.get("role", ""))
        if role not in _WRITE_ROLES:
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": f"Role '{role}' does not have write permission"
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _requires_authorization(self, scope) -> bool:
        if scope.get("type") != "http" or not get_settings().enable_auth:
            return False
        if scope.get("method") not in _WRITE_METHODS:
            return False
        path = str(scope.get("path", ""))
        if path in _AUTH_BYPASS_PATHS:
            return False
        return not path.startswith(_AUTH_BYPASS_PREFIXES)


def configure_middleware(app: FastAPI, settings: Settings) -> None:
    """Register middleware in one place while preserving the established order."""

    trusted_hosts = list(settings.trusted_hosts_list)
    if settings.env == "local":
        trusted_hosts.extend(["test", "testserver"])
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=sorted(
            set(trusted_hosts or ["localhost", "127.0.0.1"])
        ),
    )

    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Accept", "Content-Type", "X-Requested-With"],
        )

    app.add_middleware(LocalOnlyRequestMiddleware)
    app.add_middleware(BrowserOriginGuardMiddleware)
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=security_max_request_bytes(settings),
    )
    app.add_middleware(PilotWorkspaceScopeMiddleware)
    if security_headers_enabled():
        app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(WriteAuthorizationMiddleware)
