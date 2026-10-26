from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.models.side_review import SideReview
from app.services.game_review import GameReviewService, _build_move_analysis, _restore_evaluation
from app.services.llm_coach import FullCommentaryResult, ReviewComment, ReviewExplanationResult
from app.services.stockfish_analyzer import EngineScore, MoveEvaluation
from app.tasks import analysis as tasks
from tests.conftest import SAMPLE_PGN_SINGLE


def result(value=None, values=None):
    rows = MagicMock()
    rows.scalar_one_or_none.return_value = value
    rows.one_or_none.return_value = value
    rows.scalars.return_value = values or []
    return rows


def session_with(*results):
    session = AsyncMock()
    session.add = MagicMock()
    session.execute.side_effect = list(results)
    return session


def owner(status="done", version=1):
    return GameAnalysis(
        id=uuid.uuid4(), game_id=uuid.uuid4(), engine_status=status, score_version=version,
        engine_attempt_id=uuid.uuid4(), engine_result_id=uuid.uuid4(), status="done",
        summary="Legacy text remains", progress_current=12,
    )


def game(analysis):
    return Game(id=analysis.game_id, pgn_text=SAMPLE_PGN_SINGLE)


def bind_session(monkeypatch, session):
    @asynccontextmanager
    async def factory():
        yield session
    monkeypatch.setattr(tasks, "async_session_factory", factory)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "in_progress", "done"])
async def test_engine_repeat_never_resets_active_or_ready(status):
    analysis = owner(status)
    original_attempt = analysis.engine_attempt_id
    session = session_with(result(game(analysis)), result(analysis))
    returned, queued = await GameReviewService(session).queue_engine(analysis.game_id)
    assert returned is analysis and not queued
    assert analysis.engine_attempt_id == original_attempt
    assert analysis.summary == "Legacy text remains"
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_fences_old_attempt_but_retains_result_and_text():
    analysis = owner("in_progress")
    old_attempt, old_result = analysis.engine_attempt_id, analysis.engine_result_id
    session = session_with(result(game(analysis)), result(analysis), result())
    _, queued = await GameReviewService(session).queue_engine(
        analysis.game_id, recover=True, expected_attempt_id=old_attempt
    )
    assert queued and analysis.engine_attempt_id != old_attempt
    assert analysis.engine_result_id == old_result
    assert analysis.summary == "Legacy text remains"
    assert analysis.engine_status == "queued" and analysis.progress_current == 0


@pytest.mark.asyncio
async def test_recovery_rejects_stale_ui_attempt():
    analysis = owner("in_progress")
    session = session_with(result(game(analysis)), result(analysis))
    with pytest.raises(HTTPException) as exc:
        await GameReviewService(session).queue_engine(analysis.game_id, recover=True)
    assert exc.value.status_code == 409
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_completed_engine_is_not_educational_context():
    analysis = owner(version=None)
    session = session_with(result(game(analysis)), result(analysis))
    with pytest.raises(HTTPException) as exc:
        await GameReviewService(session).queue_explanations(analysis.game_id, "white")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_late_engine_save_cannot_delete_moves():
    analysis = owner("in_progress")
    session = session_with(result(analysis))
    saved = await GameReviewService(session).save_stockfish_results(
        analysis.id, [], attempt_id=uuid.uuid4()
    )
    assert not saved and session.execute.await_count == 1
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_successful_engine_save_sets_result_version_atomically():
    analysis = owner("in_progress")
    session = session_with(result(analysis), result())
    assert await GameReviewService(session).save_stockfish_results(
        analysis.id, [], attempt_id=analysis.engine_attempt_id
    )
    assert analysis.engine_result_id == analysis.engine_attempt_id
    assert analysis.engine_status == "done" and analysis.score_version == 1
    assert analysis.accuracy_white is None


