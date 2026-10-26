# Russian coaching text and Cyrillic chess notation are intentional.
# ruff: noqa: RUF001

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Annotated, Literal

import chess
import litellm
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, ValidationError

from app.core.config import settings
from app.schemas.move_commentary import CommentaryProse, MoveCommentary, MoveExplanation
from app.services.stockfish_analyzer import EngineScore
from app.utils.llm_prompts import (
    build_full_commentary_messages,
    build_game_summary_messages,
    build_move_commentary_messages,
    build_period_report_messages,
    build_review_messages,
    build_single_move_commentary_messages,
)

logger = logging.getLogger(__name__)
_LLM_TIMEOUT_SECONDS = 90
_MAX_REVIEW_COMMENTS = 5
FULL_COMMENTARY_BATCH_SIZE = 5
_CLASSIFICATIONS = frozenset({
    "theory", "excellent", "best", "good", "inaccuracy", "mistake", "blunder",
})
_MOVE_NOTATION = re.compile(
    r"(?<!\w)(?:[a-h][1-8][-x]?[a-h][1-8][qrbnQRBN]?"
    r"|(?:[KQRBN]|Кр|[КФЛС])(?:[a-h][1-8]?|[1-8])?x?[a-h][1-8](?:=?[QRBN])?"
    r"|[a-h](?:x[a-h])?[1-8](?:=?[QRBNqrbn])?"
    r"|[O0О]-[O0О](?:-[O0О])?|[♔♕♖♗♘♚♛♜♝♞][a-h][1-8])"
    r"[+#?!]*(?!\w)"
)

ReviewText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1200)
]
SummaryText = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2400)
]


