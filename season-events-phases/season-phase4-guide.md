# Fase 4: `event_creator.py` — Reescritura del FSM de creación

## Resumen
Reescritura completa del flujo FSM de `/newevent` (10 pasos) + `/deleteevent` existente.
También se reescribe `keyboards/event.py` con todos los teclados necesarios.

---

## Archivos a modificar

| Archivo | Acción | ~Líneas |
|---|---|---|
| `src/keyboards/event.py` | **Reescribir** | ~250 |
| `src/handlers/admin/event_creator.py` | **Reescribir** | ~750 |

**No crear archivos nuevos.** Solo reescribir estos dos.

---

## PARTE 1: `src/keyboards/event.py` — Teclados

Este archivo contiene TODOS los teclados inline para los flujos de creación, edición y gestión de eventos.
Los callbacks usan prefijo `ne:` para `/newevent`, `delevent:` para `/deleteevent`, `editevent:` para `/editevent`, `toggleevt:` para `/toggleevent`.

### Imports y constantes

```python
"""Teclados inline para creación, edición y gestión de eventos."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.keyboards.settings import ALL_CATEGORIES
```

### 1.1 — `groups_keyboard(groups, prefix)`

Seleccionar grupo. **Ya existe, sin cambios.**

```python
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
    buttons.append(
        [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"{prefix}:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

### 1.2 — `event_type_keyboard()`

Selección de tipo de evento (Paso 1).

```python
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
```

### 1.3 — `multiplier_keyboard(prefix)`

Selección de multiplicador (Paso 4). **Ya existe, sin cambios.**

```python
def multiplier_keyboard(prefix: str = "event") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="x1.5", callback_data=f"{prefix}:mult:1.5"),
                InlineKeyboardButton(text="x2", callback_data=f"{prefix}:mult:2.0"),
            ],
            [
                InlineKeyboardButton(text="x3", callback_data=f"{prefix}:mult:3.0"),
                InlineKeyboardButton(text="x5", callback_data=f"{prefix}:mult:5.0"),
            ],
        ]
    )
