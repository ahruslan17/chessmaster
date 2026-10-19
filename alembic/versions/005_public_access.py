"""Add one-time public-access sessions and scope stored visitor data.

Revision ID: 005
Revises: 004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("code_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "access_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "access_code_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("access_codes.id", ondelete="CASCADE"), unique=True, nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("games", sa.Column("access_session_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_games_access_session_id", "games", "access_sessions", ["access_session_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_games_access_session_id", "games", ["access_session_id"])
    op.add_column("period_reports", sa.Column("access_session_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_period_reports_access_session_id", "period_reports", "access_sessions", ["access_session_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_period_reports_access_session_id", "period_reports", ["access_session_id"])


def downgrade() -> None:
    op.drop_index("ix_period_reports_access_session_id", table_name="period_reports")
    op.drop_constraint("fk_period_reports_access_session_id", "period_reports", type_="foreignkey")
    op.drop_column("period_reports", "access_session_id")
    op.drop_index("ix_games_access_session_id", table_name="games")
    op.drop_constraint("fk_games_access_session_id", "games", type_="foreignkey")
    op.drop_column("games", "access_session_id")
    op.drop_table("access_sessions")
    op.drop_table("access_codes")
