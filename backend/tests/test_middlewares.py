import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from src.middlewares.throttling import ThrottlingMiddleware


def _mock_message(user_id: int = 1):
    msg = MagicMock()
    msg.__class__ = Message
    msg.from_user.id = user_id
    msg.from_user.is_bot = False
    return msg


@pytest.fixture
def middleware():
    return ThrottlingMiddleware(rate_limit=0.5)


@pytest.fixture
def mock_handler():
    return AsyncMock()


@pytest.mark.asyncio
async def test_allows_first_message(middleware, mock_handler):
    event = _mock_message(1)
    await middleware(mock_handler, event, {})
    mock_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocks_second_within_rate_limit(middleware, mock_handler):
    event = _mock_message(1)
    await middleware(mock_handler, event, {})
    mock_handler.assert_awaited_once()

    mock_handler.reset_mock()
    await middleware(mock_handler, event, {})
    mock_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_allows_after_rate_limit_passes(middleware, mock_handler):
    event = _mock_message(1)
    await middleware(mock_handler, event, {})
    mock_handler.assert_awaited_once()

    mock_handler.reset_mock()
    middleware.cache[1] = time.time() - 1.0

    await middleware(mock_handler, event, {})
    mock_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_different_users_not_throttled(middleware, mock_handler):
    await middleware(mock_handler, _mock_message(1), {})
    mock_handler.assert_awaited_once()

    mock_handler.reset_mock()
    await middleware(mock_handler, _mock_message(2), {})
    mock_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_ignores_event_without_user(middleware, mock_handler):
    event = MagicMock()
    event.__class__ = Message
    event.from_user = None
    await middleware(mock_handler, event, {})
    mock_handler.assert_awaited_once()


# ── UserExistsMiddleware ────────────────────────────────────────────────────


@pytest.fixture
def user_exists_mw():
    from src.middlewares.user_exists import UserExistsMiddleware

    return UserExistsMiddleware()


@pytest.mark.asyncio
@patch("src.middlewares.user_exists.PlayerRepository")
@patch("src.middlewares.user_exists.async_session_factory")
async def test_user_exists_creates_player(mock_session_factory, mock_repo_cls, user_exists_mw):
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    mock_repo = AsyncMock()
    created_player = MagicMock()
    created_player.id = 1
    created_player.telegram_id = 555
    mock_repo.get_or_create.return_value = created_player
    mock_repo_cls.return_value = mock_repo

    handler = AsyncMock()
    event = MagicMock()
    event.__class__ = Message
    event.from_user.id = 555
    event.from_user.username = "testuser"
    event.from_user.first_name = "Test"
    event.from_user.last_name = None
    event.from_user.language_code = "en"
    event.from_user.is_bot = False

    data = {}
    await user_exists_mw(handler, event, data)

    assert data["player"] is created_player
    handler.assert_awaited_once_with(event, data)


@pytest.mark.asyncio
@patch("src.middlewares.user_exists.PlayerRepository")
@patch("src.middlewares.user_exists.async_session_factory")
async def test_user_exists_skips_bot(mock_session_factory, mock_repo_cls, user_exists_mw):
    handler = AsyncMock()
    event = MagicMock()
    event.__class__ = Message
    event.from_user.is_bot = True

    data = {}
    await user_exists_mw(handler, event, data)

    assert "player" not in data
    handler.assert_awaited_once()
    mock_session_factory.assert_not_called()


@pytest.mark.asyncio
@patch("src.middlewares.user_exists.PlayerRepository")
@patch("src.middlewares.user_exists.async_session_factory")
async def test_user_exists_skips_no_user(mock_session_factory, mock_repo_cls, user_exists_mw):
    handler = AsyncMock()
    event = MagicMock()
    event.__class__ = Message
    event.from_user = None

    data = {}
    await user_exists_mw(handler, event, data)

    assert "player" not in data
    handler.assert_awaited_once()
    mock_session_factory.assert_not_called()
