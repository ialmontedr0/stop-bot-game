from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

LETTERS = [
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "I",
    "J",
    "K",
    "L",
    "M",
    "N",
    "O",
    "P",
    "Q",
    "R",
    "S",
    "T",
    "U",
    "V",
    "W",
    "X",
    "Y",
    "Z",
]


def stop_keyboard(game_id: int, stop_number: int) -> InlineKeyboardMarkup:
    filled = "🟩" * stop_number
    empty = "⬜" * (10 - stop_number)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🛑 Stop {filled}{empty}",
                    callback_data=f"stop:{game_id}:{stop_number}",
                )
            ]
        ]
    )


def letter_keyboard(game_id: int, include_n: bool = False) -> InlineKeyboardMarkup:
    letters = list(LETTERS)
    if include_n:
        idx = letters.index("N") + 1
        letters.insert(idx, "Ñ")

    row_sizes = [6, 7, 7, 7]
    keyboard = []
    start = 0
    for size in row_sizes:
        chunk = letters[start : start + size]
        if not chunk:
            break
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=letter,
                    callback_data=f"letter:{game_id}:{letter}",
                )
                for letter in chunk
            ]
        )
        start += size
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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
