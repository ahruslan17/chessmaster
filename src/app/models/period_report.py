from __future__ import annotations

from datetime import date

from sqlalchemy import Date, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PeriodReport(Base):
    """Aggregated coaching report for a time period."""

    __tablename__ = "period_reports"

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    weakness_patterns: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    strength_patterns: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    coach_feedback: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    comparison_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    comparison_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    game_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
