from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class GameNoteUpdate(BaseModel):
    content: str | None = None


class GameNoteRead(BaseModel):
    id: uuid.UUID
    game_id: uuid.UUID
    content: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GameNoteListItem(BaseModel):
    game_id: uuid.UUID
    white_player: str
    black_player: str
    played_at: date | None = None
    opening_name: str | None = None
    content: str | None = None
    updated_at: datetime
