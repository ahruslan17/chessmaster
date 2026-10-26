from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import String, cast, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.models.side_review import SideReview
from app.services.game_review import GameReviewService
from app.services.llm_coach import (
    FULL_COMMENTARY_BATCH_SIZE,
    FullCommentaryResult,
    LLMCoachService,
    ReviewExplanationResult,
)
from app.services.pgn_parser import PGNParserService
from app.services.stockfish_analyzer import StockfishAnalyzerService

logger = logging.getLogger(__name__)
_PROGRESS_INTERVAL = 10


@celery_app.task(max_retries=0)
def analyze_game_task(game_id: str, attempt_id: str | None = None) -> dict[str, str]:
    """Engine only. Retries/recovery require an explicit, newly persisted attempt."""
    return _run_task(_run_analysis_pipeline(game_id, attempt_id))


@celery_app.task(max_retries=0)
def explain_game_task(game_id: str, player_color: str, attempt_id: str) -> dict[str, str]:
    """Coach only: never rerun Stockfish or automatically retry paid requests."""
    return _run_task(_run_explanation_pipeline(game_id, player_color, attempt_id))


def _run_task(coroutine) -> dict[str, str]:
    # Celery creates a fresh loop per job; dispose pooled connections before closing it.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coroutine)
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


async def _run_analysis_pipeline(
    game_id_str: str, attempt_id_str: str | None = None
) -> dict[str, str]:
    game_id = uuid.UUID(game_id_str)
    if attempt_id_str is None:
        # Legacy broker messages must not create attempts or reset an active worker.
        return {"game_id": game_id_str, "status": "skipped"}
    attempt_id = uuid.UUID(attempt_id_str)
    async with async_session_factory() as session:
        result = await session.execute(
            update(GameAnalysis).where(
                GameAnalysis.game_id == game_id,
                GameAnalysis.engine_attempt_id == attempt_id,
                GameAnalysis.engine_status == "queued",
            ).values(
                engine_status="in_progress", status="in_progress", heartbeat_at=datetime.now(UTC)
            )
            .returning(GameAnalysis.id)
        )
        analysis_id = result.scalar_one_or_none()
        if analysis_id is None:
            return {"game_id": game_id_str, "status": "skipped"}
        game = await session.get(Game, game_id)
        pgn_text = game.pgn_text
        await session.commit()  # Claim is durable before CPU work starts.

    try:
        parsed_games = PGNParserService().parse_pgn(pgn_text)
        if len(parsed_games) != 1 or not parsed_games[0].moves:
            raise ValueError("Stored PGN must contain exactly one nonempty game")
        analyzer = StockfishAnalyzerService(
            stockfish_path=settings.stockfish_path, depth=settings.stockfish_depth,
            multipv=settings.stockfish_multipv, time_limit=settings.stockfish_time_limit,
            threads=settings.stockfish_threads,
        )
        loop = asyncio.get_running_loop()
        last_progress = -_PROGRESS_INTERVAL

        def progress(current: int, total: int) -> None:
            nonlocal last_progress
            if current - last_progress < _PROGRESS_INTERVAL and current != total:
                return
            last_progress = current
            owned = asyncio.run_coroutine_threadsafe(
                _record_progress(analysis_id, attempt_id, current, total), loop
            ).result()
            if not owned:
                raise AttemptSupersededError("Engine attempt was replaced")

        evaluations = await asyncio.to_thread(
            analyzer.analyze_game, parsed_games[0].moves, progress_callback=progress
        )
        if len(evaluations) != len(parsed_games[0].moves) or any(
            ev.score_before is None or ev.score_after is None for ev in evaluations
        ):
            raise ValueError("Engine returned incomplete typed scores")
        async with async_session_factory() as session:
            saved = await GameReviewService(session).save_stockfish_results(
                analysis_id, evaluations, attempt_id=attempt_id,
                engine_metadata={
                    "engine": "Stockfish", "score_version": 1,
                    "depth": settings.stockfish_depth, "multipv": settings.stockfish_multipv,
                    "time_limit": settings.stockfish_time_limit,
                    "threads": settings.stockfish_threads,
                },
            )
            await session.commit()
        return {"game_id": game_id_str, "status": "done" if saved else "skipped"}
    except AttemptSupersededError:
        return {"game_id": game_id_str, "status": "skipped"}
    except Exception as exc:
        await _fail_engine(analysis_id, attempt_id, str(exc))
        raise