def test_typed_mate_and_played_line_round_trip():
    evaluation = MoveEvaluation(
        move_number=1, color="white", move_san="e4", best_move_san="d4",
        eval_before=10000, eval_after=-10000, centipawn_loss=20000, classification="blunder",
        score_before=EngineScore(mate=2), score_after=EngineScore(mate=-3),
        played_line=["e4", "e5"],
    )
    restored = _restore_evaluation(_build_move_analysis(uuid.uuid4(), evaluation))
    assert restored.score_before == EngineScore(mate=2)
    assert restored.score_after == EngineScore(mate=-3)
    assert restored.played_line == ["e4", "e5"]


@pytest.mark.asyncio
async def test_broker_failure_sql_checks_stage_token_and_queued_status():
    session = session_with(result())
    attempt = uuid.uuid4()
    await GameReviewService(session).mark_publication_failed(
        "engine", uuid.uuid4(), attempt, "broker"
    )
    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "engine_attempt_id" in sql and "engine_status =" in sql
    assert attempt in statement.compile().params.values()
    assert "queued" in statement.compile().params.values()


@pytest.mark.asyncio
async def test_duplicate_engine_delivery_skips_without_engine(monkeypatch):
    session = session_with(result())
    bind_session(monkeypatch, session)
    analyzer = MagicMock()
    monkeypatch.setattr(tasks, "StockfishAnalyzerService", analyzer)
    response = await tasks._run_analysis_pipeline(str(uuid.uuid4()), str(uuid.uuid4()))
    assert response["status"] == "skipped"
    analyzer.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_task_delivery_never_creates_attempt():
    assert (await tasks._run_analysis_pipeline(str(uuid.uuid4())))["status"] == "skipped"


@pytest.mark.asyncio
async def test_late_coach_save_cannot_merge_old_engine_result(monkeypatch):
    analysis = owner()
    attempt = uuid.uuid4()
    review = SideReview(
        id=uuid.uuid4(), attempt_id=attempt, status="in_progress",
        context={"engine_result_id": str(uuid.uuid4()), "moments": []},
        comments={"0": {"reason": "ready"}},
    )
    session = session_with(result(analysis), result(review))
    bind_session(monkeypatch, session)
    assert await tasks._save_explanations(review.id, attempt, None) == "skipped"
    assert review.comments == {"0": {"reason": "ready"}}
    session.commit.assert_not_awaited()


def review_result(indices):
    comment = ReviewComment(
        reason="Причина", consequence="Последствие", alternative="Альтернатива",
        principle="Принцип", limitation="Ограничение"
    )
    return ReviewExplanationResult(comments={index: comment for index in indices}, summary="Итог",
                                   recommendations=["Совет"], usage={"total_tokens": 10})


