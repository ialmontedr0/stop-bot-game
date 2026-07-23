from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.keyboards.settings import ALL_CATEGORIES

_DAYS_MAP = [
    ("mon", "L"),
    ("tue", "M"),
    ("wed", "X"),
    ("thu", "J"),
    ("fri", "V"),
    ("sat", "S"),
    ("sun", "D"),
]

_BONUS_CYCLES = {
    "no_duplicates_bonus": [0, 15, 25, 50, 100],
    "bonus_all_filled": [0, 25, 50, 75, 100],
    "speed_bonus": [0, 10, 20, 30, 50],
    "penalty_empty": [0, -5, -10, -15, -20],
    "streak_multiplier": [1.0, 1.25, 1.5, 2.0],
    "comeback_bonus": [0, 10, 20, 30],
}


def groups_keyboard(groups: list[dict], prefix: str) -> InlineKeyboardMarkup:
    """Teclado de selección de grupo"""
    buttons = []
    for g in groups:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"📌 {g['chat_title']}",
                    callback_data=f"{prefix}:group:{g['chat_id']}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="❌ Cancelar", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def event_type_keyboard() -> InlineKeyboardMarkup:
    """Teclado de selección de tipo de evento"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Temporal",
                    callback_data="ne:type:one_time",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Diario Recurrente",
                    callback_data="ne:type:daily_recurring",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="♾ Permanente",
                    callback_data="ne:type:permanent",
                ),
            ],
        ]
    )


def multiplier_keyboard(prefix: str = "event") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="x1.0", callback_data=f"{prefix}:mult:1.0"),
                InlineKeyboardButton(text="x1.5", callback_data=f"{prefix}:mult:1.5"),
            ],
            [
                InlineKeyboardButton(text="x2", callback_data=f"{prefix}:mult:2.0"),
                InlineKeyboardButton(text="x3", callback_data=f"{prefix}:mult:3.0"),
            ],
            [
                InlineKeyboardButton(text="x5", callback_data=f"{prefix}:mult:5.0"),
            ],
        ]
    )


def duration_keyboard(prefix: str = "event") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 hora", callback_data=f"{prefix}:dur:1"),
                InlineKeyboardButton(text="6 horas", callback_data=f"{prefix}:dur:6"),
                InlineKeyboardButton(text="12 horas", callback_data=f"{prefix}:dur:12"),
            ],
            [
                InlineKeyboardButton(text="24 horas", callback_data=f"{prefix}:dur:24"),
                InlineKeyboardButton(text="3 días", callback_data=f"{prefix}:dur:72"),
                InlineKeyboardButton(text="7 días", callback_data=f"{prefix}:dur:168"),
            ],
        ]
    )


def daily_start_keyboard(prefix: str = "ne") -> InlineKeyboardMarkup:
    """Teclado de horas de inicio para evento diario"""
    hours = ["00:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=h,
                    callback_data=f"{prefix}:dstart:{h}",
                )
                for h in hours[:4]
            ],
            [
                InlineKeyboardButton(
                    text=h,
                    callback_data=f"{prefix}:dstart:{h}",
                )
                for h in hours[4:]
            ],
        ]
    )


def daily_end_keyboard(prefix: str = "ne") -> InlineKeyboardMarkup:
    """Teclado de horas de fin para evento diario"""
    hours = ["20:00", "21:00", "22:00", "23:00", "00:00", "02:00"]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=h,
                    callback_data=f"{prefix}:dend:{h}",
                )
                for h in hours[:3]
            ],
            [
                InlineKeyboardButton(
                    text=h,
                    callback_data=f"{prefix}:dend:{h}",
                )
                for h in hours[3:]
            ],
        ]
    )


def days_of_week_keyboard(
    active_days: list[str],
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Toggle de días de la semana"""
    row1 = []
    row2 = []
    for i, (key, label) in enumerate(_DAYS_MAP):
        is_active = key in active_days
        icon = "✅" if is_active else "—"
        btn = InlineKeyboardButton(
            text=f"{label} {icon}",
            callback_data=f"{prefix}:day:{key}",
        )
        if i < 4:
            row1.append(btn)
        else:
            row2.append(btn)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            row1,
            row2,
            [
                InlineKeyboardButton(
                    text="✅ Confirmar días",
                    callback_data=f"{prefix}:days_confirm",
                )
            ],
        ]
    )


