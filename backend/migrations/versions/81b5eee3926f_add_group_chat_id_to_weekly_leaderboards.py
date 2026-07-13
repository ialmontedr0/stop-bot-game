"""add group_chat_id to weekly_leaderboards

Revision ID: 81b5eee3926f
Revises: 72c23fba8cae
Create Date: 2026-07-13 09:16:50.456509
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "81b5eee3926f"
down_revision: Union[str, None] = "72c23fba8cae" # noqa: UP007
branch_labels: Union[str, Sequence[str], None] = None  # noqa: UP007
depends_on: Union[str, Sequence[str], None] = None # noqa: UP007


def upgrade() -> None:
    op.add_column(
        "weekly_leaderboards",
        sa.Column("group_chat_id", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.alter_column("weekly_leaderboards", "group_chat_id", server_default=None)
    op.drop_constraint("uq_player_week", "weekly_leaderboards", type_="unique")
    op.create_unique_constraint(
        "uq_player_week_group", "weekly_leaderboards", ["player_id", "week_start", "group_chat_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_player_week_group", "weekly_leaderboards", type_="unique")
    op.create_unique_constraint(
        "uq_player_week", "weekly_leaderboards", ["player_id", "week_start"],
    )
    op.drop_column("weekly_leaderboards", "group_chat_id")
