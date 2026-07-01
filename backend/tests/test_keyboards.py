from aiogram.types import InlineKeyboardMarkup

from src.keyboards.lobby import lobby_keyboard


def test_lobby_keyboard_returns_inline_keyboard():
    markup = lobby_keyboard(game_id=1)
    assert isinstance(markup, InlineKeyboardMarkup)


def test_lobby_keyboard_has_join_button():
    markup = lobby_keyboard(game_id=1)
    buttons = markup.inline_keyboard
    join_row = buttons[0]
    assert len(join_row) == 1
    assert join_row[0].text == "🟢 Unirse"
    assert join_row[0].callback_data == "join:1"


def test_lobby_keyboard_no_start_button_for_non_host():
    markup = lobby_keyboard(game_id=1, is_host=False)
    buttons = markup.inline_keyboard
    assert len(buttons) == 1


def test_lobby_keyboard_has_start_button_for_host():
    markup = lobby_keyboard(game_id=1, is_host=True)
    buttons = markup.inline_keyboard
    assert len(buttons) == 2
    start_row = buttons[1]
    assert start_row[0].text == "▶️ Iniciar"
    assert start_row[0].callback_data == "start:1"


def test_lobby_keyboard_game_id_in_callback():
    markup = lobby_keyboard(game_id=99, is_host=True)
    buttons = markup.inline_keyboard
    assert buttons[0][0].callback_data == "join:99"
    assert buttons[1][0].callback_data == "start:99"
