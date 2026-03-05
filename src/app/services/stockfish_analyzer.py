from __future__ import annotations

import logging
from dataclasses import dataclass, field

import chess
import chess.engine

from app.core.config import settings
from app.utils.chess_helpers import (
    classify_move,
    pv_to_san,
    score_to_centipawns,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes for analysis output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateMove:
    """A single candidate move returned by Stockfish multipv analysis."""

    move_san: str
    eval_cp: float  # centipawns from white's perspective
    pv_san: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MoveEvaluation:
    """Complete evaluation of one player move in a game."""

    move_number: int
    color: str  # "white" | "black"
    move_san: str
    best_move_san: str
    eval_before: float  # centipawns from white's perspective
    eval_after: float  # centipawns from white's perspective
    centipawn_loss: float  # always >= 0
    classification: str
    top_moves: list[CandidateMove] = field(default_factory=list)

    def top_moves_as_json(self) -> list[dict[str, object]]:
        """Serialize top_moves for JSONB storage."""
        return [
            {"move_san": cm.move_san, "eval_cp": cm.eval_cp, "pv_san": cm.pv_san}
            for cm in self.top_moves
        ]

    def continuation_lines_as_json(self) -> dict[str, list[str]]:
        """Serialize PV lines for JSONB storage (move_san -> continuation)."""
        return {cm.move_san: cm.pv_san for cm in self.top_moves}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PositionInfo:
    """Raw analysis result for a single board position."""

    eval_white_cp: float  # centipawns from white's perspective
    candidates: list[_CandidateRaw] = field(default_factory=list)


@dataclass(frozen=True)
class _CandidateRaw:
    """Raw candidate move data before SAN conversion."""

    move: chess.Move
    score: chess.engine.PovScore
    pv: list[chess.Move]


def _analyze_position(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    limit: chess.engine.Limit,
    multipv: int,
) -> _PositionInfo:
    """Run Stockfish multipv analysis on a single position."""
    effective_multipv = min(multipv, len(list(board.legal_moves)))
    if effective_multipv == 0:
        # No legal moves (checkmate or stalemate)
        return _PositionInfo(eval_white_cp=0.0, candidates=[])

    infos = engine.analyse(
        board,
        limit,
        multipv=effective_multipv,
    )

    # engine.analyse with multipv returns a list
    if not isinstance(infos, list):
        infos = [infos]

    candidates: list[_CandidateRaw] = []
    for info in infos:
        pov_score: chess.engine.PovScore = info["score"]
        pv_moves: list[chess.Move] = info.get("pv", [])
        first_move = pv_moves[0] if pv_moves else info.get("move")
        if first_move is None:
            continue
        candidates.append(_CandidateRaw(move=first_move, score=pov_score, pv=pv_moves))

    best_eval = score_to_centipawns(candidates[0].score, chess.WHITE) if candidates else 0.0
    return _PositionInfo(eval_white_cp=best_eval, candidates=candidates)


def _build_candidates_san(
    board: chess.Board,
    candidates: list[_CandidateRaw],
) -> list[CandidateMove]:
    """Convert raw candidate data to SAN-based CandidateMove objects."""
    result: list[CandidateMove] = []
    for raw in candidates:
        move_san = board.san(raw.move)
        eval_cp = score_to_centipawns(raw.score, chess.WHITE)
        pv_san = pv_to_san(board, raw.pv)
        result.append(CandidateMove(move_san=move_san, eval_cp=eval_cp, pv_san=pv_san))
    return result


def _compute_centipawn_loss(
    eval_before_white: float,
    eval_after_white: float,
    color: chess.Color,
) -> float:
    """Compute centipawn loss for a move, always >= 0.

    eval_before and eval_after are both from white's perspective.
    For white: loss = eval_before - eval_after
    For black: loss = eval_after - eval_before
    """
    if color == chess.WHITE:
        raw_loss = eval_before_white - eval_after_white
    else:
        raw_loss = eval_after_white - eval_before_white
    return max(0.0, raw_loss)


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------


class StockfishAnalyzerService:
    """Analyzes chess games using Stockfish via python-chess UCI protocol.

    Opens and closes the engine for each ``analyze_game`` call to ensure
    clean process lifecycle and safe usage inside Celery workers.

    Supports either depth-limited or time-limited analysis. When
    ``time_limit`` is set, the engine uses per-position time instead of
    fixed depth for better responsiveness on long games.
    """

    def __init__(
        self,
        stockfish_path: str = settings.stockfish_path,
        depth: int = settings.stockfish_depth,
        multipv: int = settings.stockfish_multipv,
        time_limit: float | None = settings.stockfish_time_limit,
        threads: int = settings.stockfish_threads,
    ) -> None:
        self._path = stockfish_path
        self._depth = depth
        self._multipv = multipv
        self._time_limit = time_limit
        self._threads = threads

    def analyze_game(self, moves: list[chess.Move]) -> list[MoveEvaluation]:
        """Analyze every move in a game and return per-move evaluations.

        Opens a fresh Stockfish process, replays the game, evaluates each
        position, and computes centipawn losses and move classifications.
        """
        limit_desc = f"time={self._time_limit}s" if self._time_limit else f"depth={self._depth}"
        logger.info(
            "Starting Stockfish analysis: %d moves, %s, threads=%d",
            len(moves),
            limit_desc,
            self._threads,
        )

        with chess.engine.SimpleEngine.popen_uci(self._path) as engine:
            if self._threads > 1:
                try:
                    engine.configure({"Threads": self._threads})
                except Exception as exc:
                    logger.warning("Could not set Stockfish Threads option: %s", exc)
            return self._analyze_with_engine(engine, moves)

    # ------------------------------------------------------------------
    # Internal analysis pipeline
    # ------------------------------------------------------------------

    def _analyze_with_engine(
        self,
        engine: chess.engine.SimpleEngine,
        moves: list[chess.Move],
    ) -> list[MoveEvaluation]:
        """Core analysis loop: evaluate every position, then build evaluations."""
        position_infos = self._collect_position_evals(engine, moves)
        return self._build_evaluations(moves, position_infos)

    def _get_analysis_limit(self) -> chess.engine.Limit:
        """Build the analysis limit (depth or time) from config."""
        if self._time_limit is not None and self._time_limit > 0:
            return chess.engine.Limit(time=self._time_limit)
        return chess.engine.Limit(depth=self._depth)

    def _collect_position_evals(
        self,
        engine: chess.engine.SimpleEngine,
        moves: list[chess.Move],
    ) -> list[_PositionInfo]:
        """Evaluate N+1 positions (initial + after each move)."""
        board = chess.Board()
        infos: list[_PositionInfo] = []
        limit = self._get_analysis_limit()

        # Analyze initial position
        infos.append(_analyze_position(engine, board, limit, self._multipv))

        # Analyze position after each move
        for move in moves:
            board.push(move)
            infos.append(_analyze_position(engine, board, limit, self._multipv))

        logger.info("Collected evaluations for %d positions", len(infos))
        return infos

    def _build_evaluations(
        self,
        moves: list[chess.Move],
        position_infos: list[_PositionInfo],
    ) -> list[MoveEvaluation]:
        """Build MoveEvaluation objects from position analysis data."""
        board = chess.Board()
        evaluations: list[MoveEvaluation] = []

        for idx, move in enumerate(moves):
            info_before = position_infos[idx]
            info_after = position_infos[idx + 1]
            color = board.turn
            color_str = "white" if color == chess.WHITE else "black"

            move_san = board.san(move)
            best_move_san = self._get_best_move_san(board, info_before)
            top_moves = _build_candidates_san(board, info_before.candidates)

            cp_loss = _compute_centipawn_loss(
                info_before.eval_white_cp,
                info_after.eval_white_cp,
                color,
            )

            evaluations.append(
                MoveEvaluation(
                    move_number=board.fullmove_number,
                    color=color_str,
                    move_san=move_san,
                    best_move_san=best_move_san,
                    eval_before=info_before.eval_white_cp,
                    eval_after=info_after.eval_white_cp,
                    centipawn_loss=round(cp_loss, 1),
                    classification=classify_move(cp_loss),
                    top_moves=top_moves,
                )
            )

            board.push(move)

        logger.info(
            "Built %d move evaluations (blunders=%d, mistakes=%d)",
            len(evaluations),
            sum(1 for ev in evaluations if ev.classification == "blunder"),
            sum(1 for ev in evaluations if ev.classification == "mistake"),
        )
        return evaluations

    @staticmethod
    def _get_best_move_san(board: chess.Board, info: _PositionInfo) -> str:
        """Extract the best move in SAN from position analysis."""
        if not info.candidates:
            return ""
        return board.san(info.candidates[0].move)
