"""Initial schema.

Revision ID: 001
Revises: None
Create Date: 2026-02-15

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pgn_text", sa.Text(), nullable=False),
        sa.Column("white_player", sa.String(255), nullable=False, server_default=""),
        sa.Column("black_player", sa.String(255), nullable=False, server_default=""),
        sa.Column("result", sa.String(10), nullable=False, server_default="*"),
        sa.Column("opening_name", sa.String(255), nullable=True),
        sa.Column("eco_code", sa.String(10), nullable=True),
        sa.Column("time_control", sa.String(50), nullable=True),
        sa.Column("played_at", sa.Date(), nullable=True),
        sa.Column("player_color", sa.String(5), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "game_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("opening_assessment", sa.Text(), nullable=True),
        sa.Column("middlegame_assessment", sa.Text(), nullable=True),
        sa.Column("endgame_assessment", sa.Text(), nullable=True),
        sa.Column("key_moments", postgresql.JSONB(), nullable=True),
        sa.Column("accuracy_white", sa.Float(), nullable=True),
        sa.Column("accuracy_black", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "move_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "game_analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("game_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("move_number", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(5), nullable=False),
        sa.Column("move_san", sa.String(10), nullable=False),
        sa.Column("best_move_san", sa.String(10), nullable=True),
        sa.Column("eval_before", sa.Float(), nullable=True),
        sa.Column("eval_after", sa.Float(), nullable=True),
        sa.Column("centipawn_loss", sa.Float(), nullable=True),
        sa.Column("classification", sa.String(20), nullable=True),
        sa.Column("top_moves", postgresql.JSONB(), nullable=True),
        sa.Column("continuation_lines", postgresql.JSONB(), nullable=True),
        sa.Column("llm_comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "period_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(20), nullable=False),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("weakness_patterns", postgresql.JSONB(), nullable=True),
        sa.Column("strength_patterns", postgresql.JSONB(), nullable=True),
        sa.Column("game_ids", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("period_reports")
    op.drop_table("move_analyses")
    op.drop_table("game_analyses")
    op.drop_table("games")
