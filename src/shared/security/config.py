from __future__ import annotations

import os

from src.shared.config.settings import Settings, get_settings

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def security_fail_closed() -> bool:
    return _env_bool("CTA_SECURITY_FAIL_CLOSED", True)


def security_headers_enabled() -> bool:
    return _env_bool("CTA_SECURITY_HEADERS_ENABLED", True)


def security_max_request_bytes(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    default_mb = max(settings.import_max_upload_size_mb + 10, 260)
    value = _env_int("CTA_SECURITY_MAX_REQUEST_SIZE_MB", default_mb, minimum=1, maximum=2048)
    return value * 1024 * 1024


def login_rate_limit_attempts() -> int:
    return _env_int("CTA_LOGIN_RATE_LIMIT_ATTEMPTS", 5, minimum=1, maximum=100)


def login_rate_limit_window_seconds() -> int:
    return _env_int("CTA_LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300, minimum=10, maximum=86400)


def session_cookie_samesite() -> str:
    value = os.getenv("CTA_SESSION_COOKIE_SAMESITE", "strict").strip().lower()
    return value if value in {"strict", "lax", "none"} else "strict"


def session_cookie_secure() -> bool:
    settings = get_settings()
    default = settings.public_base_url.lower().startswith("https://")
    return _env_bool("CTA_SESSION_COOKIE_SECURE", default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return default


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))
