from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MoveAnalysisRead(BaseModel):
    """Schema for a single move analysis."""

    id: uuid.UUID
    move_number: int
    color: str
    move_san: str
    best_move_san: str | None = None
    eval_before: float | None = None
    eval_after: float | None = None
    centipawn_loss: float | None = None
    classification: str | None = None
    top_moves: Any | None = None
    continuation_lines: Any | None = None
    llm_comment: str | None = None

    model_config = {"from_attributes": True}


class GameAnalysisRead(BaseModel):
    """Schema for full game analysis with move details."""

    id: uuid.UUID
    game_id: uuid.UUID
    summary: str | None = None
    opening_assessment: str | None = None
    middlegame_assessment: str | None = None
    endgame_assessment: str | None = None
    key_moments: Any | None = None
    coach_feedback: Any | None = None
    accuracy_white: float | None = None
    accuracy_black: float | None = None
    status: str
    created_at: datetime
    moves: list[MoveAnalysisRead] = []

    model_config = {"from_attributes": True}


class AnalysisStatusRead(BaseModel):
    """Lightweight schema for analysis status polling."""

    game_id: uuid.UUID
    status: str