```

### 1.4 — `duration_keyboard(prefix)`

Duración para one_time (Paso 5a). **Ya existe, sin cambios.**

```python
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
```

### 1.5 — `daily_start_keyboard(prefix)`

Horas de inicio para daily_recurring (Paso 5b-1).

```python
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
```

### 1.6 — `daily_end_keyboard(prefix)`

Horas de fin para daily_recurring (Paso 5b-2).

```python
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
```

### 1.7 — `days_of_week_keyboard(active_days, prefix)`

Toggle de días de semana (Paso 5b-3).

**Estructura:** `active_days` es una lista de strings como `["mon","tue","wed","thu","fri"]`.
El teclado muestra 7 botones (uno por día) con ✅ si está activo, — si no.
Un botón de "✅ Confirmar días" al final.

```python
_DAYS_MAP = [
    ("mon", "L"),
    ("tue", "M"),
    ("wed", "X"),
    ("thu", "J"),
    ("fri", "V"),
    ("sat", "S"),
    ("sun", "D"),
]


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
```

### 1.8 — `categories_toggle_keyboard(enabled_categories, prefix)`

Toggle de categorías activas + "Ocultar" + "Mystery" + "Todas" + "Siguiente" (Paso 6).

```python
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
```

### 1.9 — `categories_options_keyboard(hidden_categories, mystery_category, prefix)`

Selección de categorías ocultas y mystery (Paso 6 avanzado).

```python
def categories_options_keyboard(
    hidden_categories: list[str],
    mystery_category: str | None,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de opciones avanzadas de categorías"""
    rows = []
    for cat in ALL_CATEGORIES:
        hidden_icon = "🎭" if cat in hidden_categories else "  "
        mystery_icon = "🔮" if mystery_category == cat else "  "
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{hidden_icon} Ocultar: {cat}",
                    callback_data=f"{prefix}:cat_hidden:{cat}",
                ),
                InlineKeyboardButton(
                    text=f"{mystery_icon} Mystery: {cat}",
                    callback_data=f"{prefix}:cat_mystery:{cat}",
                ),
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
```

### 1.10 — `round_time_keyboard(current_time_override, prefix)`

Selección de tiempo por ronda (Paso 7).

```python
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
```

### 1.11 — `decreasing_time_keyboard(amount, prefix)`

Cantidad de decreciente (Paso 7 sub-step).

```python
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
```

### 1.12 — `forced_letter_keyboard(include_n, prefix)`

Selección de letra (Paso 7 sub-step).

```python
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
```

### 1.13 — `bonuses_keyboard(rules_data, prefix)`

Toggle de bonificaciones (Paso 8).

`rules_data` es un dict con los valores actuales de las reglas de scoring.

```python
_BONUS_CYCLES = {
    "no_duplicates_bonus": [0, 15, 25, 50, 100],
    "bonus_all_filled": [0, 25, 50, 75, 100],
    "speed_bonus": [0, 10, 20, 30, 50],
    "penalty_empty": [0, -5, -10, -15, -20],
    "streak_multiplier": [1.0, 1.25, 1.5, 2.0],
    "comeback_bonus": [0, 10, 20, 30],
}


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
```

### 1.14 — `confirm_event_keyboard(prefix)`

Confirmación / Cancelar / Editar (Paso 9). **Modificado para incluir "Editar".**

```python
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
```

### 1.15 — `events_list_keyboard(events, prefix)`

Lista de eventos para `/deleteevent`. **Ya existe, sin cambios.**

```python
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
```

### 1.16 — `event_list_manage_keyboard(events, prefix)`

Lista de eventos para `/toggleevent` (Paso futuro, Phase 5).

```python
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
            InlineKeyboardButton(
                text="❌ Cancelar", callback_data=f"{prefix}:cancel"
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

### 1.17 — `edit_event_field_keyboard()`

Campos editables para `/editevent` (Paso futuro, Phase 5).

```python
def edit_event_field_keyboard() -> InlineKeyboardMarkup:
    """Menú de campos editables"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Nombre", callback_data="editevent:field:name"
                ),
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
                    text="⏱ Tiempo/Letra",
                    callback_data="editevent:field:time_letter",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Bonificaciones",
                    callback_data="editevent:field:scoring",
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
```

---

## PARTE 2: `src/handlers/admin/event_creator.py` — FSM Completo

### Imports y setup

```python
"""Flujo FSM para crear/borrar eventos — solo chat privado"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.core.text_utils import utcnow
from src.db.engine import async_session_factory
from src.db.models import SeasonalEvent
from src.keyboards.event import (
    bonuses_keyboard,
    categories_options_keyboard,
    categories_toggle_keyboard,
    confirm_event_keyboard,
    daily_end_keyboard,
    daily_start_keyboard,
    days_of_week_keyboard,
    decreasing_time_keyboard,
    duration_keyboard,
    event_type_keyboard,
    events_list_keyboard,
    forced_letter_keyboard,
    groups_keyboard,
    multiplier_keyboard,
    round_time_keyboard,
)
from src.services.event_rules import EventRules
from src.services.event_service import event_service

logger = logging.getLogger(__name__)

event_creator_router = Router()
```

### FSM States

```python
class NewEventState(StatesGroup):
    # Sección 1: Información básica
    select_group = State()
    event_type = State()
    name = State()
    description = State()
    multiplier = State()

    # Sección 2: Horario
    schedule_one_time = State()
    schedule_daily_hours = State()
    schedule_daily_days = State()

    # Sección 3: Reglas (opcional, con skip)
    rules_categories = State()
    rules_categories_options = State()
    rules_time_and_letter = State()
    rules_decreasing = State()
    rules_scoring = State()

    # Paso 9
    confirm = State()


class DeleteEventState(StatesGroup):
    select_group = State()
    select_event = State()
    confirm = State()
```

### Helper: `is_private_chat(message_or_callback)`

```python
def _is_private_chat(target) -> bool:
    """Verifica si el mensaje/callback es chat privado."""
    if isinstance(target, Message):
        return target.chat and target.chat.type == "private"
    if isinstance(target, CallbackQuery):
        if target.message:
            return target.message.chat and target.message.chat.type == "private"
    return False
```

### Helper: `build_summary_text(data, step=None)`

Construye el texto de resumen del evento para cada paso.

```python
_TYPE_LABELS = {
    "one_time": "🔄 Temporal",
    "daily_recurring": "🔁 Diario Recurrente",
    "permanent": "♾ Permanente",
}


def _build_summary_text(data: dict, step: int | None = None) -> str:
    """Construye el texto de resumen del estado actual del evento.

    step: Número de paso actual (1-8). Si None, no muestra el número.
    """
    lines = []

    # Grupo y tipo
    if "group_title" in data:
        lines.append(f"✅ Grupo: <b>{data['group_title']}</b>")
    if "event_type" in data:
        lines.append(f"✅ Tipo: <b>{_TYPE_LABELS.get(data['event_type'], data['event_type'])}</b>")

    # Nombre
    if "name" in data:
        lines.append(f"✅ Nombre: <b>{data['name']}</b>")

    # Descripción
    if "description" in data:
        lines.append(f"✅ Descripción: <b>{data['description']}</b>")

    # Multiplicador
    if "multiplier" in data:
        lines.append(f"✅ Multiplicador: <b>x{data['multiplier']}</b>")

    # Horario
    if data.get("event_type") == "one_time" and "duration_hours" in data:
        hours = data["duration_hours"]
        if hours == 1:
            dur_label = "1 hora"
        elif hours < 24:
            dur_label = f"{hours} horas"
        elif hours % 24 == 0:
            dur_label = f"{hours // 24} días"
        else:
            dur_label = f"{hours}h"
        lines.append(f"✅ Duración: <b>{dur_label}</b>")

    if data.get("event_type") == "daily_recurring":
        start_h = data.get("daily_start_hour", "?")
        start_m = data.get("daily_start_minute", 0)
        end_h = data.get("daily_end_hour", "?")
        end_m = data.get("daily_end_minute", 0)
        if start_h != "?" and end_h != "?":
            lines.append(
                f"✅ Horario: <b>{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}</b>"
            )
        active_days = data.get("active_days", [])
        if active_days:
            day_names = {
                "mon": "L", "tue": "M", "wed": "X",
                "thu": "J", "fri": "V", "sat": "S", "sun": "D",
            }
            day_str = " ".join(day_names.get(d, d) for d in active_days)
            lines.append(f"✅ Días: <b>{day_str}</b>")

    if data.get("event_type") == "permanent":
        lines.append("✅ Duración: <b>Permanente</b>")

    return "\n".join(lines)
```

### Helper: `build_full_summary_text(data)`

Construye el texto completo del Paso 9 (confirmación).

```python
def _build_full_summary_text(data: dict) -> str:
    """Construye el texto completo de resumen para el Paso 9."""
    lines = []
    lines.append("✅ <b>Resumen del Evento</b>")
    lines.append("")

    # Información básica
    lines.append(f"📌 <b>{data.get('name', 'Sin nombre')}</b>")
    lines.append(f"📝 {data.get('description', 'Sin descripción')}")

    event_type = data.get("event_type", "one_time")
    type_label = _TYPE_LABELS.get(event_type, event_type)

    if event_type == "one_time":
        hours = data.get("duration_hours", 1)
        if hours == 1:
            dur = "1 hora"
        elif hours < 24:
            dur = f"{hours} horas"
        elif hours % 24 == 0:
            dur = f"{hours // 24} días"
        else:
            dur = f"{hours}h"
        lines.append(f"📅 Tipo: <b>{type_label}</b> — {dur}")
    elif event_type == "daily_recurring":
        start_h = data.get("daily_start_hour", 0)
        start_m = data.get("daily_start_minute", 0)
        end_h = data.get("daily_end_hour", 23)
        end_m = data.get("daily_end_minute", 59)
        lines.append(
            f"📅 Tipo: <b>{type_label}</b> — {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"
        )
        active_days = data.get("active_days", ["mon", "tue", "wed", "thu", "fri"])
        day_names = {
            "mon": "Lun", "tue": "Mar", "wed": "Mié",
            "thu": "Jue", "fri": "Vie", "sat": "Sáb", "sun": "Dom",
        }
        day_str = ", ".join(day_names.get(d, d) for d in active_days)
        lines.append(f"📅 Días: <b>{day_str}</b>")
    else:
        lines.append(f"📅 Tipo: <b>{type_label}</b>")

    lines.append(f"⚡ Multiplicador: <b>x{data.get('multiplier', 1.0)}</b>")
    lines.append("")

    # Categorías
    rules_data = data.get("rules_data", {})
    enabled = rules_data.get("categories_enabled", list(EventRules().categories_enabled))
    disabled = rules_data.get("categories_disabled", [])
    hidden = rules_data.get("hidden_categories", [])
    mystery = rules_data.get("mystery_category")

    active_cats = [c for c in enabled if c not in disabled]
    if active_cats:
        lines.append(f"📋 <b>Categorías activas:</b> {', '.join(active_cats)}")

    if disabled:
        lines.append(f"🚫 <b>Sin:</b> {', '.join(disabled)}")
    if hidden:
        lines.append(f"🎭 <b>Oculta:</b> {', '.join(hidden)}")
    if mystery:
        lines.append(f"🔮 <b>Mystery:</b> {mystery}")
    lines.append("")

    # Tiempo y letra
    time_override = rules_data.get("time_override")
    if time_override:
        lines.append(f"⏱ <b>Tiempo:</b> {time_override}s por ronda")
    else:
        lines.append("⏱ <b>Tiempo:</b> Config del grupo")

    if rules_data.get("time_decreasing"):
        dec_amount = rules_data.get("time_decreasing_amount", 5)
        lines.append(f"📉 <b>Decreciente:</b> -{dec_amount}s por ronda")

    forced_letter = rules_data.get("forced_letter")
    vowel_forced = rules_data.get("vowel_forced", False)
    letter_seq = rules_data.get("letter_sequence")

    if letter_seq:
        lines.append(f"🔤 <b>Letra:</b> Secuencia ({', '.join(letter_seq)})")
    elif forced_letter:
        lines.append(f"🔤 <b>Letra:</b> {forced_letter}")
    elif vowel_forced:
        lines.append("🔤 <b>Letra:</b> Solo vocales")
    else:
        lines.append("🔤 <b>Letra:</b> Aleatoria")
    lines.append("")

    # Bonificaciones
    bonuses = []
    no_dup = rules_data.get("no_duplicates_bonus", 0)
    if no_dup > 0:
        bonuses.append(f"  • Respuesta única: +{no_dup} pts")

    bonus_all = rules_data.get("bonus_all_filled", 0)
    if bonus_all > 0:
        bonuses.append(f"  • Llenar todo: +{bonus_all} pts")

    speed = rules_data.get("speed_bonus", 0)
    speed_win = rules_data.get("speed_bonus_window", 0)
    if speed > 0:
        bonuses.append(f"  • Velocidad: +{speed} pts ({speed_win}s)")

    streak = rules_data.get("streak_multiplier", 1.0)
    if streak > 1.0:
        bonuses.append(f"  • Streak: x{streak}")

    pen = rules_data.get("penalty_empty", 0)
    if pen < 0:
        bonuses.append(f"  • Pen vacío: {pen} pts")

    double_last = rules_data.get("double_points_last_round", False)
    if double_last:
        bonuses.append("  • Doble última ronda: Sí")

    comeback = rules_data.get("comeback_bonus", 0)
    if comeback > 0:
        bonuses.append(f"  • Comeback: +{comeback} pts")

    if bonuses:
        lines.append("⭐ <b>Bonificaciones:</b>")
        lines.extend(bonuses)
    else:
        lines.append("⭐ <b>Bonificaciones:</b> Ninguna")
    lines.append("")

    # Horario
    if event_type == "one_time":
        starts_at = data.get("starts_at")
        ends_at = data.get("ends_at")
        if starts_at and ends_at:
            lines.append(f"📅 Inicio: {starts_at}")
            lines.append(f"📅 Fin: {ends_at}")
    elif event_type == "permanent":
        lines.append("📅 <b>Activo hasta que se desactive manualmente</b>")

    return "\n".join(lines)
```

### Paso 0 — `/newevent` + selección de grupo

```python
@event_creator_router.message(F.text.startswith("/newevent"))
async def cmd_new_event(message: Message, bot: Bot, state: FSMContext) -> None:
    if not _is_private_chat(message):
        await message.reply("⚠️ Usa este comando en tu chat privado con el bot.")
        return

    user_id = message.from_user.id if message.from_user else 0
    groups = await event_service.get_user_admin_groups(user_id, bot)

    if not groups:
        await message.reply(
            "❌ No eres admin de ningún grupo donde el bot esté presente.\n\n"
            "Añade el bot a un grupo y pide que te hagan admin para crear eventos."
        )
        return

    await state.set_state(NewEventState.select_group)
    await state.update_data(groups=groups)
    await message.reply(
        "🎉 <b>Crear Evento de Temporada</b>\n\n"
        "Selecciona el grupo donde quieres crear el evento:",
        parse_mode="HTML",
        reply_markup=groups_keyboard(groups, prefix="ne"),
    )
```

### Paso 0 → Paso 1 — Selección de grupo

```python
@event_creator_router.callback_query(F.data.startswith("ne:group:"))
async def ne_select_group(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        chat_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    data = await state.get_data()
    groups = data.get("groups", [])
    selected = next((g for g in groups if g["chat_id"] == chat_id), None)
    if not selected:
        await callback.answer("❌ Grupo no encontrado.", show_alert=True)
        return

    await state.update_data(group_chat_id=chat_id, group_title=selected["chat_title"])
    await state.set_state(NewEventState.event_type)
    await callback.message.edit_text(
        "📅 <b>Tipo de Evento</b>\n\n"
        "🔄 <b>Temporal</b> — Dura X horas/días desde ahora\n"
        "🔁 <b>Diario Recurrente</b> — Activo todos los días en horario específico\n"
        "♾ <b>Permanente</b> — Activo hasta que se desactive manualmente\n\n"
        "<i>Selecciona el tipo:</i>",
        parse_mode="HTML",
        reply_markup=event_type_keyboard(),
    )
    await callback.answer()
```

### Paso 1 → Paso 2 — Selección de tipo

```python
@event_creator_router.callback_query(F.data.startswith("ne:type:"))
async def ne_select_type(callback: CallbackQuery, state: FSMContext) -> None:
    event_type = callback.data.split(":")[2]
    valid_types = {"one_time", "daily_recurring", "permanent"}
    if event_type not in valid_types:
        await callback.answer("❌ Tipo inválido.", show_alert=True)
        return

    await state.update_data(event_type=event_type)
    data = await state.get_data()
    await state.set_state(NewEventState.name)

    summary = _build_summary_text(data)
    step_label = "Paso 1/8" if event_type != "permanent" else "Paso 1/8"

    await callback.message.edit_text(
        f"{summary}\n\n"
        f"{step_label}: <b>¿Cómo se llamará el evento?</b>\n\n"
        "Ejemplos: Copa Navideña, Torneo de Verano, Noche de Stop\n\n"
        "<i>Escribe el nombre (máx. 64 caracteres):</i>",
        parse_mode="HTML",
    )
    await callback.answer()
```

### Paso 2 — Nombre (texto)

```python
@event_creator_router.message(NewEventState.name)
async def ne_process_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 3:
        await message.reply("❌ Mínimo 3 caracteres. Intenta de nuevo:")
        return
    if len(name) > 64:
        await message.reply("❌ Máximo 64 caracteres. Intenta de nuevo:")
        return

    # Verificar nombre duplicado en el grupo
    data = await state.get_data()
    async with async_session_factory() as session:
        from sqlalchemy import and_, select

        stmt = select(SeasonalEvent).where(
            and_(
                SeasonalEvent.name == name,
                SeasonalEvent.group_chat_id == data["group_chat_id"],
            )
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none():
            await message.reply("❌ Ya existe un evento con ese nombre en este grupo. Elige otro:")
            return

    await state.update_data(name=name)
    data = await state.get_data()
    await state.set_state(NewEventState.description)

    summary = _build_summary_text(data)
    await message.reply(
        f"{summary}\n\n"
        "Paso 2/8: <b>Escribe una descripción del evento</b>\n\n"
        "<i>(máx. 500 caracteres):</i>",
        parse_mode="HTML",
    )
```

### Paso 3 — Descripción (texto)

```python
@event_creator_router.message(NewEventState.description)
async def ne_process_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if len(desc) < 5:
        await message.reply("❌ Mínimo 5 caracteres:")
        return
    if len(desc) > 500:
        await message.reply("❌ Máximo 500 caracteres:")
        return

    await state.update_data(description=desc)
    data = await state.get_data()
    await state.set_state(NewEventState.multiplier)

    summary = _build_summary_text(data)
    await message.reply(
        f"{summary}\n\n"
        "Paso 3/8: <b>¿Cuánto multiplicará el XP?</b>\n\n"
        "Selecciona:",
        parse_mode="HTML",
        reply_markup=multiplier_keyboard(prefix="ne"),
    )
```

### Paso 4 — Multiplicador

```python
@event_creator_router.callback_query(F.data.startswith("ne:mult:"))
async def ne_process_multiplier(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        multiplier = float(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    if multiplier < 1.0 or multiplier > 10.0:
        await callback.answer("❌ Entre 1.0 y 10.0.", show_alert=True)
        return

    await state.update_data(multiplier=multiplier)
    data = await state.get_data()
    event_type = data.get("event_type", "one_time")

    summary = _build_summary_text(data)

    if event_type == "one_time":
        await state.set_state(NewEventState.schedule_one_time)
        await callback.message.edit_text(
            f"{summary}\n\n"
            "Paso 4/8: <b>¿Cuánto durará el evento?</b>",
            parse_mode="HTML",
            reply_markup=duration_keyboard(prefix="ne"),
        )
    elif event_type == "daily_recurring":
        await state.set_state(NewEventState.schedule_daily_hours)
        await callback.message.edit_text(
            f"{summary}\n\n"
            "Paso 4/8: <b>¿A qué hora inicia el evento cada día?</b>",
            parse_mode="HTML",
            reply_markup=daily_start_keyboard(prefix="ne"),
        )
    else:  # permanent
        # Permanent no necesita horario, saltar a reglas
        await state.set_state(NewEventState.rules_categories)
        await state.update_data(
            rules_data={"categories_enabled": list(EventRules().categories_enabled)}
        )
        summary2 = _build_summary_text(await state.get_data())
        enabled = await state.get_data()
        rules_data = enabled.get("rules_data", {})
        await callback.message.edit_text(
            f"{summary2}\n\n"
            "Paso 5/8: <b>Selecciona las categorías activas:</b>\n\n"
            "<i>Las desactivadas no se puntuarán.</i>",
            parse_mode="HTML",
            reply_markup=categories_toggle_keyboard(
                rules_data.get("categories_enabled", list(EventRules().categories_enabled)),
                prefix="ne",
            ),
        )
    await callback.answer()
```

### Paso 5a — Duración (one_time)

```python
@event_creator_router.callback_query(F.data.startswith("ne:dur:"))
async def ne_process_duration(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        hours = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    if hours < 1 or hours > 168:
        await callback.answer("❌ Entre 1 y 168 horas.", show_alert=True)
        return

    starts_at = utcnow()
    ends_at = starts_at + timedelta(hours=hours)

    await state.update_data(
        duration_hours=hours,
        starts_at=starts_at.strftime("%d/%m/%Y %H:%M UTC"),
        ends_at=ends_at.strftime("%d/%m/%Y %H:%M UTC"),
        _starts_at_iso=starts_at.isoformat(),
        _ends_at_iso=ends_at.isoformat(),
    )

    data = await state.get_data()
    summary = _build_summary_text(data)

    # Inicializar rules_data con defaults
    default_rules = EventRules()
    await state.update_data(
        rules_data={"categories_enabled": list(default_rules.categories_enabled)}
    )
    await state.set_state(NewEventState.rules_categories)

    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 5/8: <b>Selecciona las categorías activas:</b>\n\n"
        "<i>Las desactivadas no se puntuarán.</i>",
        parse_mode="HTML",
        reply_markup=categories_toggle_keyboard(
            default_rules.categories_enabled, prefix="ne"
        ),
    )
    await callback.answer()
```

### Paso 5b-1 — Hora inicio diaria

```python
@event_creator_router.callback_query(F.data.startswith("ne:dstart:"))
async def ne_daily_start(callback: CallbackQuery, state: FSMContext) -> None:
    time_str = callback.data.split(":", 2)[2]  # "18:00"
    try:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        await callback.answer("❌ Hora inválida.", show_alert=True)
        return

    await state.update_data(daily_start_hour=hour, daily_start_minute=minute)
    data = await state.get_data()
    summary = _build_summary_text(data)

    await state.set_state(NewEventState.schedule_daily_hours)
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 4/8: <b>¿A qué hora termina el evento cada día?</b>",
        parse_mode="HTML",
        reply_markup=daily_end_keyboard(prefix="ne"),
    )
    await callback.answer()
```

### Paso 5b-2 — Hora fin diaria

```python
@event_creator_router.callback_query(F.data.startswith("ne:dend:"))
async def ne_daily_end(callback: CallbackQuery, state: FSMContext) -> None:
    time_str = callback.data.split(":", 2)[2]  # "22:00"
    try:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        await callback.answer("❌ Hora inválida.", show_alert=True)
        return

    await state.update_data(daily_end_hour=hour, daily_end_minute=minute)
    data = await state.get_data()

    # Default: lunes a viernes
    default_days = ["mon", "tue", "wed", "thu", "fri"]
    await state.update_data(active_days=default_days)
    await state.set_state(NewEventState.schedule_daily_days)

    summary = _build_summary_text(await state.get_data())
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 4/8: <b>¿Qué días está activo?</b>\n\n"
        "(Toggle: ✅ = activo, — = inactivo)",
        parse_mode="HTML",
        reply_markup=days_of_week_keyboard(default_days, prefix="ne"),
    )
    await callback.answer()
```

### Paso 5b-3 — Días de semana (toggle)

```python
@event_creator_router.callback_query(F.data.startswith("ne:day:"))
async def ne_toggle_day(callback: CallbackQuery, state: FSMContext) -> None:
    day = callback.data.split(":")[2]
    valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    if day not in valid_days:
        await callback.answer("❌ Día inválido.", show_alert=True)
        return

    data = await state.get_data()
    active_days = list(data.get("active_days", ["mon", "tue", "wed", "thu", "fri"]))

    if day in active_days:
        active_days.remove(day)
    else:
        active_days.append(day)

    await state.update_data(active_days=active_days)
    data = await state.get_data()
    summary = _build_summary_text(data)

    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 4/8: <b>¿Qué días está activo?</b>\n\n"
        "(Toggle: ✅ = activo, — = inactivo)",
        parse_mode="HTML",
        reply_markup=days_of_week_keyboard(active_days, prefix="ne"),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:days_confirm")
async def ne_confirm_days(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    active_days = data.get("active_days", [])
    if not active_days:
        await callback.answer("❌ Selecciona al menos un día.", show_alert=True)
        return

    # Inicializar rules_data
    default_rules = EventRules()
    await state.update_data(
        rules_data={"categories_enabled": list(default_rules.categories_enabled)}
    )
    await state.set_state(NewEventState.rules_categories)

    summary = _build_summary_text(await state.get_data())
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 5/8: <b>Selecciona las categorías activas:</b>\n\n"
        "<i>Las desactivadas no se puntuarán.</i>",
        parse_mode="HTML",
        reply_markup=categories_toggle_keyboard(
            default_rules.categories_enabled, prefix="ne"
        ),
    )
    await callback.answer()
```

### Paso 6 — Categorías (toggle)

```python
@event_creator_router.callback_query(F.data.startswith("ne:cat:"))
async def ne_toggle_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    if cat not in EventRules._VALID_CATEGORIES if hasattr(EventRules, '_VALID_CATEGORIES') else cat not in {
        "Nombre", "Apellido", "Color", "Fruta", "País", "Artista", "Animal", "Cosa"
    }:
        await callback.answer("❌ Categoría inválida.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    enabled = list(rules_data.get("categories_enabled", list(EventRules().categories_enabled)))

    if cat in enabled:
        enabled.remove(cat)
    else:
        enabled.append(cat)

    rules_data["categories_enabled"] = enabled
    await state.update_data(rules_data=rules_data)

    await callback.message.edit_reply_markup(
        reply_markup=categories_toggle_keyboard(enabled, prefix="ne")
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:cat_all")
async def ne_select_all_categories(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    rules_data["categories_enabled"] = list(EventRules().categories_enabled)
    await state.update_data(rules_data=rules_data)

    await callback.message.edit_reply_markup(
        reply_markup=categories_toggle_keyboard(
            EventRules().categories_enabled, prefix="ne"
        )
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:rules_next")
async def ne_rules_next(callback: CallbackQuery, state: FSMContext) -> None:
    """Avanzar de categorías a opciones avanzadas (hidden/mystery)."""
    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    enabled = rules_data.get("categories_enabled", list(EventRules().categories_enabled))

    if not enabled:
        await callback.answer("❌ Selecciona al menos una categoría.", show_alert=True)
        return

    hidden = rules_data.get("hidden_categories", [])
    mystery = rules_data.get("mystery_category")

    await state.set_state(NewEventState.rules_categories_options)
    await callback.message.edit_text(
        "📋 <b>Categorías avanzadas</b>\n\n"
        "Opcional: selecciona categorías ocultas o mystery.\n"
        "Si no necesitas, pulsa Siguiente.",
        parse_mode="HTML",
        reply_markup=categories_options_keyboard(hidden, mystery, prefix="ne"),
    )
    await callback.answer()
```

### Paso 6 — Categorías opciones avanzadas (hidden / mystery)

```python
@event_creator_router.callback_query(F.data.startswith("ne:cat_hidden:"))
async def ne_toggle_hidden(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[3]
    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    hidden = list(rules_data.get("hidden_categories", []))

    if cat in hidden:
        hidden.remove(cat)
    else:
        hidden.append(cat)

    rules_data["hidden_categories"] = hidden
    await state.update_data(rules_data=rules_data)

    mystery = rules_data.get("mystery_category")
    await callback.message.edit_reply_markup(
        reply_markup=categories_options_keyboard(hidden, mystery, prefix="ne")
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ne:cat_mystery:"))
async def ne_toggle_mystery(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[3]
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    # Toggle: si ya es mystery, quitarlo
    if rules_data.get("mystery_category") == cat:
        rules_data["mystery_category"] = None
    else:
        rules_data["mystery_category"] = cat

    await state.update_data(rules_data=rules_data)

    hidden = rules_data.get("hidden_categories", [])
    mystery = rules_data.get("mystery_category")
    await callback.message.edit_reply_markup(
        reply_markup=categories_options_keyboard(hidden, mystery, prefix="ne")
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:options_next")
async def ne_options_next(callback: CallbackQuery, state: FSMContext) -> None:
    """Avanzar de categorías avanzadas a tiempo/letra."""
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    await state.set_state(NewEventState.rules_time_and_letter)
    await callback.message.edit_text(
        "⏱ <b>Tiempo y Letra</b>\n\n"
        "Paso 6/8: <b>Tiempo por ronda:</b>",
        parse_mode="HTML",
        reply_markup=round_time_keyboard(
            rules_data.get("time_override"), prefix="ne"
        ),
    )
    await callback.answer()
```

### Paso 7 — Tiempo por ronda

```python
@event_creator_router.callback_query(F.data.startswith("ne:time:"))
async def ne_select_time(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        time_val = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    if time_val == 0:
        # Usar config del grupo (no override)
        rules_data.pop("time_override", None)
    else:
        rules_data["time_override"] = time_val

    await state.update_data(rules_data=rules_data)

    # Preguntar si quiere tiempo decreciente
    await state.set_state(NewEventState.rules_decreasing)
    dec_amount = rules_data.get("time_decreasing_amount", 5)
    await callback.message.edit_text(
        f"⏱ Tiempo: <b>{time_val}s</b> (o config grupo si es 0)\n\n"
        "¿Quieres tiempo decreciente?\n\n"
        "<i>El tiempo disminuye cada ronda.</i>",
        parse_mode="HTML",
        reply_markup=decreasing_time_keyboard(dec_amount, prefix="ne"),
    )
    await callback.answer()
```

### Paso 7 — Tiempo decreciente

```python
@event_creator_router.callback_query(F.data.startswith("ne:dec:"))
async def ne_select_decreasing(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        amount = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    rules_data["time_decreasing"] = True
    rules_data["time_decreasing_amount"] = amount
    await state.update_data(rules_data=rules_data)

    await callback.message.edit_reply_markup(
        reply_markup=decreasing_time_keyboard(amount, prefix="ne")
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:dec_confirm")
async def ne_confirm_decreasing(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    # Si no se activó decreciente, marcar False
    if "time_decreasing" not in rules_data:
        rules_data["time_decreasing"] = False

    await state.update_data(rules_data=rules_data)

    # Ahora mostrar selección de letra
    await callback.message.edit_text(
        "🔤 <b>Letra para el evento:</b>",
        parse_mode="HTML",
        reply_markup=forced_letter_keyboard(prefix="ne"),
    )
    await callback.answer()
```

### Paso 7 — Selección de letra

```python
@event_creator_router.callback_query(F.data.startswith("ne:letter:"))
async def ne_select_letter(callback: CallbackQuery, state: FSMContext) -> None:
    letter = callback.data.split(":")[2]
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    if letter == "RANDOM":
        rules_data.pop("forced_letter", None)
        rules_data.pop("letter_sequence", None)
        rules_data["vowel_forced"] = False
    elif letter == "EXCLUDE_VOWELS":
        rules_data.pop("forced_letter", None)
        rules_data.pop("letter_sequence", None)
        rules_data["vowel_forced"] = True
    elif letter == "SEQUENCE":
        # Para simplificar, pedimos que escriba la secuencia como texto
        # Por ahora, usar solo forced_letter
        rules_data.pop("forced_letter", None)
        rules_data["letter_sequence"] = None  # Se puede expandir después
        rules_data["vowel_forced"] = False
    else:
        rules_data["forced_letter"] = letter
        rules_data.pop("letter_sequence", None)
        rules_data["vowel_forced"] = False

    await state.update_data(rules_data=rules_data)

    # Avanzar a bonificaciones
    await state.set_state(NewEventState.rules_scoring)
    await callback.message.edit_text(
        "⭐ <b>Bonificaciones y Penalizaciones</b>\n\n"
        "Paso 7/8: <b>Configura los bonos (pulsa para rotar valores):</b>",
        parse_mode="HTML",
        reply_markup=bonuses_keyboard(rules_data, prefix="ne"),
    )
    await callback.answer()
```

### Paso 8 — Bonificaciones (toggle)

```python
@event_creator_router.callback_query(F.data.startswith("ne:bonus:"))
async def ne_toggle_bonus(callback: CallbackQuery, state: FSMContext) -> None:
    bonus_key = callback.data.split(":")[2]
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    _BONUS_CYCLES = {
        "no_duplicates_bonus": [0, 15, 25, 50, 100],
        "bonus_all_filled": [0, 25, 50, 75, 100],
        "speed_bonus": [0, 10, 20, 30, 50],
        "penalty_empty": [0, -5, -10, -15, -20],
        "streak_multiplier": [1.0, 1.25, 1.5, 2.0],
        "comeback_bonus": [0, 10, 20, 30],
    }

    if bonus_key in _BONUS_CYCLES:
        cycle = _BONUS_CYCLES[bonus_key]
        current = rules_data.get(bonus_key, cycle[0])
        try:
            idx = cycle.index(current)
            rules_data[bonus_key] = cycle[(idx + 1) % len(cycle)]
        except ValueError:
            rules_data[bonus_key] = cycle[0]
    elif bonus_key == "double_points_last_round":
        rules_data["double_points_last_round"] = not rules_data.get(
            "double_points_last_round", False
        )
    elif bonus_key == "answer_reveal":
        rules_data["answer_reveal"] = not rules_data.get("answer_reveal", False)
    else:
        await callback.answer("❌ Bonus desconocido.", show_alert=True)
        return

    await state.update_data(rules_data=rules_data)
    await callback.message.edit_reply_markup(
        reply_markup=bonuses_keyboard(rules_data, prefix="ne")
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:bonus_next")
async def ne_bonus_next(callback: CallbackQuery, state: FSMContext) -> None:
    """Avanzar de bonificaciones a confirmación."""
    await state.set_state(NewEventState.confirm)
    data = await state.get_data()
    summary = _build_full_summary_text(data)

    await callback.message.edit_text(
        summary,
        parse_mode="HTML",
        reply_markup=confirm_event_keyboard(prefix="ne"),
    )
    await callback.answer()
```

### Paso 9 — Confirmación

```python
@event_creator_router.callback_query(F.data == "ne:confirm")
async def ne_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    event_type = data.get("event_type", "one_time")

    # Construir reglas
    rules_data = data.get("rules_data", {})
    event_rules = EventRules(
        categories_enabled=rules_data.get(
            "categories_enabled", list(EventRules().categories_enabled)
        ),
        categories_disabled=rules_data.get("categories_disabled", []),
        hidden_categories=rules_data.get("hidden_categories", []),
        mystery_category=rules_data.get("mystery_category"),
        time_override=rules_data.get("time_override"),
        time_decreasing=rules_data.get("time_decreasing", False),
        time_decreasing_amount=rules_data.get("time_decreasing_amount", 5),
        forced_letter=rules_data.get("forced_letter"),
        vowel_forced=rules_data.get("vowel_forced", False),
        no_duplicates_bonus=rules_data.get("no_duplicates_bonus", 0),
        bonus_all_filled=rules_data.get("bonus_all_filled", 0),
        speed_bonus=rules_data.get("speed_bonus", 0),
        speed_bonus_window=rules_data.get("speed_bonus_window", 8),
        streak_multiplier=rules_data.get("streak_multiplier", 1.0),
        penalty_empty=rules_data.get("penalty_empty", 0),
        comeback_bonus=rules_data.get("comeback_bonus", 0),
        double_points_last_round=rules_data.get("double_points_last_round", False),
        answer_reveal=rules_data.get("answer_reveal", False),
    )
    rules_json = event_rules.to_json()

    # Calcular horarios
    starts_at = None
    ends_at = None
    if event_type == "one_time":
        starts_at_str = data.get("_starts_at_iso")
        ends_at_str = data.get("_ends_at_iso")
        if starts_at_str and ends_at_str:
            starts_at = datetime.fromisoformat(starts_at_str)
            ends_at = datetime.fromisoformat(ends_at_str)

    # Construir kwargs del evento
    event_kwargs = {
        "group_chat_id": data["group_chat_id"],
        "name": data["name"],
        "description": data.get("description", ""),
        "event_type": event_type,
        "multiplier": data.get("multiplier", 1.0),
        "starts_at": starts_at,
        "ends_at": ends_at,
        "active": True,
        "rules": rules_json,
        "timezone": "America/Argentina/Buenos_Aires",
    }

    # Horario diario
    if event_type == "daily_recurring":
        event_kwargs["daily_start_hour"] = data.get("daily_start_hour", 0)
        event_kwargs["daily_start_minute"] = data.get("daily_start_minute", 0)
        event_kwargs["daily_end_hour"] = data.get("daily_end_hour", 23)
        event_kwargs["daily_end_minute"] = data.get("daily_end_minute", 59)
        event_kwargs["active_days"] = json.dumps(
            data.get("active_days", ["mon", "tue", "wed", "thu", "fri"])
        )

    # Guardar en BD
    async with async_session_factory() as session:
        event = SeasonalEvent(**event_kwargs)
        session.add(event)
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>¡Evento creado!</b>",
        parse_mode="HTML",
    )
    await callback.answer("🎉 Evento creado", show_alert=True)

    # Notificar al grupo
    try:
        if event_type == "one_time":
            ends_display = data.get("ends_at", "")
            notification = (
                "🎉 <b>¡Nuevo Evento de Temporada!</b>\n\n"
                f"📌 <b>{data['name']}</b>\n"
                f"📝 {data.get('description', '')}\n"
                f"⚡ Multiplicador: <b>x{data.get('multiplier', 1.0)} XP</b>\n"
                f"⏱ Termina: {ends_display}\n\n"
                "<i>¡Juega Stop y gana más experiencia!</i>"
            )
        elif event_type == "daily_recurring":
            start_h = data.get("daily_start_hour", 0)
            start_m = data.get("daily_start_minute", 0)
            end_h = data.get("daily_end_hour", 23)
            end_m = data.get("daily_end_minute", 59)
            notification = (
                "🎉 <b>¡Nuevo Evento de Temporada!</b>\n\n"
                f"📌 <b>{data['name']}</b>\n"
                f"📝 {data.get('description', '')}\n"
                f"⚡ Multiplicador: <b>x{data.get('multiplier', 1.0)} XP</b>\n"
                f"⏰ Horario: {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}\n\n"
                "<i>¡Juega Stop y gana más experiencia!</i>"
            )
        else:
            notification = (
                "🎉 <b>¡Nuevo Evento de Temporada!</b>\n\n"
                f"📌 <b>{data['name']}</b>\n"
                f"📝 {data.get('description', '')}\n"
                f"⚡ Multiplicador: <b>x{data.get('multiplier', 1.0)} XP</b>\n\n"
                "<i>¡Juega Stop y gana más experiencia!</i>"
            )
        await bot.send_message(data["group_chat_id"], notification, parse_mode="HTML")
    except Exception:
        logger.exception("Error notificando grupo %s sobre nuevo evento", data["group_chat_id"])
```

### Paso 9 — Editar (volver atrás)

```python
@event_creator_router.callback_query(F.data == "ne:edit")
async def ne_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Volver al paso de nombre para editar."""
    await state.set_state(NewEventState.name)
    data = await state.get_data()
    summary = _build_summary_text(data)
    await callback.message.edit_text(
        f"{summary}\n\n"
        "<b>Edita el nombre del evento:</b>\n\n"
        "<i>Escribe el nuevo nombre (máx. 64 caracteres):</i>",
        parse_mode="HTML",
    )
    await callback.answer()
