from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportCreate(BaseModel):
    """Schema for requesting a period report."""

    period_start: date
    period_end: date
    period_type: str = Field(pattern="^(daily|weekly|monthly)$")


class ReportRead(BaseModel):
    """Schema for reading a period report."""

    id: uuid.UUID
    period_start: date
    period_end: date
    period_type: str
    recommendations: str | None = None
    weakness_patterns: Any | None = None
    strength_patterns: Any | None = None
    coach_feedback: Any | None = None
    comparison_metrics: Any | None = None
    comparison_summary: str | None = None
    game_ids: Any | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
