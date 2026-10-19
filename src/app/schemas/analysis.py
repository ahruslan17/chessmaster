from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EngineScoreRead(BaseModel):
    """Stockfish evaluation from White's perspective, without mate sentinels."""

    cp: float | None = None
    mate: int | None = None
    mate_winner: Literal["white", "black"] | None = None
    perspective: Literal["white"] = "white"


class SideReviewRead(BaseModel):
    player_color: Literal["white", "black"]
    status: str
    error: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    comments: dict[str, dict[str, str]] = Field(default_factory=dict)
    summary: str | None = None
    recommendations: list[str] = Field(default_factory=list)
    attempt_id: uuid.UUID | None = None
    task_id: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    verification: str = "structure_checked"

    model_config = {"from_attributes": True}


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
    score_before: EngineScoreRead | None = None
    score_after: EngineScoreRead | None = None
    played_line: list[str] | None = None

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
    moves: list[MoveAnalysisRead] = Field(default_factory=list)
    engine_status: str = "pending"
    engine_error: str | None = None
    engine_attempt_id: uuid.UUID | None = None
    engine_result_id: uuid.UUID | None = None
    engine_task_id: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    heartbeat_at: datetime | None = None
    score_version: int | None = None
    review: SideReviewRead | None = None

    model_config = {"from_attributes": True}


class AnalysisStatusRead(BaseModel):
    """Lightweight schema for analysis status polling."""

    game_id: uuid.UUID
    status: str
    engine_status: str = "pending"
    engine_error: str | None = None
    engine_attempt_id: uuid.UUID | None = None
    engine_task_id: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    heartbeat_at: datetime | None = None
    review_status: str | None = None
    review_error: str | None = None


class EngineStartBody(BaseModel):
    recover: bool = False
    expected_attempt_id: uuid.UUID | None = None


class ExplanationStartBody(EngineStartBody):
    player_color: Literal["white", "black"]
