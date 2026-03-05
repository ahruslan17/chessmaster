from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.services.llm_coach import LLMCoachService
from app.services.report import ReportService

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]


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
