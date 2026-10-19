from __future__ import annotations

import hashlib
import math

import chess
import chess.engine

# --- Classification thresholds (expected points loss / win chance loss) ---
# Player-facing thresholds inspired by common platform UX:
#   best      <= 0.02
#   good      <= 0.05
#   inaccuracy<= 0.10
#   mistake   <= 0.20
#   blunder    > 0.20
BEST_LOSS_THRESHOLD = 0.02
GOOD_LOSS_THRESHOLD = 0.05
INACCURACY_LOSS_THRESHOLD = 0.10
MISTAKE_LOSS_THRESHOLD = 0.20

# Legacy classification surrogate only; not a mate distance or a public score.
MATE_SCORE_CP = 10_000


def classify_move(
    eval_before_white_cp: float,
    eval_after_white_cp: float,
    color: chess.Color,
) -> str:
    """Classify a move by loss of win chance (expected points).

    eval_before_white_cp / eval_after_white_cp are Stockfish evals from white's
    perspective. ``color`` is the side that made the move.
    """
    loss = win_chance_loss(eval_before_white_cp, eval_after_white_cp, color)
    # Search instability can improve the evaluation. It is not evidence of brilliance.
    if loss <= BEST_LOSS_THRESHOLD:
        return "best"
    if loss <= GOOD_LOSS_THRESHOLD:
        return "good"
    if loss <= INACCURACY_LOSS_THRESHOLD:
        return "inaccuracy"
    if loss <= MISTAKE_LOSS_THRESHOLD:
        return "mistake"
    return "blunder"


def win_chance_loss(
    eval_before_white_cp: float,
    eval_after_white_cp: float,
    color: chess.Color,
) -> float:
    """Loss in winning chances for the side that moved, clamped to [0, 1]."""
    if color == chess.WHITE:
        before = win_chance_from_eval(eval_before_white_cp)
        after = win_chance_from_eval(eval_after_white_cp)
    else:
        before = win_chance_from_eval(-eval_before_white_cp)
        after = win_chance_from_eval(-eval_after_white_cp)
    return max(0.0, before - after)


def win_chance_from_eval(eval_white_cp: float) -> float:
    """Convert centipawn eval to win chance in [0, 1] via logistic curve."""
    return 1.0 / (1.0 + math.exp(-0.00368208 * eval_white_cp))


def score_to_centipawns(pov_score: chess.engine.PovScore, color: chess.Color) -> float:
    """Convert a PovScore to centipawns from the perspective of *color*.

    Mate scores are mapped to +/- MATE_SCORE_CP.
    """
    score = pov_score.pov(color)
    centipawns = score.score(mate_score=MATE_SCORE_CP)
    if centipawns is None:
        return 0.0
    return float(centipawns)


def pv_to_san(
    board: chess.Board, pv_moves: list[chess.Move], max_moves: int = 10
) -> list[str]:
    """Convert a principal variation (list of Moves) to SAN notation.

    Returns at most *max_moves* moves. The board is not mutated.
    """
    san_list: list[str] = []
    temp_board = board.copy()
    for move in pv_moves[:max_moves]:
        if not temp_board.is_legal(move):
            break
        try:
            san_list.append(temp_board.san(move))
            temp_board.push(move)
        except (ValueError, AssertionError):
            break
    return san_list


def moves_fingerprint(moves: list[chess.Move]) -> str:
    """Compute a stable hash of the move sequence for duplicate detection.

    Uses SAN notation so identical games (regardless of PGN formatting)
    produce the same fingerprint.
    """
    if not moves:
        return hashlib.sha256(b"").hexdigest()
    board = chess.Board()
    sans: list[str] = []
    for move in moves:
        try:
            sans.append(board.san(move))
            board.push(move)
        except (ValueError, AssertionError):
            break
    canonical = " ".join(sans)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def moves_to_fens(moves: list[chess.Move]) -> list[str]:
    """Replay a game and return the FEN for each position before each move.

    Returns a list of length ``len(moves)`` where ``fens[i]`` is the board
    state **before** ``moves[i]`` was played.
    """
    board = chess.Board()
    fens: list[str] = []
    for move in moves:
        fens.append(board.fen())
        board.push(move)
    return fens


def compute_accuracy(centipawn_losses: list[float]) -> float:
    """Compute move accuracy percentage from centipawn losses.

    Uses an exponential model (adapted from win-probability analysis):
        per-move accuracy ≈ 103.1668 * e^(-0.04354 * |cp_loss|) - 3.1668
    Averaged across all moves and rounded to one decimal place.

    Returns a value in [0.0, 100.0].
    """
    if not centipawn_losses:
        return 100.0

    total = 0.0
    for cp_loss in centipawn_losses:
        per_move = 103.1668 * math.exp(-0.04354 * abs(cp_loss)) - 3.1668
        total += max(0.0, per_move)

    return round(total / len(centipawn_losses), 1)
