from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.game import Game
from app.services.opening_matcher import OpeningMatch
from app.services.game_review import (
    GameReviewService,
    _build_game_record,
    _build_game_summary_input,
    _build_move_analysis,
    _build_move_commentary_inputs,
)
from app.services.pgn_parser import ParsedGame
from app.services.stockfish_analyzer import MoveEvaluation
from tests.conftest import SAMPLE_PGN_SINGLE

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_parsed_game() -> ParsedGame:
    from app.services.pgn_parser import PGNParserService

    parser = PGNParserService()
    games = parser.parse_pgn(SAMPLE_PGN_SINGLE)
    assert len(games) == 1
    return games[0]


@pytest.fixture()
def sample_evaluations() -> list[MoveEvaluation]:
    from app.services.stockfish_analyzer import CandidateMove

    return [
        MoveEvaluation(
            move_number=1,
            color="white",
            move_san="e4",
            best_move_san="e4",
            eval_before=0.0,
            eval_after=30.0,
            centipawn_loss=0.0,
            classification="best",
            top_moves=[
                CandidateMove(move_san="e4", eval_cp=30.0, pv_san=["e4", "e5"]),
            ],
        ),
        MoveEvaluation(
            move_number=1,
            color="black",
            move_san="e5",
            best_move_san="e5",
            eval_before=30.0,
            eval_after=25.0,
            centipawn_loss=5.0,
            classification="good",
            top_moves=[
                CandidateMove(move_san="e5", eval_cp=25.0, pv_san=["e5", "Nf3"]),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# _build_game_record
# ---------------------------------------------------------------------------


class TestBuildGameRecord:
    def test_builds_game_from_parsed(self, sample_parsed_game: ParsedGame) -> None:
        game = _build_game_record(sample_parsed_game, player_color="white")
        assert game.white_player == "Player1"
        assert game.black_player == "Player2"
        assert game.result == "1-0"
        assert game.player_color == "white"

    def test_player_color_optional(self, sample_parsed_game: ParsedGame) -> None:
        game = _build_game_record(sample_parsed_game, None)
        assert game.player_color is None


# ---------------------------------------------------------------------------
# _build_move_analysis
# ---------------------------------------------------------------------------


class TestBuildMoveAnalysis:
    def test_builds_move_record(self, sample_evaluations: list[MoveEvaluation]) -> None:
        analysis_id = uuid.uuid4()
        ev = sample_evaluations[0]
        record = _build_move_analysis(analysis_id, ev)
        assert record.game_analysis_id == analysis_id
        assert record.move_number == 1
        assert record.color == "white"
        assert record.move_san == "e4"
        assert record.classification == "best"


# ---------------------------------------------------------------------------
# _build_move_commentary_inputs
# ---------------------------------------------------------------------------


class TestBuildMoveCommentaryInputs:
    def test_builds_inputs_with_fens(
        self, sample_evaluations: list[MoveEvaluation], sample_parsed_game: ParsedGame
    ) -> None:
        from app.utils.chess_helpers import moves_to_fens

        fens = moves_to_fens(sample_parsed_game.moves)
        inputs = _build_move_commentary_inputs(fens, sample_evaluations)
        assert len(inputs) == 2
        assert inputs[0].move_index == 0
        assert inputs[0].move_san == "e4"
        assert inputs[0].fen_before == fens[0]


# ---------------------------------------------------------------------------
# _build_game_summary_input
# ---------------------------------------------------------------------------


class TestBuildGameSummaryInput:
    def test_builds_summary_input(
        self,
        sample_evaluations: list[MoveEvaluation],
        sample_parsed_game: ParsedGame,
    ) -> None:
        from app.utils.chess_helpers import moves_to_fens

        game = Game(
            pgn_text=SAMPLE_PGN_SINGLE,
            white_player="Player1",
            black_player="Player2",
            result="1-0",
            opening_name="Italian Game",
            eco_code="C50",
            time_control="600+5",
            played_at=sample_parsed_game.played_at,
            player_color=None,
        )
        fens = moves_to_fens(sample_parsed_game.moves)
        move_inputs = _build_move_commentary_inputs(fens, sample_evaluations)

        summary_input = _build_game_summary_input(game, sample_evaluations, move_inputs)
        assert summary_input.white_player == "Player1"
        assert summary_input.total_moves == 2
        assert "best" in summary_input.classification_counts


# ---------------------------------------------------------------------------
# GameReviewService
# ---------------------------------------------------------------------------


class TestGameReviewService:
    @pytest.mark.asyncio()
    async def test_create_games_from_pgn(self, sample_parsed_game: ParsedGame) -> None:
        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()
        # _find_game_by_fingerprint uses execute; return no existing game
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = GameReviewService(mock_session)
        games, new_ids = await service.create_games_from_pgn(SAMPLE_PGN_SINGLE)

        assert len(games) == 1
        assert len(new_ids) == 1
        assert games[0].white_player == "Player1"
        mock_session.add.assert_called()
        mock_session.flush.assert_awaited()

    @pytest.mark.asyncio()
    async def test_create_games_uses_opening_matcher(self) -> None:
        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_opening_matcher = MagicMock()
        mock_opening_matcher.match.return_value = OpeningMatch(
            eco_code="B07",
            name="Pirc Defense",
            move_count=10,
        )

        service = GameReviewService(mock_session, opening_matcher=mock_opening_matcher)
        games, _ = await service.create_games_from_pgn(SAMPLE_PGN_SINGLE)

        assert len(games) == 1
        assert games[0].eco_code == "B07"
        assert games[0].opening_name == "Pirc Defense"
        mock_opening_matcher.match.assert_called_once()

    @pytest.mark.asyncio()
    async def test_duplicate_game_backfills_missing_opening(self) -> None:
        existing = Game(
            pgn_text=SAMPLE_PGN_SINGLE,
            white_player="Player1",
            black_player="Player2",
            result="1-0",
            opening_name=None,
            eco_code=None,
            time_control=None,
            played_at=None,
            player_color=None,
        )
        existing.id = uuid.uuid4()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()

        mock_opening_matcher = MagicMock()
        mock_opening_matcher.match.return_value = OpeningMatch(
            eco_code="B07",
            name="Pirc Defense",
            move_count=10,
        )

        service = GameReviewService(mock_session, opening_matcher=mock_opening_matcher)
        games, new_ids = await service.create_games_from_pgn(SAMPLE_PGN_SINGLE)

        assert games == [existing]
        assert new_ids == []
        assert existing.opening_name == "Pirc Defense"
        assert existing.eco_code == "B07"
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio()
    async def test_create_games_empty_pgn(self) -> None:
        mock_session = AsyncMock()
        service = GameReviewService(mock_session)
        games, new_ids = await service.create_games_from_pgn("")
        assert games == []
        assert new_ids == []
