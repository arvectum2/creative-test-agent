"""Small operational endpoints that belong to the application shell."""

from fastapi import APIRouter

from src.shared.config.settings import get_settings
from src.shared.db.session import check_db_connection, get_database_url
from src.shared.security.hardening import validate_security_posture
from src.shared.version import get_version_info

router = APIRouter(tags=["system"])


@router.get("/health/db")
def health_db() -> dict[str, str]:
    connected = check_db_connection()
    return {
        "status": "ok" if connected else "error",
        "database": "connected" if connected else "disconnected",
        "database_url": get_database_url(masked=True),
    }


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    posture = validate_security_posture(settings)
    return {
        "status": "ok" if not posture.blocking_errors else "error",
        "app": settings.app_name,
        "local_only_mode": settings.local_only_mode,
        "security_posture": posture.status,
    }


@router.get("/version")
def version() -> dict[str, object]:
    return get_version_info()
