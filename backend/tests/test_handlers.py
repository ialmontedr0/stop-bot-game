from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, ChatMemberUpdated

from src.db.models import Player

# ── cmd_stop ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.handlers.game.lobby.lobby_manager")
async def test_cmd_stop_private_chat_rejected(mock_lm):
    from src.handlers.game.lobby import cmd_stop

    message = MagicMock()
    message.chat.type = "private"
    message.answer = AsyncMock()

    player = MagicMock(spec=Player)
    bot = AsyncMock()

    await cmd_stop(message, player, bot)
    message.answer.assert_awaited_once()
    args, _ = message.answer.await_args
    assert "solo funciona en grupos" in args[0]


@pytest.mark.asyncio
@patch("src.handlers.game.lobby.lobby_manager")
async def test_cmd_stop_group_creates_lobby(mock_lm):
    from src.handlers.game.lobby import cmd_stop

    message = MagicMock()
    message.chat.type = "group"
    message.chat.id = -100123
    message.answer = AsyncMock()

    player = MagicMock(spec=Player)
    player.telegram_id = 123
    bot = AsyncMock()

    mock_lm.create_lobby = AsyncMock(return_value=None)

    await cmd_stop(message, player, bot)
    mock_lm.create_lobby.assert_awaited_once_with(
        group_chat_id=-100123, host_player=player, bot=bot
    )


@pytest.mark.asyncio
@patch("src.handlers.game.lobby.lobby_manager")
async def test_cmd_stop_group_reports_error(mock_lm):
    from src.handlers.game.lobby import cmd_stop

    message = MagicMock()
    message.chat.type = "supergroup"
    message.chat.id = -100456
    message.answer = AsyncMock()

    player = MagicMock(spec=Player)
    bot = AsyncMock()

    mock_lm.create_lobby = AsyncMock(return_value="⚠️ Ya hay una sala abierta.")

    await cmd_stop(message, player, bot)
    message.answer.assert_awaited_once_with("⚠️ Ya hay una sala abierta.")


# ── cmd_cancel ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.handlers.game.lobby.lobby_manager")
async def test_cmd_cancel_private_chat_rejected(mock_lm):
    from src.handlers.game.lobby import cmd_cancel

    message = MagicMock()
    message.chat.type = "private"
    message.answer = AsyncMock()

    player = MagicMock(spec=Player)
    bot = AsyncMock()

    await cmd_cancel(message, player, bot)
    message.answer.assert_awaited_once()
    args, _ = message.answer.await_args
    assert "solo funciona en grupos" in args[0]


@pytest.mark.asyncio
@patch("src.handlers.game.lobby.lobby_manager")
async def test_cmd_cancel_group_cancels(mock_lm):
    from src.handlers.game.lobby import cmd_cancel

    message = MagicMock()
    message.chat.type = "group"
    message.chat.id = -100789
    message.answer = AsyncMock()

    player = MagicMock(spec=Player)
    bot = AsyncMock()

    mock_lm.cancel_game = AsyncMock(return_value="✅ Partida cancelada.")

    await cmd_cancel(message, player, bot)
    mock_lm.cancel_game.assert_awaited_once_with(group_chat_id=-100789, player=player, bot=bot)
    message.answer.assert_awaited_once_with("✅ Partida cancelada.")


# ── callback_join ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.handlers.game.lobby.lobby_manager", new_callable=AsyncMock)
async def test_callback_join_calls_manager(mock_lm):
    from src.handlers.game.lobby import callback_join

    callback = AsyncMock()
    callback.data = "join:42"

    player = MagicMock(spec=Player)
    bot = AsyncMock()

    await callback_join(callback, player, bot)
    mock_lm.join_lobby.assert_awaited_once_with(
        game_id=42, player=player, callback=callback, bot=bot
    )


# ── callback_start ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.handlers.game.lobby.lobby_manager", new_callable=AsyncMock)
async def test_callback_start_calls_manager(mock_lm):
    from src.handlers.game.lobby import callback_start

    callback = AsyncMock()
    callback.data = "start:7"

    player = MagicMock(spec=Player)
    bot = AsyncMock()

    await callback_start(callback, player, bot)
    mock_lm.start_game.assert_awaited_once_with(
        game_id=7, player=player, callback=callback, bot=bot
    )


# ── cmd_start ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_start_responds_with_welcome():
    from unittest.mock import patch

    from src.handlers.start import cmd_start

    message = AsyncMock()
    message.answer.return_value = AsyncMock()

    with patch("src.image_generator.generate_welcome_image", return_value=None):
        await cmd_start(message)

    message.answer.assert_awaited_once()
    args, _ = message.answer.await_args
    assert "Stop Bot" in args[0]
    assert "/stop" in args[0]


# ── cmd_help ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_help_responds():
    from unittest.mock import patch

    from src.handlers.start import cmd_help

    message = AsyncMock()
    message.answer.return_value = AsyncMock()

    with patch("src.image_generator.generate_help_image", return_value=None):
        await cmd_help(message)

    message.answer.assert_awaited_once()
    args, _ = message.answer.await_args
    assert "Cómo jugar" in args[0]


# ── bot_added_to_group ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bot_added_to_group_sends_welcome():
    from src.handlers.group import bot_added_to_group

    chat = MagicMock(spec=Chat)
    chat.id = -100123
    chat.title = "Test Group"

    event = MagicMock(spec=ChatMemberUpdated)
    event.chat = chat

    bot = AsyncMock()

    await bot_added_to_group(event, bot)

    bot.send_message.assert_awaited_once_with(
        -100123,
        "¡Gracias por añadirme a <b>Test Group</b>! 🎉\n\nEscribe /stop para comenzar una partida.",
    )


@pytest.mark.asyncio
async def test_bot_added_to_group_fallback_title():
    from src.handlers.group import bot_added_to_group

    chat = MagicMock(spec=Chat)
    chat.id = -100456
    chat.title = None

    event = MagicMock(spec=ChatMemberUpdated)
    event.chat = chat

    bot = AsyncMock()

    await bot_added_to_group(event, bot)

    bot.send_message.assert_awaited_once()
    args, _ = bot.send_message.await_args
    assert "este grupo" in args[1]
