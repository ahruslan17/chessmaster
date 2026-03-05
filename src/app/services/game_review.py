from __future__ import annotations

import logging
import uuid
from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.models.move_analysis import MoveAnalysis
from app.services.opening_matcher import OpeningMatch, OpeningMatcher
from app.services.llm_coach import (
    GameSummaryInput,
    LLMCoachError,
    LLMCoachService,
    MoveCommentaryInput,
)
from app.services.pgn_parser import ParsedGame, PGNParserService
from app.services.stockfish_analyzer import MoveEvaluation
from app.utils.chess_helpers import compute_accuracy, moves_fingerprint, moves_to_fens

logger = logging.getLogger(__name__)

# Classifications considered "key moments" for game summary context.
_KEY_MOMENT_CLASSIFICATIONS = frozenset({"inaccuracy", "mistake", "blunder"})


class GameReviewService:
    """Orchestrates game analysis: parse PGN -> Stockfish -> LLM commentary.

    Accepts an optional ``LLMCoachService``; when provided, the
    ``enrich_with_llm_commentary`` method generates per-move coaching
    text and an overall game summary via the LLM.
    """

    def __init__(
        self,
        session: AsyncSession,
        llm_coach: LLMCoachService | None = None,
        opening_matcher: OpeningMatcher | None = None,
    ) -> None:
        self._session = session
        self._pgn_parser = PGNParserService()
        self._llm_coach = llm_coach
        self._opening_matcher = opening_matcher or OpeningMatcher()

    # ------------------------------------------------------------------
    # PGN import
    # ------------------------------------------------------------------

    async def create_games_from_pgn(
        self,
        pgn_text: str,
        player_color: str | None = None,
    ) -> tuple[list[Game], list[uuid.UUID]]:
        """Parse PGN text and persist Game records to the database.

        For each parsed game, checks if an identical game (same moves) already
        exists. If so, returns the existing game and does not create a duplicate.
        Returns (games, new_game_ids) — only new_game_ids should be queued for analysis.
        """
        parsed_games = self._pgn_parser.parse_pgn(pgn_text)
        if not parsed_games:
            logger.warning("No games found in the provided PGN text")
            return [], []

        db_games: list[Game] = []
        new_games: list[Game] = []
        for parsed in parsed_games:
            fingerprint = moves_fingerprint(parsed.moves)
            existing = await self._find_game_by_fingerprint(fingerprint)
            if existing is not None:
                db_games.append(existing)
                logger.info(
                    "Duplicate game (fingerprint %s), reusing existing game %s",
                    fingerprint[:12],
                    existing.id,
                )
                continue
            game = _build_game_record(parsed, player_color)
            game.moves_fingerprint = fingerprint
            if game.id is None:
                game.id = uuid.uuid4()
            self._session.add(game)
            db_games.append(game)
            new_games.append(game)

        await self._session.flush()
        new_ids = [g.id for g in new_games if g.id is not None]
        logger.info(
            "Created/returned %d game record(s) in the database (%d new)",
            len(db_games),
            len(new_ids),
        )
        return db_games, new_ids

    async def _find_game_by_fingerprint(self, fingerprint: str) -> Game | None:
        """Find an existing game with the given moves fingerprint."""
        stmt = select(Game).where(Game.moves_fingerprint == fingerprint).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Analysis lifecycle
    # ------------------------------------------------------------------

    async def init_analysis(self, game_id: uuid.UUID) -> GameAnalysis:
        """Get existing or create new GameAnalysis for the game.

        If an analysis already exists: reuse it. If status is 'done', return as-is
        (caller should skip pipeline). If 'in_progress' or 'failed', reset and reuse.
        """
        stmt = select(GameAnalysis).where(GameAnalysis.game_id == game_id)
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            if existing.status == "done":
                logger.info("Analysis already done for game %s, reusing %s", game_id, existing.id)
                return existing
            # Reset for re-run: clear old move data, set in_progress
            await self._session.execute(
                delete(MoveAnalysis).where(MoveAnalysis.game_analysis_id == existing.id)
            )
            existing.summary = None
            existing.opening_assessment = None
            existing.middlegame_assessment = None
            existing.endgame_assessment = None
            existing.key_moments = None
            existing.accuracy_white = None
            existing.accuracy_black = None
            existing.status = "in_progress"
            await self._session.flush()
            logger.info("Reusing analysis %s for game %s (status reset)", existing.id, game_id)
            return existing
        analysis = GameAnalysis(game_id=game_id, status="in_progress")
        self._session.add(analysis)
        await self._session.flush()
        logger.info("Initialized analysis %s for game %s", analysis.id, game_id)
        return analysis

    async def save_stockfish_results(
        self,
        game_analysis_id: uuid.UUID,
        evaluations: list[MoveEvaluation],
        opening_move_count: int = 0,
    ) -> None:
        """Persist Stockfish evaluation results and update analysis status.

        Creates MoveAnalysis records, computes accuracy stats, and sets
        the GameAnalysis status to 'done'. Moves within the opening (index <
        opening_move_count) are marked as classification='theory'.
        """
        analysis = await self._session.get(GameAnalysis, game_analysis_id)
        if analysis is None:
            raise ValueError(f"GameAnalysis {game_analysis_id} not found")

        # Create move analysis records
        for idx, evaluation in enumerate(evaluations):
            classification = (
                "theory"
                if opening_move_count > 0 and idx < opening_move_count
                else evaluation.classification
            )
            move_record = _build_move_analysis(
                game_analysis_id, evaluation, classification_override=classification
            )
            self._session.add(move_record)

        # Compute accuracy
        white_losses = [ev.centipawn_loss for ev in evaluations if ev.color == "white"]
        black_losses = [ev.centipawn_loss for ev in evaluations if ev.color == "black"]
        analysis.accuracy_white = compute_accuracy(white_losses)
        analysis.accuracy_black = compute_accuracy(black_losses)
        analysis.status = "done"

        await self._session.flush()
        logger.info(
            "Saved %d move evaluations for analysis %s (white=%.1f%%, black=%.1f%%)",
            len(evaluations),
            game_analysis_id,
            analysis.accuracy_white,
            analysis.accuracy_black,
        )

    async def mark_analysis_failed(self, game_id: uuid.UUID) -> None:
        """Set analysis status to 'failed' for the given game."""
        stmt = select(GameAnalysis).where(GameAnalysis.game_id == game_id)
        result = await self._session.execute(stmt)
        analysis = result.scalar_one_or_none()
        if analysis is not None:
            analysis.status = "failed"
            await self._session.flush()
            logger.warning("Marked analysis as failed for game %s", game_id)

    # ------------------------------------------------------------------
    # LLM commentary enrichment
    # ------------------------------------------------------------------

    async def enrich_with_llm_commentary(
        self,
        game_analysis_id: uuid.UUID,
        game: Game,
        evaluations: list[MoveEvaluation],
        opening_move_count: int = 0,
    ) -> None:
        """Add LLM-generated commentary to an existing analysis.

        Generates per-move coaching comments and an overall game summary,
        then persists them to the corresponding DB records.  Requires
        ``self._llm_coach`` to be set; silently returns otherwise.
        Errors from the LLM are logged but do **not** propagate -- the
        Stockfish analysis remains usable without LLM enrichment.
        Moves within the opening (index < opening_move_count) are treated
        as theoretical for commentary purposes.
        """
        if self._llm_coach is None:
            logger.info("LLM coach not configured, skipping commentary enrichment")
            return

        # 1. Reconstruct FENs from the game PGN
        parsed_games = self._pgn_parser.parse_pgn(game.pgn_text)
        if not parsed_games:
            logger.warning("Could not re-parse PGN for LLM enrichment")
            return
        fens = moves_to_fens(parsed_games[0].moves)

        # 2. Build LLM input from Stockfish evaluations + FENs (theory override)
        move_inputs = _build_move_commentary_inputs(
            fens, evaluations, opening_move_count=opening_move_count
        )

        # 3. Generate per-move commentaries
        commentaries: dict[int, str] = {}
        try:
            commentaries = await self._llm_coach.generate_move_commentaries(move_inputs)
        except LLMCoachError:
            logger.exception("LLM move commentary generation failed")

        # 4. Generate game summary (use move_inputs for classification counts)
        summary_input = _build_game_summary_input(
            game, evaluations, move_inputs, use_move_inputs_for_counts=True
        )
        summary = None
        try:
            summary = await self._llm_coach.generate_game_summary(summary_input)
        except LLMCoachError:
            logger.exception("LLM game summary generation failed")

        # 5. Persist results
        await self._save_llm_results(
            game_analysis_id, commentaries, move_inputs, summary
        )

    async def _save_llm_results(
        self,
        game_analysis_id: uuid.UUID,
        commentaries: dict[int, str],
        move_inputs: list[MoveCommentaryInput],
        summary: object | None,
    ) -> None:
        """Write LLM commentary and summary to DB records."""
        # Build a lookup keyed by (move_number, color) for robust matching
        commentary_lookup: dict[tuple[int, str], str] = {}
        for move_input in move_inputs:
            comment = commentaries.get(move_input.move_index)
            if comment:
                commentary_lookup[(move_input.move_number, move_input.color)] = comment

        # Update move-level comments
        if commentary_lookup:
            stmt = select(MoveAnalysis).where(
                MoveAnalysis.game_analysis_id == game_analysis_id
            )
            result = await self._session.execute(stmt)
            for record in result.scalars():
                key = (record.move_number, record.color)
                if key in commentary_lookup:
                    record.llm_comment = commentary_lookup[key]

        # Update game-level summary
        if summary is not None:
            analysis = await self._session.get(GameAnalysis, game_analysis_id)
            if analysis is not None:
                analysis.summary = summary.summary
                analysis.opening_assessment = summary.opening_assessment
                analysis.middlegame_assessment = summary.middlegame_assessment
                analysis.endgame_assessment = summary.endgame_assessment
                analysis.key_moments = summary.key_moments

        await self._session.flush()
        logger.info(
            "Saved LLM commentary for analysis %s (%d move comments, summary=%s)",
            game_analysis_id,
            len(commentary_lookup),
            "yes" if summary else "no",
        )


