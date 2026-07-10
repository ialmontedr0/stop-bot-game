"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("language_code", sa.String(8), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index(op.f("ix_players_telegram_id"), "players", ["telegram_id"])

    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="lobby"),
        sa.Column("current_round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_rounds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_games_group_chat_id"), "games", ["group_chat_id"])

    op.create_table(
        "group_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("default_rounds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("round_time", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("categories", sa.Text(), nullable=True),
        sa.Column("include_n", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("language", sa.String(8), nullable=False, server_default="es"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_chat_id"),
    )
    op.create_index(op.f("ix_group_configs_group_chat_id"), "group_configs", ["group_chat_id"])

    op.create_table(
        "game_players",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("is_host", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rounds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("letter", sa.String(1), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="waiting"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("stopped_at", sa.DateTime(), nullable=True),
        sa.Column("stopped_by_player_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["game_id"],
            ["games.id"],
        ),
        sa.ForeignKeyConstraint(
            ["stopped_by_player_id"],
            ["players.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "answers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("game_player_id", sa.Integer(), nullable=False),
        sa.Column("word_slot", sa.String(64), nullable=False),
        sa.Column("raw_text", sa.String(256), nullable=False),
        sa.Column("normalized_text", sa.String(256), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["game_player_id"],
            ["game_players.id"],
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "weekly_leaderboards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("total_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("games_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("weekly_leaderboards")
    op.drop_table("answers")
    op.drop_table("rounds")
    op.drop_table("game_players")
    op.drop_table("group_configs")
    op.drop_table("games")
    op.drop_index(op.f("ix_players_telegram_id"), table_name="players")
    op.drop_table("players")
