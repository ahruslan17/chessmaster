from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import BigInteger, delete, func, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PGNParseError
from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.models.move_analysis import MoveAnalysis
from app.models.side_review import SideReview
from app.services.llm_coach import (
    GameSummaryInput,
    GameSummaryResult,
    LLMCoachError,
    LLMCoachService,
    MoveCommentaryInput,
)
from app.services.opening_matcher import OpeningMatch, OpeningMatcher
from app.services.pgn_parser import ParsedGame, PGNParserService
from app.services.stockfish_analyzer import CandidateMove, EngineScore, MoveEvaluation
from app.utils.chess_helpers import moves_fingerprint, moves_to_fens

logger = logging.getLogger(__name__)

# Classifications considered "key moments" for game summary context.
_KEY_MOMENT_CLASSIFICATIONS = frozenset({"inaccuracy", "mistake", "blunder"})
_NEXT_GAME_MOVES_CONTEXT = 10


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
        access_session_id: uuid.UUID | None = None,
        max_new_games: int | None = None,
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
        if max_new_games is not None and len(parsed_games) > max_new_games:
            raise HTTPException(
                status_code=429,
                detail="За одну гостевую сессию можно загрузить только одну партию",
            )

        fingerprints = [moves_fingerprint(parsed.moves) for parsed in parsed_games]
        # Transaction-scoped locks also serialize importers before a row exists.
        # Acquire the entire batch in deterministic order to avoid reversed-batch deadlocks.
        lock_keys = {
            int.from_bytes(sha256(fingerprint.encode()).digest()[:8], "big", signed=True)
            for fingerprint in fingerprints
        }
        for key in sorted(lock_keys):
            await self._session.execute(
                select(func.pg_advisory_xact_lock(literal(key, type_=BigInteger)))
            )

        db_games: list[Game] = []
        new_games: list[Game] = []
        batch_games: dict[tuple, Game] = {}
        for parsed, fingerprint in zip(parsed_games, fingerprints, strict=True):
            opening_match = self._opening_matcher.match(parsed.moves)
            identity = _game_identity(parsed)
            existing = batch_games.get(identity)
            if existing is None:
                existing = await self._find_game_by_fingerprint(
                    fingerprint, parsed, access_session_id=access_session_id
                )
            if existing is not None:
                batch_games[identity] = existing
                if player_color and existing.player_color not in (None, player_color):
                    raise HTTPException(
                        status_code=409,
                        detail=("Партия уже сохранена для другой стороны. "
                                "Откройте её и явно выберите сторону разбора."),
                    )
                if player_color and existing.player_color is None:
                    existing.player_color = player_color
                if opening_match is not None:
                    if not existing.opening_name:
                        existing.opening_name = opening_match.name
                    if not existing.eco_code:
                        existing.eco_code = opening_match.eco_code
                db_games.append(existing)
                logger.info(
                    "Duplicate game (fingerprint %s), reusing existing game %s",
                    fingerprint[:12],
                    existing.id,
                )
                continue
            game = _build_game_record(parsed, player_color, opening_match=opening_match)
            game.access_session_id = access_session_id
            game.moves_fingerprint = fingerprint
            if game.id is None:
                game.id = uuid.uuid4()
            self._session.add(game)
            db_games.append(game)
            new_games.append(game)
            batch_games[identity] = game

        await self._session.flush()
        new_ids = [g.id for g in new_games if g.id is not None]
        logger.info(
            "Created/returned %d game record(s) in the database (%d new)",
            len(db_games),
            len(new_ids),
        )
        return db_games, new_ids

    async def _find_game_by_fingerprint(
        self,
        fingerprint: str,
        parsed: ParsedGame | None = None,
        access_session_id: uuid.UUID | None = None,
    ) -> Game | None:
        """Same moves alone do not identify a game: compare normalized headers too."""
        stmt = select(Game).where(Game.moves_fingerprint == fingerprint)
        if access_session_id is not None:
            stmt = stmt.where(Game.access_session_id == access_session_id)
        stmt = stmt.execution_options(populate_existing=True)
        result = await self._session.execute(stmt)
        for game in result.scalars():
            if parsed is None:
                return game
            try:
                stored = self._pgn_parser.parse_pgn(game.pgn_text)
            except PGNParseError:
                logger.warning("Skipping invalid stored PGN for game %s during import", game.id)
                continue
            if stored and _game_identity(stored[0]) == _game_identity(parsed):
                return game
        return None

    # ------------------------------------------------------------------
    # Analysis lifecycle
    # ------------------------------------------------------------------

    async def _lock_game_analysis(self, game_id: uuid.UUID) -> tuple[Game, GameAnalysis | None]:
        # Always lock parent first: serializes creation without swallowing DB errors.
        result = await self._session.execute(
            select(Game).where(Game.id == game_id).with_for_update()
        )
        game = result.scalar_one_or_none()
        if game is None:
            raise HTTPException(status_code=404, detail="Партия не найдена")
        result = await self._session.execute(
            select(GameAnalysis).where(GameAnalysis.game_id == game_id).with_for_update()
        )
        return game, result.scalar_one_or_none()

    async def queue_engine(
        self, game_id: uuid.UUID, recover: bool = False,
        expected_attempt_id: uuid.UUID | None = None,
    ) -> tuple[GameAnalysis, bool]:
        """Persist attempt; caller commits before publishing with engine_task_id.

        Crash between commit and publication leaves queued, never auto-expires.
        Explicit recovery must provide the displayed expected_attempt_id (including null).
        """
        game, analysis = await self._lock_game_analysis(game_id)
        if recover and (analysis.engine_attempt_id if analysis else None) != expected_attempt_id:
            raise HTTPException(
                status_code=409, detail="Попытка анализа уже изменилась; обновите страницу"
            )
        if analysis is None:
            analysis = GameAnalysis(id=uuid.uuid4(), game_id=game_id)
            self._session.add(analysis)
        elif not recover and (
            analysis.engine_status in {"queued", "in_progress"}
            or (analysis.engine_status == "done" and analysis.score_version == 1)
        ):
            return analysis, False
        active_reviews = await self._session.execute(
            select(SideReview).where(
                SideReview.game_analysis_id == analysis.id,
                SideReview.status.in_({"queued", "in_progress"}),
            ).with_for_update()
        )
        for review in active_reviews.scalars():
            review.status = "partial" if review.comments else "failed"
            review.error = "Объяснение остановлено: запущена новая попытка анализа движком"
            review.heartbeat_at = datetime.now(UTC)
        analysis.engine_attempt_id = uuid.uuid4()
        analysis.engine_task_id = str(uuid.uuid4())
        analysis.engine_status = "queued"
        analysis.status = "pending"
        analysis.engine_error = None
        analysis.progress_current = 0
        parsed = self._pgn_parser.parse_pgn(game.pgn_text)
        analysis.progress_total = len(parsed[0].moves) + 1 if parsed else 0
        analysis.heartbeat_at = None
        await self._session.flush()
        return analysis, True

    async def queue_explanations(
        self, game_id: uuid.UUID, player_color: str, recover: bool = False,
        expected_attempt_id: uuid.UUID | None = None,
    ) -> tuple[SideReview, bool]:
        """Queue shared full-game commentary; selected side only scopes highlights."""
        from app.services.review_moments import build_review_context

        if player_color not in {"white", "black"}:
            raise HTTPException(status_code=422, detail="Выберите белую или чёрную сторону")
        game, analysis = await self._lock_game_analysis(game_id)
        if (analysis is None or analysis.engine_status != "done" or analysis.score_version != 1
                or analysis.engine_result_id is None):
            raise HTTPException(
                status_code=409, detail="Сначала выполните актуальный анализ движком"
            )
        result = await self._session.execute(
            select(SideReview).where(
                SideReview.game_analysis_id == analysis.id,
                (SideReview.player_color == player_color)
                | (SideReview.context["commentary_scope"].astext == "all_moves"),
            ).order_by(
                (SideReview.context["commentary_scope"].astext == "all_moves").desc().nulls_last(),
                (SideReview.player_color == player_color).desc(),
            ).limit(1).with_for_update()
        )
        review = result.scalar_one_or_none()
        if recover and (review.attempt_id if review else None) != expected_attempt_id:
            raise HTTPException(
                status_code=409, detail="Попытка объяснения уже изменилась; обновите страницу"
            )
        same_result = review is not None and (
            (review.context or {}).get("engine_result_id") == str(analysis.engine_result_id)
        )
        full_review = review is not None and (
            (review.context or {}).get("commentary_scope") == "all_moves"
        )
        if same_result and not recover and (
            review.status in {"queued", "in_progress"} or (full_review and review.status == "done")
        ):
            return review, False
        result = await self._session.execute(
            select(MoveAnalysis).where(MoveAnalysis.game_analysis_id == analysis.id)
            .order_by(MoveAnalysis.move_number, MoveAnalysis.color.desc())
        )
        records = list(result.scalars())
        if not records or any(r.score_before is None or r.score_after is None for r in records):
            raise HTTPException(
                status_code=409, detail="Результаты движка неполны; повторите анализ"
            )
        try:
            context = build_review_context(
                game.pgn_text, [_restore_evaluation(r) for r in records],
                review.player_color if review is not None else player_color,
                include_all_moves=True,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(
                status_code=409, detail="Контекст движка некорректен; повторите анализ"
            ) from exc
        context["engine_result_id"] = str(analysis.engine_result_id)
        if review is None:
            review = SideReview(
                id=uuid.uuid4(), game_analysis_id=analysis.id, player_color=player_color
            )
            self._session.add(review)
        if review.context is not None and not same_result:
            # Keep prior generation privately; never merge stale educational text.
            review.stale_result = {
                "context": review.context, "comments": review.comments, "summary": review.summary,
                "recommendations": review.recommendations, "usage": review.usage,
            }
            review.context = None
            review.comments = None
            review.summary = None
            review.recommendations = None
            review.usage = None
        if review.context is None or not full_review:
            if review.context is not None and not full_review:
                review.stale_result = {
                    "context": review.context, "comments": review.comments,
                    "summary": review.summary, "recommendations": review.recommendations,
                    "usage": review.usage,
                }
                review.summary = None
                review.recommendations = None
            review.context = context
        review.attempt_id = uuid.uuid4()
        review.task_id = str(uuid.uuid4())
        review.heartbeat_at = None
        review.error = None
        if not review.context.get("moves", review.context["moments"]):
            review.status = "done"
            review.error = "context_empty"
            review.task_id = None
            await self._session.flush()
            return review, False
        review.status = "queued"
        await self._session.flush()
        return review, True

    async def mark_publication_failed(
        self, stage: str, entity_id: uuid.UUID, attempt_id: uuid.UUID, message: str
    ) -> None:
        """Broker failure may only fail its own still-queued attempt."""
        if stage == "engine":
            stmt = update(GameAnalysis).where(
                GameAnalysis.id == entity_id, GameAnalysis.engine_attempt_id == attempt_id,
                GameAnalysis.engine_status == "queued",
            ).values(engine_status="failed", status="failed", engine_error=message[:2000])
        elif stage in {"explanations", "coach"}:
            stmt = update(SideReview).where(
                SideReview.id == entity_id, SideReview.attempt_id == attempt_id,
                SideReview.status == "queued",
            ).values(status="failed", error=message[:2000])
        else:
            raise ValueError("Unknown publication stage")
        await self._session.execute(stmt)

    async def init_analysis(self, game_id: uuid.UUID) -> GameAnalysis:
        """Get existing or create new GameAnalysis for the game.

        Legacy compatibility only: never reset existing results or active attempts.
        """
        _, existing = await self._lock_game_analysis(game_id)
        if existing is not None:
            return existing
        analysis = GameAnalysis(game_id=game_id, status="pending", engine_status="pending")
        self._session.add(analysis)
        await self._session.flush()
        logger.info("Initialized analysis %s for game %s", analysis.id, game_id)
        return analysis

    async def save_stockfish_results(
        self,
        game_analysis_id: uuid.UUID,
        evaluations: list[MoveEvaluation],
        opening_move_count: int = 0,
        attempt_id: uuid.UUID | None = None,
        engine_metadata: dict | None = None,
    ) -> bool:
        """Persist Stockfish evaluation results.

        Replace moves atomically only while owning the active engine attempt.
        Opening provenance never overrides engine move classification.
        """
        result = await self._session.execute(
            select(GameAnalysis).where(GameAnalysis.id == game_analysis_id).with_for_update()
        )
        analysis = result.scalar_one_or_none()
        if analysis is None:
            raise ValueError(f"GameAnalysis {game_analysis_id} not found")
        if attempt_id is None and analysis.engine_attempt_id is not None:
            return False
        if attempt_id is not None and (
            analysis.engine_attempt_id != attempt_id or analysis.engine_status != "in_progress"
        ):
            return False
        await self._session.execute(
            delete(MoveAnalysis).where(MoveAnalysis.game_analysis_id == game_analysis_id)
        )
        for evaluation in evaluations:
            move_record = _build_move_analysis(game_analysis_id, evaluation)
            self._session.add(move_record)
        analysis.accuracy_white = None
        analysis.accuracy_black = None
        if attempt_id is not None:
            analysis.engine_result_id = attempt_id
            analysis.score_version = 1
            analysis.engine_status = "done"
            analysis.status = "done"
            analysis.engine_error = None
            analysis.progress_current = len(evaluations) + 1
            analysis.progress_total = len(evaluations) + 1
            analysis.heartbeat_at = datetime.now(UTC)
            analysis.engine_metadata = engine_metadata
        await self._session.flush()
        return True

    async def mark_analysis_done(self, game_id: uuid.UUID) -> None:
        """Set analysis status to 'done' for the given game."""
        stmt = select(GameAnalysis).where(GameAnalysis.game_id == game_id).with_for_update()
        result = await self._session.execute(stmt)
        analysis = result.scalar_one_or_none()
        if analysis is not None and analysis.engine_attempt_id is None:
            analysis.status = "done"
            await self._session.flush()

    async def mark_analysis_failed(self, game_id: uuid.UUID) -> None:
        """Set analysis status to 'failed' for the given game."""
        stmt = select(GameAnalysis).where(GameAnalysis.game_id == game_id).with_for_update()
        result = await self._session.execute(stmt)
        analysis = result.scalar_one_or_none()
        if analysis is not None and analysis.engine_attempt_id is None:
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

        analysis = await self._session.get(GameAnalysis, game_analysis_id)
        if (analysis is None or analysis.engine_attempt_id is not None
                or analysis.score_version is not None):
            raise ValueError("Legacy commentary cannot write versioned engine analyses")

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
        summary: GameSummaryResult | None,
    ) -> None:
        """Write LLM commentary and summary to DB records."""
        result = await self._session.execute(
            select(GameAnalysis).where(GameAnalysis.id == game_analysis_id).with_for_update()
        )
        owner = result.scalar_one_or_none()
        if owner is None or owner.engine_attempt_id is not None or owner.score_version is not None:
            raise ValueError("Legacy commentary cannot write versioned engine analyses")
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
                analysis.coach_feedback = summary.coach_feedback

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
        score_before=evaluation.score_before.to_json() if evaluation.score_before else None,
        score_after=evaluation.score_after.to_json() if evaluation.score_after else None,
        played_line=evaluation.played_line,
    )