class ReviewComment(BaseModel):
    """Structure-checked model prose, not a human-verified chess explanation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    reason: ReviewText
    consequence: ReviewText
    alternative: ReviewText
    principle: ReviewText
    limitation: ReviewText


class ReviewExplanationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    comments: dict[int, ReviewComment] = Field(max_length=_MAX_REVIEW_COMMENTS)
    summary: SummaryText
    recommendations: list[ReviewText] = Field(min_length=1, max_length=2)
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    verification: Literal["structure_checked"] = "structure_checked"


class _ReviewEntry(ReviewComment):
    move_index: int = Field(ge=0)


class _ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    comments: list[_ReviewEntry] = Field(max_length=_MAX_REVIEW_COMMENTS)
    summary: SummaryText
    recommendations: list[ReviewText] = Field(min_length=1, max_length=2)


class _MoveComment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    move_index: int = Field(ge=0)
    comment: SummaryText


class _MoveCommentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    comments: list[_MoveComment]


class _FullCommentaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    move_index: int = Field(ge=0)
    played: MoveExplanation
    alternative: MoveExplanation | None = None
    comparison: CommentaryProse | None = None


class _FullCommentaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    comments: list[_FullCommentaryEntry] = Field(max_length=FULL_COMMENTARY_BATCH_SIZE)


class FullCommentaryResult(BaseModel):
    comments: dict[int, str | MoveCommentary]
    usage: dict[str, JsonValue] = Field(default_factory=dict)


class _PeriodPattern(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    pattern: ReviewText
    description: SummaryText
    frequency: ReviewText


class _PeriodReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    recommendations: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=12000)
    ]
    weakness_patterns: list[_PeriodPattern] = Field(default_factory=list, max_length=20)
    strength_patterns: list[_PeriodPattern] = Field(default_factory=list, max_length=20)
    coach_feedback: dict[str, list[ReviewText]] = Field(default_factory=dict)
    comparison_summary: Annotated[
        str, StringConstraints(strict=True, strip_whitespace=True, max_length=6000)
    ] = ""


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
    # Deprecated compatibility inputs; never sent to the model.
    accuracy_white: float | None = None
    accuracy_black: float | None = None
    classification_counts: dict[str, int] = field(default_factory=dict)
    key_moments: list[MoveCommentaryInput] = field(default_factory=list)


@dataclass(frozen=True)
class GameSummaryResult:
    """LLM-generated game summary output."""

    summary: str
    opening_assessment: str
    middlegame_assessment: str
    endgame_assessment: str
    key_moments: list[dict[str, str]] = field(default_factory=list)
    coach_feedback: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PeriodReportInput:
    """Context for generating a period coaching report."""

    period_type: str
    period_start: str
    period_end: str
    games_count: int
    game_summaries: list[str] = field(default_factory=list)
    aggregate_stats: dict[str, object] = field(default_factory=dict)
    previous_period_start: str | None = None
    previous_period_end: str | None = None
    previous_games_count: int = 0
    comparison_metrics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PeriodReportResult:
    """LLM-generated period report output."""

    recommendations: str
    weakness_patterns: list[dict[str, str]] = field(default_factory=list)
    strength_patterns: list[dict[str, str]] = field(default_factory=list)
    coach_feedback: dict[str, object] = field(default_factory=dict)
    comparison_summary: str = ""


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

    async def generate_review(self, context: dict) -> ReviewExplanationResult:
        """Explain at most five persisted own-side moments; missing comments stay partial.

        Engine variations are checked here, then rendered separately by the caller.
        Prose semantics still require human review; structure_checked is not factual proof.
        """
        indices = _validate_review_context(context)
        missing = context.get("missing_comment_indices", sorted(indices))
        if (
            not isinstance(missing, list)
            or any(type(index) is not int or index not in indices for index in missing)
            or len(set(missing)) != len(missing)
        ):
            raise LLMCoachError("Invalid missing_comment_indices")
        requested = set(missing)
        if not requested:
            summary = (
                (
                    "Новых объяснений не запрошено. Сохранённые комментарии не изменены; "
                    "новый учебный итог не сформирован."
                )
                if indices
                else (
                    "В сохранённом контексте нет выбранных учебных моментов. "
                    "Полный учебный разбор не сформирован; выводы об игре не сделаны."
                )
            )
            recommendation = (
                "Используйте уже сохранённые объяснения выбранных моментов."
                if indices
                else "Для учебного разбора нужны выбранные моменты с данными движка."
            )
            return ReviewExplanationResult(
                comments={},
                summary=summary,
                recommendations=[recommendation],
            )

        try:
            messages = build_review_messages(_review_evidence_projection(context))
        except (TypeError, ValueError) as exc:
            raise LLMCoachError("Review context must contain valid JSON data") from exc
        raw, usage = await self._call_llm_with_usage(messages)
        try:
            response = _ReviewResponse.model_validate(_parse_json_response(raw))
            prose = [response.summary, *response.recommendations]
            for entry in response.comments:
                prose.extend(entry.model_dump(exclude={"move_index"}).values())
            for text in prose:
                _reject_prose_moves(text)
            comments: dict[int, ReviewComment] = {}
            for entry in response.comments:
                if entry.move_index not in requested or entry.move_index in comments:
                    raise LLMCoachError("Invalid or duplicate review move_index", usage=usage)
                comments[entry.move_index] = ReviewComment.model_validate(
                    entry.model_dump(exclude={"move_index"})
                )
            return ReviewExplanationResult(
                comments=comments,
                summary=response.summary,
                recommendations=response.recommendations,
                usage=usage,
            )
        except (ValidationError, LLMCoachError) as exc:
            raise LLMCoachError("Invalid review response structure", usage=usage) from exc

    async def generate_move_commentaries(
        self,
        moves: list[MoveCommentaryInput],
    ) -> dict[int, str]:
        """Generate coaching commentary for a list of moves.

        Returns a mapping of ``move_index`` -> commentary text.
        Missing comments are allowed; invalid responses or foreign indices are rejected.
        """
        if not moves:
            return {}

        messages = build_move_commentary_messages(moves)
        raw = await self._call_llm(messages)
        try:
            parsed = _MoveCommentsResponse.model_validate(_parse_json_response(raw))
        except ValidationError as exc:
            raise LLMCoachError("Invalid move commentary response structure") from exc

        expected = {move.move_index for move in moves}
        result: dict[int, str] = {}
        for entry in parsed.comments:
            if entry.move_index not in expected or entry.move_index in result:
                raise LLMCoachError("Invalid or duplicate commentary move_index")
            result[entry.move_index] = entry.comment

        logger.info(
            "Generated LLM commentary for %d / %d moves",
            len(result),
            len(moves),
        )
        return result

    async def generate_full_commentary(  # noqa: PLR0912
        self, context: dict,
    ) -> FullCommentaryResult:
        """Explain every requested ply, with the same board/line checks as selected reviews."""
        moments = context.get("moves") if isinstance(context, dict) else None
        if (
            not isinstance(moments, list) or not moments
            or len(moments) > FULL_COMMENTARY_BATCH_SIZE
        ):
            raise LLMCoachError("Full commentary batch must contain 1–5 moves")
        if any(
            not isinstance(move, dict) or move.get("color") not in ("white", "black")
            for move in moments
        ):
            raise LLMCoachError("Invalid full commentary move")
        # A missing recommendation is not a recommendation to repeat the played move.
        moments = [
            dict(
                move,
                best_move_san="" if move.get("best_move_san") is None else move["best_move_san"],
                best_line=move.get("best_line", []),
            )
            for move in moments
        ]
        for color in ("white", "black"):
            own = [move for move in moments if move["color"] == color]
            for start in range(0, len(own), _MAX_REVIEW_COMMENTS):
                _validate_review_context({
                    "version": 1, "player_color": color, "perspective": "white",
                    "moments": own[start:start + _MAX_REVIEW_COMMENTS],
                }, allow_missing_best=True)
        evidence = _review_evidence_projection({
            "version": 1, "perspective": "white", "moments": moments,
        })
        for projected, original in zip(evidence["moments"], moments, strict=True):
            projected["is_theory"] = original.get("is_theory", False)
        raw, usage = await self._call_llm_with_usage(
            build_full_commentary_messages(evidence), max_tokens=8192, timeout_seconds=180,
            temperature=None,
        )
        try:
            response = _FullCommentaryResponse.model_validate(_parse_json_response(raw))
            expected = {move["move_index"]: move for move in moments}
            comments: dict[int, MoveCommentary] = {}
            for entry in response.comments:
                if entry.move_index not in expected or entry.move_index in comments:
                    raise LLMCoachError("Invalid or duplicate commentary move_index")
                moment = expected[entry.move_index]
                before = chess.Board(moment["fen_before"])
                has_alternative = bool(moment["best_move_san"]) and (
                    before.parse_san(moment["best_move_san"])
                    != before.parse_san(moment["move_san"])
                )
                if not has_alternative and (
                    entry.alternative is not None or entry.comparison is not None
                ):
                    raise LLMCoachError("Commentary must not duplicate the played move")
                if has_alternative and entry.alternative is None:
                    # Context validation already established a nonempty legal best line.
                    raise LLMCoachError("Verified alternative explanation is required")
                for explanation in (entry.played, entry.alternative):
                    if explanation is not None:
                        for text in explanation.model_dump(exclude_none=True).values():
                            _reject_prose_moves(text, allow_square_references=True)
                if entry.comparison is not None:
                    _reject_prose_moves(entry.comparison, allow_square_references=True)
                comments[entry.move_index] = MoveCommentary(
                    played=entry.played, alternative=entry.alternative,
                    comparison=entry.comparison,
                )
            return FullCommentaryResult(comments=comments, usage=usage)
        except (ValidationError, LLMCoachError) as exc:
            raise LLMCoachError("Invalid full commentary response", usage=usage) from exc

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
            key_moments=_as_list_of_dicts(parsed.get("key_moments")),
            coach_feedback=_as_dict(parsed.get("coach_feedback")),
        )
        logger.info("Generated game summary (%d chars)", len(result.summary))
        return result

    async def generate_period_report(
        self,
        context: PeriodReportInput,
    ) -> PeriodReportResult:
        """Generate a coaching report for a time period."""
        messages = build_period_report_messages(context)
        raw, usage = await self._call_llm_with_usage(messages)
        try:
            parsed = _PeriodReportResponse.model_validate(_parse_json_response(raw))
        except (ValidationError, LLMCoachError) as exc:
            raise LLMCoachError("Invalid period report response structure", usage=usage) from exc

        result = PeriodReportResult(
            recommendations=parsed.recommendations,
            weakness_patterns=[pattern.model_dump() for pattern in parsed.weakness_patterns],
            strength_patterns=[pattern.model_dump() for pattern in parsed.strength_patterns],
            coach_feedback=parsed.coach_feedback,
            comparison_summary=parsed.comparison_summary,
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
        content, _usage = await self._call_llm_with_usage(messages)
        return content

    async def _call_llm_with_usage(
        self, messages: list[dict[str, str]], *, max_tokens: int | None = None,
        timeout_seconds: int = _LLM_TIMEOUT_SECONDS,
        temperature: float | None = 0.4,
    ) -> tuple[str, dict[str, JsonValue]]:
        usage: dict[str, JsonValue] = {}
        try:
            async with asyncio.timeout(timeout_seconds):
                response = await litellm.acompletion(
                    model=self._model,
                    messages=messages,
                    api_key=self._api_key,
                    api_base=self._api_base,
                    response_format={"type": "json_object"},
                    **({"temperature": temperature} if temperature is not None else {}),
                    timeout=timeout_seconds,
                    max_retries=0,
                    **({"max_tokens": max_tokens} if max_tokens is not None else {}),
                    **({"extra_headers": {"Connection": "close"}}
                       if max_tokens is not None else {}),
                )
                usage = _response_usage(response)
                content = response.choices[0].message.content
                if not isinstance(content, str):
                    raise LLMCoachError("LLM response content must be text", usage=usage)
                return content, usage
        except Exception as exc:
            # Do not log provider payloads, which may include private game data.
            logger.warning("LLM call failed (%s)", type(exc).__name__)
            raise LLMCoachError("LLM call failed", usage=usage) from exc


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LLMCoachError(Exception):
    """Raised when the LLM coaching service encounters a non-recoverable error."""

    def __init__(self, message: str, *, usage: dict[str, JsonValue] | None = None) -> None:
        super().__init__(message)
        self.usage = usage or {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_response(text: str) -> dict[str, object]:
    """Parse the LLM's JSON response, stripping markdown fences if present.

    Reject malformed/non-object JSON rather than silently accepting empty output.
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
    except json.JSONDecodeError as exc:
        raise LLMCoachError("Invalid LLM JSON response") from exc

    if not isinstance(parsed, dict):
        raise LLMCoachError("LLM JSON response must be an object")

    return parsed


