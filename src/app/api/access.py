from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.dependencies import AsyncSessionDep
from app.services.access import AccessCodeError, get_active_session, redeem_access_code

router = APIRouter(prefix="/access", tags=["access"])
ACCESS_COOKIE = "chess_master_access"


class AccessActivateBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class AccessStatusRead(BaseModel):
    active: bool
    expires_at: datetime | None = None


class AccessConfigRead(BaseModel):
    enabled: bool


@router.post("/activate", response_model=AccessStatusRead)
async def activate_access(
    body: AccessActivateBody,
    response: Response,
    session: AsyncSessionDep,
) -> AccessStatusRead:
    """Redeem one server-generated code and set an HttpOnly session cookie."""
    try:
        token, expires_at = await redeem_access_code(session, body.code)
    except AccessCodeError as exc:
        raise HTTPException(
            status_code=401,
            detail="Код недействителен или уже использован",
        ) from exc
    response.set_cookie(
        ACCESS_COOKIE,
        token,
        max_age=settings.access_session_minutes * 60,
        expires=expires_at,
        httponly=True,
        secure=settings.access_cookie_secure,
        samesite="lax",
        path="/",
    )
    return AccessStatusRead(active=True, expires_at=expires_at)


@router.post("/logout", status_code=204)
async def logout_access(response: Response) -> Response:
    """Remove the browser credential. The one-time code remains redeemed."""
    response.delete_cookie(
        ACCESS_COOKIE,
        path="/",
        secure=settings.access_cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/config", response_model=AccessConfigRead)
async def access_config() -> AccessConfigRead:
    """Tell the web client whether this runtime is a gated public preview."""
    return AccessConfigRead(enabled=getattr(settings, "access_control_enabled", False))


@router.get("/status", response_model=AccessStatusRead)
async def access_status(request: Request, session: AsyncSessionDep) -> AccessStatusRead:
    """Restore a valid browser session after a page reload without consuming another code."""
    access_session = await get_active_session(session, request.cookies.get(ACCESS_COOKIE))
    if access_session is None:
        return AccessStatusRead(active=False)
    return AccessStatusRead(active=True, expires_at=access_session.expires_at)
