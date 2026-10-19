"""Tests for custom exceptions and API error handling."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from app.core.exceptions import GameNotFoundError
from tests.test_api.conftest import make_game


async def test_game_not_found_returns_404(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """GameNotFoundError results in 404 response."""
    mock_session.get = AsyncMock(return_value=None)

    response = await client.get(f"/api/games/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Партия не найдена"


async def test_analysis_not_found_returns_404(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """AnalysisNotFoundError results in 404 response."""
    game = make_game()
    mock_session.get = AsyncMock(return_value=game)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = await client.get(f"/api/games/{game.id}/analysis")

    assert response.status_code == 404
    assert response.json()["detail"] == "Анализ для этой партии не найден"


async def test_report_not_found_returns_404(
    client: AsyncClient,
    mock_session: AsyncMock,
) -> None:
    """ReportNotFoundError results in 404 response."""
    mock_session.get = AsyncMock(return_value=None)

    response = await client.get(f"/api/reports/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Отчёт не найден"


def test_app_error_inheritance() -> None:
    """AppError subclasses have message attribute."""
    exc = GameNotFoundError("Game X not found")
    assert exc.message == "Game X not found"
    assert str(exc) == "Game X not found"
