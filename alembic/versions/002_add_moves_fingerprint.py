"""Add moves_fingerprint to games for duplicate detection.

Revision ID: 002
Revises: 001
Create Date: 2026-02-18

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("moves_fingerprint", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_games_moves_fingerprint",
        "games",
        ["moves_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_games_moves_fingerprint", table_name="games")
    op.drop_column("games", "moves_fingerprint")
