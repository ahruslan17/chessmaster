from __future__ import annotations

from unittest.mock import MagicMock, patch

import chess
import chess.engine
import pytest

from app.services.stockfish_analyzer import (
    CandidateMove,
    EngineScore,
    MoveEvaluation,
    StockfishAnalyzerService,
    _analyze_position,
    _build_candidates_san,
    _compute_centipawn_loss,
    classify_evaluation,
)
from app.utils.chess_helpers import classify_move


class TestEngineScore:
    @pytest.mark.parametrize("pov,expected", [(chess.WHITE, 50.0), (chess.BLACK, -50.0)])
    def test_cp_white_perspective(self, pov: chess.Color, expected: float) -> None:
        score = EngineScore.from_engine(chess.engine.PovScore(chess.engine.Cp(50), pov))
        assert score.to_json() == {
            "cp": expected, "mate": None, "mate_winner": None, "perspective": "white",
        }

    @pytest.mark.parametrize(
        "distance,pov,expected,winner",
        [(3, chess.WHITE, 3, "white"), (3, chess.BLACK, -3, "black"),
         (-4, chess.WHITE, -4, "black"), (-4, chess.BLACK, 4, "white")],
    )
    def test_mate_preserved(
        self, distance: int, pov: chess.Color, expected: int, winner: str,
    ) -> None:
        score = EngineScore.from_engine(chess.engine.PovScore(chess.engine.Mate(distance), pov))
        assert score.to_json() == {
            "cp": None, "mate": expected, "mate_winner": winner, "perspective": "white",
        }

    @pytest.mark.parametrize("pov,winner", [(chess.WHITE, "black"), (chess.BLACK, "white")])
    def test_terminal_mate_has_zero_distance(self, pov: chess.Color, winner: str) -> None:
        score = EngineScore.from_engine(chess.engine.PovScore(chess.engine.Mate(0), pov))
        assert score.mate == 0
        assert score.mate_winner == winner
        assert score.cp is None

    @pytest.mark.parametrize(
        "kwargs",
        [{}, {"mate": 0}, {"cp": 5, "mate": 2}, {"mate": 3, "mate_winner": "black"},
         {"cp": float("nan")}, {"cp": float("inf")}, {"mate": 1.5},
         {"cp": 1, "perspective": "black"}],
    )
    def test_invalid_score_rejected(self, kwargs: dict) -> None:
        with pytest.raises(ValueError):
            EngineScore(**kwargs)

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
        assert result[0].score == EngineScore(cp=30.0)

    def test_mate_candidate_keeps_distance(self) -> None:
        from app.services.stockfish_analyzer import _CandidateRaw

        raw = _CandidateRaw(
            move=chess.Move.from_uci("e2e4"),
            score=chess.engine.PovScore(chess.engine.Mate(-3), chess.BLACK),
            pv=[chess.Move.from_uci("e2e4")],
        )
        assert _build_candidates_san(chess.Board(), [raw])[0].score == EngineScore(mate=3)


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
        assert info.score == EngineScore(mate=0, mate_winner="white")

    def test_stalemate_is_cp_zero(self) -> None:
        board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        engine = MagicMock()
        info = _analyze_position(engine, board, chess.engine.Limit(depth=1), multipv=5)
        assert info.score == EngineScore(cp=0.0)
        engine.analyse.assert_not_called()

    def test_score_retained_without_pv(self) -> None:
        engine = MagicMock()
        engine.analyse.return_value = [{
            "score": chess.engine.PovScore(chess.engine.Mate(-7), chess.WHITE),
        }]
        info = _analyze_position(engine, chess.Board(), chess.engine.Limit(depth=1), 1)
        assert info.score == EngineScore(mate=-7)
        assert info.candidates == []

    def test_missing_engine_score_fails_instead_of_inventing_score(self) -> None:
        engine = MagicMock()
        engine.analyse.return_value = [{"pv": [chess.Move.from_uci("e2e4")]}]
        with pytest.raises(chess.engine.EngineError, match="Primary"):
            _analyze_position(engine, chess.Board(), chess.engine.Limit(depth=1), 1)

    @pytest.mark.parametrize("position_index", [0, 1])
    @pytest.mark.parametrize("omit_rank_one", [False, True])
    def test_rank_two_score_never_replaces_missing_primary_score(
        self, position_index: int, omit_rank_one: bool,
    ) -> None:
        engine = MagicMock()
        initial = [_make_mock_info(30, "e2e4")]
        after = [_make_mock_info(20, "e7e5")]
        primary_move = "e2e4" if position_index == 0 else "e7e5"
        secondary_move = "d2d4" if position_index == 0 else "d7d5"
        secondary = {**_make_mock_info(10, secondary_move), "multipv": 2}
        damaged = [secondary]
        if not omit_rank_one:
            damaged.append({"multipv": 1, "pv": [chess.Move.from_uci(primary_move)]})
        positions = [initial, after]
        positions[position_index] = damaged
        engine.analyse.side_effect = positions
        with pytest.raises(chess.engine.EngineError, match="Primary"):
            StockfishAnalyzerService()._analyze_with_engine(
                engine, [chess.Move.from_uci("e2e4")],
            )

    @pytest.mark.parametrize("position_index", [0, 1])
    def test_rank_two_pv_never_replaces_missing_primary_pv(self, position_index: int) -> None:
        engine = MagicMock()
        positions = [[_make_mock_info(30, "e2e4")], [_make_mock_info(20, "e7e5")]]
        primary_move = "e2e4" if position_index == 0 else "e7e5"
        secondary_move = "d2d4" if position_index == 0 else "d7d5"
        positions[position_index] = [
            {**_make_mock_info(10, secondary_move), "multipv": 2},
            {"multipv": 1, "score": chess.engine.PovScore(chess.engine.Cp(50), chess.WHITE),
             "move": chess.Move.from_uci(primary_move)},
        ]
        engine.analyse.side_effect = positions
        evaluation = StockfishAnalyzerService()._analyze_with_engine(
            engine, [chess.Move.from_uci("e2e4")],
        )[0]
        if position_index == 0:
            assert evaluation.best_move_san == ""
            assert evaluation.score_before == EngineScore(cp=50.0)
            assert [candidate.move_san for candidate in evaluation.top_moves] == ["d4"]
            assert evaluation.played_line == ["e4", "e5"]
        else:
            assert evaluation.best_move_san == "e4"
            assert evaluation.score_after == EngineScore(cp=50.0)
            assert evaluation.played_line == ["e4"]


