"""Shared rendering helpers for modular UI routers."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from starlette.templating import Jinja2Templates

from src.shared.config.settings import get_settings
from src.shared.db.session import check_db_connection
from src.shared.i18n import get_translator
from src.shared.security.auth import get_optional_user_from_request
from src.shared.version import get_version_info

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def detect_lang(request: Request) -> str:
    lang = request.query_params.get("lang", "")
    if lang in ("ru", "en"):
        return lang
    lang = request.cookies.get("lang", "")
    if lang in ("ru", "en"):
        return lang
    return "ru"


def template_context(request: Request, **extra) -> dict:
    settings = get_settings()
    version_info = get_version_info()
    lang = detect_lang(request)
    base = {
        "local_only": settings.local_only_mode,
        "cloud_blocked": not settings.allow_cloud_llm,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "db_connected": check_db_connection(),
        "db_type": "SQLite",
        "auth_enabled": settings.enable_auth,
        "current_user": get_optional_user_from_request(request),
        "app_version": version_info["version"],
        "app_stage": version_info["stage"],
        "lang": lang,
        "t": get_translator(lang).t,
    }
    base.update(extra)
    return base


def render(request: Request, name: str, **context):
    return templates.TemplateResponse(request, name, template_context(request, **context))


def render_error(request: Request, message: str):
    return templates.TemplateResponse(
        request,
        "error.html",
        template_context(request, message=message),
    )
