from __future__ import annotations

from datetime import date

import chess
import pytest

from app.services.pgn_parser import PGNParserService, _parse_pgn_date


@pytest.fixture()
def parser() -> PGNParserService:
    return PGNParserService()


# ---------------------------------------------------------------------------
# PGNParserService.parse_pgn
# ---------------------------------------------------------------------------


class TestParsePgn:
    def test_single_game(self, parser: PGNParserService, sample_pgn_single: str) -> None:
        games = parser.parse_pgn(sample_pgn_single)
        assert len(games) == 1

        game = games[0]
        assert game.white_player == "Player1"
        assert game.black_player == "Player2"
        assert game.result == "1-0"
        assert game.eco_code == "C50"
        assert game.opening_name == "Italian Game"
        assert game.time_control == "600+5"
        assert game.played_at == date(2024, 6, 15)

    def test_single_game_has_moves(self, parser: PGNParserService, sample_pgn_single: str) -> None:
        games = parser.parse_pgn(sample_pgn_single)
        game = games[0]
        # 5 full moves = 10 half-moves
        assert len(game.moves) == 10
        # First move should be e2e4
        assert game.moves[0] == chess.Move.from_uci("e2e4")

    def test_multiple_games(self, parser: PGNParserService, sample_pgn_multi: str) -> None:
        games = parser.parse_pgn(sample_pgn_multi)
        assert len(games) == 2

        assert games[0].white_player == "Alice"
        assert games[0].result == "1-0"
        assert len(games[0].moves) == 4  # 2 full moves

        assert games[1].white_player == "Charlie"
        assert games[1].result == "0-1"
        assert len(games[1].moves) == 4

    def test_minimal_game(self, parser: PGNParserService, sample_pgn_minimal: str) -> None:
        games = parser.parse_pgn(sample_pgn_minimal)
        assert len(games) == 1

        game = games[0]
        assert game.white_player == "?"
        assert game.black_player == "?"
        assert game.result == "*"
        assert game.opening_name is None
        assert game.played_at is None
        assert len(game.moves) == 2

    def test_empty_input(self, parser: PGNParserService) -> None:
        games = parser.parse_pgn("")
        assert games == []

    def test_reconstructed_pgn_text(
        self, parser: PGNParserService, sample_pgn_single: str
    ) -> None:
        games = parser.parse_pgn(sample_pgn_single)
        game = games[0]
        # The reconstructed PGN should contain the header and moves
        assert "Player1" in game.pgn_text
        assert "e4" in game.pgn_text

    def test_headers_dict_populated(
        self, parser: PGNParserService, sample_pgn_single: str
    ) -> None:
        games = parser.parse_pgn(sample_pgn_single)
        headers = games[0].headers
        assert headers["White"] == "Player1"
        assert headers["Event"] == "Test Game"


# ---------------------------------------------------------------------------
# _parse_pgn_date
# ---------------------------------------------------------------------------


class TestParsePgnDate:
    def test_valid_date(self) -> None:
        assert _parse_pgn_date("2024.06.15") == date(2024, 6, 15)

    def test_unknown_day(self) -> None:
        assert _parse_pgn_date("2024.06.??") is None

    def test_fully_unknown(self) -> None:
        assert _parse_pgn_date("????.??.??") is None

    def test_empty_string(self) -> None:
        assert _parse_pgn_date("") is None

    def test_malformed(self) -> None:
        assert _parse_pgn_date("not-a-date") is None

    def test_wrong_separator(self) -> None:
        assert _parse_pgn_date("2024-06-15") is None
