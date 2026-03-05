from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.dependencies import AsyncSessionDep, LLMCoachDep
from app.core.exceptions import AnalysisNotFoundError, GameNotFoundError
from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.schemas.analysis import AnalysisStatusRead, GameAnalysisRead
from app.services.llm_coach import MoveCommentaryInput
from app.services.pgn_parser import PGNParserService
from app.utils.chess_helpers import moves_to_fens

router = APIRouter(prefix="/games/{game_id}/analysis", tags=["analysis"])
logger = logging.getLogger(__name__)
_NEXT_GAME_MOVES_CONTEXT = 10


@router.get("", response_model=GameAnalysisRead)
async def get_game_analysis(
    game_id: uuid.UUID,
    session: AsyncSessionDep,
) -> GameAnalysisRead:
    """Get full analysis with per-move commentary for a game.

    Returns the game-level summary alongside all per-move evaluations
    ordered by move number (white before black within each move).
    """
    # Verify the game exists
    game = await session.get(Game, game_id)
    if game is None:
        raise GameNotFoundError("Game not found")

    stmt = (
        select(GameAnalysis)
        .where(GameAnalysis.game_id == game_id)
        .options(selectinload(GameAnalysis.moves))
    )
    result = await session.execute(stmt)
    analysis = result.scalar_one_or_none()

    if analysis is None:
        raise AnalysisNotFoundError("Analysis not found for this game")

    # Sort moves: by move_number ascending, white before black
    analysis.moves.sort(key=lambda m: (m.move_number, m.color != "white"))
    return analysis


@router.get("/moves/{move_index}/commentary/stream")
async def stream_move_commentary(
    game_id: uuid.UUID,
    move_index: int,
    session: AsyncSessionDep,
    llm_coach: LLMCoachDep,
) -> StreamingResponse:
    """Stream LLM commentary for a single move via Server-Sent Events.

    Returns text chunks as they are generated. Each SSE event has
    ``data: <chunk>``. Use when move has no pre-generated commentary
    or for real-time display.
    """
    if move_index < 0:
        raise AnalysisNotFoundError("Move index must be non-negative")

    game = await session.get(Game, game_id)
    if game is None:
        raise GameNotFoundError("Game not found")

    stmt = (
        select(GameAnalysis)
        .where(GameAnalysis.game_id == game_id)
        .options(selectinload(GameAnalysis.moves))
    )
    result = await session.execute(stmt)
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise AnalysisNotFoundError("Analysis not found for this game")

    # Sort moves to match frontend order
    moves_sorted = sorted(analysis.moves, key=lambda m: (m.move_number, m.color != "white"))
    if move_index >= len(moves_sorted):
        raise AnalysisNotFoundError("Move index out of range")

    move_record = moves_sorted[move_index]
    if move_record.llm_comment:
        # Already have commentary - stream as single SSE event
        comment = move_record.llm_comment or ""

        async def _already_done() -> object:
            for line in comment.split("\n"):
                yield f"data: {line}\n"
            yield "\n"

        return StreamingResponse(
            _already_done(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Build MoveCommentaryInput: need FEN from game replay
    parser = PGNParserService()
    parsed = parser.parse_pgn(game.pgn_text)
    if not parsed:
        raise AnalysisNotFoundError("Could not parse game PGN for commentary")
    fens = moves_to_fens(parsed[0].moves)
    fen_before = fens[move_index] if move_index < len(fens) else ""

    move_input = MoveCommentaryInput(
        move_index=move_index,
        move_number=move_record.move_number,
        color=move_record.color,
        fen_before=fen_before,
        move_san=move_record.move_san or "",
        best_move_san=move_record.best_move_san or "",
        eval_before=move_record.eval_before or 0.0,
        eval_after=move_record.eval_after or 0.0,
        centipawn_loss=move_record.centipawn_loss or 0.0,
        classification=move_record.classification or "good",
        top_moves=(move_record.top_moves or []) if isinstance(move_record.top_moves, list) else [],
        next_game_moves=[
            _format_move_label(m.move_number, m.color, m.move_san or "?")
            for m in moves_sorted[move_index + 1 : move_index + 1 + _NEXT_GAME_MOVES_CONTEXT]
        ],
    )

    async def _stream() -> object:
        chunks: list[str] = []
        async for chunk in llm_coach.generate_single_move_commentary_stream(move_input):
            chunks.append(chunk)
            for line in chunk.split("\n"):
                yield f"data: {line}\n"
            yield "\n"

        # Cache generated commentary to avoid repeated LLM calls for the same move.
        comment = "".join(chunks).strip()
        if comment:
            move_record.llm_comment = comment
            try:
                await session.commit()
            except Exception:
                logger.exception("Failed to persist streamed commentary for game %s", game_id)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status", response_model=AnalysisStatusRead)
async def get_analysis_status(
    game_id: uuid.UUID,
    session: AsyncSessionDep,
) -> AnalysisStatusRead:
    """Check analysis status (pending / in_progress / done / failed).

    Returns ``"pending"`` when no analysis record exists yet (the game
    has been uploaded but the Celery task has not started).
    """
    stmt = select(GameAnalysis.status).where(GameAnalysis.game_id == game_id)
    result = await session.execute(stmt)
    status = result.scalar_one_or_none()

    if status is None:
        return AnalysisStatusRead(game_id=game_id, status="pending")

    return AnalysisStatusRead(game_id=game_id, status=status)


def _format_move_label(move_number: int, color: str, move_san: str) -> str:
    color_sep = "." if color == "white" else "..."
    return f"{move_number}{color_sep}{move_san}"
