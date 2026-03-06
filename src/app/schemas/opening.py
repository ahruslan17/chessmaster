from __future__ import annotations

from pydantic import BaseModel


class OpeningRead(BaseModel):
    eco_code: str
    name: str
    moves_san: list[str]
    move_count: int
