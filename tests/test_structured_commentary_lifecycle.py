from __future__ import annotations

import copy
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.side_review import SideReview
from app.schemas.move_commentary import MoveCommentary
from app.services.game_review import GameReviewService, _build_move_analysis
from app.services.llm_coach import FullCommentaryResult
from app.services.review_moments import is_structured_commentary
from app.services.stockfish_analyzer import EngineScore, MoveEvaluation
from app.tasks import analysis as tasks
from tests.test_analysis_lifecycle import bind_session, game, owner, result, session_with


def commentary(idea="Ready idea"):
    return MoveCommentary.model_validate({
        "version": 2, "played": {"idea": idea}, "alternative": None, "comparison": None,
    })


def review_for(analysis, *, status="done", full=True, target=None):
    context = {
        "engine_result_id": str(analysis.engine_result_id), "player_color": "white",
        "moments": [{"move_index": 0}],
    }
    if full:
        context.update({"commentary_scope": "all_moves", "moves": [
            {"move_index": index} for index in range(3)
        ]})
    if target is not None:
        context["commentary_version"] = target
    return SideReview(
        id=uuid.uuid4(), game_analysis_id=analysis.id, player_color="white", status=status,
        attempt_id=uuid.uuid4(), task_id=str(uuid.uuid4()), context=context,
        comments={str(index): {"text": f"Legacy {index}"} for index in range(3)},
        summary="Existing summary", recommendations=["Existing recommendation"],
    )


def queue_session(monkeypatch, analysis, review):
    evaluation = MoveEvaluation(
        move_number=1, color="white", move_san="e4", best_move_san="e4",
        eval_before=0, eval_after=0, centipawn_loss=0, classification="best",
        score_before=EngineScore(cp=0), score_after=EngineScore(cp=0), played_line=["e4"],
    )
    monkeypatch.setattr(
        "app.services.review_moments.build_review_context",
        lambda *_, **__: {
            "version": 1, "player_color": "white", "moments": [],
            "commentary_scope": "all_moves", "commentary_version": 2, "moves": [
                {"move_index": index} for index in range(3)
            ],
        },
    )
    return session_with(
        result(game(analysis)), result(analysis), result(review),
        result(values=[_build_move_analysis(analysis.id, evaluation)]),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("color", ["white", "black"])
async def test_ready_legacy_requires_explicit_detailed_upgrade(monkeypatch, color):
    analysis = owner()
    review = review_for(analysis)
    before = copy.deepcopy(review.comments)
    engine_result = analysis.engine_result_id
    previous_attempt = review.attempt_id
    session = queue_session(monkeypatch, analysis, review)
    returned, queued = await GameReviewService(session).queue_explanations(
        analysis.game_id, color,
    )
    assert returned is review and not queued
    assert review.attempt_id == previous_attempt
    session.flush.assert_not_awaited()

    session = queue_session(monkeypatch, analysis, review)
    returned, queued = await GameReviewService(session).queue_explanations(
        analysis.game_id, color, detailed=True,
    )
    assert returned is review and queued
    assert review.context["commentary_version"] == 2 and review.status == "queued"
    assert review.attempt_id != previous_attempt
    assert review.comments == before and review.summary == "Existing summary"
    assert review.player_color == "white" and analysis.engine_result_id == engine_result


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "in_progress"])
@pytest.mark.parametrize("detailed", [False, True])
async def test_duplicate_cannot_replace_active_attempt(monkeypatch, status, detailed):
    analysis = owner()
    review = review_for(analysis, status=status)
    before = (review.attempt_id, review.task_id, copy.deepcopy(review.context))
    session = queue_session(monkeypatch, analysis, review)
    returned, queued = await GameReviewService(session).queue_explanations(
        analysis.game_id, "black", detailed=detailed,
    )
    assert returned is review and not queued
    assert (review.attempt_id, review.task_id, review.context) == before
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("color", ["white", "black"])
@pytest.mark.parametrize("detailed", [False, True])
async def test_completed_v2_shared_review_is_idempotent(monkeypatch, color, detailed):
    analysis = owner()
    review = review_for(analysis, target=2)
    review.comments = {str(i): commentary().model_dump(mode="json") for i in range(3)}
    previous_attempt = review.attempt_id
    session = queue_session(monkeypatch, analysis, review)
    returned, queued = await GameReviewService(session).queue_explanations(
        analysis.game_id, color, detailed=detailed,
    )
    assert returned is review and not queued and review.attempt_id == previous_attempt
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_new_or_side_only_review_targets_v2_without_erasing_current_text(
    monkeypatch, existing,
):
    analysis = owner()
    review = review_for(analysis, full=False) if existing else None
    before = copy.deepcopy(review.comments) if review else None
    session = queue_session(monkeypatch, analysis, review)
    returned, queued = await GameReviewService(session).queue_explanations(
        analysis.game_id, "white", detailed=True,
    )
    assert queued and returned.context["commentary_version"] == 2
    assert returned.context["commentary_scope"] == "all_moves"
    assert returned.context["engine_result_id"] == str(analysis.engine_result_id)
    assert returned.comments == before


