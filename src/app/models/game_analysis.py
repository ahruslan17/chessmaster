from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.game import Game
    from app.models.move_analysis import MoveAnalysis
    from app.models.side_review import SideReview


class GameAnalysis(Base):
    """Summary-level analysis for a game (produced by Stockfish + LLM)."""

    __tablename__ = "game_analyses"

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    middlegame_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    endgame_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_moments: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    coach_feedback: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    accuracy_white: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_black: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    engine_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    engine_attempt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    engine_result_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    engine_task_id: Mapped[str | None] = mapped_column(String(255))
    engine_error: Mapped[str | None] = mapped_column(Text)
    progress_current: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    progress_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_version: Mapped[int | None] = mapped_column(Integer)
    engine_metadata: Mapped[dict | None] = mapped_column(JSONB)

    # Relationships
    game: Mapped[Game] = relationship("Game", back_populates="analysis")
    moves: Mapped[list[MoveAnalysis]] = relationship(
        "MoveAnalysis", back_populates="game_analysis", cascade="all, delete-orphan"
    )
    side_reviews: Mapped[list[SideReview]] = relationship(
        "SideReview", back_populates="game_analysis", cascade="all, delete-orphan"
    )
