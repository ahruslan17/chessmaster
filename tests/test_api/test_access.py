from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.access import router
from app.core.config import settings
from app.core.dependencies import get_db


async def test_activate_access_sets_secure_httponly_cookie(monkeypatch) -> None:
    monkeypatch.setattr(settings, "access_cookie_secure", True)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    session = AsyncMock()

    async def get_session():
        yield session

    app.dependency_overrides[get_db] = get_session
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    with patch("app.api.access.redeem_access_code", return_value=("token", expires_at)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post("/api/access/activate", json={"code": "ABCD-EFGH-JKLM"})

    assert response.status_code == 200
    assert response.json()["active"] is True
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