```

### Cancelar

```python
@event_creator_router.callback_query(F.data == "ne:cancel")
async def ne_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ <b>Creación cancelada.</b>", parse_mode="HTML")
    await callback.answer()
```

### `/deleteevent` — Sin cambios

**Copia exacta del código actual.** No modificar nada de `/deleteevent`. Solo asegurarse de que la importación de `events_list_keyboard` funciona con la nueva versión (que tiene el fix para `ends_at=None`).

```python
# ─── /deleteevent ──────────────────────────────────────────────────


@event_creator_router.message(F.text.startswith("/deleteevent"))
async def cmd_delete_event(message: Message, bot: Bot, state: FSMContext) -> None:
    if not message.chat or message.chat.type != "private":
        await message.reply("⚠️ Usa este comando en tu chat privado con el bot.")
        return

    user_id = message.from_user.id if message.from_user else 0
    groups = await event_service.get_groups_with_active_events(user_id, bot)

    if not groups:
        await message.reply("📭 No hay eventos activos en tus grupos.")
        return

    await state.set_state(DeleteEventState.select_group)
    await state.update_data(groups=groups)
    await message.reply(
        "🗑 <b>Borrar Evento</b>\n\nSelecciona el grupo:",
        parse_mode="HTML",
        reply_markup=groups_keyboard(groups, prefix="delevent"),
    )


