from __future__ import annotations

from unittest.mock import MagicMock, patch

import chess
import chess.engine

from app.services.stockfish_analyzer import (
    CandidateMove,
    MoveEvaluation,
    StockfishAnalyzerService,
    _analyze_position,
    _build_candidates_san,
    _compute_centipawn_loss,
)

# ---------------------------------------------------------------------------
# _compute_centipawn_loss
# ---------------------------------------------------------------------------


class TestComputeCentipawnLoss:
    def test_white_good_move(self) -> None:
        # White's eval stays the same → no loss
        assert _compute_centipawn_loss(100.0, 100.0, chess.WHITE) == 0.0

    def test_white_bad_move(self) -> None:
        # White's eval drops from 100 to 0 → 100 cp loss
        assert _compute_centipawn_loss(100.0, 0.0, chess.WHITE) == 100.0

    def test_white_move_improves(self) -> None:
        # White's eval improves → loss clamped to 0
        assert _compute_centipawn_loss(100.0, 150.0, chess.WHITE) == 0.0

    def test_black_good_move(self) -> None:
        # Black's move maintains eval → no loss
        assert _compute_centipawn_loss(-100.0, -100.0, chess.BLACK) == 0.0

    def test_black_bad_move(self) -> None:
        # Eval goes from -100 (good for black) to 0 → 100 cp loss for black
        assert _compute_centipawn_loss(-100.0, 0.0, chess.BLACK) == 100.0


# ---------------------------------------------------------------------------
# _build_candidates_san
# ---------------------------------------------------------------------------


