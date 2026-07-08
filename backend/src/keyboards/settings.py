from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

ALL_CATEGORIES = [
    "Nombre",
    "Apellido",
    "Color",
    "Fruta",
    "País",
    "Artista",
    "Novela/Serie",
    "Cosa",
]

ROUND_OPTIONS = [5, 10, 15]
TIME_OPTIONS = [30, 45, 60, 90]
MODE_OPTIONS = [
    ("local", "💻 Local"),
    ("ai", "🤖 AI"),
    ("hybrid", "🔀 Híbrido"),
]


def settings_main_keyboard(
    current_rounds: int,
    current_time: int,
    current_categories: list[str],
    include_n: bool,
    current_mode: str = "local",
) -> InlineKeyboardMarkup:
    mode_label = dict(MODE_OPTIONS).get(current_mode, current_mode)
    rows = [
        [
            InlineKeyboardButton(
                text=f"🎯 Rondas: {current_rounds}", callback_data="settings_rondas"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"⏱  Tiempo: {current_time}s", callback_data="settings_tiempo"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"📋 Categorias ({len(current_categories)}/{len(ALL_CATEGORIES)})",
                callback_data="settings_cats",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🔤 Ñ: {'Si' if include_n else 'No'}", callback_data="toggle_n"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"⚡ Modo: {mode_label}", callback_data="settings_mode"
            )
        ],
        [InlineKeyboardButton(text="🔙 Cerrar", callback_data="settings_close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_rounds_keyboard(current: int) -> InlineKeyboardMarkup:
    rows = []
    for opt in ROUND_OPTIONS:
        selected = "• " if opt == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{selected}{opt} rondas",
                    callback_data=f"set_rondas:{opt}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🔙 Volver", callback_data="settings_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_time_keyboard(current: int) -> InlineKeyboardMarkup:
    rows = []
    for opt in TIME_OPTIONS:
        selected = "• " if opt == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{selected}{opt}s",
                    callback_data=f"set_tiempo:{opt}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🔙 Volver", callback_data="settings_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_mode_keyboard(current: str) -> InlineKeyboardMarkup:
    rows = []
    for value, label in MODE_OPTIONS:
        selected = "• " if value == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{selected}{label}",
                    callback_data=f"set_mode:{value}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🔙 Volver", callback_data="settings_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_cats_keyboard(
    all_cats: list[str], selected_cats: list[str]
) -> InlineKeyboardMarkup:
    rows = []
    for cat in all_cats:
        checked = "✅ " if cat in selected_cats else "⬜ "
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{checked}{cat}",
                    callback_data=f"toggle_cat:{cat}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🔙 Volver", callback_data="settings_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
