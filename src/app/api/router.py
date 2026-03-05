from __future__ import annotations

from fastapi import APIRouter

from app.api.analysis import router as analysis_router
from app.api.games import router as games_router
from app.api.health import router as health_router
from app.api.reports import router as reports_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(games_router)
api_router.include_router(analysis_router)
api_router.include_router(reports_router)