class TestBuildCandidatesSan:
    def test_converts_moves_to_san(self) -> None:
        from app.services.stockfish_analyzer import _CandidateRaw

        board = chess.Board()
        raw = _CandidateRaw(
            move=chess.Move.from_uci("e2e4"),
            score=chess.engine.PovScore(chess.engine.Cp(30), chess.WHITE),
            pv=[chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")],
        )
        result = _build_candidates_san(board, [raw])

        assert len(result) == 1
        assert result[0].move_san == "e4"
        assert result[0].pv_san == ["e4", "e5"]
        assert result[0].eval_cp == 30.0


class TestAnalyzePosition:
    def test_checkmate_position_returns_mate_eval(self) -> None:
        board = chess.Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1")
        info = _analyze_position(
            engine=MagicMock(),
            board=board,
            limit=chess.engine.Limit(depth=1),
            multipv=5,
        )

        assert info.candidates == []
        assert info.eval_white_cp > 9000


# ---------------------------------------------------------------------------
# MoveEvaluation serialization
# ---------------------------------------------------------------------------


class TestMoveEvaluationSerialization:
    def test_top_moves_as_json(self) -> None:
        evaluation = MoveEvaluation(
            move_number=1,
            color="white",
            move_san="e4",
            best_move_san="e4",
            eval_before=30.0,
            eval_after=30.0,
            centipawn_loss=0.0,
            classification="best",
            top_moves=[
                CandidateMove(move_san="e4", eval_cp=30.0, pv_san=["e4", "e5"]),
                CandidateMove(move_san="d4", eval_cp=25.0, pv_san=["d4", "d5"]),
            ],
        )
        json_data = evaluation.top_moves_as_json()
        assert len(json_data) == 2
        assert json_data[0]["move_san"] == "e4"
        assert json_data[0]["eval_cp"] == 30.0
        assert json_data[0]["pv_san"] == ["e4", "e5"]

    def test_continuation_lines_as_json(self) -> None:
        evaluation = MoveEvaluation(
            move_number=1,
            color="white",
            move_san="e4",
            best_move_san="e4",
            eval_before=30.0,
            eval_after=30.0,
            centipawn_loss=0.0,
            classification="best",
            top_moves=[
                CandidateMove(move_san="e4", eval_cp=30.0, pv_san=["e4", "e5"]),
            ],
        )
        lines = evaluation.continuation_lines_as_json()
        assert lines == {"e4": ["e4", "e5"]}


# ---------------------------------------------------------------------------
# StockfishAnalyzerService.analyze_game (mocked engine)
# ---------------------------------------------------------------------------


def _make_mock_info(
    eval_cp: int,
    first_move_uci: str,
    color: chess.Color = chess.WHITE,
) -> dict:
    """Create a mock engine info dict."""
    move = chess.Move.from_uci(first_move_uci)
    return {
        "score": chess.engine.PovScore(chess.engine.Cp(eval_cp), color),
        "pv": [move],
    }


class TestStockfishAnalyzerServiceMocked:
    """Test the analyzer with a mocked Stockfish engine."""

    @patch("app.services.stockfish_analyzer.chess.engine.SimpleEngine.popen_uci")
    def test_analyze_simple_game(self, mock_popen: MagicMock) -> None:
        """Test analysis of a 2-move game (1. e4 e5) with mocked engine."""
        mock_engine = MagicMock()
        mock_popen.return_value.__enter__ = MagicMock(return_value=mock_engine)
        mock_popen.return_value.__exit__ = MagicMock(return_value=False)

        moves = [
            chess.Move.from_uci("e2e4"),
            chess.Move.from_uci("e7e5"),
        ]

        # Mock analyse calls for 3 positions (initial, after e4, after e5)
        # Position 0 (initial): best is e4 with eval +30
        # Position 1 (after e4): best is e5 with eval +25 (from white's POV)
        # Position 2 (after e5): eval +30 (from white's POV)
        mock_engine.analyse.side_effect = [
            # Initial position (white to move): +30, best e4
            [_make_mock_info(30, "e2e4", chess.WHITE)],
            # After e4 (black to move): +25 from side-to-move (black) POV
            [_make_mock_info(-25, "e7e5", chess.BLACK)],
            # After e5 (white to move): +30
            [_make_mock_info(30, "g1f3", chess.WHITE)],
        ]

        analyzer = StockfishAnalyzerService(
            stockfish_path="/mock/stockfish",
            depth=10,
            multipv=1,
        )
        evaluations = analyzer.analyze_game(moves)

        assert len(evaluations) == 2

        # Move 1: e4 (white)
        assert evaluations[0].move_san == "e4"
        assert evaluations[0].color == "white"
        assert evaluations[0].move_number == 1

        # Move 2: e5 (black)
        assert evaluations[1].move_san == "e5"
        assert evaluations[1].color == "black"
        assert evaluations[1].move_number == 1  # still move 1 in fullmove notation

    @patch("app.services.stockfish_analyzer.chess.engine.SimpleEngine.popen_uci")
    def test_analyze_detects_blunder(self, mock_popen: MagicMock) -> None:
        """A move that drops 200 cp should be classified as a blunder."""
        mock_engine = MagicMock()
        mock_popen.return_value.__enter__ = MagicMock(return_value=mock_engine)
        mock_popen.return_value.__exit__ = MagicMock(return_value=False)

        moves = [chess.Move.from_uci("e2e4")]

        # Position 0: eval +30 from white POV
        # Position 1 (after e4): eval -170 from white POV
        # PovScore(Cp(170), BLACK).pov(WHITE) = Cp(-170)
        # cp_loss for white = 30 - (-170) = 200 → blunder
        mock_engine.analyse.side_effect = [
            [_make_mock_info(30, "d2d4", chess.WHITE)],
            [_make_mock_info(170, "e7e5", chess.BLACK)],
        ]

        analyzer = StockfishAnalyzerService(stockfish_path="/mock/stockfish", depth=10, multipv=1)
        evaluations = analyzer.analyze_game(moves)

        assert len(evaluations) == 1
        assert evaluations[0].classification == "blunder"
        assert evaluations[0].centipawn_loss == 200.0

    @patch("app.services.stockfish_analyzer.chess.engine.SimpleEngine.popen_uci")
    def test_uses_time_limit_when_configured(self, mock_popen: MagicMock) -> None:
        """When time_limit is set, engine receives Limit(time=X) instead of depth."""
        mock_engine = MagicMock()
        mock_popen.return_value.__enter__ = MagicMock(return_value=mock_engine)
        mock_popen.return_value.__exit__ = MagicMock(return_value=False)
        mock_engine.analyse.side_effect = [
            [_make_mock_info(30, "e2e4", chess.WHITE)],
            [_make_mock_info(25, "e7e5", chess.BLACK)],
        ]

        analyzer = StockfishAnalyzerService(
            stockfish_path="/mock/stockfish",
            depth=10,
            time_limit=2.5,
            threads=2,
        )
        analyzer.analyze_game([chess.Move.from_uci("e2e4")])

        call_args = mock_engine.analyse.call_args
        limit = call_args[0][1]
        assert limit.time == 2.5
