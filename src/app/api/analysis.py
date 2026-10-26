from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import BigInteger, func, literal, select
from sqlalchemy.orm import selectinload

from app.api.analysis_queue import publish_attempt
from app.core.config import settings
from app.core.dependencies import AccessSessionIdDep, AsyncSessionDep
from app.core.exceptions import AnalysisNotFoundError, GameNotFoundError
from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.models.side_review import SideReview
from app.schemas.analysis import (
    AnalysisStatusRead,
    EngineStartBody,
    ExplanationStartBody,
    GameAnalysisRead,
    MoveAnalysisRead,
    SideReviewRead,
)
from app.services.game_review import GameReviewService
from app.services.opening_matcher import OpeningMatcher
from app.services.pgn_parser import PGNParserService

router = APIRouter(prefix="/games/{game_id}/analysis", tags=["analysis"])
PlayerColor = Literal["white", "black"]
_PUBLIC_ENGINE_CAPACITY_LOCK = 7_034_992_011


def _public_access_enabled() -> bool:
    """Keep older focused tests compatible with the new optional public gate."""
    return bool(getattr(settings, "access_control_enabled", False))


async def _get_analysis(
    game_id: uuid.UUID,
    session: AsyncSessionDep,
    access_session_id: uuid.UUID | None,
) -> tuple[Game, GameAnalysis]:
    if _public_access_enabled():
        game = await session.scalar(
            select(Game).where(Game.id == game_id, Game.access_session_id == access_session_id)
        )
    else:
        game = await session.get(Game, game_id)
    if game is None:
        raise GameNotFoundError("Партия не найдена")
    result = await session.execute(
        select(GameAnalysis).where(GameAnalysis.game_id == game_id)
        .options(selectinload(GameAnalysis.moves))
        .with_for_update(read=True)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise AnalysisNotFoundError("Анализ для этой партии не найден")
    return game, analysis


async def _get_review(
    session: AsyncSessionDep, analysis_id: uuid.UUID, player_color: str | None,
) -> SideReview | None:
    if player_color not in ("white", "black"):
        return None
    result = await session.execute(
        select(SideReview).where(
            SideReview.game_analysis_id == analysis_id,
            (SideReview.player_color == player_color)
            | (SideReview.context["commentary_scope"].astext == "all_moves"),
        ).order_by(
            (SideReview.context["commentary_scope"].astext == "all_moves").desc().nulls_last(),
            (SideReview.player_color == player_color).desc(),
        ).limit(1)
    )
    review = result.scalar_one_or_none()
    return review if isinstance(review, SideReview) else None


def _comment_text(comment: dict[str, str] | None) -> str | None:
    if not comment:
        return None
    if comment.get("text"):
        return comment["text"]
    return "\n".join(comment.get(key, "") for key in (
        "reason", "consequence", "alternative", "principle", "limitation",
    ) if comment.get(key)) or None


@router.get("", response_model=GameAnalysisRead)
async def get_game_analysis(
    game_id: uuid.UUID,
    session: AsyncSessionDep,
    player_color: PlayerColor | None = None,
    access_session_id: AccessSessionIdDep = None,
) -> GameAnalysisRead:
    """Read saved full-game commentary and selected-side educational highlights."""
    game, analysis = await _get_analysis(game_id, session, access_session_id)
    review = await _get_review(session, analysis.id, player_color or game.player_color)
    verified = analysis.score_version == 1
    if review is not None and (
        not verified
        or not isinstance(review.context, dict)
        or review.context.get("version") != 1
        or review.context.get("player_color") != review.player_color
        or review.context.get("engine_result_id") != str(analysis.engine_result_id)
    ):
        review = None
    comments = (review.comments or {}) if verified and review is not None else {}
    review_context = dict(review.context or {}) if review else {}
    selected_color = player_color or game.player_color
    if review_context.get("commentary_scope") == "all_moves":
        review_context.pop("moves", None)  # Internal engine evidence is not a viewer payload.
        highlights = review_context.pop("moments_by_color", {})
        review_context["player_color"] = selected_color
        review_context["moments"] = highlights.get(selected_color, [])
    parsed_games = PGNParserService().parse_pgn(game.pgn_text)
    opening = OpeningMatcher().match(parsed_games[0].moves) if parsed_games else None
    opening_move_count = opening.move_count if opening else 0
    moves = []
    ordered_moves = sorted(analysis.moves, key=lambda m: (m.move_number, m.color != "white"))
    for index, record in enumerate(ordered_moves):
        move = MoveAnalysisRead.model_validate(record)
        move.is_theory = index < opening_move_count
        move.llm_comment = _comment_text(comments.get(str(index)))
        if not verified:
            move.score_before = None
            move.score_after = None
            move.classification = None
            move.eval_before = None
            move.eval_after = None
            move.centipawn_loss = None
            move.top_moves = None
            move.continuation_lines = None
            move.played_line = None
            move.best_move_san = None
        else:
            move.eval_before = move.score_before.cp if move.score_before else None
            move.eval_after = move.score_after.cp if move.score_after else None
        moves.append(move)
    return GameAnalysisRead(
        id=analysis.id, game_id=game_id, created_at=analysis.created_at,
        status=analysis.status, moves=moves,
        summary=review.summary if verified and review else None,
        key_moments=review_context.get("moments", []) if verified and review else [],
        coach_feedback=(
            {"focus_points": review.recommendations or []} if verified and review else None
        ),
        accuracy_white=None, accuracy_black=None,
        engine_status=analysis.engine_status or analysis.status,
        engine_error=analysis.engine_error,
        engine_attempt_id=analysis.engine_attempt_id, engine_result_id=analysis.engine_result_id,
        engine_task_id=analysis.engine_task_id,
        progress_current=analysis.progress_current or 0,
        progress_total=analysis.progress_total or 0,
        heartbeat_at=analysis.heartbeat_at, score_version=analysis.score_version,
        review=SideReviewRead(
            player_color=selected_color, owner_color=review.player_color,
            status=review.status, error=review.error,
            context=review_context, comments=review.comments or {}, summary=review.summary,
            recommendations=review.recommendations or [], attempt_id=review.attempt_id,
            task_id=review.task_id, usage=review.usage or {},
        ) if verified and review else None,
    )


@router.get("/moves/{move_index}/commentary/stream")
async def stream_move_commentary(
    game_id: uuid.UUID,
    move_index: int,
    session: AsyncSessionDep,
    player_color: PlayerColor | None = None,
    access_session_id: AccessSessionIdDep = None,
) -> StreamingResponse:
    """Read saved text only. Missing text never starts a provider request."""
    if move_index < 0:
        raise AnalysisNotFoundError("Индекс хода не может быть отрицательным")
    analysis = await get_game_analysis(game_id, session, player_color, access_session_id)
    if move_index >= len(analysis.moves):
        raise AnalysisNotFoundError("Индекс хода вне диапазона")
    comment = analysis.moves[move_index].llm_comment
    if not comment:
        raise AnalysisNotFoundError("Сохранённого объяснения нет. Запустите генерацию явно.")

    async def saved_text() -> AsyncIterator[str]:
        for line in comment.split("\n"):
            yield f"data: {line}\n"
        yield "\n"

    return StreamingResponse(saved_text(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


@router.get("/status", response_model=AnalysisStatusRead)
async def get_analysis_status(
    game_id: uuid.UUID,
    session: AsyncSessionDep,
    player_color: PlayerColor | None = None,
    access_session_id: AccessSessionIdDep = None,
) -> AnalysisStatusRead:
    if _public_access_enabled():
        game = await session.scalar(
            select(Game).where(Game.id == game_id, Game.access_session_id == access_session_id)
        )
    else:
        game = await session.get(Game, game_id)
    if game is None:
        raise GameNotFoundError("Партия не найдена")
    result = await session.execute(
        select(GameAnalysis).where(GameAnalysis.game_id == game_id).with_for_update(read=True)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        return AnalysisStatusRead(game_id=game_id, status="pending")
    review = await _get_review(session, analysis.id, player_color or game.player_color)
    if review is not None and (
        analysis.score_version != 1
        or not isinstance(review.context, dict)
        or review.context.get("version") != 1
        or review.context.get("player_color") != review.player_color
        or review.context.get("engine_result_id") != str(analysis.engine_result_id)
    ):
        review = None
    response = AnalysisStatusRead(
        game_id=game_id, status=analysis.status,
        engine_status=analysis.engine_status or analysis.status,
        engine_error=analysis.engine_error,
        engine_attempt_id=analysis.engine_attempt_id, engine_task_id=analysis.engine_task_id,
        progress_current=analysis.progress_current or 0,
        progress_total=analysis.progress_total or 0,
        heartbeat_at=analysis.heartbeat_at,
        review_status=review.status if review else None,
        review_error=review.error if review else None,
    )
    return response


@router.post("/start", response_model=AnalysisStatusRead)
async def start_engine_analysis(
    game_id: uuid.UUID,
    body: EngineStartBody,
    session: AsyncSessionDep,
    access_session_id: AccessSessionIdDep = None,
) -> AnalysisStatusRead:
    if _public_access_enabled():
        game, analysis = await _get_analysis(game_id, session, access_session_id)
        if analysis.engine_status in {"queued", "in_progress"} or (
            analysis.engine_status == "done" and analysis.score_version == 1
        ):
            return AnalysisStatusRead(
                game_id=game_id,
                status=analysis.status,
                engine_status=analysis.engine_status,
            )
        await session.execute(
            select(
                func.pg_advisory_xact_lock(
                    literal(_PUBLIC_ENGINE_CAPACITY_LOCK, type_=BigInteger)
                )
            )
        )
        active_count = await session.scalar(
            select(func.count()).select_from(GameAnalysis).where(
                GameAnalysis.game_id != game.id,
                GameAnalysis.engine_status.in_(("queued", "in_progress")),
            )
        )
        if active_count and active_count >= settings.public_max_active_engine_jobs:
            await session.rollback()
            raise HTTPException(
                status_code=429,
                detail="Сейчас выполняется анализ. Дождитесь его завершения и попробуйте позже.",
            )
    analysis, queued = await GameReviewService(session).queue_engine(
        game_id, recover=body.recover, expected_attempt_id=body.expected_attempt_id,
    )
    await session.commit()
    if queued:
        published = await publish_attempt(
            session, stage="engine", entity_id=analysis.id, game_id=game_id,
            attempt_id=analysis.engine_attempt_id, task_id=analysis.engine_task_id,
        )
        if not published:
            raise HTTPException(
                status_code=503, detail="Очередь недоступна. Повторите запуск анализа.",
            )
    return AnalysisStatusRead(
        game_id=game_id, status=analysis.status, engine_status=analysis.engine_status,
    )


@router.post("/explanations", response_model=AnalysisStatusRead)
async def start_explanations(
    game_id: uuid.UUID,
    body: ExplanationStartBody,
    session: AsyncSessionDep,
    access_session_id: AccessSessionIdDep = None,
) -> AnalysisStatusRead:
    if _public_access_enabled() or await session.get(Game, game_id) is None:
        await _get_analysis(game_id, session, access_session_id)
    if not (settings.llm_api_key or settings.litellm_base_url):
        raise HTTPException(
            status_code=503, detail="AI-тренер не настроен. Данные движка сохранены.",
        )
    review, queued = await GameReviewService(session).queue_explanations(
        game_id, body.player_color, recover=body.recover,
        expected_attempt_id=body.expected_attempt_id,
    )
    await session.commit()
    if queued:
        published = await publish_attempt(
            session, stage="coach", entity_id=review.id, game_id=game_id,
            attempt_id=review.attempt_id, task_id=review.task_id, player_color=review.player_color,
        )
        if not published:
            raise HTTPException(
                status_code=503, detail="Очередь недоступна. Объяснения можно повторить.",
            )
    return AnalysisStatusRead(
        game_id=game_id, status="done", engine_status="done", review_status=review.status,
    )
