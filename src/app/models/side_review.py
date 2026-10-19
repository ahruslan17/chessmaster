from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.game_analysis import GameAnalysis


class SideReview(Base):
    """Educational context and explanations belonging to one selected side."""

    __tablename__ = "side_reviews"
    __table_args__ = (
        UniqueConstraint("game_analysis_id", "player_color", name="uq_side_review_analysis_color"),
        CheckConstraint("player_color IN ('white', 'black')", name="ck_side_review_color"),
        CheckConstraint(
            "status IN ('pending', 'queued', 'in_progress', 'done', 'partial', 'failed')",
            name="ck_side_review_status",
        ),
    )

    game_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_analyses.id", ondelete="CASCADE"), nullable=False
    )
    player_color: Mapped[str] = mapped_column(String(5), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    task_id: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSONB)
    comments: Mapped[dict | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[list | None] = mapped_column(JSONB)
    usage: Mapped[dict | None] = mapped_column(JSONB)
    stale_result: Mapped[dict | None] = mapped_column(JSONB)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    game_analysis: Mapped[GameAnalysis] = relationship(
        "GameAnalysis", back_populates="side_reviews"
    )
