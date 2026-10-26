# Russian coaching text is intentional.
# ruff: noqa: RUF001

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

import chess
import pytest
from httpx import AsyncClient

from app.api.analysis import _comment_text
from tests.test_api.conftest import (
    make_game,
    make_game_analysis,
    make_move_analysis,
    make_side_review,
    set_scalar_results,
)


def commentary() -> dict:
    return {
        "version": 2,
        "played": {"idea": "Пешка занимает центр.", "plan": "Развивать лёгкие фигуры."},
        "alternative": {"idea": "Другой пешечный центр.", "pros": "Открыта диагональ слона."},
        "comparison": "Различается пешечная структура.",
    }


def review_fixture(*, same_move: bool = False):
    game = make_game()
    analysis = make_game_analysis(game_id=game.id)
    best = "e4" if same_move else "d4"
    analysis.moves = [make_move_analysis(best_move_san=best)]
    review = make_side_review(
        context={
            "version": 1, "player_color": "white", "commentary_scope": "all_moves",
            "commentary_version": 2, "engine_result_id": str(analysis.engine_result_id),
            "moments": [], "moments_by_color": {"white": [], "black": []},
            "moves": [{
                "move_index": 0, "move_san": "e4", "best_move_san": best,
                "fen_before": chess.STARTING_FEN, "best_line": [best, "d5"],
            }],
        },
        comments={"0": commentary()},
    )
    return game, analysis, review


@pytest.mark.usefixtures("read_only_api")
@pytest.mark.parametrize("color", ["white", "black"])
async def test_structured_read_is_shared_and_preserves_storage(
    color: str, client: AsyncClient, mock_session: AsyncMock,
):
    game, analysis, review = review_fixture()
    original = copy.deepcopy(review.comments)
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis?player_color={color}")

    assert response.status_code == 200
    data = response.json()
    move = data["moves"][0]
    assert move["commentary"]["played"]["idea"] == original["0"]["played"]["idea"]
    assert move["commentary"]["alternative"]["idea"] == original["0"]["alternative"]["idea"]
    assert move["commentary"]["played"]["tactics"] is None
    assert move["best_line"] == ["d4", "d5"]
    assert "Рекомендация движка" in move["llm_comment"]
    assert "moves" not in data["review"]["context"]
    assert data["review"]["player_color"] == color
    assert review.comments == original


@pytest.mark.usefixtures("read_only_api")
async def test_equal_move_has_one_explanation_without_mutating_saved_result(
    client: AsyncClient, mock_session: AsyncMock,
):
    game, analysis, review = review_fixture(same_move=True)
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis")

    move = response.json()["moves"][0]
    assert move["commentary"]["alternative"] is None
    assert move["commentary"]["comparison"] is None
    assert "Рекомендация движка" not in move["llm_comment"]
    assert review.comments["0"]["alternative"] is not None


@pytest.mark.usefixtures("read_only_api")
@pytest.mark.parametrize("mutation", ["illegal", "null", "wrong_start", "wrong_move", "wrong_fen"])
async def test_best_line_must_belong_to_current_move_and_be_legal(
    mutation: str, client: AsyncClient, mock_session: AsyncMock,
):
    game, analysis, review = review_fixture()
    moment = review.context["moves"][0]
    if mutation == "illegal":
        moment["best_line"] = ["d4", "e1"]
    elif mutation == "null":
        moment["best_line"] = ["d4", "--", "d5"]
    elif mutation == "wrong_start":
        moment["best_line"] = ["e4", "e5"]
    elif mutation == "wrong_move":
        moment["move_san"] = "c4"
    else:
        board = chess.Board()
        board.push_san("e4")
        moment["fen_before"] = board.fen()
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 200
    assert response.json()["moves"][0]["best_line"] is None


def test_legacy_and_structured_text_fallbacks():
    assert _comment_text({"text": "Старый абзац"}) == "Старый абзац"
    assert _comment_text({"reason": "Причина", "alternative": "Альтернатива"}) == (
        "Причина\nАльтернатива"
    )
    text = _comment_text(commentary())
    assert "Дальнейший план: Развивать лёгкие фигуры." in text
    assert "Тактика:" not in text


@pytest.mark.usefixtures("read_only_api")
async def test_invalid_entry_does_not_hide_other_saved_comments(
    client: AsyncClient, mock_session: AsyncMock,
):
    game, analysis, review = review_fixture()
    review.comments.update({
        "1": {"text": "Сохранённый текст"},
        "2": {"version": 2, "played": {}, "alternative": {"idea": "Не показывать"}},
        "3": {"version": 2, "played": {}},
    })
    original = copy.deepcopy(review.comments)
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 200
    assert response.json()["review"]["comments"].keys() == {"0", "1"}
    assert response.json()["moves"][0]["commentary"]["played"]["idea"]
    assert _comment_text(original["2"]) is None
    assert review.comments == original


@pytest.mark.usefixtures("read_only_api")
async def test_legacy_side_review_exposes_its_verified_recommendation_line(
    client: AsyncClient, mock_session: AsyncMock,
):
    game, analysis, review = review_fixture()
    review.context.pop("commentary_scope")
    review.context["moments"] = review.context.pop("moves")
    review.comments = {"0": {"reason": "Старое объяснение"}}
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 200
    assert response.json()["moves"][0]["best_line"] == ["d4", "d5"]


@pytest.mark.usefixtures("read_only_api")
async def test_stale_engine_commentary_and_variations_are_not_exposed(
    client: AsyncClient, mock_session: AsyncMock,
):
    game, analysis, review = review_fixture()
    review.context["engine_result_id"] = "outdated-result"
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis")

    data = response.json()
    assert data["review"] is None
    assert data["moves"][0]["commentary"] is None
    assert data["moves"][0]["best_line"] is None
    assert data["moves"][0]["llm_comment"] is None


@pytest.mark.usefixtures("read_only_api")
async def test_saved_structured_stream_has_both_branches_without_generation(
    client: AsyncClient, mock_session: AsyncMock,
):
    game, analysis, review = review_fixture()
    mock_session.get.return_value = game
    set_scalar_results(mock_session, analysis, review)

    response = await client.get(f"/api/games/{game.id}/analysis/moves/0/commentary/stream")

    assert response.status_code == 200
    assert "data: Сыграно в партии" in response.text
    assert "data: Рекомендация движка" in response.text


async def test_explicit_detailed_upgrade_reaches_lifecycle_only_on_post(
    client: AsyncClient, mock_session: AsyncMock,
):
    game, _, review = review_fixture()
    mock_session.get.return_value = game
    with (
        patch("app.api.analysis.settings") as settings,
        patch("app.api.analysis.GameReviewService") as service,
    ):
        settings.access_control_enabled = False
        settings.llm_api_key = "test-not-a-real-key"
        service.return_value.queue_explanations = AsyncMock(return_value=(review, False))

        response = await client.post(
            f"/api/games/{game.id}/analysis/explanations",
            json={"player_color": "black", "detailed": True},
        )

    assert response.status_code == 200
    service.return_value.queue_explanations.assert_awaited_once_with(
        game.id, "black", recover=False, expected_attempt_id=None, detailed=True,
    )
