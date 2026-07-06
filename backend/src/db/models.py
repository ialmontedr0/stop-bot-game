from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    game_players: Mapped[list["GamePlayer"]] = relationship(back_populates="player")
    answers: Mapped[list["Answer"]] = relationship(back_populates="player")
    weekly_leaderboards: Mapped[list["WeeklyLeaderboard"]] = relationship(
        back_populates="player"
    )


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(String(20), default="lobby")
    current_round: Mapped[int] = mapped_column(default=0)
    total_rounds: Mapped[int] = mapped_column(default=5)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    players: Mapped[list["GamePlayer"]] = relationship(back_populates="game")
    rounds: Mapped[list["Round"]] = relationship(back_populates="game")


class GamePlayer(Base):
    __tablename__ = "game_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    score: Mapped[int] = mapped_column(default=0)
    joined_at: Mapped[datetime] = mapped_column(default=func.now())
    is_host: Mapped[bool] = mapped_column(default=False)

    game: Mapped["Game"] = relationship(back_populates="players")
    player: Mapped["Player"] = relationship(back_populates="game_players")
    answers: Mapped[list["Answer"]] = relationship(back_populates="game_player")


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    round_number: Mapped[int]
    letter: Mapped[str] = mapped_column(String(1))
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    stopped_by_player_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )

    game: Mapped["Game"] = relationship(back_populates="rounds")
    answers: Mapped[list["Answer"]] = relationship(back_populates="round")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    game_player_id: Mapped[int] = mapped_column(ForeignKey("game_players.id"))
    word_slot: Mapped[str] = mapped_column(String(64))
    raw_text: Mapped[str] = mapped_column(String(256))
    normalized_text: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(nullable=True)
    score: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    round: Mapped["Round"] = relationship(back_populates="answers")
    player: Mapped["Player"] = relationship(back_populates="answers")
    game_player: Mapped["GamePlayer"] = relationship(back_populates="answers")


class WeeklyLeaderboard(Base):
    __tablename__ = "weekly_leaderboards"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    week_start: Mapped[date] = mapped_column(default=func.current_date())
    total_score: Mapped[int] = mapped_column(default=0)
    games_played: Mapped[int] = mapped_column(default=0)
    rank: Mapped[Optional[int]] = mapped_column(nullable=True)

    player: Mapped["Player"] = relationship(back_populates="weekly_leaderboards")


class GroupConfig(Base):
    __tablename__ = "group_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    default_rounds: Mapped[int] = mapped_column(default=5)
    round_time: Mapped[int] = mapped_column(default=60)
    categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    include_n: Mapped[bool] = mapped_column(default=False)
    language: Mapped[str] = mapped_column(String(8), default="es")


class WordListItem(Base):
    __tablename__ = "word_list_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    word: Mapped[str] = mapped_column(String(128))
    normalized: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    def __repr__(self) -> str:
        return f"<WordListItem id={self.id} cat={self.category} word={self.word}>"


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(default=func.now(), index=True)
    level: Mapped[str] = mapped_column(String(20), default="ERROR")
    handler: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    game_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    exception_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    exception_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    resolved: Mapped[bool] = mapped_column(default=False)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ErrorLog id={self.id} type={self.exception_type}>"
