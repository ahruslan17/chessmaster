from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.core.dependencies import AsyncSessionDep, ReportServiceDep
from app.core.exceptions import ReportNotFoundError
from app.models.period_report import PeriodReport
from app.schemas.report import ReportCreate, ReportRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportRead, status_code=201)
async def create_report(
    body: ReportCreate,
    session: AsyncSessionDep,
    report_service: ReportServiceDep,
) -> ReportRead:
    """Generate a coaching report for a period."""
    if body.period_end < body.period_start:
        raise HTTPException(
            status_code=422,
            detail="Дата конца периода должна быть не раньше даты начала",
        )

    report = await report_service.generate_report(
        period_start=body.period_start,
        period_end=body.period_end,
        period_type=body.period_type,
    )
    await session.commit()

    logger.info(
        "Created report %s for %s to %s (%d games)",
        report.id,
        body.period_start,
        body.period_end,
        len(report.game_ids or []),
    )
    return report


@router.get("", response_model=list[ReportRead])
async def list_reports(
    session: AsyncSessionDep,
    period_type: str | None = Query(None, pattern="^(daily|weekly|monthly)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[ReportRead]:
    """List reports, optionally filtered by period type."""
    stmt = select(PeriodReport)
    if period_type is not None:
        stmt = stmt.where(PeriodReport.period_type == period_type)

    stmt = stmt.order_by(PeriodReport.created_at.desc()).offset(offset).limit(limit)
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


@router.get("/{report_id}", response_model=ReportRead)
async def get_report(
    report_id: uuid.UUID,
    session: AsyncSessionDep,
) -> ReportRead:
    """Get a previously generated report."""
    report = await session.get(PeriodReport, report_id)
    if report is None:
        raise ReportNotFoundError("Отчёт не найден")
    return report
