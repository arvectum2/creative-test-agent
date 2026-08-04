"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from src.app.lifecycle import application_lifespan
from src.app.middleware import configure_middleware
from src.app.routers import register_routers
from src.shared.api.errors import register_exception_handlers
from src.shared.config.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully configured application without import-time side effects."""

    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.app_name,
        lifespan=application_lifespan,
    )
    app.state.settings = resolved_settings
    register_exception_handlers(app)
    configure_middleware(app, resolved_settings)
    register_routers(app)
    return app