class AttemptSupersededError(RuntimeError):
    """Current worker no longer owns this attempt."""


async def _record_progress(
    analysis_id: uuid.UUID, attempt_id: uuid.UUID, current: int, total: int
) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            update(GameAnalysis).where(
                GameAnalysis.id == analysis_id, GameAnalysis.engine_attempt_id == attempt_id,
                GameAnalysis.engine_status == "in_progress",
            ).values(
                progress_current=current, progress_total=total, heartbeat_at=datetime.now(UTC)
            )
            .returning(GameAnalysis.id)
        )
        owned = result.scalar_one_or_none() is not None
        await session.commit()
        return owned


async def _fail_engine(analysis_id: uuid.UUID, attempt_id: uuid.UUID, message: str) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(GameAnalysis).where(
                GameAnalysis.id == analysis_id, GameAnalysis.engine_attempt_id == attempt_id,
                GameAnalysis.engine_status == "in_progress",
            ).values(engine_status="failed", status="failed", engine_error=message[:2000],
                     heartbeat_at=datetime.now(UTC))
        )
        await session.commit()


async def _run_explanation_pipeline(
    game_id_str: str, player_color: str, attempt_id_str: str
) -> dict[str, str]:
    game_id, attempt_id = uuid.UUID(game_id_str), uuid.UUID(attempt_id_str)
    async with async_session_factory() as session:
        # Lock shared result owner before side claim, just like queue and final save.
        owner = await session.execute(
            select(GameAnalysis.id).where(GameAnalysis.game_id == game_id).with_for_update()
        )
        if owner.scalar_one_or_none() is None:
            return {"game_id": game_id_str, "status": "skipped"}
        result = await session.execute(
            update(SideReview).where(
                SideReview.game_analysis_id.in_(
                    select(GameAnalysis.id).where(
                        GameAnalysis.game_id == game_id, GameAnalysis.engine_status == "done",
                        SideReview.context["engine_result_id"].astext
                        == cast(GameAnalysis.engine_result_id, String),
                    )
                ),
                SideReview.player_color == player_color, SideReview.attempt_id == attempt_id,
                SideReview.status == "queued",
            ).values(status="in_progress", heartbeat_at=datetime.now(UTC))
            .returning(SideReview.id, SideReview.context, SideReview.comments)
            .execution_options(synchronize_session=False)
        )
        claimed = result.one_or_none()
        if claimed is None:
            return {"game_id": game_id_str, "status": "skipped"}
        review_id, context, comments = claimed
        context = copy.deepcopy(context)
        await session.commit()

    try:
        if not _llm_enabled():
            raise ValueError("LLM не настроен; результаты движка сохранены")
        if context.get("commentary_scope") == "all_moves":
            missing = [
                move for move in context["moves"]
                if str(move["move_index"]) not in (comments or {})
            ]
            coach = LLMCoachService()
            for start in range(0, len(missing), FULL_COMMENTARY_BATCH_SIZE):
                if await _save_full_commentary(review_id, attempt_id, None) == "skipped":
                    return {"game_id": game_id_str, "status": "skipped"}
                batch = missing[start:start + FULL_COMMENTARY_BATCH_SIZE]
                result = await coach.generate_full_commentary({"moves": batch})
                status = await _save_full_commentary(review_id, attempt_id, result)
                if status == "skipped":
                    return {"game_id": game_id_str, "status": status}
                if set(result.comments) != {move["move_index"] for move in batch}:
                    break  # Partial response requires an explicit retry, never a paid auto-retry.
            status = await _save_full_commentary(review_id, attempt_id, None, finalize=True)
            return {"game_id": game_id_str, "status": status}
        ready = comments or {}
        # Full context is needed for a sound summary; coach generates only missing comments.
        context["missing_comment_indices"] = [
            m["move_index"] for m in context["moments"] if str(m["move_index"]) not in ready
        ]
        result = (
            await LLMCoachService().generate_review(context)
            if context["missing_comment_indices"] else None
        )
        status = await _save_explanations(review_id, attempt_id, result)
        return {"game_id": game_id_str, "status": status}
    except Exception as exc:
        await _fail_explanations(review_id, attempt_id, str(exc), getattr(exc, "usage", None))
        raise


