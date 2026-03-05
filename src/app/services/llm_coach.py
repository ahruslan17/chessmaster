from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import litellm

from app.core.config import settings
from app.utils.llm_prompts import (
    build_game_summary_messages,
    build_move_commentary_messages,
    build_period_report_messages,
    build_single_move_commentary_messages,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input / output data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MoveCommentaryInput:
    """All context the LLM needs to comment on a single move."""

    move_index: int  # 0-based sequential index in the game
    move_number: int  # chess move number (1-based, same for white & black)
    color: str  # "white" | "black"
    fen_before: str  # board FEN before the move
    move_san: str  # player's move in SAN
    best_move_san: str  # engine's top recommendation in SAN
    eval_before: float  # centipawns from white's perspective
    eval_after: float  # centipawns from white's perspective
    centipawn_loss: float  # always >= 0
    classification: str  # excellent / best / good / inaccuracy / mistake / blunder
    top_moves: list[dict[str, object]] = field(default_factory=list)
    next_game_moves: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GameSummaryInput:
    """Context for generating an overall game summary."""

    white_player: str
    black_player: str
    result: str
    opening_name: str | None
    eco_code: str | None
    total_moves: int
    accuracy_white: float
    accuracy_black: float
    classification_counts: dict[str, int]
    key_moments: list[MoveCommentaryInput] = field(default_factory=list)


@dataclass(frozen=True)
class GameSummaryResult:
    """LLM-generated game summary output."""

    summary: str
    opening_assessment: str
    middlegame_assessment: str
    endgame_assessment: str
    key_moments: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class PeriodReportInput:
    """Context for generating a period coaching report."""

    period_start: str
    period_end: str
    games_count: int
    game_summaries: list[str] = field(default_factory=list)
    aggregate_stats: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PeriodReportResult:
    """LLM-generated period report output."""

    recommendations: str
    weakness_patterns: list[dict[str, str]] = field(default_factory=list)
    strength_patterns: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class LLMCoachService:
    """Generates chess coaching commentary via LiteLLM.

    Provides three generation modes:
    - **Per-move commentary**: coaching explanation for every move in a game.
    - **Game summary**: overall assessment with phase-by-phase breakdown.
    - **Period report**: progress report over multiple games.
    """

    def __init__(
        self,
        model: str = settings.llm_model,
        api_key: str = settings.llm_api_key,
        api_base: str = settings.litellm_base_url,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._api_base = api_base or None  # litellm expects None, not ""
        # gpt-5 models only support temperature=1; drop unsupported params to avoid errors
        litellm.drop_params = True

    # ------------------------------------------------------------------
    # Public generation methods
    # ------------------------------------------------------------------

    async def generate_move_commentaries(
        self,
        moves: list[MoveCommentaryInput],
    ) -> dict[int, str]:
        """Generate coaching commentary for a list of moves.

        Returns a mapping of ``move_index`` -> commentary text.
        Moves that fail to get commentary are silently omitted.
        """
        if not moves:
            return {}

        messages = build_move_commentary_messages(moves)
        raw = await self._call_llm(messages)
        parsed = _parse_json_response(raw)

        result: dict[int, str] = {}
        for entry in parsed.get("comments", []):
            idx = entry.get("move_index")
            comment = entry.get("comment", "")
            if idx is not None and comment:
                result[int(idx)] = comment

        logger.info(
            "Generated LLM commentary for %d / %d moves",
            len(result),
            len(moves),
        )
        return result

    async def generate_single_move_commentary_stream(
        self, move: MoveCommentaryInput
    ) -> AsyncIterator[str]:
        """Stream coaching commentary for a single move token-by-token.

        Yields text chunks as they arrive from the LLM. Use for real-time
        display of commentary (e.g. SSE). Does not use JSON response format.
        """
        messages = build_single_move_commentary_messages(move)
        try:
            response = await litellm.acompletion(
                model=self._model,
                messages=messages,
                api_key=self._api_key,
                api_base=self._api_base,
                stream=True,
                temperature=0.4,
            )
            async for chunk in response:
                choices = (
                    chunk.choices
                    if hasattr(chunk, "choices")
                    else chunk.get("choices", [])
                )
                if not choices:
                    continue
                delta = (
                    choices[0].delta
                    if hasattr(choices[0], "delta")
                    else choices[0].get("delta", {})
                )
                content = (
                    delta.content
                    if hasattr(delta, "content")
                    else delta.get("content") or ""
                )
                if content:
                    yield content
        except Exception as exc:
            logger.error("LLM streaming failed: %s", exc)
            raise LLMCoachError(f"LLM streaming failed: {exc}") from exc

    async def generate_game_summary(
        self,
        context: GameSummaryInput,
    ) -> GameSummaryResult:
        """Generate an overall game summary with phase assessments."""
        messages = build_game_summary_messages(context)
        raw = await self._call_llm(messages)
        parsed = _parse_json_response(raw)

        result = GameSummaryResult(
            summary=parsed.get("summary", ""),
            opening_assessment=parsed.get("opening_assessment", ""),
            middlegame_assessment=parsed.get("middlegame_assessment", ""),
            endgame_assessment=parsed.get("endgame_assessment", ""),
            key_moments=parsed.get("key_moments", []),
        )
        logger.info("Generated game summary (%d chars)", len(result.summary))
        return result

    async def generate_period_report(
        self,
        context: PeriodReportInput,
    ) -> PeriodReportResult:
        """Generate a coaching report for a time period."""
        messages = build_period_report_messages(context)
        raw = await self._call_llm(messages)
        parsed = _parse_json_response(raw)

        result = PeriodReportResult(
            recommendations=parsed.get("recommendations", ""),
            weakness_patterns=parsed.get("weakness_patterns", []),
            strength_patterns=parsed.get("strength_patterns", []),
        )
        logger.info(
            "Generated period report: %d weakness(es), %d strength(s)",
            len(result.weakness_patterns),
            len(result.strength_patterns),
        )
        return result

    # ------------------------------------------------------------------
    # LLM call wrapper
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: list[dict[str, str]]) -> str:
        """Call the LLM via LiteLLM and return the raw response text.

        Raises ``LLMCoachError`` on any failure so callers can handle
        gracefully without leaking litellm internals.
        """
        try:
            response = await litellm.acompletion(
                model=self._model,
                messages=messages,
                api_key=self._api_key,
                api_base=self._api_base,
                response_format={"type": "json_object"},
                temperature=0.4,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            raise LLMCoachError(f"LLM call failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LLMCoachError(Exception):
    """Raised when the LLM coaching service encounters a non-recoverable error."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_response(text: str) -> dict[str, object]:
    """Parse the LLM's JSON response, stripping markdown fences if present.

    Returns an empty dict on parse failure so callers degrade gracefully.
    """
    cleaned = text.strip()

    # Some models wrap JSON in ```json ... ``` fences
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM JSON response: %.200s", cleaned)
        return {}

    if not isinstance(parsed, dict):
        logger.warning("LLM response is not a JSON object: %s", type(parsed).__name__)
        return {}

    return parsed
