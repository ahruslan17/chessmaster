from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.game import Game
    from app.models.period_report import PeriodReport


class AccessCode(Base):
    """A server-generated, single-use code for a short public session."""

    __tablename__ = "access_codes"

    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[AccessSession | None] = relationship(
        "AccessSession", back_populates="code", uselist=False, cascade="all, delete-orphan"
    )


class AccessSession(Base):
    """A browser session created by redeeming one access code."""

    __tablename__ = "access_sessions"

    access_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("access_codes.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    code: Mapped[AccessCode] = relationship("AccessCode", back_populates="session")
    games: Mapped[list[Game]] = relationship("Game", back_populates="access_session")
    reports: Mapped[list[PeriodReport]] = relationship(
        "PeriodReport", back_populates="access_session"
    )
