import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.db.models import Base, Game, GamePlayer, Player, WordListItem


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_session(async_engine) -> AsyncSession:
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def player(async_session: AsyncSession) -> Player:
    p = Player(
        telegram_id=123456789,
        username="testuser",
        first_name="Test",
        last_name="User",
        language_code="es",
    )
    async_session.add(p)
    await async_session.commit()
    await async_session.refresh(p)
    return p


@pytest.fixture
async def game(async_session: AsyncSession, player: Player) -> Game:
    g = Game(group_chat_id=-100123456789)
    async_session.add(g)
    await async_session.commit()
    await async_session.refresh(g)
    gp = GamePlayer(game_id=g.id, player_id=player.id, is_host=True)
    async_session.add(gp)
    await async_session.commit()
    return g


@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock()
    msg = MagicMock()
    msg.chat.id = -100123456789
    msg.message_id = 42
    bot.send_message.return_value = msg
    return bot


@pytest.fixture
def mock_message() -> MagicMock:
    msg = MagicMock()
    msg.chat.id = -100123456789
    msg.chat.type = "group"
    msg.from_user.id = 123456789
    msg.from_user.is_bot = False
    msg.message_id = 1
    return msg


@pytest.fixture
def mock_callback() -> MagicMock:
    cb = MagicMock()
    cb.answer = AsyncMock()
    cb.from_user.id = 123456789
    cb.from_user.is_bot = False
    cb.data = "join:1"
    cb.message.chat.id = -100123456789
    cb.message.message_id = 1
    return cb