def _response_usage(response: object) -> dict[str, JsonValue]:
    """Copy provider usage as JSON without carrying response objects or private text."""
    usage = getattr(response, "usage", None)
    if not isinstance(usage, dict):
        dump = getattr(usage, "model_dump", None)
        usage = dump(mode="json") if callable(dump) else None
    if not isinstance(usage, dict):
        return {}
    try:
        return json.loads(json.dumps(usage, allow_nan=False))
    except (TypeError, ValueError):
        return {}


# Keep rejection checks together at this untrusted-input boundary for auditable ordering.
def _validate_review_context(  # noqa: PLR0912, PLR0915
    context: dict, *, allow_missing_best: bool = False,
) -> set[int]:
    """Check context ownership and legal lines before any provider request."""
    if not isinstance(context, dict):
        raise LLMCoachError("Review context must be an object")
    if type(context.get("version")) is not int or context["version"] != 1:
        raise LLMCoachError("Unsupported review context version")
    if "engine_result_id" in context and not isinstance(context["engine_result_id"], str):
        raise LLMCoachError("Engine result provenance must be text")
    color = context.get("player_color")
    if color not in ("white", "black") or context.get("perspective") != "white":
        raise LLMCoachError("Invalid review context side or score perspective")
    moments = context.get("moments")
    if not isinstance(moments, list) or len(moments) > _MAX_REVIEW_COMMENTS:
        raise LLMCoachError("Review context must contain at most five moments")
    indices: set[int] = set()
    for moment in moments:
        if not isinstance(moment, dict):
            raise LLMCoachError("Review moment must be an object")
        index = moment.get("move_index")
        if type(index) is not int or index < 0 or index in indices:
            raise LLMCoachError("Invalid or duplicate context move_index")
        if moment.get("color") != color:
            raise LLMCoachError("Review moment belongs to a different side")
        try:
            loss = moment["centipawn_loss"]
            if type(loss) not in (float, int) or not math.isfinite(loss) or loss < 0:
                raise ValueError("Loss must be finite and nonnegative")
            if moment.get("classification") not in _CLASSIFICATIONS:
                raise ValueError("Invalid move classification")
            for key in ("score_before", "score_after"):
                _context_engine_score(moment.get(key))
            if not all(isinstance(moment.get(key), str) for key in ("fen_before", "fen_after")):
                raise ValueError("FEN must be text")
            before = chess.Board(moment["fen_before"])
            after = chess.Board(moment["fen_after"])
            if not before.is_valid() or not after.is_valid():
                raise ValueError("Invalid board")
            if index != before.ply() or before.turn != (color == "white"):
                raise ValueError("Index/side does not match FEN")
            move_number = moment.get("move_number")
            if type(move_number) is not int or move_number != before.fullmove_number:
                raise ValueError("Move number does not match FEN")
            played = before.parse_san(moment["move_san"])
            best_san = moment["best_move_san"]
            best = None if allow_missing_best and best_san == "" else before.parse_san(best_san)
            if played not in before.legal_moves or (
                best is not None and best not in before.legal_moves
            ):
                raise ValueError("Illegal or null move")
            expected_after = before.copy()
            expected_after.push(played)
            if expected_after.fen() != after.fen():
                raise ValueError("Played move does not match fen_after")
            _validate_context_line(before, moment["played_line"], played)
            if best is not None:
                _validate_context_line(before, moment["best_line"], best)
            elif moment["best_line"] not in ([], None):
                raise ValueError("Engine alternative line has no recommendation")
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
            raise LLMCoachError("Invalid review position or engine line") from exc
        indices.add(index)
    return indices


