from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.access import AccessSession


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
    access_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    access_session: Mapped[AccessSession | None] = relationship(
        "AccessSession", back_populates="reports"
    )
