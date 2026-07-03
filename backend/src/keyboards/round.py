from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

LETTERS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I",
    "J", "K", "L", "M", "N", "O", "P", "Q", "R",
    "S", "T", "U", "V", "W", "X", "Y", "Z",
]


def stop_keyboard(game_id: int, stop_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⏹ Stop {stop_number}/10",
                    callback_data=f"stop:{game_id}:{stop_number}",
                )
            ]
        ]
    )


def letter_keyboard(game_id: int) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, letter in enumerate(LETTERS):
        row.append(
            InlineKeyboardButton(
                text=letter,
                callback_data=f"letter:{game_id}:{letter}",
            )
        )
        if len(row) == 6 or i == len(LETTERS) - 1:
            rows.append(row)
            row = []
    return InlineKeyboardMarkup(inline_keyboard=rows)


def inter_round_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Siguiente ronda",
                    callback_data=f"next_round:{game_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⏹ Detener partida",
                    callback_data=f"stop_game:{game_id}",
                ),
            ],
        ]
    )
