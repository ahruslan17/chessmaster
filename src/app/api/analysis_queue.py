"""Publish persisted analysis attempts, recording broker failures explicitly."""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.game_review import GameReviewService
from app.tasks.analysis import analyze_game_task, explain_game_task

logger = logging.getLogger(__name__)


async def publish_attempt(
    session: AsyncSession,
    *,
    stage: str,
    entity_id: uuid.UUID,
    game_id: uuid.UUID,
    attempt_id: uuid.UUID,
    task_id: str,
    player_color: str | None = None,
) -> bool:
    """The caller must commit the queued attempt before publishing it."""
    task = analyze_game_task if stage == "engine" else explain_game_task
    args = [str(game_id), str(attempt_id)]
    if stage != "engine":
        args = [str(game_id), player_color, str(attempt_id)]
    try:
        async with asyncio.timeout(15):
            await asyncio.to_thread(task.apply_async, args=args, task_id=task_id, retry=False)
    except Exception:
        # A transport can fail after accepting the message. Only the matching
        # queued attempt is failed; a claimed attempt must not be overwritten.
        logger.exception("Could not publish %s attempt %s", stage, attempt_id)
        await GameReviewService(session).mark_publication_failed(
            stage, entity_id, attempt_id,
            "Не удалось отправить задание в очередь. Повторите запуск анализа.",
        )
        await session.commit()
        return False
    return True
