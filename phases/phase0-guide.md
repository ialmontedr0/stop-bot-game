# Phase 0 — Guía de implementación completa

> Lee este documento completo antes de empezar. Cada archivo debe crearse en la ruta indicada.
> Todos los comandos PowerShell están listos para copiar/pegar.

---

## Índice

1. [Estructura de directorios](#1-estructura-de-directorios)
2. [Archivos raíz](#2-archivos-raíz)
3. [Configuración de la aplicación (`src/config.py`)](#3-config)
4. [Modelos de base de datos (`src/db/`)](#4-modelos)
5. [Repositorios (`src/db/repositories/`)](#5-repositorios)
6. [Entry-point del bot (`src/bot.py`)](#6-bot-entry)
7. [Handlers (`src/handlers/`)](#7-handlers)
8. [Middlewares (`src/middlewares/`)](#8-middlewares)
9. [Alembic — migraciones](#9-alembic)
10. [Docker](#10-docker)
11. [Archivos restantes (`src/`)](#11-archivos-restantes)
12. [Comandos de instalación y ejecución](#12-comandos)

---

## 1. Estructura de directorios

Ejecuta este bloque **en PowerShell** desde la raíz del proyecto:

```powershell
$dirs = @(
    "src\db\repositories"
    "src\handlers\game"
    "src\middlewares"
    "src\services"
    "src\keyboards"
    "src\filters"
    "src\utils"
    "migrations\versions"
)

foreach ($d in $dirs) {
    New-Item -ItemType Directory -Path $d -Force
}
```

---

## 2. Archivos raíz

### 2.1 `.gitignore`

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
*.egg
.venv/
venv/

# Env
.env

# IDE
.vscode/
.idea/
*.swp

# OS
Thumbs.db
.DS_Store

# Docker
pgdata/
```

### 2.2 `.env.example`

```
BOT_TOKEN=tu_token_aqui
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
```

Copia a `.env` y edita con tu token real:

```powershell
Copy-Item .env.example .env
```

### 2.3 `requirements.txt`

```
aiogram>=3.15,<4.0
pydantic>=2.10,<3.0
pydantic-settings>=2.6,<3.0
sqlalchemy[asyncio]>=2.0,<3.0
asyncpg>=0.30,<1.0
alembic>=1.14,<2.0
redis[hiredis]>=5.2,<6.0
cachetools>=5.5,<6.0
python-dotenv>=1.0,<2.0
structlog>=24.4,<25.0
```

### 2.4 `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "src.bot"]
```

### 2.5 `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: stopbot
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  app:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/stopbot
      REDIS_URL: redis://redis:6379/0
    volumes:
      - .:/app
    command: python -m src.bot

volumes:
  pgdata:
```

### 2.6 `alembic.ini`

```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

---

## 3. Config (`src/config.py`)

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"


settings = Settings()
```

---

## 4. Modelos de base de datos

### 4.1 `src/db/__init__.py`

```python
from .models import Base
from .engine import engine, async_session_factory

__all__ = ["Base", "engine", "async_session_factory"]
```

### 4.2 `src/db/engine.py`

```python
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from src.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

### 4.3 `src/db/models.py`

```python
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
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
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
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
    week_start: Mapped[date]
    total_score: Mapped[int] = mapped_column(default=0)
    games_played: Mapped[int] = mapped_column(default=0)
    rank: Mapped[Optional[int]] = mapped_column(nullable=True)

    player: Mapped["Player"] = relationship()


class GroupConfig(Base):
    __tablename__ = "group_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    default_rounds: Mapped[int] = mapped_column(default=5)
    round_time: Mapped[int] = mapped_column(default=60)
    categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    include_n: Mapped[bool] = mapped_column(default=False)
    language: Mapped[str] = mapped_column(String(8), default="es")
```

---

## 5. Repositorios

### 5.1 `src/db/repositories/__init__.py`

```python
from .base import BaseRepository
from .player_repository import PlayerRepository
from .game_repository import GameRepository

__all__ = ["BaseRepository", "PlayerRepository", "GameRepository"]
```

### 5.2 `src/db/repositories/base.py`

```python
from typing import Any, Generic, Optional, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: int) -> Optional[ModelType]:
        return await self.session.get(self.model, id)

    async def get_all(self, **filters: Any) -> list[ModelType]:
        stmt = select(self.model)
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelType:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: int, **kwargs: Any) -> Optional[ModelType]:
        await self.session.execute(
            update(self.model).where(self.model.id == id).values(**kwargs)
        )
        await self.session.commit()
        return await self.get(id)

    async def delete(self, id: int) -> bool:
        result = await self.session.execute(
            delete(self.model).where(self.model.id == id)
        )
        await self.session.commit()
        return result.rowcount > 0
```

### 5.3 `src/db/repositories/player_repository.py`

```python
from typing import Optional

from sqlalchemy import select

from src.db.models import Player

from .base import BaseRepository


class PlayerRepository(BaseRepository[Player]):
    def __init__(self, session):
        super().__init__(Player, session)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Player]:
        stmt = select(Player).where(Player.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: str = "",
        last_name: Optional[str] = None,
        language_code: Optional[str] = None,
    ) -> Player:
        player = await self.get_by_telegram_id(telegram_id)
        if player:
            return player
        return await self.create(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )
```

### 5.4 `src/db/repositories/game_repository.py`

```python
from typing import Optional

from sqlalchemy import select

from src.db.models import Game, GamePlayer, Player

from .base import BaseRepository


class GameRepository(BaseRepository[Game]):
    def __init__(self, session):
        super().__init__(Game, session)

    async def get_active_game(self, group_chat_id: int) -> Optional[Game]:
        stmt = (
            select(Game)
            .where(Game.group_chat_id == group_chat_id)
            .where(Game.status.in_(["lobby", "playing"]))
            .order_by(Game.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_player_to_game(
        self, game: Game, player: Player, is_host: bool = False
    ) -> GamePlayer:
        gp = GamePlayer(
            game_id=game.id,
            player_id=player.id,
            is_host=is_host,
        )
        self.session.add(gp)
        await self.session.commit()
        await self.session.refresh(gp)
        return gp

    async def get_player_count(self, game: Game) -> int:
        stmt = (
            select(GamePlayer)
            .where(GamePlayer.game_id == game.id)
        )
        result = await self.session.execute(stmt)
        return len(result.scalars().all())
```

---

## 6. Entry-point del bot (`src/bot.py`)

```python
import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis as AsyncRedis

from src.config import settings
from src.db.engine import engine
from src.handlers.group import group_router
from src.handlers.start import start_router
from src.middlewares.throttling import ThrottlingMiddleware
from src.middlewares.user_exists import UserExistsMiddleware


def setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger(__name__)


async def on_startup() -> None:
    logger.info("Bot started", version="1.0.0")


async def on_shutdown() -> None:
    await engine.dispose()
    logger.info("Bot stopped")


async def main() -> None:
    setup_logging()
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    redis_client = AsyncRedis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    storage = RedisStorage(redis=redis_client)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=storage)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # ── Routers ──────────────────────────────────────────
    dp.include_router(start_router)
    dp.include_router(group_router)

    # ── Middlewares ──────────────────────────────────────
    throttling = ThrottlingMiddleware()
    user_exists = UserExistsMiddleware()

    dp.message.middleware(throttling)
    dp.callback_query.middleware(throttling)
    dp.message.middleware(user_exists)
    dp.callback_query.middleware(user_exists)

    logger.info("Starting polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 7. Handlers

### 7.1 `src/handlers/__init__.py`

```python
from .start import start_router
from .group import group_router

__all__ = ["start_router", "group_router"]
```

### 7.2 `src/handlers/start.py`

```python
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "<b>🛑 Stop Bot</b>\n\n"
        "El juego clásico de <b>Stop / Basta</b> ahora en Telegram.\n\n"
        "<b>Comandos:</b>\n"
        "• /stop — Iniciar una partida en el grupo\n"
        "• /help — Ayuda\n"
        "• /stats — Estadísticas\n"
        "• /weekly — Leaderboard semanal\n\n"
        "¡Añádeme a un grupo y juega con tus amigos!"
    )


@start_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>📖 ¿Cómo jugar?</b>\n\n"
        "1. Ve a un grupo y escribe /stop\n"
        "2. Espera a que se unan jugadores (máx. 10)\n"
        "3. Cuando comience la ronda, escribe palabras para cada categoría\n"
        "4. Sé el primero en completar todas y pulsa ⏹ Stop\n"
        "5. ¡Gana puntos y conviértete en el MVP!\n\n"
        "<b>Puntuación:</b>\n"
        "• Respuesta correcta única → 50 pts\n"
        "• Respuesta duplicada → 50 ÷ N jugadores\n"
        "• Respuesta incorrecta o vacía → 0 pts\n\n"
        "<b>¿Más dudas?</b> Háblale a @tu_usuario"
    )
```

### 7.3 `src/handlers/group.py`

```python
from aiogram import Router
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import ChatMemberUpdated

group_router = Router()


@group_router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER)
)
async def bot_added_to_group(event: ChatMemberUpdated) -> None:
    title = event.chat.title or "este grupo"
    await event.answer(
        f"¡Gracias por añadirme a <b>{title}</b>! 🎉\n\n"
        "Escribe /stop para comenzar una partida."
    )
```

---

## 8. Middlewares

### 8.1 `src/middlewares/__init__.py`

```python
from .throttling import ThrottlingMiddleware
from .user_exists import UserExistsMiddleware

__all__ = ["ThrottlingMiddleware", "UserExistsMiddleware"]
```

### 8.2 `src/middlewares/throttling.py`

```python
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from cachetools import TTLCache


class ThrottlingMiddleware(BaseMiddleware):
    """Rate-limiter en memoria (máx. 1 msg / 0.5s por usuario)."""

    def __init__(self, rate_limit: float = 0.5) -> None:
        self.rate_limit = rate_limit
        self.cache: TTLCache[int, float] = TTLCache(
            maxsize=10_000, ttl=60
        )

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id = self._resolve_user_id(event)
        if user_id is not None:
            now = time.time()
            last = self.cache.get(user_id, 0.0)
            if now - last < self.rate_limit:
                return  # silenciosamente ignorado
            self.cache[user_id] = now
        return await handler(event, data)

    @staticmethod
    def _resolve_user_id(event: TelegramObject) -> int | None:
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        return None
```

### 8.3 `src/middlewares/user_exists.py`

```python
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import async_session_factory
from src.db.repositories import PlayerRepository


class UserExistsMiddleware(BaseMiddleware):
    """Crea el registro Player si no existe para cualquier interacción."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = self._resolve_user(event)
        if user is not None and not user.is_bot:
            async with async_session_factory() as session:
                repo = PlayerRepository(session)
                player = await repo.get_or_create(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name or "",
                    last_name=user.last_name,
                    language_code=user.language_code,
                )
                data["player"] = player
        return await handler(event, data)

    @staticmethod
    def _resolve_user(event: TelegramObject):
        if isinstance(event, Message) and event.from_user:
            return event.from_user
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user
        return None
```

---

## 9. Alembic — migraciones

### 9.1 `migrations/env.py`

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.config import settings
from src.db.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### 9.2 `migrations/script.py.mako`

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

---

## 10. Archivos restantes (`src/`)

### 10.1 `src/__init__.py`

```python
"""Stop Bot — juego multijugador de Stop/Basta para Telegram."""
```

### 10.2 `src/handlers/game/__init__.py`

```python
# Router para lógica del juego (Fase 1+)
```

### 10.3 `src/services/__init__.py`

```python
from .game_orchestrator import GameOrchestrator
from .score_engine import ScoreEngine
from .spell_corrector import SpellCorrector
from .leaderboard import LeaderboardService

__all__ = [
    "GameOrchestrator",
    "ScoreEngine",
    "SpellCorrector",
    "LeaderboardService",
]
```

### 10.4 `src/services/game_orchestrator.py`

```python
"""Placeholder — implementar en Fase 1."""


class GameOrchestrator:
    pass
```

### 10.5 `src/services/score_engine.py`

```python
"""Placeholder — implementar en Fase 3."""


class ScoreEngine:
    pass
```

### 10.6 `src/services/spell_corrector.py`

```python
"""Placeholder — implementar en Fase 4."""


class SpellCorrector:
    pass
```

### 10.7 `src/services/leaderboard.py`

```python
"""Placeholder — implementar en Fase 6."""


class LeaderboardService:
    pass
```

### 10.8 `src/keyboards/__init__.py`

```python
"""Inline keyboards del bot."""
```

### 10.9 `src/filters/__init__.py`

```python
"""Filtros personalizados de aiogram."""
```

### 10.10 `src/utils/__init__.py`

```python
"""Utilidades generales."""
```

---

## 11. Comandos de instalación y ejecución

Sigue estos pasos **en orden**.

### 11.1 Crear estructura y archivos

Crea primero todos los directorios (paso 1), luego copia el contenido de cada archivo
en su ruta correspondiente usando tu editor.

### 11.2 Instalar dependencias (local, sin Docker)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 11.3 Configurar variables de entorno

Edita `.env` con tu token real de BotFather.


### 11.4 Ejecutar migraciones de base de datos

```powershell
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### 11.5 Iniciar el bot

```powershell
python -m src.bot
```

Deberías ver:

```
2025-01-01T12:00:00.000000Z [info     ] Bot started                  version=1.0.0
2025-01-01T12:00:00.000000Z [info     ] Starting polling...
```

### 11.7 Verificar

1. Abre Telegram, busca tu bot y escribe `/start` → debe responder con el mensaje de bienvenida.
2. Añade el bot a un grupo → debe responder "Gracias por añadirme...".
3. Escribe `/help` en el grupo → debe responder con las instrucciones.

---

## 12. Resumen de arquitectura

```
                    ┌──────────────┐
                    │   Telegram   │
                    │  Bot API     │
                    └──────┬───────┘
                           │ polling
                    ┌──────▼───────┐
                    │   aiogram    │
                    │  Dispatcher  │
                    │  + Routers   │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
       │ Middlewares │ │Handlers│ │  Services │
       │ throttling │ │ start  │ │ (future)  │
       │ user_exists│ │ group  │ │orchestrator│
       └────────────┘ └───┬───┘ │score_engine│
                          │     │spell_corr  │
                   ┌──────▼──┐  │leaderboard │
                   │   DB    │  └───────────┘
                   │  repos  │
                   └────┬───-┘
                        │
              ┌─────────┴──────────┐
              │                    │
       ┌──────▼──────┐    ┌───────▼──────┐
       │  PostgreSQL  │    │    Redis     │
       │  (persist)   │    │ (cache/FSM)  │
       └─────────────┘    └──────────────┘
```

---