def _build_move_commentary_inputs(
    fens: list[str],
    evaluations: list[MoveEvaluation],
    opening_move_count: int = 0,
) -> list[MoveCommentaryInput]:
    """Combine per-position FENs with Stockfish evaluations into LLM inputs."""
    inputs: list[MoveCommentaryInput] = []
    move_labels = [_format_move_label(ev.move_number, ev.color, ev.move_san) for ev in evaluations]
    for idx, evaluation in enumerate(evaluations):
        classification = evaluation.classification
        fen = fens[idx] if idx < len(fens) else ""
        next_game_moves = move_labels[idx + 1 : idx + 1 + _NEXT_GAME_MOVES_CONTEXT]
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
                next_game_moves=next_game_moves,
            )
        )
    return inputs


def _format_move_label(move_number: int, color: str, move_san: str) -> str:
    color_sep = "." if color == "white" else "..."
    return f"{move_number}{color_sep}{move_san}"


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

    return GameSummaryInput(
        white_player=game.white_player,
        black_player=game.black_player,
        result=game.result,
        opening_name=game.opening_name,
        eco_code=game.eco_code,
        total_moves=len(evaluations),
        accuracy_white=None,
        accuracy_black=None,
        classification_counts=classification_counts,
        key_moments=key_moments,
    )


def _game_identity(parsed: ParsedGame) -> tuple:
    technical = {"playercolor", "annotator", "plycount", "analysis", "analysedby"}
    headers = tuple(sorted(
        (k, v.strip()) for k, v in parsed.headers.items() if k.lower() not in technical
    ))
    return headers, tuple(move.uci() for move in parsed.moves)


def _restore_evaluation(record: MoveAnalysis) -> MoveEvaluation:
    """Restore typed scores without ever guessing mate from legacy float fields."""
    candidates = [
        CandidateMove(
            move_san=item["move_san"], eval_cp=item["eval_cp"], pv_san=item.get("pv_san", []),
            score=EngineScore(**item["score"]) if item.get("score") else None,
        ) for item in (record.top_moves or [])
    ]
    return MoveEvaluation(
        move_number=record.move_number, color=record.color, move_san=record.move_san,
        best_move_san=record.best_move_san or "", eval_before=record.eval_before,
        eval_after=record.eval_after, centipawn_loss=record.centipawn_loss,
        classification=record.classification or "good", top_moves=candidates,
        score_before=EngineScore(**record.score_before) if record.score_before else None,
        score_after=EngineScore(**record.score_after) if record.score_after else None,
        played_line=record.played_line or [],
    )
