from __future__ import annotations

import hashlib
import math

import chess
import chess.engine

# --- Classification thresholds (centipawns) ---
# Aligned with Lichess classic cp-based scheme (see e.g. chess.stackexchange.com/q/12451).
# Chess.com uses stricter blunder threshold (~500 cp).
BEST_THRESHOLD = 10
GOOD_THRESHOLD = 30
INACCURACY_THRESHOLD = 50
MISTAKE_THRESHOLD = 100
BLUNDER_THRESHOLD = 300

# Conventional centipawn value used to represent mate scores.
MATE_SCORE_CP = 10_000


def classify_move(centipawn_loss: float) -> str:
    """Classify a move based on its centipawn loss.

    Thresholds (Lichess-style):
      - |cp_loss| <  10  -> best
      - |cp_loss| <  30  -> good
      - |cp_loss| <  50  -> inaccuracy
      - |cp_loss| < 300  -> mistake
      - |cp_loss| >= 300 -> blunder
    """
    abs_loss = abs(centipawn_loss)
    if abs_loss < BEST_THRESHOLD:
        return "best"
    if abs_loss < GOOD_THRESHOLD:
        return "good"
    if abs_loss < INACCURACY_THRESHOLD:
        return "inaccuracy"
    if abs_loss < BLUNDER_THRESHOLD:
        return "mistake"
    return "blunder"


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
