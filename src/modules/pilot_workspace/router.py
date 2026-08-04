"""Composition root for the unified pilot workspace UI."""

from fastapi import APIRouter

from src.modules.pilot_workspace.intake_router import router as intake_router
from src.modules.pilot_workspace.overview_router import router as overview_router
from src.modules.pilot_workspace.quality_router import router as quality_router
from src.modules.pilot_workspace.table_router import router as table_router

router = APIRouter()
for child_router in (
    overview_router,
    intake_router,
    table_router,
    quality_router,
):
    router.include_router(child_router)

__all__ = ["router"]
