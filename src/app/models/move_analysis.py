from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.game_analysis import GameAnalysis


class MoveAnalysis(Base):
    """Per-move Stockfish evaluation and LLM commentary."""

    __tablename__ = "move_analyses"

    game_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("game_analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    move_number: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(5), nullable=False)
    move_san: Mapped[str] = mapped_column(String(10), nullable=False)
    best_move_san: Mapped[str | None] = mapped_column(String(10), nullable=True)
    eval_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    eval_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    centipawn_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    top_moves: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    continuation_lines: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    llm_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    game_analysis: Mapped[GameAnalysis] = relationship("GameAnalysis", back_populates="moves")
