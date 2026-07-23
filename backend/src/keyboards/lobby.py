from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def lobby_keyboard(game_id: int, is_host: bool = False, in_lobby: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🟢 Unirse a la partida", callback_data=f"join:{game_id}")]
    ]
    if is_host:
        buttons.append(
            [InlineKeyboardButton(text="▶️ Iniciar partida ahora", callback_data=f"start:{game_id}")]
        )
    if in_lobby:
        buttons.append(
            [InlineKeyboardButton(text="🚪 Salir de la partida", callback_data=f"leave:{game_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def mode_selection_keyboard(host_telegram_id: int) -> InlineKeyboardMarkup:
    """Teclado de selección de modo: normal vs con evento.

    Solo el host (quien ejecutó /stop) puede usar estos botones.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎮 Modo Normal",
                    callback_data=f"mode:normal:{host_telegram_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎉 Eventos",
                    callback_data=f"mode:event:{host_telegram_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Salir",
                    callback_data=f"mode:exit:{host_telegram_id}",
                )
            ],
        ]
    )


def event_selection_keyboard(events: list[dict], host_id: int, prefix: str = "select_event") -> InlineKeyboardMarkup:
    """Lista de eventos activos para seleccionar al iniciar partida.

    Solo el host puede seleccionar un evento.
    """
    from src.services.event_rules import EventRules

    buttons = []
    for e in events:
        rules = e.get("rules")
        if not isinstance(rules, EventRules):
            rules = EventRules()
        mult = e.get("multiplier", 1.0)
        parts = [f"{e['name']} (x{mult})"]
        if rules.forced_letter:
            parts.append(f"🔤{rules.forced_letter}")
        if rules.time_override:
            parts.append(f"⏱{rules.time_override}s")
        text = " — ".join(parts)
        buttons.append(
            [InlineKeyboardButton(text=text, callback_data=f"{prefix}:{host_id}:{e['id']}")]
        )
    buttons.append(
        [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"{prefix}:{host_id}:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
