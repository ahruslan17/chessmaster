from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.services.llm_coach import LLMCoachService
from app.services.report import ReportService

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]


def get_access_session_id(request: Request) -> uuid.UUID | None:
    """Return the public browser scope that access middleware has verified."""
    raw_session_id = getattr(request.state, "access_session_id", None)
    if raw_session_id is None:
        return None
    try:
        return uuid.UUID(raw_session_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Сессия доступа недействительна") from exc


AccessSessionIdDep = Annotated[uuid.UUID | None, Depends(get_access_session_id)]


def get_llm_coach() -> LLMCoachService:
    """Provide LLMCoachService for streaming and generation."""
    return LLMCoachService()


LLMCoachDep = Annotated[LLMCoachService, Depends(get_llm_coach)]


def get_report_service(session: AsyncSessionDep) -> ReportService:
    """Provide ReportService with the current DB session."""
    return ReportService(session)


ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Alias for get_async_session — used in route dependencies."""
    async for session in get_async_session():
        yield session
