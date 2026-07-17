from datetime import date, datetime, timezone
from typing import Optional

from src.core.text_utils import utcnow

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow()
    )

    game_players: Mapped[list["GamePlayer"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    weekly_leaderboards: Mapped[list["WeeklyLeaderboard"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )

    xp: Mapped[Optional["PlayerXP"]] = relationship(
        back_populates="player", uselist=False, cascade="all, delete-orphan"
    )
    streak: Mapped[Optional["Streak"]] = relationship(
        back_populates="player", uselist=False, cascade="all, delete-orphan"
    )


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(String(20), default="lobby")
    current_round: Mapped[int] = mapped_column(default=0)
    total_rounds: Mapped[int] = mapped_column(default=5)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow()
    )
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    players: Mapped[list["GamePlayer"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    rounds: Mapped[list["Round"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class GamePlayer(Base):
    __tablename__ = "game_players"

    __table_args__ = (UniqueConstraint("game_id", "player_id", name="uq_game_player"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    score: Mapped[int] = mapped_column(default=0)
    joined_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow()
    )
    is_host: Mapped[bool] = mapped_column(default=False)

    game: Mapped["Game"] = relationship(back_populates="players")
    player: Mapped["Player"] = relationship(back_populates="game_players")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="game_player", cascade="all, delete-orphan"
    )


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    round_number: Mapped[int]
    letter: Mapped[str] = mapped_column(String(1))
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stopped_by_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )

    game: Mapped["Game"] = relationship(back_populates="rounds")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    game_player_id: Mapped[int] = mapped_column(ForeignKey("game_players.id", ondelete="CASCADE"))
    word_slot: Mapped[str] = mapped_column(String(64))
    raw_text: Mapped[str] = mapped_column(String(256))
    normalized_text: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(nullable=True)
    score: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow()
    )

    round: Mapped["Round"] = relationship(back_populates="answers")
    player: Mapped["Player"] = relationship(back_populates="answers")
    game_player: Mapped["GamePlayer"] = relationship(back_populates="answers")


class WeeklyLeaderboard(Base):
    __tablename__ = "weekly_leaderboards"

    __table_args__ = (
        UniqueConstraint("player_id", "week_start", "group_chat_id", name="uq_player_week_group"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    group_chat_id: Mapped[int] = mapped_column(BigInteger, default=0)
    week_start: Mapped[date] = mapped_column(default=lambda: date.today())
    total_score: Mapped[int] = mapped_column(default=0)
    games_played: Mapped[int] = mapped_column(default=0)
    rank: Mapped[int | None] = mapped_column(nullable=True)

    player: Mapped["Player"] = relationship(back_populates="weekly_leaderboards")


class PlayerXP(Base):
    __tablename__ = "player_xp"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), unique=True, index=True
    )
    xp: Mapped[int] = mapped_column(default=0)
    level: Mapped[int] = mapped_column(default=1)
    total_xp_earned: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow(),
        onupdate=lambda: utcnow(),
    )

    player: Mapped["Player"] = relationship(back_populates="xp")


class Streak(Base):
    __tablename__ = "streaks"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), unique=True, index=True
    )
    current_streak: Mapped[int] = mapped_column(default=0)
    max_streak: Mapped[int] = mapped_column(default=0)
    last_played_date: Mapped[date | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow(),
        onupdate=lambda: utcnow(),
    )

    player: Mapped["Player"] = relationship(back_populates="streak")


class SeasonalEvent(Base):
    __tablename__ = "seasonal_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    multiplier: Mapped[float] = mapped_column(default=1.0)  # ej: 2.0 = doble xp
    starts_at: Mapped[datetime] = mapped_column()
    ends_at: Mapped[datetime] = mapped_column()
    active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow()
    )


class GroupConfig(Base):
    __tablename__ = "group_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    default_rounds: Mapped[int] = mapped_column(default=5)
    round_time: Mapped[int] = mapped_column(default=60)
    categories: Mapped[str | None] = mapped_column(Text, nullable=True)
    include_n: Mapped[bool] = mapped_column(default=False)
    language: Mapped[str] = mapped_column(String(8), default="es")
    validation_mode: Mapped[str | None] = mapped_column(String(16), default="local", nullable=True)


class WordListItem(Base):
    __tablename__ = "word_list_items"

    __table_args__ = (UniqueConstraint("category", "normalized", name="uq_category_word"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    word: Mapped[str] = mapped_column(String(128))
    normalized: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(16), default="seed")
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow()
    )

    def __repr__(self) -> str:
        return f"<WordListItem id={self.id} cat={self.category} word={self.word}>"


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        default=lambda: utcnow(), index=True
    )
    level: Mapped[str] = mapped_column(String(20), default="ERROR")
    handler: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    game_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exception_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    resolved: Mapped[bool] = mapped_column(default=False)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ErrorLog id={self.id} type={self.exception_type}>"


class GameStateCache(Base):
    __tablename__ = "game_state_cache"

    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow(),
        onupdate=lambda: utcnow(),
    )


class MessageLog(Base):
    __tablename__ = "message_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: utcnow()
    )
