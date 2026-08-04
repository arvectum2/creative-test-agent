from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.modules.auth.service import login
from src.modules.ui.router import _ctx, templates
from src.shared.config.settings import get_settings
from src.shared.security.login import (
    check_login_rate_limit,
    clear_login_failures,
    delete_session_cookie,
    record_login_failure,
    set_session_cookie,
)

router = APIRouter()


def _render_login(
    request: Request,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    **context,
):
    return templates.TemplateResponse(
        request,
        "login.html",
        _ctx(request, **context),
        status_code=status_code,
        headers=headers,
    )


@router.get("/ui/login", include_in_schema=False)
def ui_login_page(request: Request):
    settings = get_settings()
    return _render_login(request, auth_disabled=not settings.enable_auth)


@router.post("/ui/login", include_in_schema=False)
async def ui_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    settings = get_settings()
    if not settings.enable_auth:
        return _render_login(
            request,
            auth_disabled=True,
            message="Auth is disabled in local/demo mode",
        )

    allowed, retry_after = check_login_rate_limit(request, email)
    if not allowed:
        return _render_login(
            request,
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            auth_disabled=False,
            error="Too many login attempts",
        )

    try:
        result = login(email, password)
    except ValueError:
        record_login_failure(request, email)
        return _render_login(
            request,
            status_code=401,
            auth_disabled=False,
            error="Invalid email or password",
        )

    clear_login_failures(request, email)
    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, result["token"])
    return response


@router.post("/ui/logout", include_in_schema=False)
def ui_logout():
    response = RedirectResponse(url="/ui/login", status_code=303)
    delete_session_cookie(response)
    return response
