"""add source to word_list_items
Revision ID: xxxx
"""

import sqlalchemy as sa
from alembic import op

revision = "xxxx"
down_revision = "0a0eda58588a"


def upgrade():
    op.add_column(
        "word_list_items",
        sa.Column("source", sa.String(16), nullable=False, server_default="seed"),
    )
    op.create_index("ix_word_list_items_source", "word_list_items", ["source"])


def downgrade():
    op.drop_index("ix_word_list_items_source", table_name="word_list_items")
    op.drop_column("word_list_items", "source")