# ---------------------------------------------------------------------------
# Pure builder functions (no DB access)
# ---------------------------------------------------------------------------


def _build_game_record(
    parsed: ParsedGame,
    player_color: str | None,
    opening_match: OpeningMatch | None = None,
) -> Game:
    """Build a Game ORM object from parsed PGN data.

    When opening_match is provided, uses its eco_code and name; otherwise
    falls back to PGN headers (Opening, ECO).
    """
    if opening_match is not None:
        opening_name = opening_match.name
        eco_code = opening_match.eco_code
    else:
        opening_name = parsed.opening_name
        eco_code = parsed.eco_code
    return Game(
        pgn_text=parsed.pgn_text,
        white_player=parsed.white_player,
        black_player=parsed.black_player,
        result=parsed.result,
        opening_name=opening_name,
        eco_code=eco_code,
        time_control=parsed.time_control,
        played_at=parsed.played_at,
        player_color=player_color,
    )


def _build_move_analysis(
    game_analysis_id: uuid.UUID,
    evaluation: MoveEvaluation,
    classification_override: str | None = None,
) -> MoveAnalysis:
    """Build a MoveAnalysis ORM object from a MoveEvaluation."""
    classification = (
        classification_override if classification_override else evaluation.classification
    )
    return MoveAnalysis(
        game_analysis_id=game_analysis_id,
        move_number=evaluation.move_number,
        color=evaluation.color,
        move_san=evaluation.move_san,
        best_move_san=evaluation.best_move_san,
        eval_before=evaluation.eval_before,
        eval_after=evaluation.eval_after,
        centipawn_loss=evaluation.centipawn_loss,
        classification=classification,
        top_moves=evaluation.top_moves_as_json(),
        continuation_lines=evaluation.continuation_lines_as_json(),
    )