def categories_toggle_keyboard(
    enabled_categories: list[str],
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Toggle de categorías activas para el evento"""
    rows = []
    row = []
    for i, cat in enumerate(ALL_CATEGORIES):
        icon = "✅" if cat in enabled_categories else "⬜"
        row.append(
            InlineKeyboardButton(
                text=f"{icon} {cat}",
                callback_data=f"{prefix}:cat:{cat}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                text="⏭ Todas",
                callback_data=f"{prefix}:cat_all",
            ),
            InlineKeyboardButton(
                text="▶️ Siguiente",
                callback_data=f"{prefix}:rules_next",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def categories_options_keyboard(
    hidden_categories: list[str],
    mystery_category: str | None,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de opciones avanzadas de categorías: oculta y mystery.

    - hidden_categories: lista de categorías ocultas (ej: ["Cosa"])
    - mystery_category: una sola categoría mystery o None
    - prefix: prefijo del callback (ne=newevent, ee=editevent)
    """
    rows = []

    row = []
    for i, cat in enumerate(ALL_CATEGORIES):
        icons = []
        if cat in hidden_categories:
            icons.append("🎭")
        if mystery_category == cat:
            icons.append("🔮")
        icon_str = "".join(icons) if icons else "⬜"

        row.append(
            InlineKeyboardButton(
                text=f"{icon_str} {cat}",
                callback_data=f"{prefix}:cat_hidden:{cat}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                text=f"🔮 Mystery: {mystery_category or 'Ninguna'}",
                callback_data=f"{prefix}:cat_mystery:{mystery_category or 'none'}",
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="▶️ Siguiente",
                callback_data=f"{prefix}:options_next",
            ),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def round_time_keyboard(
    current_time_override: int | None,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de selección de tiempo de ronda"""
    options = [15, 30, 45, 60, 90]
    row1 = [
        InlineKeyboardButton(
            text=f"⚙️ Config grupo",
            callback_data=f"{prefix}:time:0",
        ),
    ]
    row2 = []
    for t in options:
        selected = "• " if current_time_override == t else ""
        row2.append(
            InlineKeyboardButton(
                text=f"{selected}{t}s",
                callback_data=f"{prefix}:time:{t}",
            )
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row1,
            row2[:3],
            row2[3:],
        ]
    )


def decreasing_time_keyboard(
    amount: int,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de selección de decremento por ronda"""
    options = [3, 5, 7, 10]
    row = []
    for a in options:
        selected = "• " if amount == a else ""
        row.append(
            InlineKeyboardButton(
                text=f"{selected}-{a}s",
                callback_data=f"{prefix}:dec:{a}",
            )
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [
                InlineKeyboardButton(
                    text="✅ Confirmar decreciente",
                    callback_data=f"{prefix}:dec_confirm",
                )
            ],
        ]
    )


def forced_letter_keyboard(
    include_n: bool = False,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de selección de letra forzada"""
    letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if include_n:
        letters.insert(letters.index("N") + 1, "Ñ")

    # Agrupar en filas de 6, 7, 7, 7
    row_sizes = [6, 7, 7, 7]
    rows = []
    start = 0
    for size in row_sizes:
        chunk = letters[start : start + size]
        if not chunk:
            break
        rows.append(
            [
                InlineKeyboardButton(
                    text=letter,
                    callback_data=f"{prefix}:letter:{letter}",
                )
                for letter in chunk
            ]
        )
        start += size

    # Fila de opciones especiales
    rows.append(
        [
            InlineKeyboardButton(
                text="⏭ Aleatoria",
                callback_data=f"{prefix}:letter:RANDOM",
            ),
            InlineKeyboardButton(
                text="🚫 Excluir vocal",
                callback_data=f"{prefix}:letter:EXCLUDE_VOWELS",
            ),
            InlineKeyboardButton(
                text="📜 Secuencia",
                callback_data=f"{prefix}:letter:SEQUENCE",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bonuses_keyboard(
    rules_data: dict,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de bonificaciones y penalizaciones"""

    def _fmt_bonus(key: str, value) -> str:
        """Formatea el valor del bonus para el botón."""
        if key == "streak_multiplier":
            return f"x{value}"
        if key == "penalty_empty":
            return str(value) if value != 0 else "0"
        return f"+{value}" if value > 0 else str(value)

    def _next_value(key: str, current):
        """Retorna el siguiente valor en el ciclo."""
        cycle = _BONUS_CYCLES.get(key, [0])
        try:
            idx = cycle.index(current)
            return cycle[(idx + 1) % len(cycle)]
        except ValueError:
            return cycle[0]

    rows = []

    # Fila 1: Bonus respuesta única + Bonus llenar todo
    rows.append(
        [
            InlineKeyboardButton(
                text=f"Bonus única: {_fmt_bonus('no_duplicates_bonus', rules_data.get('no_duplicates_bonus', 0))}",
                callback_data=f"{prefix}:bonus:no_duplicates_bonus",
            ),
            InlineKeyboardButton(
                text=f"Bonus todo: {_fmt_bonus('bonus_all_filled', rules_data.get('bonus_all_filled', 0))}",
                callback_data=f"{prefix}:bonus:bonus_all_filled",
            ),
        ]
    )

    # Fila 2: Bonus velocidad + Penalización vacío
    rows.append(
        [
            InlineKeyboardButton(
                text=f"Velocidad: {_fmt_bonus('speed_bonus', rules_data.get('speed_bonus', 0))}",
                callback_data=f"{prefix}:bonus:speed_bonus",
            ),
            InlineKeyboardButton(
                text=f"Pen vacío: {_fmt_bonus('penalty_empty', rules_data.get('penalty_empty', 0))}",
                callback_data=f"{prefix}:bonus:penalty_empty",
            ),
        ]
    )

    # Fila 3: Streak multiplier + Doble última ronda
    double_val = rules_data.get("double_points_last_round", False)
    rows.append(
        [
            InlineKeyboardButton(
                text=f"Streak: {_fmt_bonus('streak_multiplier', rules_data.get('streak_multiplier', 1.0))}",
                callback_data=f"{prefix}:bonus:streak_multiplier",
            ),
            InlineKeyboardButton(
                text=f"Doble última: {'ON' if double_val else 'OFF'}",
                callback_data=f"{prefix}:bonus:double_points_last_round",
            ),
        ]
    )

    # Fila 4: Comeback bonus + Reveal
    reveal_val = rules_data.get("answer_reveal", False)
    rows.append(
        [
            InlineKeyboardButton(
                text=f"Comeback: {_fmt_bonus('comeback_bonus', rules_data.get('comeback_bonus', 0))}",
                callback_data=f"{prefix}:bonus:comeback_bonus",
            ),
            InlineKeyboardButton(
                text=f"Reveal: {'ON' if reveal_val else 'OFF'}",
                callback_data=f"{prefix}:bonus:answer_reveal",
            ),
        ]
    )

    # Fila 5: Siguiente
    rows.append(
        [
            InlineKeyboardButton(
                text="▶️ Siguiente",
                callback_data=f"{prefix}:bonus_next",
            ),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_event_keyboard(prefix: str = "ne") -> InlineKeyboardMarkup:
    """Teclado de confirmación de evento"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Confirmar",
                    callback_data=f"{prefix}:confirm",
                ),
                InlineKeyboardButton(
                    text="✏️ Editar",
                    callback_data=f"{prefix}:edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data=f"{prefix}:cancel",
                ),
            ],
        ]
    )


def delete_action_keyboard() -> InlineKeyboardMarkup:
    """Teclado para elegir entre desactivar o eliminar permanentemente"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛑 Desactivar",
                    callback_data="delevent:action:deactivate",
                ),
                InlineKeyboardButton(
                    text="🗑 Eliminar",
                    callback_data="delevent:action:delete",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Volver",
                    callback_data="delevent:back",
                ),
                InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data="delevent:cancel",
                ),
            ],
        ]
    )