@pytest.mark.asyncio
@pytest.mark.parametrize("detailed", [False, True])
async def test_side_only_queue_to_worker_expansion_requires_opt_in_for_replacement(
    monkeypatch, detailed,
):
    analysis = owner()
    review = review_for(analysis, full=False)
    legacy = {"reason": "Previously explained", "consequence": "Existing consequence"}
    review.comments = {"0": legacy}
    engine_result = analysis.engine_result_id
    session = queue_session(monkeypatch, analysis, review)
    _, queued = await GameReviewService(session).queue_explanations(
        analysis.game_id, "white", detailed=detailed,
    )
    assert queued and review.comments == {"0": legacy}
    assert (review.context.get("commentary_version") == 2) is detailed
    assert review.summary == "Existing summary"
    assert review.recommendations == ["Existing recommendation"]

    # Emulate the SQL claim; subsequent saves use the real attempt/engine fence.
    review.status = "in_progress"
    session = session_with(
        result(analysis.id), result((review.id, review.context, review.comments)),
        *[rows for _ in range(3) for rows in (result(analysis), result(review))],
    )
    bind_session(monkeypatch, session)
    monkeypatch.setattr(tasks, "_llm_enabled", lambda: True)
    expected_indices = [0, 1, 2] if detailed else [1, 2]
    coach = MagicMock()
    coach.generate_full_commentary = AsyncMock(return_value=FullCommentaryResult(
        comments={index: commentary(f"New {index}") for index in expected_indices},
    ))
    monkeypatch.setattr(tasks, "LLMCoachService", lambda: coach)
    response = await tasks._run_explanation_pipeline(
        str(analysis.game_id), "white", str(review.attempt_id),
    )
    assert response["status"] == "done"
    coach.generate_full_commentary.assert_awaited_once_with({"moves": [
        {"move_index": index} for index in expected_indices
    ]})
    assert review.comments["0"] == (
        commentary("New 0").model_dump(mode="json") if detailed else legacy
    )
    assert all(is_structured_commentary(review.comments[str(index)]) for index in [1, 2])
    assert review.summary == "Existing summary"
    assert review.recommendations == ["Existing recommendation"]
    assert analysis.engine_result_id == engine_result


@pytest.mark.asyncio
async def test_save_without_upgrade_target_never_replaces_existing_legacy(monkeypatch):
    analysis = owner()
    review = review_for(analysis, status="in_progress")
    review.comments.pop("2")
    before = copy.deepcopy(review.comments)
    bind_session(monkeypatch, session_with(result(analysis), result(review)))
    assert await tasks._save_full_commentary(
        review.id, review.attempt_id, FullCommentaryResult(comments={
            0: commentary("Unrequested replacement"), 2: commentary("Missing comment"),
        }), finalize=True,
    ) == "done"
    assert review.comments["0"] == before["0"] and review.comments["1"] == before["1"]
    assert is_structured_commentary(review.comments["2"])


@pytest.mark.parametrize("value", [
    None, "Legacy", {"text": "Legacy"}, {"version": 2},
    {"played": {"idea": "Missing version"}},
    {"version": 2, "played": None},
    {"version": 2, "played": {"idea": 12}},
    {"version": 1, "played": {"idea": "Wrong version"}},
])
def test_version_marker_alone_does_not_make_comment_complete(value):
    assert not is_structured_commentary(value)


def test_valid_structured_comment_is_complete():
    assert is_structured_commentary(commentary().model_dump(mode="json"))


@pytest.mark.asyncio
async def test_ordinary_partial_legacy_retry_does_not_opt_into_upgrade(monkeypatch):
    analysis = owner()
    review = review_for(analysis, status="partial")
    review.comments.pop("2")
    before = copy.deepcopy(review.comments)
    session = queue_session(monkeypatch, analysis, review)
    _, queued = await GameReviewService(session).queue_explanations(analysis.game_id, "white")
    assert queued and "commentary_version" not in review.context
    assert review.comments == before


