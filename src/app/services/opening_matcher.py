"""Matches game moves to ECO openings database using longest-prefix rule."""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import chess

logger = logging.getLogger(__name__)

# Default path relative to project root (works when cwd is project root or /app in Docker)
_OPENINGS_DIR = Path("chess-openings")
_TSV_FILES = ["a.tsv", "b.tsv", "c.tsv", "d.tsv", "e.tsv"]

# Tokens to skip when parsing PGN move strings (move numbers, results)
_MOVE_NUMBER_PATTERN = re.compile(r"^\d+\.$")
_RESULT_TOKENS = frozenset({"1-0", "0-1", "1/2-1/2", "*"})


@dataclass(frozen=True)
class OpeningMatch:
    """ECO code, name, and move count for a matched opening."""

    eco_code: str
    name: str
    move_count: int  # number of half-moves (plies) in the opening


def _pgn_to_move_sans(pgn_str: str) -> list[str]:
    """Extract SAN moves from a PGN move string like '1. Nh3 d5 2. g3 e5 3. f4'.

    Returns a list of move tokens in order.
    """
    moves: list[str] = []
    for token in pgn_str.split():
        token = token.strip()
        if not token:
            continue
        if _MOVE_NUMBER_PATTERN.match(token) or token in _RESULT_TOKENS:
            continue
        moves.append(token)
    return moves


def _game_moves_to_sans(moves: list[chess.Move]) -> list[str]:
    """Convert a game's move list to SAN notation."""
    board = chess.Board()
    sans: list[str] = []
    for move in moves:
        try:
            sans.append(board.san(move))
            board.push(move)
        except (ValueError, AssertionError) as e:
            logger.debug("Failed to convert move %s to SAN: %s", move, e)
            break
    return sans


def _load_openings_data(dir_path: Path) -> list[tuple[list[str], str, str]]:
    """Load all TSV files and return [(move_sans, eco_code, name), ...]."""
    entries: list[tuple[list[str], str, str]] = []

    for filename in _TSV_FILES:
        tsv_path = dir_path / filename
        if not tsv_path.exists():
            logger.warning("Openings file not found: %s", tsv_path)
            continue
        try:
            with open(tsv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    eco = (row.get("eco") or "").strip()
                    name = (row.get("name") or "").strip()
                    pgn = (row.get("pgn") or "").strip()
                    if not eco or not name or not pgn:
                        continue
                    move_sans = _pgn_to_move_sans(pgn)
                    if not move_sans:
                        continue
                    entries.append((move_sans, eco, name))
        except (OSError, csv.Error) as e:
            logger.warning("Failed to load openings from %s: %s", tsv_path, e)

    return entries


def _find_longest_prefix_match(
    game_sans: list[str],
    openings: list[tuple[list[str], str, str]],
) -> OpeningMatch | None:
    """Find the opening whose move sequence is a prefix of the game and has the longest match."""
    best: tuple[int, str, str] | None = None

    for opening_sans, eco, name in openings:
        if len(opening_sans) > len(game_sans):
            continue
        if opening_sans == game_sans[: len(opening_sans)]:
            if best is None or len(opening_sans) > best[0]:
                best = (len(opening_sans), eco, name)

    if best is None:
        return None
    move_count, eco, name = best
    return OpeningMatch(eco_code=eco, name=name, move_count=move_count)


class OpeningMatcher:
    """Matches game moves to ECO openings from TSV database.

    Uses longest-prefix matching: when multiple openings match (opening moves
    are a prefix of the game), selects the most specific (longest) match.
    """

    def __init__(self, openings_dir: Path | None = None) -> None:
        self._dir = openings_dir or _OPENINGS_DIR
        self._entries: list[tuple[list[str], str, str]] | None = None

    def _ensure_loaded(self) -> list[tuple[list[str], str, str]]:
        if self._entries is None:
            self._entries = _load_openings_data(self._dir)
            logger.info("Loaded %d opening variants from %s", len(self._entries), self._dir)
        return self._entries

    def match(self, moves: list[chess.Move]) -> OpeningMatch | None:
        """Find the best-matching opening for the given game moves.

        Returns the most specific (longest matching prefix) opening, or None
        if no opening matches.
        """
        if not moves:
            return None
        entries = self._ensure_loaded()
        game_sans = _game_moves_to_sans(moves)
        return _find_longest_prefix_match(game_sans, entries)