@pytest.mark.asyncio
async def test_partial_coach_result_preserves_ready_comments_and_summary(monkeypatch):
    analysis = owner()
    attempt = uuid.uuid4()
    review = SideReview(
        id=uuid.uuid4(), attempt_id=attempt, status="in_progress", summary="Ready summary",
        context={"engine_result_id": str(analysis.engine_result_id),
                 "moments": [{"move_index": 0}, {"move_index": 2}, {"move_index": 4}]},
        comments={"0": {"reason": "Ready original"}},
    )
    session = session_with(result(analysis), result(review))
    bind_session(monkeypatch, session)
    assert await tasks._save_explanations(review.id, attempt, review_result([0, 2])) == "partial"
    assert review.comments["0"] == {"reason": "Ready original"}
    assert "2" in review.comments and "4" not in review.comments
    assert review.summary == "Ready summary"
    assert review.usage["total"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_coach_disabled_fails_without_engine_or_llm(monkeypatch):
    analysis = owner()
    attempt = uuid.uuid4()
    review = SideReview(
        id=uuid.uuid4(), attempt_id=attempt, status="in_progress", context={
            "engine_result_id": str(analysis.engine_result_id), "moments": [{"move_index": 0}]
        }, comments={"2": {"reason": "ready"}},
    )
    session = session_with(
        result(analysis.id), result((review.id, review.context, review.comments)),
        result(analysis), result(review)
    )
    bind_session(monkeypatch, session)
    monkeypatch.setattr(tasks, "_llm_enabled", lambda: False)
    llm, engine = MagicMock(), MagicMock()
    monkeypatch.setattr(tasks, "LLMCoachService", llm)
    monkeypatch.setattr(tasks, "StockfishAnalyzerService", engine)
    with pytest.raises(ValueError, match="LLM"):
        await tasks._run_explanation_pipeline(str(analysis.game_id), "white", str(attempt))
    assert review.status == "partial" and review.comments
    llm.assert_not_called()
    engine.assert_not_called()


def test_usage_preserves_per_attempt_totals():
    first, second = uuid.uuid4(), uuid.uuid4()
    usage = tasks._merge_usage(None, first, {"total_tokens": 12})
    usage = tasks._merge_usage(usage, second, {"total_tokens": 7})
    assert usage["total"]["total_tokens"] == 19
    assert usage["attempts"][str(first)]["total_tokens"] == 12


@pytest.mark.asyncio
async def test_legacy_llm_save_refuses_versioned_analysis():
    session = session_with(result(owner()))
    with pytest.raises(ValueError, match="Legacy"):
        await GameReviewService(session)._save_llm_results(uuid.uuid4(), {}, [], None)
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_no_selected_errors_still_queues_commentary_for_every_move(monkeypatch):
    analysis = owner()
    evaluation = MoveEvaluation(
        move_number=1, color="white", move_san="e4", best_move_san="e4",
        eval_before=0, eval_after=0, centipawn_loss=0, classification="best",
        score_before=EngineScore(cp=0), score_after=EngineScore(cp=0), played_line=["e4"],
    )
    record = _build_move_analysis(analysis.id, evaluation)
    session = session_with(
        result(game(analysis)), result(analysis), result(), result(values=[record])
    )
    monkeypatch.setattr(
        "app.services.review_moments.build_review_context",
        lambda *_, **__: {
            "version": 1, "player_color": "white", "moments": [],
            "commentary_scope": "all_moves", "moves": [{"move_index": 0}],
        },
    )
    review, queued = await GameReviewService(session).queue_explanations(analysis.game_id, "white")
    assert queued and review.status == "queued" and review.error is None
    assert review.task_id is not None
    assert review.context["engine_result_id"] == str(analysis.engine_result_id)


@pytest.mark.asyncio
async def test_new_engine_generation_archives_old_text_without_merging(monkeypatch):
    analysis = owner()
    review = SideReview(
        id=uuid.uuid4(), player_color="white", status="done", comments={"0": {"reason": "old"}},
        summary="Old summary", context={"engine_result_id": str(uuid.uuid4()), "moments": []},
    )
    evaluation = MoveEvaluation(
        move_number=1, color="white", move_san="e4", best_move_san="e4",
        eval_before=0, eval_after=0, centipawn_loss=0, classification="best",
        score_before=EngineScore(cp=0), score_after=EngineScore(cp=0), played_line=["e4"],
    )
    session = session_with(
        result(game(analysis)), result(analysis), result(review),
        result(values=[_build_move_analysis(analysis.id, evaluation)]),
    )
    monkeypatch.setattr(
        "app.services.review_moments.build_review_context",
        lambda *_, **__: {
            "version": 1, "player_color": "white", "moments": [{"move_index": 0}],
            "commentary_scope": "all_moves", "moves": [{"move_index": 0}],
        },
    )
    returned, queued = await GameReviewService(session).queue_explanations(
        analysis.game_id, "white"
    )
    assert queued and returned is review
    assert review.comments is None and review.summary is None
    assert review.stale_result["summary"] == "Old summary"
    assert review.context["engine_result_id"] == str(analysis.engine_result_id)


@pytest.mark.asyncio
async def test_coach_retry_sends_full_context_and_missing_indices(monkeypatch):
    analysis, attempt = owner(), uuid.uuid4()
    context = {
        "engine_result_id": str(analysis.engine_result_id),
        "moments": [{"move_index": 0}, {"move_index": 2}],
    }
    session = session_with(
        result(analysis.id), result((uuid.uuid4(), context, {"0": {"reason": "ready"}}))
    )
    bind_session(monkeypatch, session)
    monkeypatch.setattr(tasks, "_llm_enabled", lambda: True)
    coach = MagicMock()
    coach.generate_review = AsyncMock(return_value=review_result([2]))
    monkeypatch.setattr(tasks, "LLMCoachService", lambda: coach)
    save = AsyncMock(return_value="done")
    monkeypatch.setattr(tasks, "_save_explanations", save)
    await tasks._run_explanation_pipeline(str(analysis.game_id), "white", str(attempt))
    sent = coach.generate_review.call_args.args[0]
    assert sent["moments"] == context["moments"]
    assert sent["missing_comment_indices"] == [2]
    assert "missing_comment_indices" not in context
    claim = session.execute.call_args_list[1].args[0]
    assert claim.get_execution_options()["synchronize_session"] is False


@pytest.mark.asyncio
async def test_validation_failure_usage_saved_without_erasing_text(monkeypatch):
    analysis, attempt = owner(), uuid.uuid4()
    review = SideReview(
        id=uuid.uuid4(), attempt_id=attempt, status="in_progress",
        context={"engine_result_id": str(analysis.engine_result_id), "moments": []},
        comments={"0": {"reason": "ready"}}, summary="Ready summary",
    )
    session = session_with(result(analysis), result(review))
    bind_session(monkeypatch, session)
    await tasks._fail_explanations(review.id, attempt, "invalid", {"total_tokens": 21})
    assert review.status == "partial" and review.summary == "Ready summary"
    assert review.usage["attempts"][str(attempt)]["total_tokens"] == 21


@pytest.mark.asyncio
async def test_full_batches_save_progress_and_complete_only_when_every_ply_is_present(monkeypatch):
    analysis, attempt = owner(), uuid.uuid4()
    review = SideReview(
        id=uuid.uuid4(), attempt_id=attempt, status="in_progress",
        context={"engine_result_id": str(analysis.engine_result_id),
                 "moves": [{"move_index": i} for i in range(3)]},
        comments={"0": {"reason": "Existing explanation"}},
    )
    for indices, finalize, expected_status in [([1], False, "in_progress"), ([], True, "partial")]:
        bind_session(monkeypatch, session_with(result(analysis), result(review)))
        status = await tasks._save_full_commentary(
            review.id, attempt, FullCommentaryResult(
                comments={i: "Новый комментарий" for i in indices}, usage={"total_tokens": 10},
            ), finalize=finalize,
        )
        assert status == expected_status
    assert review.comments["0"] == {"reason": "Existing explanation"}
    assert review.usage["total"]["total_tokens"] == 20
    review.status = "in_progress"  # Explicitly claimed retry, same engine.
    bind_session(monkeypatch, session_with(result(analysis), result(review)))
    assert await tasks._save_full_commentary(
        review.id, attempt, FullCommentaryResult(comments={2: "Последний комментарий"}),
        finalize=True,
    ) == "done"
    assert review.error is None


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_full_worker_batches_only_missing_moves_and_requires_explicit_retry(
    monkeypatch, partial,
):
    analysis, attempt = owner(), uuid.uuid4()
    context = {
        "commentary_scope": "all_moves", "engine_result_id": str(analysis.engine_result_id),
        "moves": [{"move_index": i} for i in range(23)], "moments": [],
    }
    session = session_with(
        result(analysis.id), result((uuid.uuid4(), context, {"0": {"text": "Ready"}})),
    )
    bind_session(monkeypatch, session)
    monkeypatch.setattr(tasks, "_llm_enabled", lambda: True)
    coach = MagicMock()

    async def generate(batch):
        moves = batch["moves"][:1] if partial else batch["moves"]
        return FullCommentaryResult(comments={m["move_index"]: "Comment" for m in moves})

    coach.generate_full_commentary = AsyncMock(side_effect=generate)
    monkeypatch.setattr(tasks, "LLMCoachService", lambda: coach)
    save = AsyncMock(return_value="in_progress")
    monkeypatch.setattr(tasks, "_save_full_commentary", save)
    await tasks._run_explanation_pipeline(str(analysis.game_id), "white", str(attempt))
    calls = coach.generate_full_commentary.call_args_list
    assert len(calls) == (1 if partial else 5)
    assert [m["move_index"] for m in calls[0].args[0]["moves"]] == list(range(1, 6))
    assert save.call_args.kwargs == {"finalize": True}
    assert "missing_comment_indices" not in context


@pytest.mark.asyncio
async def test_other_side_reuses_full_review_without_new_attempt():
    analysis = owner()
    review = SideReview(
        id=uuid.uuid4(), player_color="white", status="done", attempt_id=uuid.uuid4(),
        context={"engine_result_id": str(analysis.engine_result_id),
                 "commentary_scope": "all_moves", "player_color": "white"},
    )
    session = session_with(result(game(analysis)), result(analysis), result(review))
    returned, queued = await GameReviewService(session).queue_explanations(
        analysis.game_id, "black"
    )
    assert returned is review and not queued
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_full_commentary_cannot_write_into_new_engine_generation(monkeypatch):
    analysis, attempt = owner(), uuid.uuid4()
    review = SideReview(
        id=uuid.uuid4(), attempt_id=attempt, status="in_progress",
        context={"engine_result_id": str(uuid.uuid4()), "moves": [{"move_index": 0}]},
        comments={"0": {"text": "Previously saved"}},
    )
    session = session_with(result(analysis), result(review))
    bind_session(monkeypatch, session)
    assert await tasks._save_full_commentary(
        review.id, attempt, FullCommentaryResult(comments={0: "Late replacement"}),
        finalize=True,
    ) == "skipped"
    assert review.comments == {"0": {"text": "Previously saved"}}
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("coach_status", ["queued", "in_progress"])
@pytest.mark.parametrize("has_comments", [False, True])
async def test_engine_replacement_terminates_coach_even_if_engine_then_fails(
    monkeypatch, coach_status, has_comments
):
    analysis = owner()
    attempt = uuid.uuid4()
    context = {"engine_result_id": str(analysis.engine_result_id), "moments": [{"move_index": 0}]}
    comments = {"0": {"reason": "ready"}} if has_comments else None
    review = SideReview(
        id=uuid.uuid4(), attempt_id=attempt, status=coach_status, context=context,
        comments=comments, summary="Preserved summary",
    )
    session = session_with(
        result(game(analysis)), result(analysis), result(values=[review])
    )
    _, queued = await GameReviewService(session).queue_engine(
        analysis.game_id, recover=True, expected_attempt_id=analysis.engine_attempt_id
    )
    assert queued and analysis.engine_status == "queued"
    expected_status = "partial" if has_comments else "failed"
    assert review.status == expected_status
    assert "движком" in review.error
    assert review.context == context and review.comments == comments
    assert review.summary == "Preserved summary"
    lock = session.execute.call_args_list[2].args[0]
    assert "FOR UPDATE" in str(lock.compile(dialect=postgresql.dialect()))

    # Queued or failed replacement must never revive or overwrite the stopped coach.
    for engine_status in ("queued", "failed"):
        analysis.engine_status = engine_status
        save_session = session_with(result(analysis), result(review))
        bind_session(monkeypatch, save_session)
        assert await tasks._save_explanations(review.id, attempt, review_result([0])) == "skipped"
        assert review.status == expected_status and review.comments == comments
        save_session.commit.assert_not_awaited()
