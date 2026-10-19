"""Add attempt-fenced engine lifecycle and side-specific educational reviews.

Revision ID: 004
Revises: 003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("engine_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("engine_attempt_id", postgresql.UUID(as_uuid=True)),
        sa.Column("engine_result_id", postgresql.UUID(as_uuid=True)),
        sa.Column("engine_task_id", sa.String(255)),
        sa.Column("engine_error", sa.Text()),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("score_version", sa.Integer()),
        sa.Column("engine_metadata", postgresql.JSONB()),
    ):
        op.add_column("game_analyses", column)
    # Legacy results remain readable, but lack the typed scores needed by the coach.
    op.execute("UPDATE game_analyses SET engine_status = 'done' WHERE status = 'done'")
    for name in ("score_before", "score_after", "played_line"):
        op.add_column("move_analyses", sa.Column(name, postgresql.JSONB(), nullable=True))
    op.create_table(
        "side_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("game_analysis_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("game_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_color", sa.String(5), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True)),
        sa.Column("task_id", sa.String(255)),
        sa.Column("error", sa.Text()),
        sa.Column("context", postgresql.JSONB()),
        sa.Column("comments", postgresql.JSONB()),
        sa.Column("summary", sa.Text()),
        sa.Column("recommendations", postgresql.JSONB()),
        sa.Column("usage", postgresql.JSONB()),
        sa.Column("stale_result", postgresql.JSONB()),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "game_analysis_id", "player_color", name="uq_side_review_analysis_color"
        ),
        sa.CheckConstraint("player_color IN ('white', 'black')", name="ck_side_review_color"),
        sa.CheckConstraint(
            "status IN ('pending', 'queued', 'in_progress', 'done', 'partial', 'failed')",
            name="ck_side_review_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("side_reviews")
    for name in ("played_line", "score_after", "score_before"):
        op.drop_column("move_analyses", name)
    for name in (
        "engine_metadata", "score_version", "heartbeat_at", "progress_total", "progress_current",
        "engine_error", "engine_task_id", "engine_result_id", "engine_attempt_id", "engine_status",
    ):
        op.drop_column("game_analyses", name)