def _context_engine_score(value: object) -> EngineScore | None:
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("perspective") != "white":
        raise ValueError("Engine score must explicitly use White perspective")
    cp = value.get("cp")
    if cp is not None and type(cp) not in (int, float):
        raise ValueError("Centipawns must be numeric, not boolean")
    return EngineScore(**value)


def _reject_prose_moves(text: str, *, allow_square_references: bool = False) -> None:
    """No generated SAN/UCI, even legal tokens: only the UI renders engine lines.

    Bare pawn SAN is indistinguishable from a square. Explicit Russian square
    references ("на h5", "поле h5") remain prose, not a new displayed variation.
    This is a conservative syntax gate, not semantic/factual verification.
    """
    for match in _MOVE_NOTATION.finditer(text):
        token = match.group()
        if re.fullmatch(r"[a-h][1-8]", token) and (
            allow_square_references or re.search(
                r"(?:\bна|\bполе|\bполя|\bклетке)\s+$", text[:match.start()], re.IGNORECASE
            )
        ):
            continue
        raise LLMCoachError("Generated prose must not contain SAN/UCI moves")


def _review_evidence_projection(context: dict) -> dict:
    """Separate the played move from hypothetical, moment-local engine branches."""
    projected = {key: context[key] for key in (
        "version", "player_color", "perspective", "engine_result_id", "missing_comment_indices",
    ) if key in context}
    projected["history_scope"] = (
        "Only each moment's actual move and before/after boards are supplied. "
        "Engine branches are not game history and must not be joined across moments."
    )
    moments = []
    for moment in context["moments"]:
        safe = {key: moment[key] for key in (
            "move_index", "move_number", "color", "fen_before", "fen_after", "move_san",
            "best_move_san", "centipawn_loss", "classification",
        )}
        for key in ("score_before", "score_after"):
            score = _context_engine_score(moment.get(key))
            safe[key] = score.to_json() if score is not None else None
        before = chess.Board(moment["fen_before"])
        after = chess.Board(moment["fen_after"])
        safe["actual_move"] = {
            "source": "actual_game", "move_index": moment["move_index"],
            "san": moment["move_san"],
            "material_before": _board_material(before),
            "material_after": _board_material(after),
            "events": _line_events(before, [moment["move_san"]]),
        }
        # The first token of played_line is actual. All subsequent tokens, even
        # if legal or repeated in another selected moment, are hypothetical.
        safe["engine_lines"] = {
            "after_played_move": {
                "source": "hypothetical_engine", "move_index": moment["move_index"],
                "fen_start": moment["fen_after"], "moves": moment["played_line"][1:],
                "events": _line_events(after, moment["played_line"][1:]),
            },
            "alternative": {
                "source": "hypothetical_engine", "move_index": moment["move_index"],
                "fen_start": moment["fen_before"], "moves": moment["best_line"] or [],
                "events": _line_events(before, moment["best_line"] or []),
            },
        }
        if moment["best_line"]:
            alternative_after = before.copy()
            alternative_after.push_san(moment["best_line"][0])
            safe["engine_lines"]["alternative"]["first_move"] = {
                "source": "hypothetical_engine", "san": moment["best_move_san"],
                "fen_after": alternative_after.fen(),
                "material_before": _board_material(before),
                "material_after": _board_material(alternative_after),
                "events": _line_events(before, moment["best_line"][:1]),
            }
        facts = [
            "Tactical motive and forced play are not established by legal lines.",
            "Numeric scores, loss and classification are engine evidence, not board-proven facts.",
        ]
        if len(moment["played_line"]) == 1 and not chess.Board(moment["fen_after"]).is_game_over():
            facts.append("No verified engine reply after the played move is available.")
        if not moment["best_line"]:
            facts.append("No verified engine alternative is available.")
        if safe["score_before"] is None or safe["score_after"] is None:
            facts.append(
                "Exact cp/mate evidence is unavailable; do not infer mate from legacy values."
            )
        safe["facts"] = facts
        safe["verification"] = "legal_lines_and_board_events_only"
        moments.append(safe)
    projected["moments"] = moments
    return projected


