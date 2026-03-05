"""Tests for LLM commentary streaming endpoint."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from tests.test_api.conftest import make_game, make_game_analysis, make_move_analysis


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
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = analysis
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get(f"/api/games/{game.id}/analysis/moves/0/commentary/stream")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
