from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.opening import OpeningRead
from app.services.opening_matcher import OpeningMatcher

router = APIRouter(prefix="/openings", tags=["openings"])

_opening_matcher = OpeningMatcher()


@router.get("", response_model=list[OpeningRead])
async def list_openings(
    q: str | None = Query(None, description="Search by ECO code or opening name"),
    limit: int = Query(5000, ge=1, le=10000),
) -> list[OpeningRead]:
    query = q.strip().lower() if q else None
    rows: list[OpeningRead] = []

    for index, (moves_san, eco_code, name) in enumerate(_opening_matcher.list_openings()):
        if query and query not in f"{eco_code} {name}".lower():
            continue
        rows.append(
            OpeningRead(
                id=f"{eco_code}-{index}",
                eco_code=eco_code,
                name=name,
                moves_san=moves_san,
                move_count=len(moves_san),
            )
        )
        if len(rows) >= limit:
            break

    return rows
