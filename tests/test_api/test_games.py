from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from tests.conftest import SAMPLE_PGN_SINGLE
from tests.test_api.conftest import make_game

# ---------------------------------------------------------------------------
# POST /api/games/upload
# ---------------------------------------------------------------------------


@patch("app.api.games.analyze_game_task")
@patch("app.api.games.GameReviewService")
async def test_upload_pgn_creates_games_and_queues_analysis(
    mock_review_cls: MagicMock,
    mock_task: MagicMock,
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Uploading a valid PGN creates games and dispatches Celery tasks."""
    game = make_game()

    mock_service = mock_review_cls.return_value
    mock_service.create_games_from_pgn = AsyncMock(return_value=([game], [game.id]))

    response = await client.post(
        "/api/games/upload",
        files={"file": ("test.pgn", SAMPLE_PGN_SINGLE.encode(), "application/x-chess-pgn")},
    )

    assert response.status_code == 201
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(game.id)
    assert data[0]["white_player"] == "White"

    mock_service.create_games_from_pgn.assert_awaited_once()
    mock_session.commit.assert_awaited_once()
    mock_task.delay.assert_called_once_with(str(game.id))


@patch("app.api.games.analyze_game_task")
@patch("app.api.games.GameReviewService")
async def test_upload_pgn_empty_file_returns_400(
    mock_review_cls: MagicMock,
    mock_task: MagicMock,
    client: AsyncClient,
) -> None:
    """Uploading an empty file returns 400."""
    response = await client.post(
        "/api/games/upload",
        files={"file": ("empty.pgn", b"   ", "application/x-chess-pgn")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()
    mock_task.delay.assert_not_called()


@patch("app.api.games.analyze_game_task")
@patch("app.api.games.GameReviewService")
async def test_upload_pgn_no_valid_games_returns_422(
    mock_review_cls: MagicMock,
    mock_task: MagicMock,
    client: AsyncClient,
) -> None:
    """Uploading a PGN with no parseable games returns 422."""
    mock_service = mock_review_cls.return_value
    mock_service.create_games_from_pgn = AsyncMock(return_value=([], []))

    response = await client.post(
        "/api/games/upload",
        files={"file": ("bad.pgn", b"not a pgn", "application/x-chess-pgn")},
    )

    assert response.status_code == 422
    assert "no valid games" in response.json()["detail"].lower()
    mock_task.delay.assert_not_called()


@patch("app.api.games.analyze_game_task")
@patch("app.api.games.GameReviewService")
async def test_import_pgn_text_creates_games(
    mock_review_cls: MagicMock,
    mock_task: MagicMock,
    client: AsyncClient,
) -> None:
    """Importing PGN text creates games and queues analysis."""
    game = make_game()
    mock_service = mock_review_cls.return_value
    mock_service.create_games_from_pgn = AsyncMock(return_value=([game], [game.id]))

    response = await client.post(
        "/api/games/import",
        json={"pgn_text": SAMPLE_PGN_SINGLE},
    )

    assert response.status_code == 201
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(game.id)
    mock_service.create_games_from_pgn.assert_awaited_once()
    call_args = mock_service.create_games_from_pgn.call_args
    assert "Player1" in call_args.args[0] and "1. e4 e5" in call_args.args[0]
    assert call_args.kwargs.get("player_color") is None
    mock_task.delay.assert_called_once_with(str(game.id))


@patch("app.api.games.analyze_game_task")
@patch("app.api.games.GameReviewService")
async def test_import_pgn_text_empty_returns_400(
    mock_review_cls: MagicMock,
    mock_task: MagicMock,
    client: AsyncClient,
) -> None:
    """Importing empty PGN text returns 400."""
    response = await client.post(
        "/api/games/import",
        json={"pgn_text": "   "},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()
    mock_task.delay.assert_not_called()


@patch("app.api.games.analyze_game_task")
@patch("app.api.games.GameReviewService")
async def test_upload_pgn_with_player_color(
    mock_review_cls: MagicMock,
    mock_task: MagicMock,
    client: AsyncClient,
) -> None:
    """The optional player_color query parameter is passed to the service."""
    game = make_game(player_color="black")
    mock_service = mock_review_cls.return_value
    mock_service.create_games_from_pgn = AsyncMock(return_value=([game], [game.id]))

    response = await client.post(
        "/api/games/upload?player_color=black",
        files={"file": ("test.pgn", SAMPLE_PGN_SINGLE.encode(), "application/x-chess-pgn")},
    )

    assert response.status_code == 201
    mock_service.create_games_from_pgn.assert_awaited_once()
    call_kwargs = mock_service.create_games_from_pgn.call_args
    assert call_kwargs.kwargs.get("player_color") == "black"


# ---------------------------------------------------------------------------
# GET /api/games
# ---------------------------------------------------------------------------


async def test_list_games_returns_games(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Listing games returns stored games ordered newest-first."""
    games = [make_game(), make_game(white_player="Alice")]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = games
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get("/api/games")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # GameListItem should NOT include pgn_text
    assert "pgn_text" not in data[0]


async def test_list_games_empty(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Listing games returns an empty list when no games exist."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get("/api/games")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_games_with_result_filter(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Providing ?result= passes the filter to the query."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get("/api/games?result=1-0")

    assert response.status_code == 200
    mock_session.execute.assert_awaited_once()


async def test_list_games_pagination(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Offset and limit query parameters are accepted."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get("/api/games?offset=10&limit=5")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}
# ---------------------------------------------------------------------------


async def test_get_game_success(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Getting an existing game returns its full data including PGN."""
    game = make_game()
    mock_session.get = AsyncMock(return_value=game)

    response = await client.get(f"/api/games/{game.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(game.id)
    assert "pgn_text" in data


async def test_get_game_not_found(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Getting a non-existent game returns 404."""
    mock_session.get = AsyncMock(return_value=None)

    response = await client.get(f"/api/games/{uuid.uuid4()}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
