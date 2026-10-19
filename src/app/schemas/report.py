from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, SerializerFunctionWrapHandler, model_serializer

REPORT_CONTENT_VERSION = 2
_COMPARISON_KEYS = {
    "games", "previous_period_has_data", "blunder_moves", "mistake_moves",
    "inaccuracy_moves", "best_moves", "excellent_moves", "good_moves", "theory_moves",
}


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

    @model_serializer(mode="wrap")
    def suppress_legacy_coaching(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Do not expose old prose based on retired metrics or mutate stored reports."""
        data = handler(self)
        metrics = self.comparison_metrics if isinstance(self.comparison_metrics, dict) else {}
        if metrics.get("content_version") != REPORT_CONTENT_VERSION:
            for key in (
                "recommendations", "weakness_patterns", "strength_patterns",
                "coach_feedback", "comparison_summary",
            ):
                data[key] = None
        data["comparison_metrics"] = {
            key: value for key, value in metrics.items() if key in _COMPARISON_KEYS
        } or None
        return data