def confirm_delete_keyboard() -> InlineKeyboardMarkup:
    """Teclado de confirmación de eliminación permanente"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Sí, eliminar permanentemente",
                    callback_data="delevent:confirm_delete",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Volver",
                    callback_data="delevent:back",
                ),
                InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data="delevent:cancel",
                ),
            ],
        ]
    )


def delete_all_confirm_keyboard() -> InlineKeyboardMarkup:
    """Teclado de confirmación para borrar TODOS los eventos"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Sí, eliminar TODOS los eventos",
                    callback_data="delevtall:confirm",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data="delevtall:cancel",
                ),
            ],
        ]
    )


def events_list_keyboard(events: list[dict], prefix: str = "delevent") -> InlineKeyboardMarkup:
    """Teclado de eventos para borrar"""
    from datetime import datetime

    buttons = []
    for e in events:
        if e.get("ends_at") is not None:
            ends = (
                e["ends_at"]
                if isinstance(e["ends_at"], datetime)
                else datetime.fromisoformat(e["ends_at"])
            )
            remaining = ends - datetime.utcnow()
            hours = remaining.total_seconds() / 3600
            if hours >= 24:
                time_str = f"{int(hours // 24)}d"
            else:
                time_str = f"{int(hours)}h"
        else:
            time_str = "∞"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"❌ {e['name']} (x{e['multiplier']} — {time_str})",
                    callback_data=f"{prefix}:event:{e['id']}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(text="◀️ Volver", callback_data=f"{prefix}:back"),
            InlineKeyboardButton(text="❌ Cancelar", callback_data=f"{prefix}:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def event_list_manage_keyboard(
    events: list[dict], prefix: str = "toggleevt"
) -> InlineKeyboardMarkup:
    """Lista de eventos con toggle pausar/reanudar"""
    buttons = []
    for e in events:
        status = "🟢" if not e.get("is_paused") else "⏸"
        action = "Pausar" if not e.get("is_paused") else "Reanudar"
        event_type_icon = {
            "one_time": "🔄",
            "daily_recurring": "🔁",
            "permanent": "♾",
        }.get(e.get("event_type", "one_time"), "🔄")
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {event_type_icon} {e['name']} (x{e['multiplier']})",
                    callback_data=f"{prefix}:toggle:{e['id']}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(text="❌ Cancelar", callback_data=f"{prefix}:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def edit_event_field_keyboard() -> InlineKeyboardMarkup:
    """Menú de campos editables"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Nombre", callback_data="editevent:field:name"),
                InlineKeyboardButton(
                    text="📄 Descripción", callback_data="editevent:field:description"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚡ Multiplicador",
                    callback_data="editevent:field:multiplier",
                ),
                InlineKeyboardButton(
                    text="📅 Tipo/Horario",
                    callback_data="editevent:field:schedule",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📋 Categorías",
                    callback_data="editevent:field:categories",
                ),
                InlineKeyboardButton(
                    text="⚡ Mult. categorías",
                    callback_data="editevent:field:cat_multipliers",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⏱ Tiempo/Letra",
                    callback_data="editevent:field:time_letter",
                ),
                InlineKeyboardButton(
                    text="🔇 Letras excluidas",
                    callback_data="editevent:field:excluded_letters",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Bonificaciones",
                    callback_data="editevent:field:scoring",
                ),
                InlineKeyboardButton(
                    text="🎮 Modo juego",
                    callback_data="editevent:field:game_mode",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Guardar y salir",
                    callback_data="editevent:save",
                ),
            ],
        ]
    )


def events_edit_list_keyboard(
    events: list[dict], prefix: str = "editevent"
) -> InlineKeyboardMarkup:
    """Teclado de eventos para editar"""
    from datetime import datetime

    buttons = []
    for e in events:
        if e.get("ends_at") is not None:
            ends = (
                e["ends_at"]
                if isinstance(e["ends_at"], datetime)
                else datetime.fromisoformat(str(e["ends_at"]))
            )
            remaining = ends - datetime.utcnow()
            hours = remaining.total_seconds() / 3600
            if hours >= 24:
                time_str = f"{int(hours // 24)}d"
            else:
                time_str = f"{int(hours)}h"
        else:
            time_str = "∞"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {e['name']} (x{e['multiplier']} — {time_str})",
                    callback_data=f"{prefix}:event:{e['id']}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(text="❌ Cancelar", callback_data=f"{prefix}:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def event_status_keyboard(
    events: list[dict], prefix: str = "toggleevt"
) -> InlineKeyboardMarkup:
    """Lista de eventos — cada evento ocupa UNA fila, toggle al click.

    Estados visuales:
        🟢 = activo y dentro del horario
        ⏸ = pausado por el admin
        🔴 = no pausado pero fuera del horario configurado
    """
    buttons = []
    for e in events:
        is_paused = e.get("is_paused", False)
        is_now_active = e.get("is_now_active", True)
        event_type = e.get("event_type", "one_time")

        if is_paused:
            status_icon = "⏸"
        elif not is_now_active:
            status_icon = "🔴"
        else:
            status_icon = "🟢"

        type_icon = {
            "one_time": "🔄",
            "daily_recurring": "🔁",
            "permanent": "♾",
        }.get(event_type, "🔄")

        if is_paused:
            action_icon = "▶️ Reanudar"
        elif not is_now_active:
            action_icon = "⏰ Fuera de horario"
        else:
            action_icon = "⏸ Pausar"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{status_icon} {type_icon} {e['name']} (x{e['multiplier']}) — {action_icon}",
                    callback_data=f"{prefix}:toggle:{e['id']}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text="❌ Cancelar", callback_data=f"{prefix}:cancel"
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Nuevos teclados Fase 6c, 7d, 8b ─────────────────────────────

_MULT_CYCLES = [None, 1.5, 2.0, 3.0, 5.0]


def category_multipliers_keyboard(
    current_mults: dict[str, float],
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Toggle de multiplicadores por categoría.

    Cada botón rota por: OFF, x1.5, x2, x3, x5
    """
    rows = []
    row = []
    for i, cat in enumerate(ALL_CATEGORIES):
        val = current_mults.get(cat)
        label = f"x{val}" if val else "x1"
        row.append(
            InlineKeyboardButton(
                text=f"{cat[:6]}: {label}",
                callback_data=f"{prefix}:catmult:{cat}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                text="▶️ Siguiente",
                callback_data=f"{prefix}:catmult_next",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


_ALPHABET_LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZÑ")


def excluded_letters_keyboard(
    excluded: list[str],
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Toggle de letras excluidas."""
    rows = []
    # 6 por fila
    chunk_size = 6
    for start in range(0, len(_ALPHABET_LETTERS), chunk_size):
        chunk = _ALPHABET_LETTERS[start : start + chunk_size]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'🔇' if l in excluded else l}",
                    callback_data=f"{prefix}:excl:{l}",
                )
                for l in chunk
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="📜 Secuencia personalizada",
                callback_data=f"{prefix}:letter_seq",
            ),
            InlineKeyboardButton(
                text="▶️ Siguiente",
                callback_data=f"{prefix}:excl_next",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def letter_sequence_keyboard(
    current_seq: list[str] | None,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado para configurar secuencia de letras o volver."""
    seq_label = ",".join(current_seq) if current_seq else "Ninguna"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📜 Secuencia: {seq_label}",
                    callback_data=f"{prefix}:seq_edit",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Limpiar secuencia",
                    callback_data=f"{prefix}:seq_clear",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="▶️ Siguiente",
                    callback_data=f"{prefix}:seq_next",
                ),
            ],
        ]
    )