@event_creator_router.callback_query(F.data.startswith("delevent:group:"))
async def de_select_group(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        chat_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌", show_alert=True)
        return

    data = await state.get_data()
    groups = data.get("groups", [])
    selected = next((g for g in groups if g["chat_id"] == chat_id), None)
    if not selected:
        await callback.answer("❌", show_alert=True)
        return

    await state.update_data(group_chat_id=chat_id)
    await state.set_state(DeleteEventState.select_event)
    await callback.message.edit_text(
        f"📌 <b>{selected['chat_title']}</b>\n\nSelecciona el evento a borrar:",
        parse_mode="HTML",
        reply_markup=events_list_keyboard(selected["events"], prefix="delevent"),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("delevent:event:"))
async def de_select_event(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        event_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌", show_alert=True)
        return

    await state.update_data(event_id=event_id)
    await state.set_state(DeleteEventState.confirm)
    await callback.message.edit_text(
        "⚠️ <b>¿Estás seguro?</b>\n\nEl evento será desactivado y se notificará al grupo.",
        parse_mode="HTML",
        reply_markup=confirm_event_keyboard(prefix="delevent"),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "delevent:confirm")
async def de_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    event_id = data.get("event_id")
    group_chat_id = data.get("group_chat_id")

    success = await event_service.deactivate_event(event_id)
    if not success:
        await callback.answer("❌ Evento no encontrado.", show_alert=True)
        await state.clear()
        return

    await state.clear()
    await callback.message.edit_text("✅ <b>Evento desactivado.</b>", parse_mode="HTML")
    await callback.answer("✅ Desactivado", show_alert=True)

    try:
        await bot.send_message(
            group_chat_id,
            "❌ <b>Un evento de temporada ha sido desactivado.</b>",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Error notificando grupo %s sobre evento borrado", group_chat_id)


@event_creator_router.callback_query(F.data.startswith("delevent:cancel"))
async def de_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ <b>Cancelado.</b>", parse_mode="HTML")
    await callback.answer()


@event_creator_router.callback_query(F.data == "delevent:back")
async def de_back(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """Volver a selección de grupo"""
    user_id = callback.from_user.id
    groups = await event_service.get_groups_with_active_events(user_id, bot)
    if not groups:
        await callback.message.edit_text("📭 No hay eventos activos.")
        await state.clear()
        await callback.answer()
        return

    await state.set_state(DeleteEventState.select_group)
    await state.update_data(groups=groups)
    await callback.message.edit_text(
        "🗑 <b>Borrar Evento</b>\n\nSelecciona el grupo:",
        parse_mode="HTML",
        reply_markup=groups_keyboard(groups, prefix="delevent"),
    )
    await callback.answer()
```

---

## PARTE 3: Validación de categorías

El código usa `EventRules._VALID_CATEGORIES` para validar categorías. Sin embargo, este es un atributo privado del módulo `_VALID_CATEGORIES` (no del dataclass). Para evitar depender de internals, define una constante local en `event_creator.py`:

```python
# Al inicio del archivo, después de las imports
_VALID_CATEGORIES = {"Nombre", "Apellido", "Color", "Fruta", "País", "Artista", "Animal", "Cosa"}
```

Y usa `_VALID_CATEGORIES` en vez de `EventRules._VALID_CATEGORIES` en el handler `ne_toggle_category`.

---

## PARTE 4: Errores comunes y edge cases

### 4.1 — `callback.message.edit_text()` puede fallar si el mensaje no tiene contenido editado
**Solución:** Si `callback.message.text` es None (ej: imagen), usar `callback.message.edit_caption()` o enviar un mensaje nuevo.

### 4.2 — `callback.message.edit_reply_markup()` puede fallar si el teclado es idéntico
**Solución:** Esto es normal. aiogram lanza `TelegramBadRequest` si no hay cambios. Envolvér con `try/except` y `contextlib.suppress`:

```python
import contextlib
from aiogram.exceptions import TelegramBadRequest

# En handlers que solo cambian el teclado:
with contextlib.suppress(TelegramBadRequest):
    await callback.message.edit_reply_markup(reply_markup=...)
```

### 4.3 — Duración de callback expirado (>30 segundos)
Si el usuario tarda mucho en responder, el callback expira. El handler debe manejar esto:
```python
try:
    await callback.answer()
except TelegramBadRequest:
    pass  # Callback expirado, no es crítico
```

### 4.4 — Estado stale (refresh del chat)
Si el usuario escribe un comando mientras el FSM está en un paso diferente, aiogram ignora el mensaje (correcto).

### 4.5 — daily_recurring sin días seleccionados
En `ne_confirm_days`, validar que `active_days` no esté vacío.

### 4.6 — permanent sin horario
En `ne_process_multiplier`, cuando `event_type == "permanent"`, saltar directamente a `rules_categories` sin pedir horario.

---

## PARTE 5: Patrones de callback data

Todos los callbacks de `/newevent` usan prefijo `ne:`:

| Callback | Acción |
|---|---|
| `ne:group:{chat_id}` | Seleccionar grupo |
| `ne:type:{one_time\|daily_recurring\|permanent}` | Seleccionar tipo |
| `ne:mult:{1.5\|2.0\|3.0\|5.0}` | Seleccionar multiplicador |
| `ne:dur:{hours}` | Seleccionar duración (1, 6, 12, 24, 72, 168) |
| `ne:dstart:{HH:MM}` | Hora inicio diaria |
| `ne:dend:{HH:MM}` | Hora fin diaria |
| `ne:day:{mon\|tue\|wed\|thu\|fri\|sat\|sun}` | Toggle día |
| `ne:days_confirm` | Confirmar días |
| `ne:cat:{Nombre\|Apellido\|...}` | Toggle categoría activa |
| `ne:cat_all` | Seleccionar todas las categorías |
| `ne:rules_next` | Siguiente: categorías avanzadas |
| `ne:cat_hidden:{Nombre\|...}` | Toggle categoría oculta |
| `ne:cat_mystery:{Nombre\|...}` | Toggle mystery category |
| `ne:options_next` | Siguiente: tiempo/letra |
| `ne:time:{0\|15\|30\|45\|60\|90}` | Seleccionar tiempo |
| `ne:dec:{3\|5\|7\|10}` | Seleccionar decremento |
| `ne:dec_confirm` | Confirmar decreciente |
| `ne:letter:{A-Z\|Ñ\|RANDOM\|EXCLUDE_VOWELS\|SEQUENCE}` | Seleccionar letra |
| `ne:bonus:{key}` | Rotar bonus |
| `ne:bonus_next` | Siguiente: confirmación |
| `ne:confirm` | Confirmar y crear evento |
| `ne:edit` | Volver a editar nombre |
| `ne:cancel` | Cancelar creación |

---

## PARTE 6: Orden de ejecución del FSM

```
/newevent
  → Paso 0: select_group → ne:group:{chat_id}
  → Paso 1: event_type → ne:type:{type}
  → Paso 2: name → texto del usuario
  → Paso 3: description → texto del usuario
  → Paso 4: multiplier → ne:mult:{value}
  → SI one_time:
      → Paso 5a: schedule_one_time → ne:dur:{hours}
  → SI daily_recurring:
      → Paso 5b-1: schedule_daily_hours → ne:dstart:{time}
      → Paso 5b-2: schedule_daily_hours → ne:dend:{time}
      → Paso 5b-3: schedule_daily_days → ne:day:{day} / ne:days_confirm
  → SI permanent:
      → Saltar a rules_categories
  → Paso 6: rules_categories → ne:cat:{cat} / ne:cat_all / ne:rules_next
  → Paso 6+: rules_categories_options → ne:cat_hidden / ne:cat_mystery / ne:options_next
  → Paso 7: rules_time_and_letter → ne:time:{val}
  → Paso 7+: rules_decreasing → ne:dec:{val} / ne:dec_confirm
  → Paso 7++: rules_time_and_letter → ne:letter:{val}
  → Paso 8: rules_scoring → ne:bonus:{key} / ne:bonus_next
  → Paso 9: confirm → ne:confirm / ne:edit / ne:cancel
```

---

## PARTE 7: Flujo del Paso 8 (bonificaciones) — Detalle

El teclado de bonificaciones muestra 8 botones. Cada botón rota entre valores predefinidos:

| Botón | Campo en rules_data | Ciclo |
|---|---|---|
| Bonus respuesta única | `no_duplicates_bonus` | 0 → 15 → 25 → 50 → 100 → 0 |
| Bonus llenar todo | `bonus_all_filled` | 0 → 25 → 50 → 75 → 100 → 0 |
| Bonus velocidad | `speed_bonus` | 0 → 10 → 20 → 30 → 50 → 0 |
| Penalización vacío | `penalty_empty` | 0 → -5 → -10 → -15 → -20 → 0 |
| Streak multiplier | `streak_multiplier` | 1.0 → 1.25 → 1.5 → 2.0 → 1.0 |
| Doble última ronda | `double_points_last_round` | OFF → ON → OFF |
| Comeback bonus | `comeback_bonus` | 0 → 10 → 20 → 30 → 0 |
| Reveal respuestas | `answer_reveal` | OFF → ON → OFF |

---

## PARTE 8: Validación de datos antes de crear

Antes de insertar en BD, validar:

1. **Nombre:** 3-64 caracteres, no duplicado en el grupo
2. **Descripción:** 5-500 caracteres
3. **Multiplicador:** 1.0-10.0
4. **one_time:** `duration_hours` debe existir y estar entre 1-168
5. **daily_recurring:** `daily_start_hour`, `daily_end_hour`, `active_days` deben existir
6. **Categorías:** Al menos 1 categoría activa
7. **Decreciente:** Si `time_decreasing=True`, `time_decreasing_amount` debe estar entre 1-30

---

## PARTE 9: Testing

### 9.1 — Tests unitarios para keyboards

Crear `tests/test_event_keyboards.py`:

```python
"""Tests para keyboards de eventos."""
import pytest
from src.keyboards.event import (
    categories_toggle_keyboard,
    confirm_event_keyboard,
    daily_end_keyboard,
    daily_start_keyboard,
    days_of_week_keyboard,
    decreasing_time_keyboard,
    duration_keyboard,
    event_type_keyboard,
    forced_letter_keyboard,
    groups_keyboard,
    multiplier_keyboard,
    round_time_keyboard,
)


def test_event_type_keyboard():
    kb = event_type_keyboard()
    assert len(kb.inline_keyboard) == 3
    # Verificar callback_data
    assert kb.inline_keyboard[0][0].callback_data == "ne:type:one_time"
    assert kb.inline_keyboard[1][0].callback_data == "ne:type:daily_recurring"
    assert kb.inline_keyboard[2][0].callback_data == "ne:type:permanent"


def test_groups_keyboard():
    groups = [{"chat_id": 123, "chat_title": "Test Group"}]
    kb = groups_keyboard(groups, prefix="ne")
    assert len(kb.inline_keyboard) == 2  # 1 group + cancel
    assert "ne:group:123" in kb.inline_keyboard[0][0].callback_data


def test_multiplier_keyboard():
    kb = multiplier_keyboard(prefix="ne")
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "ne:mult:1.5"


def test_duration_keyboard():
    kb = duration_keyboard(prefix="ne")
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "ne:dur:1"


def test_daily_start_keyboard():
    kb = daily_start_keyboard(prefix="ne")
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "ne:dstart:00:00"


def test_daily_end_keyboard():
    kb = daily_end_keyboard(prefix="ne")
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "ne:dend:20:00"


def test_days_of_week_keyboard():
    kb = days_of_week_keyboard(["mon", "tue", "wed"], prefix="ne")
    assert len(kb.inline_keyboard) == 3  # 2 rows of days + confirm
    # Primer botón debería ser L ✅
    assert "L ✅" in kb.inline_keyboard[0][0].text
    # Sábado debería ser S —
    assert "S —" in kb.inline_keyboard[1][1].text


def test_categories_toggle_keyboard():
    kb = categories_toggle_keyboard(["Nombre", "Color"], prefix="ne")
    # 4 rows de 2 categorías + 1 row final
    assert len(kb.inline_keyboard) == 5
    # Nombre debería tener ✅
    assert "✅ Nombre" in kb.inline_keyboard[0][0].text
    # Apellido debería tener ⬜
    assert "⬜ Apellido" in kb.inline_keyboard[0][1].text


def test_round_time_keyboard():
    kb = round_time_keyboard(60, prefix="ne")
    assert len(kb.inline_keyboard) == 3
    # 60s debería tener "•"
    assert "• 60s" in kb.inline_keyboard[1][2].text


def test_decreasing_time_keyboard():
    kb = decreasing_time_keyboard(5, prefix="ne")
    assert len(kb.inline_keyboard) == 2
    assert "• -5s" in kb.inline_keyboard[0][1].text


def test_forced_letter_keyboard():
    kb = forced_letter_keyboard(include_n=False, prefix="ne")
    # 4 filas de letras + 1 fila de opciones
    assert len(kb.inline_keyboard) == 5
    assert kb.inline_keyboard[4][0].callback_data == "ne:letter:RANDOM"


def test_bonuses_keyboard():
    rules_data = {"no_duplicates_bonus": 0, "streak_multiplier": 1.0}
    kb = bonuses_keyboard(rules_data, prefix="ne")
    assert len(kb.inline_keyboard) == 5  # 4 rows + next


def test_confirm_event_keyboard():
    kb = confirm_event_keyboard(prefix="ne")
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "ne:confirm"
```

### 9.2 — Tests del FSM (unitarios con mocks)

Crear `tests/test_event_creator.py`:

```python
"""Tests para el FSM de creación de eventos."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, Chat, User

from src.handlers.admin.event_creator import (
    NewEventState,
    ne_select_group,
    ne_select_type,
    _build_summary_text,
    _build_full_summary_text,
)


@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


@pytest.fixture
def mock_callback():
    cb = AsyncMock(spec=CallbackQuery)
    cb.data = "ne:group:123"
    cb.answer = AsyncMock()
    cb.message = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.text = "Test"
    cb.from_user = MagicMock(spec=User)
    cb.from_user.id = 456
    return cb


def test_build_summary_text_empty():
    result = _build_summary_text({})
    assert result == ""


def test_build_summary_text_with_group():
    data = {"group_title": "Test Group"}
    result = _build_summary_text(data)
    assert "Test Group" in result
    assert "✅ Grupo:" in result


def test_build_full_summary_text_basic():
    data = {
        "name": "Test Event",
        "description": "Test description",
        "event_type": "one_time",
        "multiplier": 2.0,
        "duration_hours": 24,
        "rules_data": {
            "categories_enabled": ["Nombre", "Color"],
            "categories_disabled": [],
            "hidden_categories": [],
            "mystery_category": None,
            "time_override": 60,
        },
    }
    result = _build_full_summary_text(data)
    assert "Test Event" in result
    assert "Test description" in result
    assert "x2.0" in result
    assert "24 horas" in result
    assert "60s" in result
```

---

## PARTE 10: Checklist de implementación

### Archivos a modificar:
- [ ] `src/keyboards/event.py` — Reescribir completamente
- [ ] `src/handlers/admin/event_creator.py` — Reescribir completamente

### Pasos:
1. [ ] Reescribir `keyboards/event.py` con todas las funciones de teclado
2. [ ] Reescribir `event_creator.py` con FSM de 10 pasos
3. [ ] Añadir constante `_VALID_CATEGORIES` al inicio de `event_creator.py`
4. [ ] Testear cada paso del FSM manualmente en Telegram
5. [ ] Ejecutar `pytest tests/test_event_keyboards.py -v`
6. [ ] Ejecutar `pytest tests/test_event_creator.py -v`
7. [ ] Ejecutar `pytest --tb=short` para verificar que no se rompió nada

### Comandos de verificación:
```bash
cd backend
pytest tests/test_event_keyboards.py -v
pytest tests/test_event_creator.py -v
pytest --tb=short
```

---

## Notas de implementación

1. **Los imports de `EventRules._VALID_CATEGORIES`** — Este es un atributo privado. Usar la constante local `_VALID_CATEGORIES` definida en `event_creator.py`.

2. **`callback.message.edit_reply_markup()`** — Cuando solo cambias el teclado (no el texto), usa `edit_reply_markup`. Pero si el teclado es idéntico, aiogram lanza `TelegramBadRequest`. Envolver con `contextlib.suppress`.

3. **`contextlib.suppress(TelegramBadRequest)`** — Para handlers que solo cambian teclado, siempre usar suppress.

4. **Flujo de permanent** — Cuando `event_type == "permanent"`, saltar directamente de `multiplier` a `rules_categories` sin pedir horario.

5. **Flujo de daily_recurring** — Tres sub-pasos: hora inicio → hora fin → días de semana.

6. **`rules_data` en state** — Se guarda como dict en `state.update_data(rules_data={...})`. Se actualiza incrementalmente en cada paso.

7. **`_build_summary_text()`** — Se llama en cada paso para mostrar el progreso. Es una función pura (no toca state).

8. **`_build_full_summary_text()`** — Solo se llama en el Paso 9 (confirmación).

9. **La confirmación crea el evento en BD** — En `ne_confirm`, se construye `EventRules` desde `rules_data`, se serializa a JSON, y se inserta `SeasonalEvent`.

10. **Notificación al grupo** — Después de crear el evento, se envía un mensaje al grupo con los detalles.
