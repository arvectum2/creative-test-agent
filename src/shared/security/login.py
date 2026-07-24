from __future__ import annotations

from fastapi import Request, Response

from src.shared.config.settings import get_settings
from src.shared.security.config import (
    login_rate_limit_attempts,
    login_rate_limit_window_seconds,
    session_cookie_samesite,
    session_cookie_secure,
)
from src.shared.security.rate_limit import login_rate_limiter


def _normalized_email(email: str) -> str:
    return email.strip().casefold()


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def login_rate_limit_keys(request: Request, email: str) -> tuple[str, str]:
    client = _client_host(request)
    normalized_email = _normalized_email(email)
    return (
        f"login-client:{client}",
        f"login-client-email:{client}:{normalized_email}",
    )


def check_login_rate_limit(request: Request, email: str) -> tuple[bool, int]:
    attempts = login_rate_limit_attempts()
    window = login_rate_limit_window_seconds()
    retry_after = 0
    for key in login_rate_limit_keys(request, email):
        allowed, key_retry_after = login_rate_limiter.check(
            key,
            max_attempts=attempts,
            window_seconds=window,
        )
        if not allowed:
            retry_after = max(retry_after, key_retry_after)
    return retry_after == 0, retry_after


def record_login_failure(request: Request, email: str) -> None:
    window = login_rate_limit_window_seconds()
    for key in login_rate_limit_keys(request, email):
        login_rate_limiter.record_failure(key, window_seconds=window)


def clear_login_failures(request: Request, email: str) -> None:
    for key in login_rate_limit_keys(request, email):
        login_rate_limiter.clear(key)


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=session_cookie_secure(),
        max_age=settings.session_ttl_hours * 3600,
        samesite=session_cookie_samesite(),
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def delete_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=session_cookie_secure(),
        samesite=session_cookie_samesite(),
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
