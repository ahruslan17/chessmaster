from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.access import AccessSession
    from app.models.game_analysis import GameAnalysis
    from app.models.game_note import GameNote


class Game(Base):
    """A single chess game imported from PGN."""

    __tablename__ = "games"

    pgn_text: Mapped[str] = mapped_column(Text, nullable=False)
    moves_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    white_player: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    black_player: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    result: Mapped[str] = mapped_column(String(10), nullable=False, default="*")
    opening_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eco_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    time_control: Mapped[str | None] = mapped_column(String(50), nullable=True)
    played_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    player_color: Mapped[str | None] = mapped_column(String(5), nullable=True)
    access_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Relationships
    analysis: Mapped[GameAnalysis | None] = relationship(
        "GameAnalysis", back_populates="game", uselist=False, cascade="all, delete-orphan"
    )
    note: Mapped[GameNote | None] = relationship(
        "GameNote", back_populates="game", uselist=False, cascade="all, delete-orphan"
    )
    access_session: Mapped[AccessSession | None] = relationship(
        "AccessSession", back_populates="games"
    )