@pytest.mark.parametrize("color", [chess.WHITE, chess.BLACK])
@pytest.mark.parametrize("transition", ["allow_mate", "lose_mate"])
def test_typed_transition_classification_bypasses_saturated_cp(
    color: chess.Color, transition: str,
) -> None:
    from app.services.stockfish_analyzer import _PositionInfo

    sign = 1 if color else -1
    if transition == "allow_mate":
        before = EngineScore(cp=-1500.0 * sign)
        after = EngineScore(mate=-sign)
        before_cp, after_cp = -1500.0 * sign, -9999.0 * sign
        expected = "blunder"
    else:
        before = EngineScore(mate=sign)
        after = EngineScore(cp=1500.0 * sign)
        before_cp, after_cp = 9999.0 * sign, 1500.0 * sign
        expected = "mistake"
    assert classify_move(before_cp, after_cp, color) == "best"
    assert classify_evaluation(before_cp, after_cp, color, before, after) == expected
    board = chess.Board()
    moves = [board.push_san("e4")]
    infos = [_PositionInfo(before_cp, score=before), _PositionInfo(after_cp, score=after)]
    if color == chess.BLACK:
        moves.append(board.push_san("e5"))
        infos.insert(0, _PositionInfo(0.0, score=EngineScore(cp=0.0)))
    evaluation = StockfishAnalyzerService()._build_evaluations(moves, infos)[-1]
    assert evaluation.classification == expected


