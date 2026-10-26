"""Persistable full-move commentary; move identity remains in trusted engine context."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

CommentaryProse = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2400)
]


class MoveExplanation(BaseModel):
    """Only idea is mandatory; unsupported teaching sections stay absent/null."""

    model_config = ConfigDict(extra="forbid", strict=True)

    idea: CommentaryProse
    pros: CommentaryProse | None = None
    cons: CommentaryProse | None = None
    tactics: CommentaryProse | None = None
    plan: CommentaryProse | None = None
    opponent_reply: CommentaryProse | None = None
    missed_opportunity: CommentaryProse | None = None


class MoveCommentary(BaseModel):
    """Structure-checked prose, not a guarantee of factual chess correctness."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[2] = 2
    played: MoveExplanation
    alternative: MoveExplanation | None = None
    comparison: CommentaryProse | None = None
