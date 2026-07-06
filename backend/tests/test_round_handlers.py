from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import Player


# ── handle_round_answer ─────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.handlers.game.round.round_manager")
async def test_handle_round_answer_skips_commands(mock_rm):
    from src.handlers.game.round import handle_round_answer

    message = MagicMock()
    message.text = "/stop"
    message.chat.type = "group"

    player = MagicMock(spec=Player)
    bot = AsyncMock()

    await handle_round_answer(message, player, bot)
    mock_rm.get_active_round_by_group.assert_not_called()


@pytest.mark.asyncio
@patch("src.handlers.game.round.round_manager")
async def test_handle_round_answer_skips_no_active_round(mock_rm):
    from src.handlers.game.round import handle_round_answer

    mock_rm.get_active_round_by_group.return_value = None

    message = MagicMock()
    message.text = "Nombre: Juan"
    message.chat.type = "group"
    message.from_user = None

    player = MagicMock(spec=Player)
    bot = AsyncMock()

    await handle_round_answer(message, player, bot)
    mock_rm.submit_answers.assert_not_called()


@pytest.mark.asyncio
@patch("src.handlers.game.round.round_manager")
async def test_handle_round_answer_invalid_format(mock_rm):
    from src.handlers.game.round import handle_round_answer

    mock_state = MagicMock()
    mock_state.categories = ["Nombre", "Color"]
    mock_rm.get_active_round_by_group.return_value = mock_state

    message = MagicMock()
    message.text = "some random text without format"
    message.chat.type = "group"
    message.from_user = None

    player = MagicMock(spec=Player)
    bot = AsyncMock()

    await handle_round_answer(message, player, bot)
    mock_rm.submit_answers.assert_not_called()


@pytest.mark.asyncio
@patch("src.handlers.game.round.round_manager")
async def test_handle_round_answer_submits(mock_rm):
    from src.handlers.game.round import handle_round_answer

    mock_state = MagicMock()
    mock_state.game_id = 1
    mock_state.categories = ["Nombre", "Color"]
    mock_state.player_names = {}
    mock_rm.get_active_round_by_group.return_value = mock_state

    mock_rm.submit_answers = AsyncMock(return_value=False)

    message = MagicMock()
    message.text = "Nombre: Juan\nColor: Rojo"
    message.chat.type = "group"
    message.from_user = None
    message.reply = AsyncMock()

    player = MagicMock(spec=Player)
    player.first_name = "TestUser"
    player.username = "test"
    player.telegram_id = 123
    player.id = 1
    bot = AsyncMock()

    await handle_round_answer(message, player, bot)

    mock_rm.submit_answers.assert_awaited_once_with(
        game_id=1, player=player, text=message.text, bot=bot
    )


# ── callback_stop ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.handlers.game.round.round_manager")
async def test_callback_stop_calls_press_stop(mock_rm):
    from src.handlers.game.round import callback_stop

    callback = MagicMock()
    callback.data = "stop:1:5"

    player = MagicMock(spec=Player)
    player.telegram_id = 111
    bot = AsyncMock()

    mock_rm.press_stop = AsyncMock()

    await callback_stop(callback, player, bot)
    mock_rm.press_stop.assert_awaited_once_with(
        game_id=1, player_id=111, callback=callback, bot=bot
    )


# ── callback_letter ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.handlers.game.round.round_manager")
async def test_callback_letter_calls_handle_letter_selection(mock_rm):
    from src.handlers.game.round import callback_letter

    callback = MagicMock()
    callback.data = "letter:1:F"

    player = MagicMock(spec=Player)
    player.telegram_id = 111
    bot = AsyncMock()

    mock_rm.handle_letter_selection = AsyncMock()

    await callback_letter(callback, player, bot)
    mock_rm.handle_letter_selection.assert_awaited_once_with(
        game_id=1, player_id=111, letter="F", callback=callback, bot=bot
    )


@pytest.mark.asyncio
@patch("src.handlers.game.round.round_manager")
async def test_callback_letter_invalid_letter(mock_rm):
    from src.handlers.game.round import callback_letter

    callback = AsyncMock()
    callback.data = "letter:1:Ñ"

    player = MagicMock(spec=Player)
    player.telegram_id = 111
    bot = AsyncMock()

    await callback_letter(callback, player, bot)
    callback.answer.assert_awaited_with("❌ Letra inválida.", show_alert=True)
    mock_rm.handle_letter_selection.assert_not_called()
