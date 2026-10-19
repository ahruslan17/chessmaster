"""Tests for LLM commentary streaming endpoint."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from tests.test_api.conftest import (
    make_game,
    make_game_analysis,
    make_move_analysis,
    make_side_review,
    set_scalar_results,
)

pytestmark = pytest.mark.usefixtures("read_only_api")


async def test_stream_commentary_move_index_negative(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Negative move index returns 404."""
    game = make_game()
    mock_session.get = AsyncMock(return_value=game)

    response = await client.get(f"/api/games/{game.id}/analysis/moves/-1/commentary/stream")

    assert response.status_code == 404


async def test_stream_commentary_game_not_found(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Streaming for non-existent game returns 404."""
    mock_session.get = AsyncMock(return_value=None)

    response = await client.get(f"/api/games/{uuid.uuid4()}/analysis/moves/0/commentary/stream")

    assert response.status_code == 404


async def test_stream_commentary_analysis_not_found(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Streaming when analysis doesn't exist returns 404."""
    game = make_game()
    mock_session.get = AsyncMock(return_value=game)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get(f"/api/games/{game.id}/analysis/moves/0/commentary/stream")

    assert response.status_code == 404


async def test_stream_commentary_with_existing_comment(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """When move already has commentary, streams it as SSE without calling LLM."""
    game = make_game()
    analysis = make_game_analysis(game_id=game.id)
    move = make_move_analysis(
        game_analysis_id=analysis.id,
        move_number=1,
        color="white",
        move_san="e4",
        llm_comment="Solid opening move.",
    )
    analysis.moves = [move]

    mock_session.get = AsyncMock(return_value=game)
    review = make_side_review(
        game_analysis_id=analysis.id,
        comments={"0": {"reason": "Solid opening move."}},
    )
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis/moves/0/commentary/stream")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert response.text == "data: Solid opening move.\n\n"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.parametrize("missing_kind", ["review", "comment", "legacy", "out_of_range"])
async def test_missing_saved_comment_never_generates_text(
    missing_kind: str, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    game = make_game()
    analysis = make_game_analysis(
        game_id=game.id, score_version=0 if missing_kind == "legacy" else 1,
    )
    analysis.moves = [make_move_analysis(llm_comment="Old unscoped text must not leak")]
    review = None if missing_kind == "review" else make_side_review(
        comments={} if missing_kind == "comment" else {"0": {"reason": "Saved text"}},
    )
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)
    index = 1 if missing_kind == "out_of_range" else 0

    response = await client.get(f"/api/games/{game.id}/analysis/moves/{index}/commentary/stream")

    assert response.status_code == 404
    assert "Old unscoped" not in response.text


async def test_saved_multiline_comment_preserves_spaces_and_blank_lines(
    client: AsyncClient, mock_session: AsyncMock,
) -> None:
    game = make_game()
    analysis = make_game_analysis(game_id=game.id)
    analysis.moves = [make_move_analysis()]
    review = make_side_review(comments={"0": {
        "reason": "  Reason  \n\n next line ",
        "consequence": " Consequence ",
        "alternative": "Alternative",
        "principle": "Principle",
        "limitation": " Limit ",
    }})
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis/moves/0/commentary/stream")

    assert response.status_code == 200
    assert response.text == (
        "data:   Reason  \ndata: \ndata:  next line \ndata:  Consequence \n"
        "data: Alternative\ndata: Principle\ndata:  Limit \n\n"
    )


async def test_stream_uses_explicit_side_not_game_default(
    client: AsyncClient, mock_session: AsyncMock,
) -> None:
    game = make_game(player_color="white")
    analysis = make_game_analysis(game_id=game.id)
    analysis.moves = [make_move_analysis(color="black")]
    review = make_side_review(player_color="black", comments={"0": {"reason": "Black only"}})
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(
        f"/api/games/{game.id}/analysis/moves/0/commentary/stream?player_color=black",
    )

    assert response.status_code == 200
    assert response.text == "data: Black only\n\n"
    query = mock_session.execute.call_args_list[1].args[0]
    assert "black" in query.compile().params.values()
