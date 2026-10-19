from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.access import ACCESS_COOKIE
from app.api.router import api_router
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.exceptions import (
    AnalysisNotFoundError,
    GameNotFoundError,
    PGNParseError,
    ReportNotFoundError,
)
from app.services.access import get_active_session
from app.services.llm_coach import LLMCoachError

logger = logging.getLogger(__name__)


def _register_exception_handlers(app: FastAPI) -> None:
    """Register handlers for custom and common exceptions."""

    @app.exception_handler(GameNotFoundError)
    @app.exception_handler(AnalysisNotFoundError)
    @app.exception_handler(ReportNotFoundError)
    async def handle_not_found(
        _request: Request, exc: GameNotFoundError | AnalysisNotFoundError | ReportNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": exc.message})

    @app.exception_handler(PGNParseError)
    async def handle_pgn_parse(_request: Request, exc: PGNParseError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.message})

    @app.exception_handler(LLMCoachError)
    async def handle_llm_error(_request: Request, exc: LLMCoachError) -> JSONResponse:
        logger.warning("LLM coach error: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "Сервис AI-комментариев временно недоступен"},
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    # Startup: nothing yet (DB engine is created at import time)
    yield
    # Shutdown: dispose engine to release connections
    from app.core.database import engine

    await engine.dispose()


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title="Chess Master",
        description="AI-powered chess coaching and game analysis",
        version="0.1.0",
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    _register_exception_handlers(app)

    @app.middleware("http")
    async def require_public_access(request: Request, call_next):
        access_enabled = getattr(settings, "access_control_enabled", False)
        if not access_enabled or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path in {
            "/api/health",
            "/api/access/activate",
            "/api/access/config",
            "/api/access/status",
        }:
            return await call_next(request)
        if request.url.path.startswith("/api/reports"):
            return JSONResponse(
                status_code=403,
                content={"detail": "Отчёты недоступны в гостевом режиме"},
            )
        async with async_session_factory() as session:
            access_session = await get_active_session(
                session, request.cookies.get(ACCESS_COOKIE)
            )
            if access_session is None:
                return JSONResponse(status_code=401, content={"detail": "Введите код доступа"})
            request.state.access_session_id = str(access_session.id)
            request.state.access_expires_at = access_session.expires_at
        return await call_next(request)
    return app


app = create_app()