async def _lock_current_review(
    session: AsyncSession, review_id: uuid.UUID, attempt_id: uuid.UUID
) -> SideReview | None:
    # Match queue's lock order: engine owner, then side. Engine replacement cannot race this save.
    rows = await session.execute(
        select(GameAnalysis).join(SideReview, SideReview.game_analysis_id == GameAnalysis.id)
        .where(SideReview.id == review_id).with_for_update(of=GameAnalysis)
    )
    analysis = rows.scalar_one_or_none()
    if analysis is None:
        return None
    rows = await session.execute(
        select(SideReview).where(SideReview.id == review_id).with_for_update()
    )
    review = rows.scalar_one_or_none()
    if (review is None or review.attempt_id != attempt_id or review.status != "in_progress"
            or analysis.engine_status != "done" or analysis.engine_result_id is None
            or (review.context or {}).get("engine_result_id") != str(analysis.engine_result_id)):
        return None
    return review


def _merge_usage(existing: dict | None, attempt_id: uuid.UUID, usage: dict | None) -> dict:
    attempts = dict((existing or {}).get("attempts", {}))
    if usage:
        previous = attempts.get(str(attempt_id), {})
        attempts[str(attempt_id)] = {
            **previous, **usage,
            **{key: previous.get(key, 0) + value for key, value in usage.items()
               if isinstance(value, (int, float)) and not isinstance(value, bool)},
        }
    totals: dict[str, int | float] = {}
    for entry in attempts.values():
        for key, value in entry.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] = totals.get(key, 0) + value
    return {"attempts": attempts, "total": totals}


async def _save_full_commentary(
    review_id: uuid.UUID, attempt_id: uuid.UUID, result: FullCommentaryResult | None,
    *, finalize: bool = False,
) -> str:
    """Persist each batch under the existing attempt fence; never discard ready text."""
    async with async_session_factory() as session:
        review = await _lock_current_review(session, review_id, attempt_id)
        if review is None:
            return "skipped"
        expected = {str(move["move_index"]) for move in review.context["moves"]}
        comments = dict(review.comments or {})
        if result is not None:
            for index, text in result.comments.items():
                if str(index) in expected:
                    comments.setdefault(str(index), {"text": text})
            review.usage = _merge_usage(review.usage, attempt_id, result.usage)
        review.comments = comments
        if finalize:
            complete = expected <= comments.keys()
            review.status = "done" if complete else "partial"
            review.error = (
                None if complete else "Комментарии получены не для всех ходов. Дополните разбор."
            )
        review.heartbeat_at = datetime.now(UTC)
        await session.commit()
        return review.status


async def _save_explanations(
    review_id: uuid.UUID, attempt_id: uuid.UUID, result: ReviewExplanationResult | None
) -> str:
    async with async_session_factory() as session:
        review = await _lock_current_review(session, review_id, attempt_id)
        if review is None:
            return "skipped"
        expected = {str(m["move_index"]) for m in review.context["moments"]}
        comments = dict(review.comments or {})
        if result is not None:
            for index, comment in result.comments.items():
                if str(index) in expected:
                    comments.setdefault(str(index), comment.model_dump(mode="json"))
            review.usage = _merge_usage(review.usage, attempt_id, result.usage)
        review.comments = comments
        complete = expected <= comments.keys()
        review.status = "done" if complete else "partial"
        review.error = None if complete else "Объяснения получены не для всех выбранных моментов"
        if complete and result is not None:
            review.summary = result.summary
            review.recommendations = result.recommendations
        review.heartbeat_at = datetime.now(UTC)
        await session.commit()
        return review.status


async def _fail_explanations(
    review_id: uuid.UUID, attempt_id: uuid.UUID, message: str, usage: dict | None = None
) -> None:
    async with async_session_factory() as session:
        review = await _lock_current_review(session, review_id, attempt_id)
        if review is not None:
            review.status = "partial" if review.comments else "failed"
            review.error = message[:2000]
            review.heartbeat_at = datetime.now(UTC)
            review.usage = _merge_usage(review.usage, attempt_id, usage)
            await session.commit()


def _llm_enabled() -> bool:
    return bool(settings.llm_api_key or settings.litellm_base_url)
