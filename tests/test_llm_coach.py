from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_coach import (
    GameSummaryInput,
    GameSummaryResult,
    LLMCoachError,
    LLMCoachService,
    MoveCommentaryInput,
    PeriodReportInput,
    PeriodReportResult,
    _parse_json_response,
)
from app.utils.llm_prompts import (
    GAME_SUMMARY_SYSTEM,
    MOVE_COMMENTARY_SYSTEM,
    PERIOD_REPORT_SYSTEM,
    build_game_summary_messages,
    build_move_commentary_messages,
    build_period_report_messages,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_move_input(
    *,
    move_index: int = 0,
    move_number: int = 1,
    color: str = "white",
    classification: str = "good",
    centipawn_loss: float = 15.0,
) -> MoveCommentaryInput:
    """Create a MoveCommentaryInput with sensible defaults for testing."""
    return MoveCommentaryInput(
        move_index=move_index,
        move_number=move_number,
        color=color,
        fen_before="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        move_san="e5",
        best_move_san="e5",
        eval_before=0.3,
        eval_after=0.2,
        centipawn_loss=centipawn_loss,
        classification=classification,
        top_moves=[
            {"move_san": "e5", "eval_cp": 0.2, "pv_san": ["e5", "Nf3", "Nc6"]},
            {"move_san": "d5", "eval_cp": -0.1, "pv_san": ["d5", "exd5", "Qxd5"]},
        ],
        next_game_moves=["2.Nf3", "2...Nc6", "3.Bb5"],
    )


def _make_game_summary_input() -> GameSummaryInput:
    """Create a GameSummaryInput with sensible defaults for testing."""
    return GameSummaryInput(
        white_player="Player1",
        black_player="Player2",
        result="1-0",
        opening_name="Italian Game",
        eco_code="C50",
        total_moves=20,
        accuracy_white=85.0,
        accuracy_black=72.3,
        classification_counts={
            "best": 8,
            "good": 6,
            "inaccuracy": 3,
            "mistake": 2,
            "blunder": 1,
        },
        key_moments=[_make_move_input(classification="blunder", centipawn_loss=150.0)],
    )


def _make_period_report_input() -> PeriodReportInput:
    """Create a PeriodReportInput with sensible defaults for testing."""
    return PeriodReportInput(
        period_start="2024-01-01",
        period_end="2024-01-31",
        games_count=5,
        game_summaries=[
            "Game 1: Solid opening, middlegame mistake cost a pawn.",
            "Game 2: Excellent tactical play, clean finish.",
        ],
        aggregate_stats={
            "avg_accuracy": 78.5,
            "total_blunders": 3,
            "most_common_opening": "Sicilian Defense",
        },
    )


def _mock_llm_response(content: str) -> MagicMock:
    """Create a mock litellm response object."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# Tests: _parse_json_response
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    """Tests for the JSON response parser helper."""

    def test_parses_clean_json(self) -> None:
        data = {"comments": [{"move_index": 0, "comment": "Good move."}]}
        result = _parse_json_response(json.dumps(data))
        assert result == data

    def test_strips_markdown_fences(self) -> None:
        raw = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(raw)
        assert result == {"key": "value"}

    def test_strips_plain_fences(self) -> None:
        raw = '```\n{"key": "value"}\n```'
        result = _parse_json_response(raw)
        assert result == {"key": "value"}

    def test_returns_empty_dict_on_invalid_json(self) -> None:
        result = _parse_json_response("not json at all")
        assert result == {}

    def test_returns_empty_dict_on_non_object(self) -> None:
        result = _parse_json_response("[1, 2, 3]")
        assert result == {}

    def test_handles_empty_string(self) -> None:
        result = _parse_json_response("")
        assert result == {}

    def test_handles_whitespace_around_json(self) -> None:
        result = _parse_json_response('  \n {"key": "val"} \n ')
        assert result == {"key": "val"}


# ---------------------------------------------------------------------------
# Tests: prompt builders
# ---------------------------------------------------------------------------


class TestPromptBuilders:
    """Tests for prompt template builder functions."""

    def test_move_commentary_messages_structure(self) -> None:
        moves = [_make_move_input(move_index=0), _make_move_input(move_index=1)]
        messages = build_move_commentary_messages(moves)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == MOVE_COMMENTARY_SYSTEM
        assert messages[1]["role"] == "user"
        assert "[Move 0]" in messages[1]["content"]
        assert "[Move 1]" in messages[1]["content"]

    def test_move_commentary_includes_fen_and_eval(self) -> None:
        moves = [_make_move_input()]
        messages = build_move_commentary_messages(moves)
        user_content = messages[1]["content"]

        assert "FEN:" in user_content
        assert "Eval:" in user_content
        assert "Engine lines:" in user_content
        assert "Actual game continuation" in user_content

    def test_game_summary_messages_structure(self) -> None:
        context = _make_game_summary_input()
        messages = build_game_summary_messages(context)

        assert len(messages) == 2
        assert messages[0]["content"] == GAME_SUMMARY_SYSTEM
        user_content = messages[1]["content"]
        assert "Player1 vs Player2" in user_content
        assert "Italian Game" in user_content
        assert "85.0%" in user_content

    def test_game_summary_omits_opening_when_none(self) -> None:
        context = GameSummaryInput(
            white_player="A",
            black_player="B",
            result="*",
            opening_name=None,
            eco_code=None,
            total_moves=4,
            accuracy_white=90.0,
            accuracy_black=90.0,
            classification_counts={"best": 4},
        )
        messages = build_game_summary_messages(context)
        assert "Opening:" not in messages[1]["content"]

    def test_period_report_messages_structure(self) -> None:
        context = _make_period_report_input()
        messages = build_period_report_messages(context)

        assert len(messages) == 2
        assert messages[0]["content"] == PERIOD_REPORT_SYSTEM
        user_content = messages[1]["content"]
        assert "2024-01-01" in user_content
        assert "Game 1" in user_content
        assert "avg_accuracy" in user_content


# ---------------------------------------------------------------------------
# Tests: LLMCoachService
# ---------------------------------------------------------------------------


class TestLLMCoachService:
    """Tests for LLMCoachService with mocked LiteLLM calls."""

    @pytest.fixture()
    def service(self) -> LLMCoachService:
        return LLMCoachService(model="test-model", api_key="test-key", api_base="")

    @pytest.mark.asyncio()
    async def test_generate_move_commentaries_success(
        self, service: LLMCoachService
    ) -> None:
        llm_response = json.dumps(
            {
                "comments": [
                    {"move_index": 0, "comment": "Solid opening move."},
                    {"move_index": 1, "comment": "This was a blunder."},
                ]
            }
        )
        mock_response = _mock_llm_response(llm_response)

        with patch(
            "app.services.llm_coach.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_response
            moves = [
                _make_move_input(move_index=0, classification="good"),
                _make_move_input(
                    move_index=1, classification="blunder", centipawn_loss=200.0
                ),
            ]
            result = await service.generate_move_commentaries(moves)

        assert result == {0: "Solid opening move.", 1: "This was a blunder."}
        mock.assert_called_once()

    @pytest.mark.asyncio()
    async def test_generate_move_commentaries_empty_input(
        self, service: LLMCoachService
    ) -> None:
        result = await service.generate_move_commentaries([])
        assert result == {}

    @pytest.mark.asyncio()
    async def test_generate_move_commentaries_handles_partial_json(
        self, service: LLMCoachService
    ) -> None:
        """Missing entries in the JSON response should not crash."""
        llm_response = json.dumps(
            {"comments": [{"move_index": 0, "comment": "Only first move commented."}]}
        )
        mock_response = _mock_llm_response(llm_response)

        with patch(
            "app.services.llm_coach.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_response
            moves = [
                _make_move_input(move_index=0),
                _make_move_input(move_index=1),
            ]
            result = await service.generate_move_commentaries(moves)

        assert 0 in result
        assert 1 not in result

    @pytest.mark.asyncio()
    async def test_generate_move_commentaries_raises_on_llm_error(
        self, service: LLMCoachService
    ) -> None:
        with patch(
            "app.services.llm_coach.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = Exception("API rate limit exceeded")
            with pytest.raises(LLMCoachError, match="LLM call failed"):
                await service.generate_move_commentaries([_make_move_input()])

    @pytest.mark.asyncio()
    async def test_generate_game_summary_success(
        self, service: LLMCoachService
    ) -> None:
        llm_response = json.dumps(
            {
                "summary": "A well-played game with a critical blunder.",
                "opening_assessment": "The Italian Game was handled well.",
                "middlegame_assessment": "Missed a tactic on move 15.",
                "endgame_assessment": "Game did not reach the endgame.",
                "key_moments": [
                    {"move": "15...Bxd5??", "description": "Lost a piece."}
                ],
            }
        )
        mock_response = _mock_llm_response(llm_response)

        with patch(
            "app.services.llm_coach.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_response
            result = await service.generate_game_summary(_make_game_summary_input())

        assert isinstance(result, GameSummaryResult)
        assert "well-played" in result.summary
        assert result.opening_assessment != ""
        assert len(result.key_moments) == 1

    @pytest.mark.asyncio()
    async def test_generate_game_summary_handles_malformed_json(
        self, service: LLMCoachService
    ) -> None:
        """Malformed JSON should produce empty fields, not crash."""
        mock_response = _mock_llm_response("not valid json {{{")

        with patch(
            "app.services.llm_coach.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_response
            result = await service.generate_game_summary(_make_game_summary_input())

        assert isinstance(result, GameSummaryResult)
        assert result.summary == ""

    @pytest.mark.asyncio()
    async def test_generate_period_report_success(
        self, service: LLMCoachService
    ) -> None:
        llm_response = json.dumps(
            {
                "recommendations": "Focus on endgame technique and avoid time trouble.",
                "weakness_patterns": [
                    {
                        "pattern": "Endgame technique",
                        "description": "Struggles converting advantages.",
                        "frequency": "3 out of 5 games",
                    }
                ],
                "strength_patterns": [
                    {
                        "pattern": "Opening preparation",
                        "description": "Consistently reaches good positions.",
                        "frequency": "4 out of 5 games",
                    }
                ],
            }
        )
        mock_response = _mock_llm_response(llm_response)

        with patch(
            "app.services.llm_coach.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_response
            result = await service.generate_period_report(_make_period_report_input())

        assert isinstance(result, PeriodReportResult)
        assert "endgame" in result.recommendations.lower()
        assert len(result.weakness_patterns) == 1
        assert len(result.strength_patterns) == 1

    @pytest.mark.asyncio()
    async def test_generate_period_report_raises_on_llm_error(
        self, service: LLMCoachService
    ) -> None:
        with patch(
            "app.services.llm_coach.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = Exception("Connection timeout")
            with pytest.raises(LLMCoachError, match="LLM call failed"):
                await service.generate_period_report(_make_period_report_input())

    @pytest.mark.asyncio()
    async def test_generate_single_move_commentary_stream(
        self, service: LLMCoachService
    ) -> None:
        """Streaming yields text chunks from the LLM."""

        async def _fake_stream() -> object:
            for c in ("Good ", "opening ", "move."):
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta = MagicMock()
                chunk.choices[0].delta.content = c
                yield chunk

        with patch(
            "app.services.llm_coach.litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_fake_stream(),
        ) as mock:
            move = _make_move_input()
            result_chunks = [
                c async for c in service.generate_single_move_commentary_stream(move)
            ]

        assert result_chunks == ["Good ", "opening ", "move."]
        mock.assert_called_once()
        assert mock.call_args.kwargs["stream"] is True

    @pytest.mark.asyncio()
    async def test_llm_call_passes_correct_params(
        self, service: LLMCoachService
    ) -> None:
        """Verify model, api_key, api_base, and temperature are forwarded."""
        mock_response = _mock_llm_response('{"comments": []}')

        with patch(
            "app.services.llm_coach.litellm.acompletion", new_callable=AsyncMock
        ) as mock:
            mock.return_value = mock_response
            await service.generate_move_commentaries([_make_move_input()])

        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["api_key"] == "test-key"
        assert call_kwargs["api_base"] is None  # empty string -> None
        assert call_kwargs["temperature"] == 0.4
        assert call_kwargs["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# Tests: helper functions from chess_helpers (moves_to_fens)
# ---------------------------------------------------------------------------


class TestMovesToFens:
    """Tests for the moves_to_fens helper."""

    def test_returns_fens_for_each_move(self) -> None:
        import chess

        from app.utils.chess_helpers import moves_to_fens

        board = chess.Board()
        moves = [
            board.parse_san("e4"),
        ]
        board.push(moves[0])
        moves.append(board.parse_san("e5"))

        fens = moves_to_fens(moves)
        assert len(fens) == 2
        # First FEN should be the starting position
        assert fens[0] == chess.STARTING_FEN

    def test_empty_moves(self) -> None:
        from app.utils.chess_helpers import moves_to_fens

        assert moves_to_fens([]) == []
