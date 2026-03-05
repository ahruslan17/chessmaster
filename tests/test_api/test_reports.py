from __future__ import annotations

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from app.services.llm_coach import PeriodReportResult
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
    assert "period_end" in detail_str


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
    assert "not found" in response.json()["detail"].lower()
