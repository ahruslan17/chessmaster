from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.dialects import postgresql

from app.models.game import Game
from tests.test_api.conftest import (
    make_game,
    make_game_analysis,
    make_move_analysis,
    make_side_review,
    set_scalar_results,
)

pytestmark = pytest.mark.usefixtures("read_only_api")

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

    set_scalar_results(mock_session, analysis, None)

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
    assert data["summary"] is None
    assert data["accuracy_white"] is None
    assert data["accuracy_black"] is None


async def test_get_analysis_game_not_found(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Requesting analysis for a non-existent game returns 404."""
    mock_session.get = AsyncMock(return_value=None)

    response = await client.get(f"/api/games/{uuid.uuid4()}/analysis")

    assert response.status_code == 404
    assert response.json()["detail"] == "Партия не найдена"
    mock_session.execute.assert_not_awaited()


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
    assert response.json()["detail"] == "Анализ для этой партии не найден"


# ---------------------------------------------------------------------------
# GET /api/games/{game_id}/analysis/status
# ---------------------------------------------------------------------------


async def test_get_analysis_status_done(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Status endpoint returns the current analysis status."""
    game = make_game()
    game_id = game.id
    mock_session.get.return_value = game
    set_scalar_results(mock_session, make_game_analysis(game_id=game_id), None)

    response = await client.get(f"/api/games/{game_id}/analysis/status")

    assert response.status_code == 200
    data = response.json()
    assert data["game_id"] == str(game_id)
    assert data["status"] == "done"
    assert data["engine_status"] == "done"
    mock_session.get.assert_awaited_once_with(Game, game_id)


async def test_get_analysis_status_in_progress(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Status endpoint returns 'in_progress' when analysis is running."""
    game = make_game()
    game_id = game.id
    analysis = make_game_analysis(
        game_id=game_id, status="in_progress", engine_status="in_progress",
        progress_current=2, progress_total=10,
    )
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, None)

    response = await client.get(f"/api/games/{game_id}/analysis/status")

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert response.json()["progress_current"] == 2
    assert response.json()["progress_total"] == 10


async def test_get_analysis_status_pending_when_no_record(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Status endpoint returns 'pending' when no analysis record exists."""
    game = make_game()
    game_id = game.id
    mock_session.get.return_value = game

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get(f"/api/games/{game_id}/analysis/status")

    assert response.status_code == 200
    data = response.json()
    assert data["game_id"] == str(game_id)
    assert data["status"] == "pending"
    assert data["engine_status"] == "pending"
    mock_session.execute.assert_awaited_once()


async def test_status_missing_game_returns_404(
    client: AsyncClient, mock_session: AsyncMock,
) -> None:
    response = await client.get(f"/api/games/{uuid.uuid4()}/analysis/status")

    assert response.status_code == 404
    assert response.json()["detail"] == "Партия не найдена"
    mock_session.execute.assert_not_awaited()


@pytest.mark.parametrize("color", ["white", "black"])
async def test_get_analysis_projects_only_selected_review(
    color: str, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    game = make_game(player_color="white")
    analysis = make_game_analysis(game_id=game.id)
    analysis.moves = [
        make_move_analysis(color="black", move_san="e5", llm_comment="Unscoped black"),
        make_move_analysis(color="white", llm_comment="Unscoped white"),
    ]
    review = make_side_review(
        game_analysis_id=analysis.id, player_color=color, summary=f"For {color}",
        comments={"0" if color == "white" else "1": {"reason": f"Only {color}"}},
        recommendations=[f"Practice {color}"], context={
            "version": 1, "player_color": color,
            "engine_result_id": str(analysis.engine_result_id), "moments": [{"move_index": 0}],
        },
    )
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis?player_color={color}")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == f"For {color}"
    assert data["review"]["player_color"] == color
    assert data["coach_feedback"] == {"focus_points": [f"Practice {color}"]}
    assert data["key_moments"] == [{"move_index": 0}]
    comments = [move["llm_comment"] for move in data["moves"]]
    assert comments == (["Only white", None] if color == "white" else [None, "Only black"])
    review_query = mock_session.execute.call_args_list[1].args[0]
    assert color in review_query.compile().params.values()
    assert analysis.id in review_query.compile().params.values()


@pytest.mark.parametrize("score_version", [None, 0])
async def test_legacy_analysis_suppresses_unverified_scores_and_coaching(
    score_version: int | None, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    game = make_game()
    analysis = make_game_analysis(game_id=game.id, score_version=score_version)
    analysis.moves = [make_move_analysis(
        llm_comment="Old unscoped commentary", score_before={"cp": 12},
        score_after={"cp": 30}, classification="best",
    )]
    review = make_side_review(summary="Saved but unverified", comments={"0": {"reason": "Old"}})
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 200
    data = response.json()
    for key in ("summary", "accuracy_white", "accuracy_black", "coach_feedback", "review"):
        assert data[key] is None
    assert data["key_moments"] == []
    for key in ("llm_comment", "score_before", "score_after", "classification"):
        assert data["moves"][0][key] is None


async def test_get_analysis_without_color_keeps_engine_data_only(
    client: AsyncClient, mock_session: AsyncMock,
) -> None:
    game = make_game(player_color=None)
    analysis = make_game_analysis(game_id=game.id)
    analysis.moves = [make_move_analysis(score_after={"cp": 30}, llm_comment="Unscoped")]
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 200
    assert response.json()["moves"][0]["score_after"]["cp"] == 30
    assert response.json()["moves"][0]["llm_comment"] is None
    assert response.json()["review"] is None
    mock_session.execute.assert_awaited_once()


async def test_status_includes_selected_side_failure_without_losing_engine_progress(
    client: AsyncClient, mock_session: AsyncMock,
) -> None:
    game = make_game()
    analysis = make_game_analysis(engine_attempt_id=uuid.uuid4(), engine_task_id="engine-task")
    review = make_side_review(player_color="black", status="failed", error="Provider unavailable")
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis/status?player_color=black")

    assert response.status_code == 200
    assert response.json()["engine_status"] == "done"
    assert response.json()["engine_attempt_id"] == str(analysis.engine_attempt_id)
    assert response.json()["engine_task_id"] == "engine-task"
    assert response.json()["review_status"] == "failed"
    assert response.json()["review_error"] == "Provider unavailable"


@pytest.mark.parametrize("stale_field", ["version", "player_color", "engine_result_id"])
async def test_stale_side_review_is_hidden_but_engine_scores_remain(
    stale_field: str, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    game = make_game()
    analysis = make_game_analysis(game_id=game.id)
    analysis.moves = [make_move_analysis(score_after={"cp": 24}, classification="best")]
    review = make_side_review(summary="Stale summary", comments={"0": {"reason": "Stale"}})
    review.context[stale_field] = {
        "version": 0, "player_color": "black", "engine_result_id": str(uuid.uuid4()),
    }[stale_field]
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] is None
    assert data["review"] is None
    assert data["moves"][0]["llm_comment"] is None
    assert data["moves"][0]["score_after"]["cp"] == 24
    assert data["moves"][0]["classification"] == "best"


async def test_saved_side_review_null_optional_payloads_normalize_to_empty(
    client: AsyncClient, mock_session: AsyncMock,
) -> None:
    game = make_game()
    analysis = make_game_analysis(game_id=game.id)
    review = make_side_review(comments=None, recommendations=None, usage=None)
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 200
    assert response.json()["review"]["comments"] == {}
    assert response.json()["review"]["recommendations"] == []
    assert response.json()["review"]["usage"] == {}


@pytest.mark.parametrize("suffix", ["", "/status", "/moves/0/commentary/stream"])
async def test_analysis_reads_share_lock_owner_before_loading_side_review(
    suffix: str, client: AsyncClient, mock_session: AsyncMock,
) -> None:
    """Reads lock the analysis generation, without committing or starting work."""
    game = make_game()
    analysis = make_game_analysis(game_id=game.id)
    analysis.moves = [make_move_analysis(game_analysis_id=analysis.id)]
    review = make_side_review(
        game_analysis_id=analysis.id, comments={"0": {"reason": "Saved explanation"}},
    )
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis{suffix}")

    assert response.status_code == 200
    assert mock_session.execute.await_count == 2
    owner_query, review_query = [call.args[0] for call in mock_session.execute.await_args_list]
    assert owner_query.is_select
    assert owner_query._for_update_arg is not None
    assert owner_query._for_update_arg.read is True
    owner_sql = str(owner_query.compile(dialect=postgresql.dialect()))
    assert "FROM game_analyses" in owner_sql
    assert "FOR SHARE" in owner_sql
    assert "FOR UPDATE" not in owner_sql
    assert game.id in owner_query.compile().params.values()
    assert review_query.is_select
    assert "FROM side_reviews" in str(review_query.compile(dialect=postgresql.dialect()))
    assert analysis.id in review_query.compile().params.values()
