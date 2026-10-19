"""Explicit analysis commands and persisted-attempt broker publication."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api.analysis_queue import publish_attempt
from tests.test_api.conftest import make_game, make_game_analysis, make_side_review


@pytest.fixture()
def command_service():
    with (
        patch("app.api.analysis.GameReviewService") as service_cls,
        patch("app.api.analysis.publish_attempt", new_callable=AsyncMock) as publish,
        patch(
            "app.api.analysis.settings", SimpleNamespace(llm_api_key="", litellm_base_url=""),
        ) as config,
    ):
        service = service_cls.return_value
        service.queue_engine = AsyncMock()
        service.queue_explanations = AsyncMock()
        publish.return_value = True
        yield service, publish, config


@pytest.mark.parametrize("queued", [True, False])
async def test_start_engine_persists_before_publishing_or_reuses_attempt(
    queued: bool, command_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish, _ = command_service
    game_id = uuid.uuid4()
    analysis = make_game_analysis(
        game_id=game_id, status="pending", engine_status="queued",
        engine_attempt_id=uuid.uuid4(), engine_task_id="engine-task",
    )
    service.queue_engine.return_value = (analysis, queued)
    order = MagicMock()
    order.attach_mock(service.queue_engine, "queue")
    order.attach_mock(mock_session.commit, "commit")
    order.attach_mock(publish, "publish")

    response = await client.post(f"/api/games/{game_id}/analysis/start", json={})

    assert response.status_code == 200
    assert response.json()["engine_status"] == "queued"
    service.queue_engine.assert_awaited_once_with(
        game_id, recover=False, expected_attempt_id=None,
    )
    assert [call[0] for call in order.mock_calls] == (
        ["queue", "commit", "publish"] if queued else ["queue", "commit"]
    )
    if queued:
        publish.assert_awaited_once_with(
            mock_session, stage="engine", entity_id=analysis.id, game_id=game_id,
            attempt_id=analysis.engine_attempt_id, task_id="engine-task",
        )
    else:
        publish.assert_not_awaited()
    service.queue_explanations.assert_not_awaited()


async def test_start_engine_broker_failure_returns_retryable_503(
    command_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish, _ = command_service
    game_id = uuid.uuid4()
    service.queue_engine.return_value = (make_game_analysis(
        engine_status="queued", engine_attempt_id=uuid.uuid4(), engine_task_id="task",
    ), True)
    publish.return_value = False

    response = await client.post(f"/api/games/{game_id}/analysis/start", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == "Очередь недоступна. Повторите запуск анализа."
    mock_session.commit.assert_awaited_once()
    service.queue_engine.assert_awaited_once()


@pytest.mark.parametrize("endpoint", ["start", "explanations"])
async def test_recovery_forwards_expected_attempt_to_own_stage(
    endpoint: str, command_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, _, config = command_service
    config.litellm_base_url = "http://configured-provider.invalid"
    game = make_game()
    mock_session.get.return_value = game
    expected = uuid.uuid4()
    body = {"recover": True, "expected_attempt_id": str(expected)}
    if endpoint == "start":
        method = service.queue_engine
        method.return_value = (make_game_analysis(), False)
        args = (game.id,)
    else:
        method = service.queue_explanations
        method.return_value = (make_side_review(player_color="black"), False)
        body["player_color"] = "black"
        args = (game.id, "black")

    response = await client.post(f"/api/games/{game.id}/analysis/{endpoint}", json=body)

    assert response.status_code == 200
    method.assert_awaited_once_with(*args, recover=True, expected_attempt_id=expected)


async def test_explanations_unconfigured_returns_503_without_redoing_engine(
    command_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish, _ = command_service
    game = make_game()
    mock_session.get.return_value = game

    response = await client.post(
        f"/api/games/{game.id}/analysis/explanations", json={"player_color": "black"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "AI-тренер не настроен. Данные движка сохранены."
    service.queue_explanations.assert_not_awaited()
    service.queue_engine.assert_not_awaited()
    publish.assert_not_awaited()
    mock_session.commit.assert_not_awaited()


async def test_explanations_missing_game_returns_404_before_provider_configuration(
    command_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish, _ = command_service

    response = await client.post(
        f"/api/games/{uuid.uuid4()}/analysis/explanations", json={"player_color": "white"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Партия не найдена"
    service.queue_explanations.assert_not_awaited()
    service.queue_engine.assert_not_awaited()
    publish.assert_not_awaited()
    mock_session.commit.assert_not_awaited()


@pytest.mark.parametrize("publication", ["queued", "existing", "broker_failure"])
async def test_explanations_only_queues_selected_coach_stage(
    publication: str, command_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish, config = command_service
    config.llm_api_key = "fake-test-key"
    game = make_game(player_color="white")
    mock_session.get.return_value = game
    review = make_side_review(
        player_color="black", status="queued", attempt_id=uuid.uuid4(), task_id="coach-task",
    )
    service.queue_explanations.return_value = (review, publication != "existing")
    publish.return_value = publication != "broker_failure"
    order = MagicMock()
    order.attach_mock(service.queue_explanations, "queue")
    order.attach_mock(mock_session.commit, "commit")
    order.attach_mock(publish, "publish")

    response = await client.post(
        f"/api/games/{game.id}/analysis/explanations", json={"player_color": "black"},
    )

    assert response.status_code == (503 if publication == "broker_failure" else 200)
    service.queue_explanations.assert_awaited_once_with(
        game.id, "black", recover=False, expected_attempt_id=None,
    )
    service.queue_engine.assert_not_awaited()
    assert [call[0] for call in order.mock_calls] == (
        ["queue", "commit"] if publication == "existing" else ["queue", "commit", "publish"]
    )
    if publication != "existing":
        publish.assert_awaited_once_with(
            mock_session, stage="coach", entity_id=review.id, game_id=game.id,
            attempt_id=review.attempt_id, task_id="coach-task", player_color="black",
        )


@pytest.mark.parametrize("body", [{}, {"player_color": "green"}, {"player_color": None}])
async def test_explanations_requires_explicit_valid_side(
    body: dict, command_service, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    service, publish, _ = command_service

    response = await client.post(f"/api/games/{uuid.uuid4()}/analysis/explanations", json=body)

    assert response.status_code == 422
    service.queue_explanations.assert_not_awaited()
    service.queue_engine.assert_not_awaited()
    publish.assert_not_awaited()
    mock_session.commit.assert_not_awaited()


@pytest.mark.parametrize("stage", ["engine", "coach"])
@pytest.mark.parametrize("fails", [False, True])
async def test_publish_attempt_uses_persisted_task_id_and_marks_matching_failure(
    stage: str, fails: bool, mock_session: AsyncMock,
) -> None:
    game_id, entity_id, attempt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with (
        patch("app.api.analysis_queue.analyze_game_task") as engine,
        patch("app.api.analysis_queue.explain_game_task") as coach,
        patch("app.api.analysis_queue.GameReviewService") as service_cls,
    ):
        service = service_cls.return_value
        service.mark_publication_failed = AsyncMock()
        task, other_task = (engine, coach) if stage == "engine" else (coach, engine)
        if fails:
            task.apply_async.side_effect = ConnectionError("Broker unavailable")

        result = await publish_attempt(
            mock_session, stage=stage, entity_id=entity_id, game_id=game_id,
            attempt_id=attempt_id, task_id="persisted-task", player_color="black",
        )

        assert result is not fails
        args = ([str(game_id), str(attempt_id)] if stage == "engine"
                else [str(game_id), "black", str(attempt_id)])
        task.apply_async.assert_called_once_with(args=args, task_id="persisted-task", retry=False)
        task.delay.assert_not_called()
        other_task.apply_async.assert_not_called()
        if fails:
            service.mark_publication_failed.assert_awaited_once_with(
                stage, entity_id, attempt_id,
                "Не удалось отправить задание в очередь. Повторите запуск анализа.",  # noqa: RUF001
            )
            mock_session.commit.assert_awaited_once()
        else:
            service.mark_publication_failed.assert_not_awaited()
            mock_session.commit.assert_not_awaited()
