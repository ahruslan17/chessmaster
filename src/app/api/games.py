from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Query, UploadFile
from sqlalchemy import select

from app.core.dependencies import AsyncSessionDep
from app.core.exceptions import GameNotFoundError, PGNParseError
from app.models.game import Game
from app.models.game_note import GameNote
from app.schemas.game import GameListItem, GameRead, PgnImportBody
from app.schemas.note import GameNoteListItem, GameNoteRead, GameNoteUpdate
from app.services.game_review import GameReviewService
from app.tasks.analysis import analyze_game_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])

_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=list[GameRead], status_code=201)
async def upload_pgn(
    file: UploadFile,
    session: AsyncSessionDep,
    player_color: str | None = Query(None, pattern="^(white|black)$"),
) -> list[GameRead]:
    """Upload a PGN file containing one or more games."""
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Размер файла превышает лимит 10 МБ")

    try:
        pgn_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # PGN files sometimes use Latin-1 encoding.
        pgn_text = raw.decode("latin-1")

    if not pgn_text.strip():
        raise HTTPException(status_code=400, detail="Загруженный файл пуст")

    service = GameReviewService(session)
    games, new_game_ids = await service.create_games_from_pgn(
        pgn_text, player_color=player_color
    )

    if not games:
        raise PGNParseError("В PGN-файле не найдено корректных партий")

    await session.commit()

    # Queue analysis only for newly created games (not duplicates).
    for game_id in new_game_ids:
        analyze_game_task.delay(str(game_id))

    logger.info("Uploaded %d game(s), analysis queued for %d new", len(games), len(new_game_ids))
    return games


@router.post("/import", response_model=list[GameRead], status_code=201)
async def import_pgn_text(
    body: PgnImportBody,
    session: AsyncSessionDep,
) -> list[GameRead]:
    """Import PGN from pasted text."""
    pgn_text = body.pgn_text.strip()
    if not pgn_text:
        raise HTTPException(status_code=400, detail="Текст PGN пуст")

    if len(pgn_text.encode("utf-8")) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Размер текста PGN превышает лимит 10 МБ")

    player_color = body.player_color if body.player_color in ("white", "black") else None
    service = GameReviewService(session)
    games, new_game_ids = await service.create_games_from_pgn(
        pgn_text, player_color=player_color
    )

    if not games:
        raise PGNParseError("В тексте PGN не найдено корректных партий")

    await session.commit()
    for game_id in new_game_ids:
        analyze_game_task.delay(str(game_id))

    logger.info(
        "Imported %d game(s) from text, analysis queued for %d new",
        len(games),
        len(new_game_ids),
    )
    return games


@router.get("", response_model=list[GameListItem])
async def list_games(
    session: AsyncSessionDep,
    result: str | None = None,
    opening_name: str | None = None,
    eco_code: str | None = None,
    played_after: date | None = None,
    played_before: date | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[GameListItem]:
    """List all games with optional filters."""
    stmt = select(Game)

    if result is not None:
        stmt = stmt.where(Game.result == result)
    if opening_name is not None:
        stmt = stmt.where(Game.opening_name.ilike(f"%{opening_name}%"))
    if eco_code is not None:
        stmt = stmt.where(Game.eco_code == eco_code)
    if played_after is not None:
        stmt = stmt.where(Game.played_at >= played_after)
    if played_before is not None:
        stmt = stmt.where(Game.played_at <= played_before)

    stmt = stmt.order_by(Game.created_at.desc()).offset(offset).limit(limit)
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


@router.get("/notes", response_model=list[GameNoteListItem])
async def list_game_notes(
    session: AsyncSessionDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[GameNoteListItem]:
    """List non-empty game notes ordered by update time."""
    stmt = (
        select(GameNote, Game)
        .join(Game, Game.id == GameNote.game_id)
        .where(GameNote.content.is_not(None))
        .order_by(GameNote.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = await session.execute(stmt)

    items: list[GameNoteListItem] = []
    for note, game in rows.all():
        content = (note.content or "").strip()
        if not content:
            continue
        items.append(
            GameNoteListItem(
                game_id=game.id,
                white_player=game.white_player,
                black_player=game.black_player,
                played_at=game.played_at,
                opening_name=game.opening_name,
                content=content,
                updated_at=note.updated_at,
            )
        )
    return items


@router.get("/{game_id}/note", response_model=GameNoteRead)
async def get_game_note(
    game_id: uuid.UUID,
    session: AsyncSessionDep,
) -> GameNoteRead:
    """Get a game note and create an empty placeholder if it does not exist."""
    game = await session.get(Game, game_id)
    if game is None:
        raise GameNotFoundError("Партия не найдена")

    stmt = select(GameNote).where(GameNote.game_id == game_id)
    result = await session.execute(stmt)
    note = result.scalar_one_or_none()

    if note is None:
        note = GameNote(game_id=game_id, content=None)
        session.add(note)
        await session.commit()
        await session.refresh(note)

    return note


@router.put("/{game_id}/note", response_model=GameNoteRead)
async def upsert_game_note(
    game_id: uuid.UUID,
    body: GameNoteUpdate,
    session: AsyncSessionDep,
) -> GameNoteRead:
    """Create or update the player note for a game."""
    game = await session.get(Game, game_id)
    if game is None:
        raise GameNotFoundError("Партия не найдена")

    stmt = select(GameNote).where(GameNote.game_id == game_id)
    result = await session.execute(stmt)
    note = result.scalar_one_or_none()

    if note is None:
        note = GameNote(game_id=game_id)
        session.add(note)

    content = (body.content or "").strip()
    note.content = content or None
    await session.commit()
    await session.refresh(note)
    return note


@router.get("/{game_id}", response_model=GameRead)
async def get_game(
    game_id: uuid.UUID,
    session: AsyncSessionDep,
) -> GameRead:
    """Get a single game by ID."""
    game = await session.get(Game, game_id)
    if game is None:
        raise GameNotFoundError("Партия не найдена")
    return game
