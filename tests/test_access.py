from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.access import AccessCode
from app.services.access import AccessCodeError, redeem_access_code


@pytest.mark.asyncio()
async def test_redeem_access_code_creates_a_15_minute_session(monkeypatch) -> None:
    monkeypatch.setattr("app.services.access.settings.access_code_secret", "test-secret")
    monkeypatch.setattr("app.services.access.settings.access_session_minutes", 15)
    record = AccessCode(
        code_hash="unused",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    session = AsyncMock()
    session.execute.return_value = result
    session.add = MagicMock()

    token, expires_at = await redeem_access_code(session, "ABCD-EFGH-JKLM")

    assert token
    assert record.redeemed_at is not None
    assert timedelta(minutes=14) < expires_at - record.redeemed_at <= timedelta(minutes=15)
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio()
async def test_redeem_access_code_rejects_used_code(monkeypatch) -> None:
    monkeypatch.setattr("app.services.access.settings.access_code_secret", "test-secret")
    record = AccessCode(
        code_hash="used",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        redeemed_at=datetime.now(UTC),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    session = AsyncMock()
    session.execute.return_value = result

    with pytest.raises(AccessCodeError, match="Код доступа не принят"):
        await redeem_access_code(session, "ABCD-EFGH-JKLM")

    session.add.assert_not_called()
    session.commit.assert_not_awaited()
