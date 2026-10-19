from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.access import AccessCode, AccessSession

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_GROUPS = 3
_CODE_GROUP_LENGTH = 4


class AccessCodeError(ValueError):
    """Raised when an access-code operation cannot be completed safely."""


def hash_access_value(value: str) -> str:
    """Hash a browser credential without storing replayable data in the database."""
    return hmac.new(
        settings.access_code_secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _require_access_secret() -> None:
    if not settings.access_code_secret:
        raise AccessCodeError("ACCESS_CODE_SECRET не настроен")


def generate_access_code() -> str:
    """Create a human-readable code with enough entropy for selective sharing."""
    return "-".join(
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_GROUP_LENGTH))
        for _ in range(_CODE_GROUPS)
    )


async def create_access_code(session: AsyncSession, valid_for: timedelta) -> str:
    """Persist one code and return its plaintext exactly once to the operator."""
    _require_access_secret()
    if valid_for <= timedelta():
        raise AccessCodeError("Срок действия кода должен быть больше нуля")
    code = generate_access_code()
    session.add(
        AccessCode(
            code_hash=hash_access_value(code),
            expires_at=datetime.now(UTC) + valid_for,
        )
    )
    await session.commit()
    return code


async def redeem_access_code(session: AsyncSession, code: str) -> tuple[str, datetime]:
    """Redeem one code atomically and issue a fixed-duration browser session."""
    _require_access_secret()
    normalized = code.strip().upper()
    if not normalized:
        raise AccessCodeError("Код доступа не принят")
    result = await session.execute(
        select(AccessCode)
        .where(AccessCode.code_hash == hash_access_value(normalized))
        .with_for_update()
    )
    record = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if record is None or record.redeemed_at is not None or record.expires_at <= now:
        raise AccessCodeError("Код доступа не принят")
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(minutes=settings.access_session_minutes)
    record.redeemed_at = now
    session.add(
        AccessSession(
            access_code_id=record.id,
            token_hash=hash_access_value(token),
            expires_at=expires_at,
        )
    )
    await session.commit()
    return token, expires_at


async def get_active_session(session: AsyncSession, token: str | None) -> AccessSession | None:
    """Return an active public session; expired and unknown tokens look identical."""
    if not token or not settings.access_code_secret:
        return None
    result = await session.execute(
        select(AccessSession).where(
            AccessSession.token_hash == hash_access_value(token),
            AccessSession.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()
