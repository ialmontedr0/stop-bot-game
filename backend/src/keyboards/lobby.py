from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def lobby_keyboard(game_id: int, is_host: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text="🟢 Unirse a la partida",
            callback_data=f"join:{game_id}"
        )]
    ]
    if is_host:
        buttons.append(
            [InlineKeyboardButton(
                text="▶️ Iniciar partida ahora",
                callback_data=f"start:{game_id}"
            )]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
