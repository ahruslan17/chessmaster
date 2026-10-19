from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select

from app.api.analysis_queue import publish_attempt
from app.core.config import settings
from app.core.dependencies import AccessSessionIdDep, AsyncSessionDep
from app.core.exceptions import GameNotFoundError, PGNParseError
from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.models.game_note import GameNote
from app.schemas.game import GameListItem, GameRead, PgnImportBody
from app.schemas.note import GameNoteListItem, GameNoteRead, GameNoteUpdate
from app.services.game_review import GameReviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])

_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
def _public_access_enabled() -> bool:
    """Keep older focused tests compatible with the new optional public gate."""
    return bool(getattr(settings, "access_control_enabled", False))


@router.post("/upload", response_model=list[GameRead], status_code=201)
async def upload_pgn(
    file: UploadFile,
    session: AsyncSessionDep,
    player_color: str | None = Query(None, pattern="^(white|black)$"),
    form_player_color: str | None = Form(None, alias="player_color", pattern="^(white|black)$"),
    access_session_id: AccessSessionIdDep = None,
) -> list[GameRead]:
    """Upload a PGN file containing one or more games."""
    raw = await file.read(_MAX_UPLOAD_SIZE + 1)
    if len(raw) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Размер файла превышает лимит 10 МБ")

    try:
        pgn_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # PGN files sometimes use Latin-1 encoding.
        pgn_text = raw.decode("latin-1")

    if not pgn_text.strip():
        raise HTTPException(status_code=400, detail="Загруженный файл пуст")

    if player_color and form_player_color and player_color != form_player_color:
        raise HTTPException(
            status_code=422, detail="Цвет в форме и параметрах запроса не совпадает",
        )
    player_color = player_color or form_player_color
    await _enforce_public_import_limit(session, access_session_id)
    service = GameReviewService(session)
    games, new_game_ids = await service.create_games_from_pgn(
        pgn_text,
        player_color=player_color,
        access_session_id=access_session_id,
        max_new_games=(
            settings.public_max_games_per_session if _public_access_enabled() else None
        ),
    )

    if not games:
        raise PGNParseError("В PGN-файле не найдено корректных партий")

    try:
        await _enforce_public_engine_capacity(session, new_game_ids)
    except HTTPException:
        await session.rollback()
        raise
    await _queue_imported_games(session, service, new_game_ids)

    logger.info("Uploaded %d game(s), analysis queued for %d new", len(games), len(new_game_ids))
    return games


@router.post("/import", response_model=list[GameRead], status_code=201)
async def import_pgn_text(
    body: PgnImportBody,
    session: AsyncSessionDep,
    access_session_id: AccessSessionIdDep = None,
) -> list[GameRead]:
    """Import PGN from pasted text."""
    pgn_text = body.pgn_text.strip()
    if not pgn_text:
        raise HTTPException(status_code=400, detail="Текст PGN пуст")

    if len(pgn_text.encode("utf-8")) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Размер текста PGN превышает лимит 10 МБ")

    player_color = body.player_color if body.player_color in ("white", "black") else None
    await _enforce_public_import_limit(session, access_session_id)
    service = GameReviewService(session)
    games, new_game_ids = await service.create_games_from_pgn(
        pgn_text,
        player_color=player_color,
        access_session_id=access_session_id,
        max_new_games=(
            settings.public_max_games_per_session if _public_access_enabled() else None
        ),
    )

    if not games:
        raise PGNParseError("В тексте PGN не найдено корректных партий")

    try:
        await _enforce_public_engine_capacity(session, new_game_ids)
    except HTTPException:
        await session.rollback()
        raise
    await _queue_imported_games(session, service, new_game_ids)

    logger.info(
        "Imported %d game(s) from text, analysis queued for %d new",
        len(games),
        len(new_game_ids),
    )
    return games


async def _queue_imported_games(
    session: AsyncSessionDep,
    service: GameReviewService,
    game_ids: list[uuid.UUID],
) -> None:
    attempts = []
    for game_id in game_ids:
        analysis, queued = await service.queue_engine(game_id)
        if queued:
            attempts.append((
                game_id, analysis.id, analysis.engine_attempt_id, analysis.engine_task_id,
            ))
    await session.commit()
    failed_ids = []
    for game_id, entity_id, attempt_id, task_id in attempts:
        published = await publish_attempt(
            session, stage="engine", entity_id=entity_id, game_id=game_id,
            attempt_id=attempt_id, task_id=task_id,
        )
        if not published:
            failed_ids.append(str(game_id))
    if failed_ids:
        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    "Партии сохранены, но отправка части анализов не подтверждена. "
                    "Откройте библиотеку и проверьте состояния."
                ),
                "game_id": failed_ids[0], "game_ids": failed_ids,
            },
        )


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
    access_session_id: AccessSessionIdDep = None,
) -> list[GameListItem]:
    """List all games with optional filters."""
    stmt = select(Game)
    if _public_access_enabled():
        stmt = stmt.where(Game.access_session_id == access_session_id)

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
    access_session_id: AccessSessionIdDep = None,
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
    if _public_access_enabled():
        stmt = stmt.where(Game.access_session_id == access_session_id)
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
    access_session_id: AccessSessionIdDep = None,
) -> GameNoteRead:
    """Get a game note and create an empty placeholder if it does not exist."""
    game = await _get_game(session, game_id, access_session_id)
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
    access_session_id: AccessSessionIdDep = None,
) -> GameNoteRead:
    """Create or update the player note for a game."""
    game = await _get_game(session, game_id, access_session_id)
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
    access_session_id: AccessSessionIdDep = None,
) -> GameRead:
    """Get a single game by ID."""
    game = await _get_game(session, game_id, access_session_id)
    if game is None:
        raise GameNotFoundError("Партия не найдена")
    return game


async def _get_game(
    session: AsyncSessionDep,
    game_id: uuid.UUID,
    access_session_id: uuid.UUID | None,
) -> Game | None:
    if not _public_access_enabled():
        return await session.get(Game, game_id)
    return await session.scalar(
        select(Game).where(Game.id == game_id, Game.access_session_id == access_session_id)
    )


async def _enforce_public_import_limit(
    session: AsyncSessionDep,
    access_session_id: uuid.UUID | None,
) -> None:
    if not _public_access_enabled():
        return
    count = await session.scalar(
        select(func.count()).select_from(Game).where(Game.access_session_id == access_session_id)
    )
    if count and count >= settings.public_max_games_per_session:
        raise HTTPException(
            status_code=429,
            detail="Эта гостевая сессия уже использовала доступный анализ",
        )


async def _enforce_public_engine_capacity(
    session: AsyncSessionDep,
    game_ids: list[uuid.UUID],
) -> None:
    if not _public_access_enabled() or not game_ids:
        return
    active_count = await session.scalar(
        select(func.count()).select_from(GameAnalysis).where(
            GameAnalysis.engine_status.in_(("queued", "in_progress"))
        )
    )
    if active_count and active_count >= settings.public_max_active_engine_jobs:
        raise HTTPException(
            status_code=429,
            detail="Сейчас выполняется анализ. Дождитесь его завершения и попробуйте позже.",
        )
