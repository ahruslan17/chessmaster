from __future__ import annotations

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from app.schemas.report import REPORT_CONTENT_VERSION, ReportRead
from app.services.llm_coach import PeriodReportResult
from app.services.report import ReportService
from app.utils.llm_prompts import build_period_report_messages
from tests.test_api.conftest import (
    make_game,
    make_game_analysis,
    make_move_analysis,
    make_period_report,
)

# ---------------------------------------------------------------------------
# POST /api/reports
# ---------------------------------------------------------------------------


@patch(
    "app.services.report.LLMCoachService.generate_period_report",
    new_callable=AsyncMock,
    return_value=PeriodReportResult(
        recommendations="Practice tactics and endgames.",
        weakness_patterns=[],
        strength_patterns=[],
    ),
)
async def test_create_report_success(
    mock_llm_report: AsyncMock,
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Creating a report with valid dates stores it and returns 201."""
    game = make_game()
    analysis = make_game_analysis(game_id=game.id)
    analysis.moves = [
        make_move_analysis(classification="best"),
        make_move_analysis(classification="blunder"),
    ]
    game.analysis = analysis

    # Mock: select(Game).join(GameAnalysis) returns games with analyses
    mock_result = MagicMock()
    mock_result.unique.return_value.scalars.return_value.all.return_value = [game]
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Mock flush to simulate DB-generated fields
    created_report: list = []

    def _capture_add(obj: object) -> None:
        created_report.append(obj)

    mock_session.add = MagicMock(side_effect=_capture_add)

    async def _fake_flush() -> None:
        from datetime import datetime

        for obj in created_report:
            if not hasattr(obj, "created_at") or obj.created_at is None:
                obj.created_at = datetime.now(tz=UTC)
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid.uuid4()

    mock_session.flush = AsyncMock(side_effect=_fake_flush)

    response = await client.post(
        "/api/reports",
        json={
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
            "period_type": "monthly",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["period_type"] == "monthly"
    assert data["period_start"] == "2024-01-01"
    assert data["period_end"] == "2024-01-31"
    assert isinstance(data["game_ids"], list)
    assert len(data["game_ids"]) == 1
    assert data["recommendations"] == "Practice tactics and endgames."
    assert "accuracy" not in str(data["comparison_metrics"]).lower()
    context = mock_llm_report.call_args.args[0]
    prompt = str(build_period_report_messages(context)).lower()
    assert "accuracy" not in prompt
    assert "точность" not in prompt
    assert "92.5" not in prompt
    mock_session.commit.assert_awaited_once()


async def test_create_report_invalid_dates_returns_422(
    client: AsyncClient,
) -> None:
    """period_end before period_start returns 422."""
    response = await client.post(
        "/api/reports",
        json={
            "period_start": "2024-02-01",
            "period_end": "2024-01-01",
            "period_type": "monthly",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    detail_str = detail.lower() if isinstance(detail, str) else str(detail).lower()
    assert "дата конца периода" in detail_str


# ---------------------------------------------------------------------------
# GET /api/reports
# ---------------------------------------------------------------------------


async def test_list_reports_returns_reports(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Listing reports returns stored reports."""
    reports = [make_period_report(), make_period_report(period_type="weekly")]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = reports
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get("/api/reports")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


async def test_list_reports_with_period_type_filter(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Filtering by period_type is accepted."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get("/api/reports?period_type=weekly")

    assert response.status_code == 200
    mock_session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET /api/reports/{report_id}
# ---------------------------------------------------------------------------


async def test_get_report_success(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Getting an existing report returns its data."""
    report = make_period_report()
    mock_session.get = AsyncMock(return_value=report)

    response = await client.get(f"/api/reports/{report.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(report.id)
    assert data["period_type"] == "monthly"


async def test_get_report_not_found(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """Getting a non-existent report returns 404."""
    mock_session.get = AsyncMock(return_value=None)

    response = await client.get(f"/api/reports/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Отчёт не найден"


async def test_legacy_report_hides_retired_metrics_and_generated_prose(
    client: AsyncClient, mock_session: AsyncMock,
) -> None:
    report = make_period_report(
        recommendations="Accuracy 92.5%; practise more.",
        weakness_patterns=[{"description": "Точность снизилась"}],
        strength_patterns=[{"description": "Accuracy increased"}],
        coach_feedback={"pluses": ["Точность 95%"]},
        comparison_summary="Средняя точность выросла",
        comparison_metrics={
            "overall_accuracy": {"current": 92.5},
            "white_accuracy": {"current": 95},
            "games": {"current": 3, "previous": 2, "delta": 1},
        },
    )
    mock_session.get = AsyncMock(return_value=report)
    response = await client.get(f"/api/reports/{report.id}")
    assert response.status_code == 200
    data = response.json()
    for key in (
        "recommendations", "weakness_patterns", "strength_patterns", "coach_feedback",
        "comparison_summary",
    ):
        assert data[key] is None
    assert data["comparison_metrics"] == {
        "games": {"current": 3, "previous": 2, "delta": 1},
    }
    # Serialization never modifies the stored report or triggers regeneration.
    assert report.recommendations == "Accuracy 92.5%; practise more."
    assert "overall_accuracy" in report.comparison_metrics


async def test_report_with_invalid_llm_text_keeps_deterministic_fallback(
    client: AsyncClient, mock_session: AsyncMock,
) -> None:
    from datetime import datetime

    game = make_game()
    game.analysis = make_game_analysis()
    game.analysis.moves = [make_move_analysis(classification="blunder")]
    rows = MagicMock()
    rows.unique.return_value.scalars.return_value.all.return_value = [game]
    mock_session.execute = AsyncMock(return_value=rows)
    added = []
    mock_session.add = MagicMock(side_effect=added.append)

    async def flush() -> None:
        for obj in added:
            obj.created_at = datetime.now(tz=UTC)
            obj.id = uuid.uuid4()

    mock_session.flush = AsyncMock(side_effect=flush)
    response = MagicMock()
    response.usage = {"total_tokens": 20}
    response.choices[0].message.content = '{"recommendations":["not a Text value"]}'
    with patch(
        "app.services.llm_coach.litellm.acompletion", new_callable=AsyncMock,
        return_value=response,
    ) as call:
        result = await client.post("/api/reports", json={
            "period_start": "2024-01-01", "period_end": "2024-01-31", "period_type": "monthly",
        })
    assert result.status_code == 201
    assert result.json()["recommendations"] is None
    assert isinstance(result.json()["comparison_summary"], str)
    assert added[0].recommendations is None
    call.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


def test_versioned_report_preserves_new_prose_but_filters_metrics() -> None:
    report = make_period_report(
        recommendations="Проверьте угрозы перед ходом.",
        comparison_summary="Число отмеченных ошибок уменьшилось.",
        comparison_metrics={
            "content_version": REPORT_CONTENT_VERSION,
            "overall_accuracy": {"current": 95},
            "blunder_moves": {"current": 1, "previous": 3, "delta": -2},
        },
    )
    result = ReportRead.model_validate(report).model_dump()
    assert result["recommendations"] == report.recommendations
    assert result["comparison_summary"] == report.comparison_summary
    assert result["comparison_metrics"] == {
        "blunder_moves": {"current": 1, "previous": 3, "delta": -2},
    }


def test_report_input_drops_legacy_game_summary_accuracy(mock_session: AsyncMock) -> None:
    from datetime import date

    game = make_game()
    game.analysis = make_game_analysis(
        summary="Accuracy 95%",
        opening_assessment="Точность 94%",
        middlegame_assessment="Accuracy 93%",
        endgame_assessment="Точность 92%",
    )
    game.analysis.moves = [make_move_analysis(classification="blunder")]
    service = ReportService(mock_session)
    stats = service._aggregate_period_stats([game])
    metrics = service._build_comparison_metrics(stats, stats)
    summary = service._build_comparison_summary(stats, stats)
    context = service._build_period_report_input(
        "monthly", date(2024, 1, 1), date(2024, 1, 31), [game], stats,
        date(2023, 12, 1), date(2023, 12, 31), stats, metrics,
    )
    prompt = str(build_period_report_messages(context)).lower()
    assert "accuracy" not in prompt
    assert "точность" not in prompt
    assert "accuracy" not in str(metrics).lower()
    assert "точность" not in summary.lower()
    assert "blunder" in prompt


def test_report_counts_only_selected_side_and_excludes_unknown_side(
    mock_session: AsyncMock,
) -> None:
    from datetime import date

    white_game = make_game(player_color="white")
    black_game = make_game(player_color="black")
    unknown_game = make_game(player_color=None)
    for game in (white_game, black_game, unknown_game):
        game.analysis = make_game_analysis()
        game.analysis.moves = [
            make_move_analysis(color="white", classification="best"),
            make_move_analysis(color="black", classification="blunder"),
        ]
    service = ReportService(mock_session)
    stats = service._aggregate_period_stats([white_game, black_game, unknown_game])
    assert stats.games_count == 2
    assert stats.classification_counts == {"best": 1, "blunder": 1}
    assert "Student side: white" in service._build_game_summary(white_game)
    assert "'blunder'" not in service._build_game_summary(white_game)
    assert "Student side: black" in service._build_game_summary(black_game)
    assert "'best'" not in service._build_game_summary(black_game)
    assert service._build_game_summary(unknown_game) == ""
    context = service._build_period_report_input(
        "monthly", date(2024, 1, 1), date(2024, 1, 31),
        [white_game, black_game, unknown_game], stats,
        date(2023, 12, 1), date(2023, 12, 31), stats, {},
    )
    assert context.games_count == 2
    assert len(context.game_summaries) == 2


async def test_report_without_selected_side_omits_personal_model_call(
    mock_session: AsyncMock,
) -> None:
    from datetime import date

    game = make_game(player_color=None)
    game.analysis = make_game_analysis()
    game.analysis.moves = [make_move_analysis(classification="blunder")]
    llm = MagicMock()
    llm.generate_period_report = AsyncMock()
    service = ReportService(mock_session, llm_coach=llm)
    with patch.object(service, "_fetch_games_with_analyses", new_callable=AsyncMock,
                      return_value=[game]):
        report = await service.generate_report(date(2024, 1, 1), date(2024, 1, 31), "monthly")
    llm.generate_period_report.assert_not_awaited()
    assert report.recommendations is None
    assert "без выбранной стороны" in report.comparison_summary
    assert "blunder_moves" not in report.comparison_metrics
