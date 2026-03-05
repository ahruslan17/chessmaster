"""Tests for OpeningMatcher."""

from __future__ import annotations

import tempfile
from pathlib import Path

import chess

from app.services.opening_matcher import OpeningMatcher, _pgn_to_move_sans


def test_pgn_to_move_sans() -> None:
    assert _pgn_to_move_sans("1. Nh3 d5 2. g3 e5 3. f4") == [
        "Nh3",
        "d5",
        "g3",
        "e5",
        "f4",
    ]
    assert _pgn_to_move_sans("1. Nh3") == ["Nh3"]
    assert _pgn_to_move_sans("1. e4 e5 2. Nf3 Nc6") == ["e4", "e5", "Nf3", "Nc6"]


def test_longest_prefix_match_amar_paris_gambit() -> None:
    """Game 1. Nh3 d5 2. g3 e5 3. f4 should match Paris Gambit, not just Amar."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tsv = Path(tmpdir) / "a.tsv"
        tsv.write_text(
            "eco\tname\tpgn\n"
            "A00\tAmar Opening\t1. Nh3\n"
            "A00\tAmar Opening: Paris Gambit\t1. Nh3 d5 2. g3 e5 3. f4\n",
            encoding="utf-8",
        )
        matcher = OpeningMatcher(openings_dir=Path(tmpdir))
        board = chess.Board()
        sans = ["Nh3", "d5", "g3", "e5", "f4"]
        moves = []
        for san in sans:
            move = board.parse_san(san)
            moves.append(move)
            board.push(move)
        result = matcher.match(moves)
        assert result is not None
        assert result.name == "Amar Opening: Paris Gambit"
        assert result.eco_code == "A00"
        assert result.move_count == 5
