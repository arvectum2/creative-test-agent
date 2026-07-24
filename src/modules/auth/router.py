from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.shared.config.settings import get_settings
from src.shared.security.auth import get_current_user_from_request
from src.shared.security.login import (
    check_login_rate_limit,
    clear_login_failures,
    delete_session_cookie,
    record_login_failure,
    set_session_cookie,
)

from .schemas import LoginRequest
from .service import login

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def auth_login(body: LoginRequest, request: Request):
    settings = get_settings()
    if not settings.enable_auth:
        return {"message": "Auth is disabled in local/demo mode", "auth_enabled": False}

    allowed, retry_after = check_login_rate_limit(request, body.email)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        result = login(body.email, body.password)
    except ValueError:
        record_login_failure(request, body.email)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    clear_login_failures(request, body.email)
    response = JSONResponse(content=result)
    set_session_cookie(response, result["token"])
    return response


@router.post("/logout")
def auth_logout():
    response = JSONResponse(content={"message": "Logged out"})
    delete_session_cookie(response)
    return response


@router.get("/me")
def auth_me(current_user: dict = Depends(get_current_user_from_request)):
    settings = get_settings()
    return {
        "user_id": current_user["user_id"],
        "display_name": current_user["display_name"],
        "role": current_user["role"],
        "is_active": current_user.get("is_active", True),
        "auth_enabled": settings.enable_auth,
    }
