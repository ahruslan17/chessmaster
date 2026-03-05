from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from tests.test_api.conftest import make_game, make_game_analysis, make_move_analysis

# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/analysis
# ---------------------------------------------------------------------------


async def test_get_analysis_returns_analysis_with_moves(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Full analysis includes game-level summary and per-move evaluations."""
    game = make_game()
    analysis = make_game_analysis(game_id=game.id)

    move_w = make_move_analysis(
        game_analysis_id=analysis.id,
        move_number=1,
        color="white",
        move_san="e4",
    )
    move_b = make_move_analysis(
        game_analysis_id=analysis.id,
        move_number=1,
        color="black",
        move_san="e5",
    )
    analysis.moves = [move_b, move_w]  # intentionally out of order

    # session.get(Game, game_id) for game existence check
    mock_session.get = AsyncMock(return_value=game)

    # session.execute(select(GameAnalysis)...) for analysis query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = analysis
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(analysis.id)
    assert data["game_id"] == str(game.id)
    assert data["status"] == "done"
    assert len(data["moves"]) == 2
    # White should come before black (sorted by the endpoint)
    assert data["moves"][0]["color"] == "white"
    assert data["moves"][1]["color"] == "black"


async def test_get_analysis_game_not_found(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Requesting analysis for a non-existent game returns 404."""
    mock_session.get = AsyncMock(return_value=None)

    response = await client.get(f"/api/games/{uuid.uuid4()}/analysis")

    assert response.status_code == 404
    assert "game not found" in response.json()["detail"].lower()


async def test_get_analysis_no_analysis_yet(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Requesting analysis when none exists returns 404."""
    game = make_game()
    mock_session.get = AsyncMock(return_value=game)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 404
    assert "analysis not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/analysis/status
# ---------------------------------------------------------------------------


async def test_get_analysis_status_done(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Status endpoint returns the current analysis status."""
    game_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "done"
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get(f"/api/games/{game_id}/analysis/status")

    assert response.status_code == 200
    data = response.json()
    assert data["game_id"] == str(game_id)
    assert data["status"] == "done"


async def test_get_analysis_status_in_progress(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Status endpoint returns 'in_progress' when analysis is running."""
    game_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "in_progress"
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get(f"/api/games/{game_id}/analysis/status")

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


async def test_get_analysis_status_pending_when_no_record(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Status endpoint returns 'pending' when no analysis record exists."""
    game_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get(f"/api/games/{game_id}/analysis/status")

    assert response.status_code == 200
    data = response.json()
    assert data["game_id"] == str(game_id)
    assert data["status"] == "pending"
