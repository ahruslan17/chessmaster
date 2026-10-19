from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from httpx import AsyncClient

from tests.conftest import SAMPLE_PGN_SINGLE
from tests.test_api.conftest import make_game, make_game_analysis


@pytest.fixture()
def import_service():
    """No import test may publish real Celery work."""
    with (
        patch("app.api.games.GameReviewService") as service_cls,
        patch("app.api.games.publish_attempt", new_callable=AsyncMock) as publish,
    ):
        service = service_cls.return_value
        service.queue_engine = AsyncMock(return_value=(make_game_analysis(
            status="queued", engine_status="queued", engine_attempt_id=uuid.uuid4(),
            engine_task_id="import-engine-task",
        ), True))
        publish.return_value = True
        yield service, publish

# ---------------------------------------------------------------------------
# POST /api/games/upload
# ---------------------------------------------------------------------------


async def test_upload_pgn_creates_games_and_queues_analysis(
    import_service,
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Uploading a valid PGN creates games and dispatches Celery tasks."""
    game = make_game()

    mock_service, publish = import_service
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
    mock_service.queue_engine.assert_awaited_once_with(game.id)
    analysis = mock_service.queue_engine.return_value[0]
    publish.assert_awaited_once_with(
        mock_session, stage="engine", entity_id=analysis.id, game_id=game.id,
        attempt_id=analysis.engine_attempt_id, task_id=analysis.engine_task_id,
    )


async def test_upload_pgn_empty_file_returns_400(
    import_service,
    client: AsyncClient,
) -> None:
    """Uploading an empty file returns 400."""
    response = await client.post(
        "/api/games/upload",
        files={"file": ("empty.pgn", b"   ", "application/x-chess-pgn")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Загруженный файл пуст"
    import_service[1].assert_not_awaited()


async def test_upload_pgn_no_valid_games_returns_422(
    import_service,
    client: AsyncClient,
) -> None:
    """Uploading a PGN with no parseable games returns 422."""
    mock_service, publish = import_service
    mock_service.create_games_from_pgn = AsyncMock(return_value=([], []))

    response = await client.post(
        "/api/games/upload",
        files={"file": ("bad.pgn", b"not a pgn", "application/x-chess-pgn")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "В PGN-файле не найдено корректных партий"  # noqa: RUF001
    publish.assert_not_awaited()


async def test_import_pgn_text_creates_games(
    import_service,
    client: AsyncClient,
) -> None:
    """Importing PGN text creates games and queues analysis."""
    game = make_game()
    mock_service, publish = import_service
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
    mock_service.queue_engine.assert_awaited_once_with(game.id)
    publish.assert_awaited_once()


async def test_import_pgn_text_empty_returns_400(
    import_service,
    client: AsyncClient,
) -> None:
    """Importing empty PGN text returns 400."""
    response = await client.post(
        "/api/games/import",
        json={"pgn_text": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Текст PGN пуст"
    import_service[1].assert_not_awaited()


@pytest.mark.parametrize("source", ["query", "form", "both"])
async def test_upload_pgn_with_player_color(
    source: str,
    import_service,
    client: AsyncClient,
) -> None:
    """The optional player_color query parameter is passed to the service."""
    game = make_game(player_color="black")
    mock_service, _ = import_service
    mock_service.create_games_from_pgn = AsyncMock(return_value=([game], [game.id]))

    response = await client.post(
        "/api/games/upload" + ("?player_color=black" if source != "form" else ""),
        files={"file": ("test.pgn", SAMPLE_PGN_SINGLE.encode(), "application/x-chess-pgn")},
        data={"player_color": "black"} if source != "query" else {},
    )

    assert response.status_code == 201
    mock_service.create_games_from_pgn.assert_awaited_once()
    call_kwargs = mock_service.create_games_from_pgn.call_args
    assert call_kwargs.kwargs.get("player_color") == "black"


async def test_import_persists_queue_before_commit_and_publication(
    import_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish = import_service
    game = make_game(player_color=None)
    service.create_games_from_pgn = AsyncMock(return_value=([game], [game.id]))
    order = MagicMock()
    order.attach_mock(service.queue_engine, "queue")
    order.attach_mock(mock_session.commit, "commit")
    order.attach_mock(publish, "publish")

    response = await client.post("/api/games/import", json={"pgn_text": SAMPLE_PGN_SINGLE})

    assert response.status_code == 201
    assert response.json()[0]["player_color"] is None
    assert [call[0] for call in order.mock_calls] == ["queue", "commit", "publish"]
    assert publish.await_args.kwargs["stage"] == "engine"
    service.queue_explanations.assert_not_called()


async def test_import_duplicate_does_not_queue_again(
    import_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish = import_service
    game = make_game()
    service.create_games_from_pgn = AsyncMock(return_value=([game], []))

    response = await client.post("/api/games/import", json={"pgn_text": SAMPLE_PGN_SINGLE})

    assert response.status_code == 201
    service.queue_engine.assert_not_awaited()
    publish.assert_not_awaited()
    mock_session.commit.assert_awaited_once()


async def test_import_existing_attempt_is_not_published_again(
    import_service, client: AsyncClient,
) -> None:
    service, publish = import_service
    game = make_game()
    service.create_games_from_pgn = AsyncMock(return_value=([game], [game.id]))
    service.queue_engine.return_value = (make_game_analysis(), False)

    response = await client.post("/api/games/import", json={"pgn_text": SAMPLE_PGN_SINGLE})

    assert response.status_code == 201
    service.queue_engine.assert_awaited_once_with(game.id)
    publish.assert_not_awaited()


async def test_import_queue_publication_failure_preserves_created_game(
    import_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish = import_service
    game = make_game()
    service.create_games_from_pgn = AsyncMock(return_value=([game], [game.id]))
    publish.return_value = False

    response = await client.post("/api/games/import", json={"pgn_text": SAMPLE_PGN_SINGLE})

    assert response.status_code == 503
    assert response.json()["detail"]["game_id"] == str(game.id)
    assert response.json()["detail"]["game_ids"] == [str(game.id)]
    assert "Партии сохранены" in response.json()["detail"]["message"]
    mock_session.commit.assert_awaited_once()
    publish.assert_awaited_once()


@pytest.mark.parametrize("endpoint", ["import", "upload"])
@pytest.mark.parametrize("published", [(False, True, True), (False, True, False)])
async def test_bulk_import_publishes_all_committed_attempts_despite_first_failure(
    endpoint: str, published: tuple[bool, bool, bool],
    import_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish = import_service
    games = [make_game() for _ in range(3)]
    analyses = [make_game_analysis(
        game_id=game.id, status="pending", engine_status="queued",
        engine_attempt_id=uuid.uuid4(), engine_task_id=str(uuid.uuid4()),
    ) for game in games]
    game_ids = [game.id for game in games]
    service.create_games_from_pgn = AsyncMock(return_value=(games, game_ids))
    service.queue_engine.side_effect = [(analysis, True) for analysis in analyses]
    publish.side_effect = published
    order = MagicMock()
    order.attach_mock(service.queue_engine, "queue")
    order.attach_mock(mock_session.commit, "commit")
    order.attach_mock(publish, "publish")

    if endpoint == "import":
        response = await client.post("/api/games/import", json={"pgn_text": SAMPLE_PGN_SINGLE})
    else:
        response = await client.post(
            "/api/games/upload", files={"file": ("test.pgn", SAMPLE_PGN_SINGLE.encode())},
        )

    assert response.status_code == 503
    failed_ids = [
        str(game.id) for game, success in zip(games, published, strict=True) if not success
    ]
    assert response.json()["detail"]["game_id"] == failed_ids[0]
    assert response.json()["detail"]["game_ids"] == failed_ids
    assert "Партии сохранены" in response.json()["detail"]["message"]
    assert service.queue_engine.await_args_list == [call(game_id) for game_id in game_ids]
    mock_session.commit.assert_awaited_once()
    assert [entry[0] for entry in order.mock_calls] == [
        "queue", "queue", "queue", "commit", "publish", "publish", "publish",
    ]
    assert publish.await_args_list == [call(
        mock_session, stage="engine", entity_id=analysis.id, game_id=game.id,
        attempt_id=analysis.engine_attempt_id, task_id=analysis.engine_task_id,
    ) for game, analysis in zip(games, analyses, strict=True)]
    service.queue_explanations.assert_not_called()


async def test_upload_conflicting_colors_rejected_before_import(
    import_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    response = await client.post(
        "/api/games/upload?player_color=white",
        files={"file": ("test.pgn", SAMPLE_PGN_SINGLE.encode())},
        data={"player_color": "black"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Цвет в форме и параметрах запроса не совпадает"
    import_service[0].create_games_from_pgn.assert_not_called()
    import_service[1].assert_not_awaited()
    mock_session.commit.assert_not_awaited()


@pytest.mark.parametrize("source", ["query", "form", "json"])
async def test_invalid_player_color_rejected(
    source: str, import_service, client: AsyncClient,
) -> None:
    if source == "json":
        response = await client.post(
            "/api/games/import", json={"pgn_text": SAMPLE_PGN_SINGLE, "player_color": "green"},
        )
    else:
        response = await client.post(
            "/api/games/upload" + ("?player_color=green" if source == "query" else ""),
            files={"file": ("test.pgn", SAMPLE_PGN_SINGLE.encode())},
            data={"player_color": "green"} if source == "form" else {},
        )

    assert response.status_code == 422
    import_service[0].create_games_from_pgn.assert_not_called()
    import_service[1].assert_not_awaited()


async def test_upload_reads_only_limit_plus_one_and_rejects_oversize(
    import_service, mock_session: AsyncMock,
) -> None:
    from fastapi import HTTPException

    from app.api.games import _MAX_UPLOAD_SIZE, upload_pgn

    upload = MagicMock()
    upload.read = AsyncMock(return_value=b"x" * (_MAX_UPLOAD_SIZE + 1))

    with pytest.raises(HTTPException) as exc:
        await upload_pgn(upload, mock_session, player_color=None, form_player_color=None)

    assert exc.value.status_code == 413
    upload.read.assert_awaited_once_with(_MAX_UPLOAD_SIZE + 1)
    import_service[0].create_games_from_pgn.assert_not_called()
    import_service[1].assert_not_awaited()
    mock_session.commit.assert_not_awaited()


async def test_import_no_valid_games_rejected(import_service, client: AsyncClient) -> None:
    service, publish = import_service
    service.create_games_from_pgn = AsyncMock(return_value=([], []))

    response = await client.post("/api/games/import", json={"pgn_text": "not a game"})

    assert response.status_code == 422
    assert response.json()["detail"] == "В тексте PGN не найдено корректных партий"  # noqa: RUF001
    service.queue_engine.assert_not_awaited()
    publish.assert_not_awaited()


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
    assert response.json()["detail"] == "Партия не найдена"
