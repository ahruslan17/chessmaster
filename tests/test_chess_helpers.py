from __future__ import annotations

import chess

from app.utils.chess_helpers import (
    classify_move,
    compute_accuracy,
    moves_to_fens,
    pv_to_san,
    score_to_centipawns,
    win_chance_loss,
)

# ---------------------------------------------------------------------------
# classify_move
# ---------------------------------------------------------------------------


class TestClassifyMove:
    def test_best_move(self) -> None:
        assert classify_move(0, -20, chess.WHITE) == "best"

    def test_good_move(self) -> None:
        assert classify_move(0, -40, chess.WHITE) == "good"

    def test_inaccuracy(self) -> None:
        assert classify_move(0, -90, chess.WHITE) == "inaccuracy"

    def test_mistake(self) -> None:
        assert classify_move(0, -170, chess.WHITE) == "mistake"

    def test_blunder(self) -> None:
        assert classify_move(0, -300, chess.WHITE) == "blunder"

    def test_black_perspective(self) -> None:
        assert classify_move(0, 170, chess.BLACK) == "mistake"


class TestWinChanceLoss:
    def test_loss_is_clamped_to_non_negative(self) -> None:
        assert win_chance_loss(0, 50, chess.WHITE) == 0.0


# ---------------------------------------------------------------------------
# score_to_centipawns
# ---------------------------------------------------------------------------


class TestScoreToCentipawns:
    def test_white_positive_cp(self) -> None:
        import chess.engine

        score = chess.engine.PovScore(chess.engine.Cp(50), chess.WHITE)
        assert score_to_centipawns(score, chess.WHITE) == 50.0

    def test_black_pov_conversion(self) -> None:
        import chess.engine

        # Black is +100 means white is -100
        score = chess.engine.PovScore(chess.engine.Cp(100), chess.BLACK)
        assert score_to_centipawns(score, chess.WHITE) == -100.0


# ---------------------------------------------------------------------------
# pv_to_san
# ---------------------------------------------------------------------------


class TestPvToSan:
    def test_converts_pv_to_san(self) -> None:
        board = chess.Board()
        pv = [
            chess.Move.from_uci("e2e4"),
            chess.Move.from_uci("e7e5"),
            chess.Move.from_uci("g1f3"),
        ]
        result = pv_to_san(board, pv)
        assert result == ["e4", "e5", "Nf3"]

    def test_respects_max_moves(self) -> None:
        board = chess.Board()
        pv = [
            chess.Move.from_uci("e2e4"),
            chess.Move.from_uci("e7e5"),
            chess.Move.from_uci("g1f3"),
            chess.Move.from_uci("b8c6"),
        ]
        result = pv_to_san(board, pv, max_moves=2)
        assert result == ["e4", "e5"]


# ---------------------------------------------------------------------------
# moves_to_fens
# ---------------------------------------------------------------------------


class TestMovesToFens:
    def test_returns_fen_before_each_move(self) -> None:
        board = chess.Board()
        e4 = board.parse_san("e4")
        board.push(e4)
        e5 = board.parse_san("e5")
        moves = [e4, e5]
        fens = moves_to_fens(moves)
        assert len(fens) == 2
        assert fens[0] == chess.STARTING_FEN
        assert "4P3" in fens[1]  # position after e4, before e5

    def test_empty_moves(self) -> None:
        assert moves_to_fens([]) == []


# ---------------------------------------------------------------------------
# compute_accuracy
# ---------------------------------------------------------------------------


class TestComputeAccuracy:
    def test_perfect_accuracy(self) -> None:
        assert compute_accuracy([]) == 100.0
        assert compute_accuracy([0.0, 0.0]) == 100.0

    def test_reasonable_losses(self) -> None:
        # Small losses -> higher accuracy than blunders
        acc = compute_accuracy([5.0, 15.0, 10.0])
        assert acc > 60
        assert acc <= 100

    def test_blunders_reduce_accuracy(self) -> None:
        acc = compute_accuracy([100.0, 150.0])
        assert acc < 80
