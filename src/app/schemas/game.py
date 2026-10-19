from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class GameBase(BaseModel):
    """Shared fields for game schemas."""

    white_player: str = ""
    black_player: str = ""
    result: str = "*"
    opening_name: str | None = None
    eco_code: str | None = None
    time_control: str | None = None
    played_at: date | None = None
    player_color: str | None = None


class GameCreate(BaseModel):
    """Schema for creating a game (PGN upload)."""

    pgn_text: str


class PgnImportBody(BaseModel):
    """Schema for pasting PGN text (no file upload)."""

    pgn_text: str
    player_color: Literal["white", "black"] | None = None


class GameRead(GameBase):
    """Schema for reading a game from the API."""

    id: uuid.UUID
    pgn_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class GameListItem(GameBase):
    """Schema for game list (without full PGN text)."""

    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