def game_mode_keyboard(
    rules_data: dict,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de configuración de modo de juego.

    Incluye: sudden_death, wager, collaborative, infinite_rounds,
    no_stop, min_words_required, min_word_length, require_all_different,
    shared_answer_penalty, perfect_round_bonus, elimination_rounds.
    """
    sd = rules_data.get("sudden_death", False)
    wager = rules_data.get("wager_enabled", False)
    collab = rules_data.get("collaborative", False)
    infinite = rules_data.get("infinite_rounds", False)
    no_stop = rules_data.get("no_stop", False)
    all_diff = rules_data.get("require_all_different", False)
    min_words = rules_data.get("min_words_required", 0)
    min_len = rules_data.get("min_word_length", 0)
    shared = rules_data.get("shared_answer_penalty", 0)
    perfect = rules_data.get("perfect_round_bonus", 0)

    def _b(label: str, val, callback: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=f"{label}: {val}", callback_data=f"{prefix}:{callback}")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b("💀 Muerte súbita", "ON" if sd else "OFF", f"gm_toggle_sudden")],
            [
                _b("🎲 Apuestas", "ON" if wager else "OFF", "gm_toggle_wager"),
                _b("👥 Equipos", "ON" if collab else "OFF", "gm_toggle_collab"),
            ],
            [
                _b("♾ Rondas infinitas", "ON" if infinite else "OFF", "gm_toggle_infinite"),
                _b("🚫 No Stop", "ON" if no_stop else "OFF", "gm_toggle_nostop"),
            ],
            [
                _b("🚫 Todas diferentes", "ON" if all_diff else "OFF", "gm_toggle_alldiff"),
                _b("📝 Palabras mín", str(min_words), "gm_cycle_minwords"),
            ],
            [
                _b("📏 Longitud mín", str(min_len), "gm_cycle_minlen"),
                _b("🤝 Penalización dup", str(shared), "gm_cycle_shared"),
            ],
            [
                InlineKeyboardButton(
                    text=f"⭐ Ronda perfecta: {perfect}",
                    callback_data=f"{prefix}:gm_cycle_perfect",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="▶️ Siguiente",
                    callback_data=f"{prefix}:gm_next",
                ),
            ],
        ]
    )


def save_event_keyboard(prefix: str = "editevent") -> InlineKeyboardMarkup:
    """Teclado de guardado para edición de eventos"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Guardar cambios",
                    callback_data=f"{prefix}:save",
                ),
                InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data=f"{prefix}:cancel",
                ),
            ],
        ]
    )


