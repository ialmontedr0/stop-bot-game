"""add validation_mode to group_configs

Revision ID: 864f644481b0
Revises: xxxx
Create Date: 2026-07-07 11:16:40.351641
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "864f644481b0"
down_revision: str | None = "xxxx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "group_configs",
        sa.Column("validation_mode", sa.String(16), nullable=True, server_default="local"),
    )


def downgrade() -> None:
    op.drop_column("group_configs", "validation_mode")
