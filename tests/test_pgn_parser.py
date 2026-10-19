from __future__ import annotations

from datetime import date

import chess
import pytest

from app.core.exceptions import PGNParseError
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

    @pytest.mark.parametrize("pgn_text", ["", " \t\n", "; comment only\n", "% comment only\n"])
    def test_empty_input(self, parser: PGNParserService, pgn_text: str) -> None:
        with pytest.raises(PGNParseError):
            parser.parse_pgn(pgn_text)

    @pytest.mark.parametrize("pgn_text", ['[Event "Empty"]\n\n*', "{comment only}", "1-0"])
    def test_empty_mainline(self, parser: PGNParserService, pgn_text: str) -> None:
        with pytest.raises(PGNParseError, match="нет ходов"):
            parser.parse_pgn(pgn_text)

    @pytest.mark.parametrize(
        "pgn_text",
        [
            "not a PGN",
            "1. b3 e5 2. Ba3 Ke9 *",
            "1. e4 garbage e5 *",
            "1. e4 e5 2. Nf3oops *",
            "1. e4 e5 (1... Ke9) *",
            "1. e4 e5 2. -- *",
            "1. e4 e5 2. 0000 *",
            "1. e4 e5 2. Z0 *",
            "1. e4 e5 2. @@@@ *",
            "1. e4 e5 2. N@f3 *",
        ],
    )
    def test_unknown_or_unsupported_move_tokens(
        self, parser: PGNParserService, pgn_text: str
    ) -> None:
        with pytest.raises(PGNParseError, match="Некорректный токен PGN"):
            parser.parse_pgn(pgn_text)

    @pytest.mark.parametrize(
        "pgn_text", ["1. e4 e5 2. Bh6 *", "1. e4 e5 (1... Bh6) 2. Nf3 *", "1. e4e5 *"]
    )
    def test_parser_errors(self, parser: PGNParserService, pgn_text: str) -> None:
        with pytest.raises(PGNParseError, match="Некорректный PGN") as error:
            parser.parse_pgn(pgn_text)
        assert isinstance(error.value.__cause__, ValueError)

    @pytest.mark.parametrize(
        "pgn_text",
        [
            '[Event "Broken]\n\n1. e4 e5 *',
            "1. e4 {unclosed",
            "1. e4 } e5 *",
            "1. e4 (1. d4 d5 e5 *",
            "1. e4 ) e5 *",
        ],
    )
    def test_malformed_structure(self, parser: PGNParserService, pgn_text: str) -> None:
        with pytest.raises(PGNParseError):
            parser.parse_pgn(pgn_text)

    @pytest.mark.parametrize(
        "header",
        [
            '[FEN "8/8/8/8/8/8/4k3/4K3 w - - 0 1"]',
            f'[FEN "{chess.STARTING_FEN}"]',
            '[FEN "not a FEN"]',
            '[SetUp "1"]',
            '[SetUp "invalid"]',
            '[Variant "Chess960"]',
            '[Variant "Atomic"]',
            '[Variant "unknown"]',
        ],
    )
    def test_unsupported_positions(self, parser: PGNParserService, header: str) -> None:
        with pytest.raises(PGNParseError, match="не поддерживаются"):
            parser.parse_pgn(f"{header}\n\n1. e4 e5 *")

    def test_explicit_standard_chess(self, parser: PGNParserService) -> None:
        games = parser.parse_pgn('[Variant "Standard"]\n[SetUp "0"]\n\n1. e4 e5 *')
        assert len(games[0].moves) == 2

    @pytest.mark.parametrize(
        "headers", ['[Event "X"] [White "Alice"]', '  [Event "X" ]\t[White "Alice" ]']
    )
    def test_multiple_headers_on_same_line(self, parser: PGNParserService, headers: str) -> None:
        game = parser.parse_pgn(f"{headers}\n\n1. e4 e5 *")[0]
        assert game.headers["Event"] == "X"
        assert game.white_player == "Alice"

    def test_quoted_brackets_and_escapes_in_headers(self, parser: PGNParserService) -> None:
        event = r'X \"quoted\" \\ [White \"Not Alice\"]'
        game = parser.parse_pgn(f'[Event "{event}"] [White "Alice"]\n\n1. e4 e5 *')[0]
        assert game.headers["Event"] == event
        assert game.white_player == "Alice"

    @pytest.mark.parametrize(
        "header", ['[Variant "Atomic"]', f'[FEN "{chess.STARTING_FEN}"]', '[SetUp "1"]']
    )
    def test_unsupported_second_header(self, parser: PGNParserService, header: str) -> None:
        with pytest.raises(PGNParseError, match="не поддерживаются"):
            parser.parse_pgn(f'[Event "X"] {header}\n\n1. e4 e5 *')

    @pytest.mark.parametrize(
        "prefix",
        ["", "1.", "$1", "!", "*", "{comment}", "1.e4 (", "1.e4 (1.", "1.e4 ($1"],
    )
    def test_variation_requires_preceding_move(
        self, parser: PGNParserService, prefix: str
    ) -> None:
        with pytest.raises(PGNParseError, match="без предшествующего хода"):
            parser.parse_pgn(f"{prefix} (1.e4 e5) 1.d4 d5 *")

    def test_new_game_does_not_inherit_preceding_move(self, parser: PGNParserService) -> None:
        with pytest.raises(PGNParseError, match="без предшествующего хода"):
            parser.parse_pgn("1.e4 e5\n\n(1.e4 e5) 1.d4 d5 *")

    def test_variation_after_move_preserves_mainline(self, parser: PGNParserService) -> None:
        game = parser.parse_pgn("1.e4 (1.d4 d5) e5 *")[0]
        assert [move.uci() for move in game.moves] == ["e2e4", "e7e5"]

    def test_comments_variations_annotations_and_compact_numbers(
        self, parser: PGNParserService
    ) -> None:
        pgn_text = '''\ufeff[Event "Ke9 and unknown tokens are valid in headers"]

% escape line: Ke9
{Start comment: Ke9 () $bad

[Variant "Atomic"] and ; text}
1.e4! $1 (1.d4 d5 (1...Nf6)) 1...e5 ; Ke9
2.Nf3?! Nc6 {Ke9, [FEN "not a position"]} 3.Bb5 a6 4.Ba4 Nf6
5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O *
'''
        game = parser.parse_pgn(pgn_text)[0]
        assert len(game.moves) == 16
        assert game.moves[8] == chess.Move.from_uci("e1g1")

    def test_capture_promotion_and_checkmate(self, parser: PGNParserService) -> None:
        game = parser.parse_pgn(
            "1. a4 h5 2. a5 h4 3. a6 h3 4. axb7 hxg2 5. bxa8=Q gxh1=Q *"
        )[0]
        assert game.moves[-1].promotion == chess.QUEEN
        mate = parser.parse_pgn("1. f3 e5 2. g4 Qh4# 0-1")[0]
        assert len(mate.moves) == 4

    @pytest.mark.parametrize("invalid_game", ["1. b3 e5 2. Ba3 Ke9 *", "*", "1. e4 Bh6 *"])
    def test_multiple_games_never_silently_skip_invalid_game(
        self, parser: PGNParserService, invalid_game: str
    ) -> None:
        with pytest.raises(PGNParseError):
            parser.parse_pgn(f"1. e4 e5 *\n\n{invalid_game}\n")

    def test_long_game_is_not_truncated(self, parser: PGNParserService) -> None:
        cycles = 300
        pgn_text = " ".join(
            f"{2 * index + 1}. Nf3 Nf6 {2 * index + 2}. Ng1 Ng8" for index in range(cycles)
        )
        game = parser.parse_pgn(f"{pgn_text} *")[0]
        assert len(game.moves) == cycles * 4

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