def _board_material(board: chess.Board) -> dict[str, dict[str, list[str]]]:
    """Piece locations are observed board state, not inferred capture history."""
    return {
        "white" if color else "black": {
            chess.piece_name(piece): [chess.square_name(sq) for sq in board.pieces(piece, color)]
            for piece in chess.PIECE_TYPES
        }
        for color in (chess.WHITE, chess.BLACK)
    }


def _line_events(before: chess.Board, line: list[str]) -> list[dict[str, object]]:
    """Derive events within one branch; the caller assigns actual/hypothetical scope."""
    board = before.copy()
    events = []
    for ply, token in enumerate(line, 1):
        move = board.parse_san(token)
        mover = "white" if board.turn else "black"
        captured = board.piece_at(move.to_square)
        if board.is_en_passant(move):
            captured = chess.Piece(chess.PAWN, not board.turn)
        if captured:
            events.append({"ply": ply, "color": mover, "event": "capture",
                           "piece": chess.piece_name(captured.piece_type)})
        board.push(move)
        if board.is_check():
            events.append({"ply": ply, "color": mover,
                           "event": "checkmate" if board.is_checkmate() else "check"})
        if move.promotion:
            events.append({"ply": ply, "color": mover, "event": "promotion",
                           "piece": chess.piece_name(move.promotion)})
    return events


def _validate_context_line(before: chess.Board, line: object, first: chess.Move) -> None:
    if not isinstance(line, list) or not line:
        raise ValueError("Engine line must be a nonempty SAN/UCI list")
    board = before.copy()
    for index, token in enumerate(line):
        if not isinstance(token, str):
            raise ValueError("Engine line token must be text")
        move = board.parse_san(token)
        if move not in board.legal_moves or (index == 0 and move != first):
            raise ValueError("Illegal or mismatched engine line")
        board.push(move)


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list_of_dicts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            result.append({str(k): str(v) for k, v in item.items()})
    return result
