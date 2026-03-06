"""Add diary-related fields and game notes.

Revision ID: 003
Revises: 002
Create Date: 2026-03-06

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "game_analyses",
        sa.Column("coach_feedback", postgresql.JSONB(), nullable=True),
    )

    op.add_column(
        "period_reports",
        sa.Column("coach_feedback", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "period_reports",
        sa.Column("comparison_metrics", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "period_reports",
        sa.Column("comparison_summary", sa.Text(), nullable=True),
    )

    op.create_table(
        "game_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("game_notes")
    op.drop_column("period_reports", "comparison_summary")
    op.drop_column("period_reports", "comparison_metrics")
    op.drop_column("period_reports", "coach_feedback")
    op.drop_column("game_analyses", "coach_feedback")
