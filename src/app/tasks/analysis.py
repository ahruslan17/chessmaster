from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.exc import IntegrityError

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.models.game import Game
from app.services.game_review import GameReviewService
from app.services.llm_coach import LLMCoachService
from app.services.opening_matcher import OpeningMatcher
from app.services.pgn_parser import PGNParserService
from app.services.stockfish_analyzer import StockfishAnalyzerService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def analyze_game_task(self, game_id: str) -> dict[str, str]:  # type: ignore[override]
    """Celery task: run full analysis pipeline for one game.

    Pipeline: Stockfish evaluation -> LLM commentary enrichment.
    The heavy work (Stockfish) runs synchronously; DB access uses asyncio.run().
    LLM enrichment runs if configured; failures are logged but do not fail the task.
    """
    logger.info("Celery task started: analyze game %s", game_id)
    try:
        asyncio.run(_run_analysis_pipeline(game_id))
        return {"game_id": game_id, "status": "done"}
    except IntegrityError as exc:
        logger.warning(
            "Analysis already exists for game %s (concurrent task?), skipping: %s",
            game_id,
            exc,
        )
        return {"game_id": game_id, "status": "skipped"}
    except Exception as exc:
        logger.error("Analysis task failed for game %s: %s", game_id, exc, exc_info=True)
        asyncio.run(_dispose_and_mark_failed(game_id))
        raise self.retry(exc=exc) from exc


async def _run_analysis_pipeline(game_id_str: str) -> None:
    """Execute the full analysis pipeline: fetch game -> Stockfish -> save -> LLM enrichment."""
    game_uuid = uuid.UUID(game_id_str)

    # --- Step 1: Fetch game and initialize analysis record ---
    async with async_session_factory() as session:
        game = await session.get(Game, game_uuid)
        if game is None:
            raise ValueError(f"Game {game_uuid} not found")
        pgn_text = game.pgn_text

        service = GameReviewService(session)
        analysis = await service.init_analysis(game_uuid)
        analysis_id = analysis.id
        await session.commit()
        if analysis.status == "done":
            logger.info("Analysis already complete for game %s, skipping", game_id_str)
            return

    logger.info("Analysis record %s created/reused for game %s", analysis_id, game_id_str)

    # --- Step 2: Parse PGN to get moves ---
    parser = PGNParserService()
    parsed_games = parser.parse_pgn(pgn_text)
    if not parsed_games:
        raise ValueError(f"No games parsed from PGN for game {game_uuid}")
    parsed_game = parsed_games[0]

    # --- Step 3: Run Stockfish analysis (synchronous, CPU-bound) ---
    analyzer = StockfishAnalyzerService(
        stockfish_path=settings.stockfish_path,
        depth=settings.stockfish_depth,
        multipv=settings.stockfish_multipv,
    )
    evaluations = analyzer.analyze_game(parsed_game.moves)
    logger.info("Stockfish analysis complete: %d moves evaluated", len(evaluations))

    # Opening match for theory move marking
    opening_matcher = OpeningMatcher()
    opening_match = opening_matcher.match(parsed_game.moves)
    opening_move_count = opening_match.move_count if opening_match else 0

    # --- Step 4: Save results to DB ---
    async with async_session_factory() as session:
        service = GameReviewService(session)
        await service.save_stockfish_results(
            analysis_id, evaluations, opening_move_count=opening_move_count
        )
        await session.commit()

    # --- Step 5: LLM commentary enrichment (if configured) ---
    async with async_session_factory() as session:
        game = await session.get(Game, game_uuid)
        if game is not None:
            llm_coach = LLMCoachService()
            service = GameReviewService(session, llm_coach=llm_coach)
            await service.enrich_with_llm_commentary(
                analysis_id, game, evaluations, opening_move_count=opening_move_count
            )
            await session.commit()

    logger.info("Analysis pipeline complete for game %s", game_id_str)


async def _dispose_and_mark_failed(game_id_str: str) -> None:
    """Dispose engine connections, then mark analysis as failed.

    Must dispose first so the next session uses a fresh event loop/connections,
    avoiding 'Future attached to a different loop' errors in Celery workers.
    """
    try:
        await engine.dispose()
    except Exception as e:
        logger.warning("Engine dispose during cleanup: %s", e)
    try:
        game_uuid = uuid.UUID(game_id_str)
        async with async_session_factory() as session:
            service = GameReviewService(session)
            await service.mark_analysis_failed(game_uuid)
            await session.commit()
    except Exception:
        logger.error("Failed to mark analysis as failed for %s", game_id_str, exc_info=True)
