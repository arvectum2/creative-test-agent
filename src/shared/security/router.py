from fastapi import APIRouter, Request

from src.shared.security.auth import get_current_user_from_request
from src.shared.security.hardening import validate_security_posture
from src.shared.errors import AppError

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/posture")
def security_posture(request: Request):
    user = get_current_user_from_request(request)
    if user.get("role") not in {"admin", "manager"}:
        raise AppError("security_posture_forbidden", "Security posture requires admin or manager role", 403)
    return validate_security_posture().as_dict()