@pytest.mark.parametrize("color", [chess.WHITE, chess.BLACK])
def test_preserved_mate_distance_change_not_an_error(color: chess.Color) -> None:
    sign = 1 if color else -1
    assert classify_evaluation(
        9999.0 * sign, 9992.0 * sign, color,
        EngineScore(mate=sign), EngineScore(mate=8 * sign),
    ) == "best"
    assert classify_evaluation(
        -9992.0 * sign, -9999.0 * sign, color,
        EngineScore(mate=-8 * sign), EngineScore(mate=-sign),
    ) == "best"


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
        assert json_data[0]["score"] is None  # Old floats cannot establish mate.

    def test_candidate_score_as_json(self) -> None:
        evaluation = MoveEvaluation(
            1, "white", "e4", "e4", 0.0, 0.0, 0.0, "best",
            top_moves=[CandidateMove("e4", 9997.0, ["e4"], EngineScore(mate=3))],
        )
        assert evaluation.top_moves_as_json()[0]["score"] == EngineScore(mate=3).to_json()

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
        assert evaluations[0].score_before == EngineScore(cp=30.0)
        assert evaluations[0].score_after == EngineScore(cp=25.0)
        assert evaluations[0].played_line == ["e4", "e5"]

        # Move 2: e5 (black)
        assert evaluations[1].move_san == "e5"
        assert evaluations[1].color == "black"
        assert evaluations[1].move_number == 1  # still move 1 in fullmove notation
        assert evaluations[1].played_line == ["e5", "Nf3"]

    @patch("app.services.stockfish_analyzer.chess.engine.SimpleEngine.popen_uci")
    def test_analyze_detects_blunder(self, mock_popen: MagicMock) -> None:
        """A move with a large win-chance drop should be classified as a blunder."""
        mock_engine = MagicMock()
        mock_popen.return_value.__enter__ = MagicMock(return_value=mock_engine)
        mock_popen.return_value.__exit__ = MagicMock(return_value=False)

        moves = [chess.Move.from_uci("e2e4")]

        # Position 0: eval +30 from white POV
        # Position 1 (after e4): eval -500 from white POV
        # PovScore(Cp(500), BLACK).pov(WHITE) = Cp(-500)
        # cp_loss for white = 30 - (-500) = 530 (large expected-points drop)
        mock_engine.analyse.side_effect = [
            [_make_mock_info(30, "d2d4", chess.WHITE)],
            [_make_mock_info(500, "e7e5", chess.BLACK)],
        ]

        analyzer = StockfishAnalyzerService(stockfish_path="/mock/stockfish", depth=10, multipv=1)
        evaluations = analyzer.analyze_game(moves)

        assert len(evaluations) == 1
        assert evaluations[0].classification == "blunder"
        assert evaluations[0].centipawn_loss == 530.0

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

    @patch("app.services.stockfish_analyzer.chess.engine.SimpleEngine.popen_uci")
    def test_progress_threads_and_position_history(self, mock_popen: MagicMock) -> None:
        engine = MagicMock()
        mock_popen.return_value.__enter__.return_value = engine
        histories: list[list[chess.Move]] = []

        def analyse(board: chess.Board, *args, **kwargs) -> list[dict]:
            histories.append(list(board.move_stack))
            return [{"score": chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE)}]

        engine.analyse.side_effect = analyse
        progress: list[tuple[int, int]] = []
        analyzer = StockfishAnalyzerService(stockfish_path="/mock/stockfish", threads=1)
        moves = [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")]
        analyzer.analyze_game(moves, lambda completed, total: progress.append((completed, total)))
        engine.configure.assert_called_once_with({"Threads": 1})
        assert progress == [(1, 3), (2, 3), (3, 3)]
        assert histories == [[], moves[:1], moves]

    @patch("app.services.stockfish_analyzer.chess.engine.SimpleEngine.popen_uci")
    def test_actual_line_not_alternative_and_mate_score(self, mock_popen: MagicMock) -> None:
        engine = MagicMock()
        mock_popen.return_value.__enter__.return_value = engine
        engine.analyse.side_effect = [
            [_make_mock_info(30, "d2d4")],
            [{"score": chess.engine.PovScore(chess.engine.Mate(3), chess.BLACK),
              "pv": [chess.Move.from_uci("e7e5"), chess.Move.from_uci("g1f3")]}],
        ]
        analyzer = StockfishAnalyzerService(stockfish_path="/mock/stockfish")
        ev = analyzer.analyze_game([chess.Move.from_uci("e2e4")])[0]
        assert ev.best_move_san == "d4"
        assert ev.played_line == ["e4", "e5", "Nf3"]
        assert ev.score_after == EngineScore(mate=-3)

    def test_played_checkmate_has_no_fabricated_continuation(self) -> None:
        from app.services.stockfish_analyzer import _PositionInfo

        board = chess.Board()
        moves = [board.push_san(san) for san in ("f3", "e5", "g4", "Qh4#")]
        infos = [_PositionInfo(0.0, score=EngineScore(cp=0.0)) for _ in range(4)]
        infos.append(_PositionInfo(-10000.0, score=EngineScore(mate=0, mate_winner="black")))
        ev = StockfishAnalyzerService()._build_evaluations(moves, infos)[-1]
        assert ev.score_after == EngineScore(mate=0, mate_winner="black")
        assert ev.played_line == ["Qh4#"]
