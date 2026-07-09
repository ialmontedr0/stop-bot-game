from aiogram.types import InlineKeyboardMarkup

from src.keyboards.lobby import lobby_keyboard
from src.keyboards.round import LETTERS, letter_keyboard, stop_keyboard
from src.keyboards.settings import (
    ALL_CATEGORIES,
    ROUND_OPTIONS,
    TIME_OPTIONS,
    MODE_OPTIONS,
    settings_main_keyboard,
    settings_rounds_keyboard,
    settings_time_keyboard,
    settings_mode_keyboard,
    settings_cats_keyboard,
)


def test_lobby_keyboard_returns_inline_keyboard():
    markup = lobby_keyboard(game_id=1)
    assert isinstance(markup, InlineKeyboardMarkup)


def test_lobby_keyboard_has_join_button():
    markup = lobby_keyboard(game_id=1)
    buttons = markup.inline_keyboard
    join_row = buttons[0]
    assert len(join_row) == 1
    assert join_row[0].text == "🟢 Unirse a la partida"
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
    assert start_row[0].text == "▶️ Iniciar partida ahora"
    assert start_row[0].callback_data == "start:1"


def test_lobby_keyboard_game_id_in_callback():
    markup = lobby_keyboard(game_id=99, is_host=True)
    buttons = markup.inline_keyboard
    assert buttons[0][0].callback_data == "join:99"
    assert buttons[1][0].callback_data == "start:99"


# ── Round keyboards ────────────────────────────────────────────────────────────


def test_stop_keyboard_returns_inline_keyboard():
    markup = stop_keyboard(game_id=1, stop_number=1)
    assert isinstance(markup, InlineKeyboardMarkup)


def test_stop_keyboard_has_stop_button():
    markup = stop_keyboard(game_id=1, stop_number=3)
    buttons = markup.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 1
    assert buttons[0][0].text == "🛑 Stop 🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜"
    assert buttons[0][0].callback_data == "stop:1:3"


def test_stop_keyboard_different_stops():
    markup_1 = stop_keyboard(game_id=42, stop_number=1)
    assert markup_1.inline_keyboard[0][0].callback_data == "stop:42:1"
    assert markup_1.inline_keyboard[0][0].text == "🛑 Stop 🟩⬜⬜⬜⬜⬜⬜⬜⬜⬜"

    markup_10 = stop_keyboard(game_id=42, stop_number=10)
    assert markup_10.inline_keyboard[0][0].callback_data == "stop:42:10"
    assert markup_10.inline_keyboard[0][0].text == "🛑 Stop 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩"


def test_letter_keyboard_returns_inline_keyboard():
    markup = letter_keyboard(game_id=1)
    assert isinstance(markup, InlineKeyboardMarkup)


def test_letter_keyboard_has_all_letters():
    markup = letter_keyboard(game_id=1)
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(buttons) == 26
    texts = [btn.text for btn in buttons]
    for letter in LETTERS:
        assert letter in texts


def test_letter_keyboard_callback_format():
    markup = letter_keyboard(game_id=7)
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    a_button = next(btn for btn in buttons if btn.text == "A")
    assert a_button.callback_data == "letter:7:A"

    z_button = next(btn for btn in buttons if btn.text == "Z")
    assert z_button.callback_data == "letter:7:Z"


def test_letter_keyboard_rows_grouped():
    markup = letter_keyboard(game_id=1)
    rows = markup.inline_keyboard
    assert len(rows) == 4
    assert len(rows[0]) == 6
    assert len(rows[1]) == 7
    assert len(rows[2]) == 7
    assert len(rows[3]) == 6


# ── Settings keyboards ──────────────────────────────────────────────────────


def test_settings_main_keyboard_returns_inline_keyboard():
    markup = settings_main_keyboard(
        current_rounds=5, current_time=60,
        current_categories=ALL_CATEGORIES, include_n=False,
    )
    assert isinstance(markup, InlineKeyboardMarkup)


def test_settings_main_keyboard_has_all_sections():
    markup = settings_main_keyboard(
        current_rounds=10, current_time=45,
        current_categories=ALL_CATEGORIES[:4], include_n=True,
        current_mode="hybrid",
    )
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    assert any("Rondas" in t for t in texts)
    assert any("Tiempo" in t for t in texts)
    assert any("Categorias" in t for t in texts)
    assert any("Ñ" in t for t in texts)
    assert any("Híbrido" in t for t in texts)


def test_settings_main_keyboard_close_button():
    markup = settings_main_keyboard(
        current_rounds=5, current_time=60,
        current_categories=ALL_CATEGORIES, include_n=False,
    )
    last_row = markup.inline_keyboard[-1]
    assert last_row[0].callback_data == "settings_close"


def test_settings_rounds_keyboard():
    markup = settings_rounds_keyboard(current=10)
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    for opt in ROUND_OPTIONS:
        assert any(str(opt) in t and "rondas" in t for t in texts)
    assert any("Volver" in t for t in texts)


def test_settings_rounds_keyboard_selected():
    markup = settings_rounds_keyboard(current=10)
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    selected_row = [t for t in texts if "10 rondas" in t][0]
    assert "•" in selected_row


def test_settings_time_keyboard():
    markup = settings_time_keyboard(current=60)
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    for opt in TIME_OPTIONS:
        assert any(f"{opt}s" in t for t in texts)
    assert any("Volver" in t for t in texts)


def test_settings_time_keyboard_selected():
    markup = settings_time_keyboard(current=60)
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    selected_row = [t for t in texts if "60s" in t][0]
    assert "•" in selected_row


def test_settings_mode_keyboard():
    markup = settings_mode_keyboard(current="local")
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    for _, label in MODE_OPTIONS:
        assert any(label in t for t in texts)
    assert any("Volver" in t for t in texts)


def test_settings_mode_keyboard_selected():
    markup = settings_mode_keyboard(current="ai")
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    ai_row = [t for t in texts if "AI" in t][0]
    assert "•" in ai_row


def test_settings_cats_keyboard():
    markup = settings_cats_keyboard(ALL_CATEGORIES, ALL_CATEGORIES[:4])
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    for cat in ALL_CATEGORIES:
        assert any(cat in t for t in texts)
    assert any("Volver" in t for t in texts)


def test_settings_cats_keyboard_checkmarks():
    selected = ALL_CATEGORIES[:3]
    markup = settings_cats_keyboard(ALL_CATEGORIES, selected)
    texts = [btn.text for row in markup.inline_keyboard for btn in row]
    for cat in selected:
        cat_row = [t for t in texts if cat in t][0]
        assert "✅" in cat_row
    for cat in ALL_CATEGORIES[3:]:
        cat_row = [t for t in texts if cat in t][0]
        assert "⬜" in cat_row