@pytest.mark.asyncio
async def test_upgrade_batches_replace_only_legacy_and_complete_only_v2(monkeypatch):
    analysis = owner()
    review = review_for(analysis, status="in_progress", target=2)
    preserved = commentary("Existing structured idea").model_dump(mode="json")
    review.comments["0"] = preserved
    attempt = review.attempt_id
    bind_session(monkeypatch, session_with(result(analysis), result(review)))
    assert await tasks._save_full_commentary(
        review.id, attempt, FullCommentaryResult(comments={
            0: commentary("Must not replace ready v2"), 1: commentary("New idea"),
            17: commentary("Foreign move"),
        }, usage={"total_tokens": 10}),
    ) == "in_progress"
    assert review.comments["0"] == preserved
    assert review.comments["1"] == commentary("New idea").model_dump(mode="json")
    assert review.comments["2"] == {"text": "Legacy 2"}
    assert "17" not in review.comments

    bind_session(monkeypatch, session_with(result(analysis), result(review)))
    assert await tasks._save_full_commentary(review.id, attempt, None, finalize=True) == "partial"
    assert review.error and review.summary == "Existing summary"
    review.status = "in_progress"  # Explicit recovery claims another execution.
    bind_session(monkeypatch, session_with(result(analysis), result(review)))
    assert await tasks._save_full_commentary(
        review.id, attempt, FullCommentaryResult(comments={2: commentary("Last idea")}),
        finalize=True,
    ) == "done"
    assert review.error is None and review.usage["total"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_legacy_fixture_result_does_not_clobber_legacy_or_finish_target2(monkeypatch):
    analysis = owner()
    review = review_for(analysis, status="in_progress", target=2)
    before = copy.deepcopy(review.comments)
    bind_session(monkeypatch, session_with(result(analysis), result(review)))
    assert await tasks._save_full_commentary(
        review.id, review.attempt_id, FullCommentaryResult(comments={0: "Fixture string"}),
        finalize=True,
    ) == "partial"
    assert review.comments == before


@pytest.mark.asyncio
async def test_worker_requests_legacy_and_malformed_entries_but_not_valid_v2(monkeypatch):
    analysis = owner()
    review = review_for(analysis, status="queued", target=2)
    review.comments["0"] = commentary().model_dump(mode="json")
    review.comments["2"] = {"version": 2, "played": {}}
    session = session_with(
        result(analysis.id), result((review.id, review.context, review.comments)),
    )
    bind_session(monkeypatch, session)
    monkeypatch.setattr(tasks, "_llm_enabled", lambda: True)
    coach = MagicMock()
    coach.generate_full_commentary = AsyncMock(return_value=FullCommentaryResult(
        comments={1: commentary(), 2: commentary()},
    ))
    monkeypatch.setattr(tasks, "LLMCoachService", lambda: coach)
    save = AsyncMock(return_value="in_progress")
    monkeypatch.setattr(tasks, "_save_full_commentary", save)
    await tasks._run_explanation_pipeline(str(analysis.game_id), "white", str(review.attempt_id))
    coach.generate_full_commentary.assert_awaited_once_with({"moves": [
        {"move_index": 1}, {"move_index": 2},
    ]})
    assert save.call_args.kwargs == {"finalize": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("fence", ["attempt", "engine"])
async def test_upgrade_stale_save_cannot_replace_existing_text(monkeypatch, fence):
    analysis = owner()
    review = review_for(analysis, status="in_progress", target=2)
    before = copy.deepcopy(review.comments)
    attempt = review.attempt_id
    if fence == "attempt":
        review.attempt_id = uuid.uuid4()
    else:
        analysis.engine_result_id = uuid.uuid4()
    session = session_with(result(analysis), result(review))
    bind_session(monkeypatch, session)
    assert await tasks._save_full_commentary(
        review.id, attempt, FullCommentaryResult(comments={0: commentary()}), finalize=True,
    ) == "skipped"
    assert review.comments == before
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_upgrade_recovery_rejects_stale_expected_attempt(monkeypatch):
    analysis = owner()
    review = review_for(analysis, status="partial", target=2)
    session = queue_session(monkeypatch, analysis, review)
    with pytest.raises(HTTPException) as exc:
        await GameReviewService(session).queue_explanations(
            analysis.game_id, "black", detailed=True, recover=True,
            expected_attempt_id=uuid.uuid4(),
        )
    assert exc.value.status_code == 409
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_upgrade_recovery_preserves_progress_and_owner(monkeypatch):
    analysis = owner()
    review = review_for(analysis, status="partial", target=2)
    review.comments["0"] = commentary("Ready before recovery").model_dump(mode="json")
    before = copy.deepcopy(review.comments)
    old_attempt, engine_result = review.attempt_id, analysis.engine_result_id
    session = queue_session(monkeypatch, analysis, review)
    returned, queued = await GameReviewService(session).queue_explanations(
        analysis.game_id, "black", detailed=True, recover=True,
        expected_attempt_id=old_attempt,
    )
    assert returned is review and queued and review.attempt_id != old_attempt
    assert review.comments == before and review.player_color == "white"
    assert analysis.engine_result_id == engine_result
