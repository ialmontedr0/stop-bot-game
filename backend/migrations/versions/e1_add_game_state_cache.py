"""add game_state_cache table for GameStateStore

Revision ID: e1
Revises: 81b5eee3926f
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1"
down_revision: str | None = "81b5eee3926f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_state_cache",
        sa.Column("key", sa.String(256), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("game_state_cache")
