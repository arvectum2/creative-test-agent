"""Composition root for the server-rendered UI."""

from fastapi import APIRouter

from src.modules.ui.admin_router import router as admin_router
from src.modules.ui.assets_router import router as assets_router
from src.modules.ui.common import (
    detect_lang as _detect_lang,
    render as _render,
    render_error as _error,
    template_context as _ctx,
    templates,
)
from src.modules.ui.core_router import router as core_router
from src.modules.ui.operations_router import router as operations_router
from src.modules.ui.projects_router import router as projects_router

router = APIRouter()
for child_router in (
    core_router,
    projects_router,
    assets_router,
    operations_router,
    admin_router,
):
    router.include_router(child_router)

__all__ = ["router"]