def _build_move_commentary_inputs(
    fens: list[str],
    evaluations: list[MoveEvaluation],
    opening_move_count: int = 0,
) -> list[MoveCommentaryInput]:
    """Combine per-position FENs with Stockfish evaluations into LLM inputs."""
    inputs: list[MoveCommentaryInput] = []
    for idx, evaluation in enumerate(evaluations):
        classification = (
            "theory"
            if opening_move_count > 0 and idx < opening_move_count
            else evaluation.classification
        )
        fen = fens[idx] if idx < len(fens) else ""
        inputs.append(
            MoveCommentaryInput(
                move_index=idx,
                move_number=evaluation.move_number,
                color=evaluation.color,
                fen_before=fen,
                move_san=evaluation.move_san,
                best_move_san=evaluation.best_move_san,
                eval_before=evaluation.eval_before,
                eval_after=evaluation.eval_after,
                centipawn_loss=evaluation.centipawn_loss,
                classification=classification,
                top_moves=evaluation.top_moves_as_json(),
            )
        )
    return inputs


def _build_game_summary_input(
    game: Game,
    evaluations: list[MoveEvaluation],
    move_inputs: list[MoveCommentaryInput],
    use_move_inputs_for_counts: bool = False,
) -> GameSummaryInput:
    """Build the context object needed for LLM game summary generation."""
    if use_move_inputs_for_counts:
        classification_counts = dict(Counter(m.classification for m in move_inputs))
    else:
        classification_counts = dict(
            Counter(ev.classification for ev in evaluations)
        )
    key_moments = [
        m for m in move_inputs if m.classification in _KEY_MOMENT_CLASSIFICATIONS
    ]

    white_losses = [ev.centipawn_loss for ev in evaluations if ev.color == "white"]
    black_losses = [ev.centipawn_loss for ev in evaluations if ev.color == "black"]

    return GameSummaryInput(
        white_player=game.white_player,
        black_player=game.black_player,
        result=game.result,
        opening_name=game.opening_name,
        eco_code=game.eco_code,
        total_moves=len(evaluations),
        accuracy_white=compute_accuracy(white_losses),
        accuracy_black=compute_accuracy(black_losses),
        classification_counts=classification_counts,
        key_moments=key_moments,
    )
