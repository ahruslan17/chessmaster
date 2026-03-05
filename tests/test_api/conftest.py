from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_async_session
from app.main import create_app
from app.models.game import Game
from app.models.game_analysis import GameAnalysis
from app.models.move_analysis import MoveAnalysis
from app.models.period_report import PeriodReport


@pytest.fixture()
def mock_session():
    """Create a mock async database session."""
    session = AsyncMock(spec_set=["get", "execute", "add", "flush", "commit", "refresh"])
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture()
async def client(mock_session: AsyncMock):
    """Create an async test client with mocked DB session."""
    app = create_app()

    async def _override_session():
        yield mock_session

    app.dependency_overrides[get_async_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Factory helpers — create model instances for test assertions
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=UTC)


def make_game(**overrides: object) -> Game:
    """Build a ``Game`` instance with sensible defaults."""
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "pgn_text": '[Event "Test"]\n\n1. e4 e5 *',
        "white_player": "White",
        "black_player": "Black",
        "result": "1-0",
        "opening_name": "Italian Game",
        "eco_code": "C50",
        "time_control": "600+5",
        "played_at": date(2024, 6, 15),
        "player_color": "white",
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return Game(**defaults)


def make_game_analysis(**overrides: object) -> GameAnalysis:
    """Build a ``GameAnalysis`` instance with sensible defaults."""
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "game_id": uuid.uuid4(),
        "summary": "A well-played game.",
        "opening_assessment": "Solid opening.",
        "middlegame_assessment": "Good middlegame play.",
        "endgame_assessment": "Clean conversion.",
        "key_moments": [],
        "accuracy_white": 92.5,
        "accuracy_black": 88.0,
        "status": "done",
        "created_at": _NOW,
    }
    defaults.update(overrides)
    analysis = GameAnalysis(**defaults)
    # Initialise the moves list (normally done by relationship loading)
    if not hasattr(analysis, "moves") or analysis.moves is None:
        analysis.moves = []
    return analysis


def make_move_analysis(**overrides: object) -> MoveAnalysis:
    """Build a ``MoveAnalysis`` instance with sensible defaults."""
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "game_analysis_id": uuid.uuid4(),
        "move_number": 1,
        "color": "white",
        "move_san": "e4",
        "best_move_san": "e4",
        "eval_before": 0.0,
        "eval_after": 0.3,
        "centipawn_loss": 0.0,
        "classification": "best",
        "top_moves": [],
        "continuation_lines": [],
        "llm_comment": None,
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return MoveAnalysis(**defaults)


def make_period_report(**overrides: object) -> PeriodReport:
    """Build a ``PeriodReport`` instance with sensible defaults."""
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 1, 31),
        "period_type": "monthly",
        "recommendations": None,
        "weakness_patterns": None,
        "strength_patterns": None,
        "game_ids": [],
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return PeriodReport(**defaults)
