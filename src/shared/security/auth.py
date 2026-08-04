from typing import TypedDict

from fastapi import HTTPException, Request

from src.shared.config.settings import get_settings

from .session import decode_session_token


class CurrentUser(TypedDict):
    user_id: str
    role: str
    display_name: str
    is_active: bool


AUTH_DISABLED_USER: CurrentUser = {
    "user_id": "system",
    "role": "admin",
    "display_name": "System",
    "is_active": True,
}


def get_current_user_from_request(request: Request) -> CurrentUser:
    settings = get_settings()
    if not settings.enable_auth:
        return dict(AUTH_DISABLED_USER)

    cookie_name = settings.session_cookie_name
    token = request.cookies.get(cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    data = decode_session_token(token)
    if data is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    from src.modules.users.models import User
    from src.shared.db.repository import db_session

    with db_session() as db:
        user = db.query(User).filter(User.id == data["user_id"]).first()
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")

        return CurrentUser(
            user_id=user.id,
            role=user.role,
            display_name=user.display_name,
            is_active=user.is_active,
        )


def get_optional_user_from_request(request: Request) -> CurrentUser | None:
    """Return the current user, treating authentication failures as anonymous.

    Only expected authentication failures are swallowed. Database and programming
    errors still propagate so operational faults cannot be mislabeled as anonymous
    requests.
    """

    try:
        return get_current_user_from_request(request)
    except HTTPException:
        return None


def get_optional_user_id(request: Request) -> str | None:
    user = get_optional_user_from_request(request)
    return user["user_id"] if user else None
