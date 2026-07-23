# Fase 6: Teclados de Eventos Reescritos

## Resumen
Reescribir `src/keyboards/event.py` para que tenga **todas** las funciones de teclado necesarias para los flujos de creación (`/newevent`), edición (`/editevent`), toggle (`/toggleevent`) y selección de modo al iniciar partida.

---

## Estado actual y bugs encontrados

### Bugs críticos

| # | Bug | Severidad | Ubicación |
|---|---|---|---|
| 1 | **`categories_options_keyboard` no existe** — importado y usado 7 veces en `event_creator.py` pero la función NO está definida en `keyboards/event.py`. Cualquier intento de crear evento con categorías ocultas/mystery crashea con `ImportError`. | CRÍTICO | `event_creator.py:33,825,855,883,1796,1820,1845` |
| 2 | **`confirm_event_keyboard` está definido 2 veces** — línea 69 (solo Confirmar/Cancelar) y línea 429 (Confirmar/Editar/Cancelar). La segunda sobreescribe a la primera. La de la línea 69 nunca se usa. | MEDIO | `event.py:69` y `event.py:429` |

### Funciones existentes vs plan

| Función del plan | Estado actual | Notas |
|---|---|---|
| `event_type_keyboard()` | ✅ Existe (línea 43) | Correcto |
| `daily_time_keyboard(prefix)` | ✅ Existe como 2 funciones separadas | `daily_start_keyboard` + `daily_end_keyboard` — MEJOR que el plan |
| `days_of_week_keyboard(active_days, prefix)` | ✅ Existe (línea 158) | Correcto |
| `categories_toggle_keyboard(active_categories, prefix)` | ✅ Existe (línea 191) | Correcto |
| `categories_options_keyboard(hidden, mystery, prefix)` | ❌ **NO EXISTE** | CRÍTICO — crear |
| `round_time_keyboard(prefix)` | ✅ Existe (línea 227) | Firma: `(current_time_override, prefix)` |
| `forced_letter_keyboard(include_n, prefix)` | ✅ Existe (línea 285) | Correcto |
| `bonuses_keyboard(rules, prefix)` | ✅ Existe (línea 333) | Firma: `(rules_data, prefix)` |
| `event_list_manage_keyboard(events, prefix)` | ✅ Existe (línea 490) | Correcto |
| `edit_field_keyboard()` | ✅ Existe como `edit_event_field_keyboard()` (línea 519) | Correcto |
| `groups_keyboard(groups, prefix)` | ✅ Existe (línea 27) | Correcto |
| `confirm_event_keyboard(prefix)` | ⚠️ Duplicado | Ver bug #2 |

### Funciones extra (no en plan pero necesarias)

| Función | Propósito | Usada por |
|---|---|---|
| `multiplier_keyboard(prefix)` | Selección de multiplicador x1.5/x2/x3/x5 | `event_creator.py` (newevent paso 4) |
| `duration_keyboard(prefix)` | Duración para eventos one_time | `event_creator.py` (newevent paso 5a) |
| `decreasing_time_keyboard(amount, prefix)` | Segundos de decremento | `event_creator.py` (newevent paso 7) |
| `events_list_keyboard(events, prefix)` | Lista de eventos para `/deleteevent` | `event_creator.py` |
| `events_edit_list_keyboard(events, prefix)` | Lista de eventos para `/editevent` | `event_creator.py` |
| `event_status_keyboard(events, prefix)` | Lista con toggle pausar/reanudar | `event_creator.py` |
| `save_event_keyboard(prefix)` | Guardar/Cancelar en edición | `event_creator.py` |

---

## Archivo a modificar

**`src/keyboards/event.py`** — Reescritura completa

### Imports necesarios

```python
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.keyboards.settings import ALL_CATEGORIES
```

### Constantes

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

_BONUS_CYCLES = {
    "no_duplicates_bonus": [0, 15, 25, 50, 100],
    "bonus_all_filled": [0, 25, 50, 75, 100],
    "speed_bonus": [0, 10, 20, 30, 50],
    "penalty_empty": [0, -5, -10, -15, -20],
    "streak_multiplier": [1.0, 1.25, 1.5, 2.0],
    "comeback_bonus": [0, 10, 20, 30],
}
```

---

## Código completo de cada función

A continuación se presenta el código de **todas** las funciones en el orden correcto. **No omitas ninguna.**

---

### 1. `groups_keyboard(groups, prefix)`

Teclado de selección de grupo. Usado en `/newevent`, `/editevent`, `/toggleevent`, `/deleteevent`.

```python
def groups_keyboard(groups: list[dict], prefix: str) -> InlineKeyboardMarkup:
    """Teclado de selección de grupo.

    Cada dict en groups debe tener: {"chat_id": int, "chat_title": str}
    """
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

---

### 2. `event_type_keyboard(prefix)`

Selección de tipo de evento: Temporal / Diario Recurrente / Permanente.

```python
def event_type_keyboard(prefix: str = "ne") -> InlineKeyboardMarkup:
    """Teclado de selección de tipo de evento."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Temporal",
                    callback_data=f"{prefix}:type:one_time",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Diario Recurrente",
                    callback_data=f"{prefix}:type:daily_recurring",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="♾ Permanente",
                    callback_data=f"{prefix}:type:permanent",
                ),
            ],
        ]
    )
```

---

### 3. `multiplier_keyboard(prefix)`

Selección de multiplicador de XP.

```python
def multiplier_keyboard(prefix: str = "ne") -> InlineKeyboardMarkup:
    """Teclado de selección de multiplicador."""
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

---

### 4. `duration_keyboard(prefix)`

Duración para eventos one_time (temporales).

```python
def duration_keyboard(prefix: str = "ne") -> InlineKeyboardMarkup:
    """Teclado de duración para evento temporal."""
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

---

### 5. `daily_start_keyboard(prefix)`

Horas de inicio para evento diario recurrente.

```python
def daily_start_keyboard(prefix: str = "ne") -> InlineKeyboardMarkup:
    """Teclado de horas de inicio para evento diario."""
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

---

### 6. `daily_end_keyboard(prefix)`

Horas de fin para evento diario recurrente.

```python
def daily_end_keyboard(prefix: str = "ne") -> InlineKeyboardMarkup:
    """Teclado de horas de fin para evento diario."""
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

---

### 7. `days_of_week_keyboard(active_days, prefix)`

Toggle de días de la semana para eventos diarios.

```python
def days_of_week_keyboard(
    active_days: list[str],
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Toggle de días de la semana.

    active_days: lista de keys como ["mon", "tue", "wed", ...]
    """
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

---

### 8. `categories_toggle_keyboard(enabled_categories, prefix)`

Toggle de 8 categorías del juego + botón "Todas" y "Siguiente".

```python
def categories_toggle_keyboard(
    enabled_categories: list[str],
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Toggle de categorías activas para el evento.

    Muestra las 8 categorías con check/bucket, más "Todas" y "Siguiente".
    """
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

---

### 9. `categories_options_keyboard(hidden_categories, mystery_category, prefix)` — **NUEVA**

Selección de categorías ocultas y mystery. **Esta función NO existe actualmente y es el bug CRÍTICO.**

**Firma:** `categories_options_keyboard(hidden_categories: list[str], mystery_category: str | None, prefix: str = "ne") -> InlineKeyboardMarkup`

**Cómo se usa en event_creator.py:**
- `categories_options_keyboard(hidden, mystery, prefix="ne")` — newevent paso 6+
- `categories_options_keyboard(hidden, mystery, prefix="ee")` — editevent

**Callbacks que genera:**
- `{prefix}:cat_hidden:{category}` — toggle categoría oculta
- `{prefix}:cat_mystery:{category}` — toggle mystery category (solo 1)
- `{prefix}:options_next` — siguiente paso

```python
def categories_options_keyboard(
    hidden_categories: list[str],
    mystery_category: str | None,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de opciones avanzadas de categorías: oculta y mystery.

    - hidden_categories: lista de categorías ocultas (ej: ["Cosa"])
    - mystery_category: una sola categoría mystery o None
    - prefix: prefijo del callback (ne=newevent, ee=editevent)

    Cada categoría tiene 2 estados:
      - Oculta: se muestra como input pero el jugador no ve el título
      - Mystery: se revela solo al puntuar, vale x2
    """
    rows = []

    # Fila header: Oculta
    rows.append(
        [
            InlineKeyboardButton(
                text="🎭 Categorías Ocultas",
                callback_data=f"{prefix}:options_next",
            )
        ]
    )

    # Filas de categorías: 2 columnas
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

    # Fila de mystery separada
    rows.append(
        [
            InlineKeyboardButton(
                text=f"🔮 Mystery: {mystery_category or 'Ninguna'}",
                callback_data=f"{prefix}:cat_mystery:{mystery_category or 'none'}",
            )
        ]
    )

    # Fila inferior: siguiente
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

**NOTA IMPORTANTE:** Los callbacks de `cat_hidden` y `cat_mystery` usan la misma fila de botones. El handler en `event_creator.py` distingue entre hidden y mystery parseando el prefijo del callback:
- `ne:cat_hidden:Color` → toggle hidden de Color
- `ne:cat_mystery:Color` → toggle mystery a Color

Pero mirando el código de `event_creator.py` (líneas 833-887), los handlers parsean así:
- `ne:cat_hidden:{cat}` → `callback.data.split(":")[3]`
- `ne:cat_mystery:{cat}` → `callback.data.split(":")[3]`

Esto significa que el callback_data debe ser `{prefix}:cat_hidden:{category}` y `{prefix}:cat_mystery:{category}`.

**CORRECCIÓN:** Revisando el handler `ne_toggle_hidden` (línea 833):
```python
@event_creator_router.callback_query(F.data.startswith("ne:cat_hidden:"))
async def ne_toggle_hidden(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[3]
```

Y `ne_toggle_mystery` (línea 862):
```python
@event_creator_router.callback_query(F.data.startswith("ne:cat_mystery:"))
async def ne_toggle_mystery(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[3]
```

Esto significa que los callbacks son:
- `ne:cat_hidden:Color` → split(":") = ["ne", "cat_hidden", "Color"] → índice [2]
- Espera índice [3] → ¡ERROR!

**Revisando:** `callback.data.split(":")` para `"ne:cat_hidden:Color"` produce `["ne", "cat_hidden", "Color"]`. Índice [3] daría `IndexError`.

**Pero espera** — mira bien la línea 835:
```python
cat = callback.data.split(":")[3]
```

Y el callback_data en el teclado que propongo es `{prefix}:cat_hidden:{cat}`. Para `prefix="ne"` y `cat="Color"`:
- callback_data = `"ne:cat_hidden:Color"`
- split(":") = `["ne", "cat_hidden", "Color"]`
- [3] = IndexError!

**Solución:** El callback_data debe tener 4 partes. Cambiar a:
```python
callback_data=f"{prefix}:cat_opt:hidden:{cat}",
callback_data=f"{prefix}:cat_opt:mystery:{cat}",
```

O **MEJOR**: verificar cómo están parseando los handlers. Veamos:

Línea 833-835:
```python
@event_creator_router.callback_query(F.data.startswith("ne:cat_hidden:"))
async def ne_toggle_hidden(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[3]
```

Para que `split(":")[3]` funcione, el callback_data debe tener al menos 4 partes (índices 0,1,2,3). Con `{prefix}:cat_hidden:{cat}`:
- "ne:cat_hidden:Color" → 3 partes → [3] = IndexError

**La solución correcta** es que el callback_data tenga 4 partes. Observando que `prefix` puede ser `"ne"` (3 chars) o `"ee"` (2 chars), y que el handler usa `F.data.startswith("ne:cat_hidden:")`, la forma correcta es:

```python
callback_data=f"{prefix}:cat_h:{cat}",   # ne:cat_h:Color → ["ne", "cat_h", "Color"] → 3 partes
```

Pero esto no funciona con [3]. Necesitamos 4 partes:

```python
callback_data=f"{prefix}:cathidden:{cat}",  # ne:cathidden:Color → ["ne", "cathidden", "Color"] → 3 partes
```

Todavía 3 partes. Para obtener 4 partes necesitamos algo como:

```python
callback_data=f"{prefix}:cat:hidden:{cat}",  # ne:cat:hidden:Color → ["ne", "cat", "hidden", "Color"] → 4 partes → [3] = "Color" ✓
callback_data=f"{prefix}:cat:mystery:{cat}", # ne:cat:mystery:Color → 4 partes → [3] = "Color" ✓
```

**PERO** — revisando el handler real en `event_creator.py` línea 833:
```python
@event_creator_router.callback_query(F.data.startswith("ne:cat_hidden:"))
```

El handler espera `ne:cat_hidden:*`. Si uso `ne:cat:hidden:Color`, el startswith no matchea.

**Decisión:** El handler y el teclado deben ser consistentes. Dado que el handler ya existe y usa:
- `F.data.startswith("ne:cat_hidden:")` 
- `cat = callback.data.split(":")[3]`

El callback_data DEBE ser `ne:cat_hidden:{cat}` pero necesitamos que split(":") tenga al menos 4 partes. La ÚNICA forma es que prefix contenga ":" o que haya un campo extra.

**Revisando más cuidadosamente el código del handler:**

```python
@event_creator_router.callback_query(F.data.startswith("ne:cat_hidden:"))
async def ne_toggle_hidden(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[3]
```

Con `callback_data = "ne:cat_hidden:Color"`:
- split(":") = ["ne", "cat_hidden", "Color"]
- [3] → IndexError

**Esto confirma que hay un bug en el handler o en el teclado.** Dado que el teclado NO existe (es el bug que estamos arreglando), debemos crear el teclado de forma que el handler funcione.

Para que `callback.data.split(":")[3]` funcione con el pattern `startswith("ne:cat_hidden:")`:
```python
callback_data=f"{prefix}:cat_hidden:dummy:{cat}"
# "ne:cat_hidden:dummy:Color" → ["ne", "cat_hidden", "dummy", "Color"] → [3] = "Color" ✓
```

Pero esto es feo. **MEJOR:** Corregir el handler para usar `[2]`:

```python
cat = callback.data.split(":")[2]
```

Y usar:
```python
callback_data=f"{prefix}:cat_hidden:{cat}"
# "ne:cat_hidden:Color" → ["ne", "cat_hidden", "Color"] → [2] = "Color" ✓
```

**Decisión final:** El teclado se crea con `{prefix}:cat_hidden:{cat}` y `{prefix}:cat_mystery:{cat}`. Se debe **corregir el handler** para usar `split(":")[2]` en vez de `split(":")[3]`. Esto es un fix necesario.

**Verificar también:** Para `ee:cat_hidden:*`:
```python
@event_creator_router.callback_query(F.data.startswith("ee:cat_hidden:"))
async def ee_toggle_hidden(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[3]
```

Mismo problema. Todos los handlers de `cat_hidden` y `cat_mystery` (6 en total) necesitan el fix.

**Corrección de handlers necesaria (no es parte de esta fase pero hay que documentarlo):**

En `event_creator.py`, cambiar TODOS los `callback.data.split(":")[3]` de cat_hidden/cat_mystery a `split(":")[2]`:

| Línea | Handler | Actual | Corregido |
|---|---|---|---|
| 835 | `ne_toggle_hidden` | `split(":")[3]` | `split(":")[2]` |
| 864 | `ne_toggle_mystery` | `split(":")[3]` | `split(":")[2]` |
| 1803 | `ee_toggle_hidden` | `split(":")[3]` | `split(":")[2]` |
| 1829 | `ee_toggle_mystery` | `split(":")[3]` | `split(":")[2]` |

---

### 10. `round_time_keyboard(current_time_override, prefix)`

Selección de tiempo por ronda con opción "Config grupo" y decremento.

```python
def round_time_keyboard(
    current_time_override: int | None,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de selección de tiempo de ronda.

    current_time_override: el tiempo seleccionado actualmente (None = config grupo)
    """
    options = [15, 30, 45, 60, 90]
    row1 = [
        InlineKeyboardButton(
            text="⚙️ Config grupo",
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

---

### 11. `decreasing_time_keyboard(amount, prefix)`

Selección de decremento de tiempo por ronda.

```python
def decreasing_time_keyboard(
    amount: int,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de selección de decremento por ronda."""
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

---

### 12. `forced_letter_keyboard(include_n, prefix)`

Selección de letra forzada: 27 letras + Aleatoria + Excluir vocal + Secuencia.

```python
def forced_letter_keyboard(
    include_n: bool = False,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de selección de letra forzada."""
    letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if include_n:
        letters.insert(letters.index("N") + 1, "Ñ")

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

---

### 13. `bonuses_keyboard(rules_data, prefix)`

Configuración de bonificaciones con toggle de valores predefinidos.

```python
def bonuses_keyboard(
    rules_data: dict,
    prefix: str = "ne",
) -> InlineKeyboardMarkup:
    """Teclado de bonificaciones y penalizaciones.

    Cada botón rota entre valores predefinidos al hacer click.
    rules_data: dict con los valores actuales de las reglas.
    """

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

---

### 14. `confirm_event_keyboard(prefix)`

Confirmación de evento — **SOLO UNA definición** (eliminar la duplicada).

```python
def confirm_event_keyboard(prefix: str = "ne") -> InlineKeyboardMarkup:
    """Teclado de confirmación de evento (Crear / Editar / Borrar).

    El prefix determina el callback: {prefix}:confirm, {prefix}:edit, {prefix}:cancel
    """
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

---

### 15. `events_list_keyboard(events, prefix)`

Lista de eventos para `/deleteevent`.

```python
def events_list_keyboard(events: list[dict], prefix: str = "delevent") -> InlineKeyboardMarkup:
    """Teclado de eventos para borrar.

    Cada dict: {"id": int, "name": str, "multiplier": float, "ends_at": datetime|None}
    """
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

---

### 16. `event_list_manage_keyboard(events, prefix)`

Lista de eventos con toggle pausar/reanudar (versión compacta).

```python
def event_list_manage_keyboard(
    events: list[dict], prefix: str = "toggleevt"
) -> InlineKeyboardMarkup:
    """Lista de eventos con toggle pausar/reanudar (versión compacta)."""
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
```

---

### 17. `events_edit_list_keyboard(events, prefix)`

Lista de eventos para `/editevent`.

```python
def events_edit_list_keyboard(
    events: list[dict], prefix: str = "editevent"
) -> InlineKeyboardMarkup:
    """Teclado de eventos para editar."""
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
```

---

### 18. `event_status_keyboard(events, prefix)`

Lista de eventos con toggle pausar/reanudar (versión detallada, dos botones por evento).

```python
def event_status_keyboard(
    events: list[dict], prefix: str = "toggleevt"
) -> InlineKeyboardMarkup:
    """Lista de eventos con toggle pausar/reanudar (versión detallada).

    Muestra 2 botones por evento: info + acción toggle.
    """
    buttons = []
    for e in events:
        is_paused = e.get("is_paused", False)
        event_type = e.get("event_type", "one_time")
        status_icon = "⏸" if is_paused else "🟢"
        type_icon = {
            "one_time": "🔄",
            "daily_recurring": "🔁",
            "permanent": "♾",
        }.get(event_type, "🔄")

        if is_paused:
            action_text = f"▶️ Reanudar: {e['name']}"
        else:
            action_text = f"⏸ Pausar: {e['name']}"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{status_icon} {type_icon} {e['name']} (x{e['multiplier']})",
                    callback_data=f"{prefix}:info:{e['id']}",
                )
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=action_text,
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

---

### 19. `edit_event_field_keyboard()`

Menú de campos editables para `/editevent`.

```python
def edit_event_field_keyboard() -> InlineKeyboardMarkup:
    """Menú de campos editables para /editevent."""
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

### 20. `save_event_keyboard(prefix)`

Teclado de guardado para edición de eventos.

```python
def save_event_keyboard(prefix: str = "editevent") -> InlineKeyboardMarkup:
    """Teclado de guardado para edición de eventos."""
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
```

---

## Fix adicional en `event_creator.py`

Dado que la función `categories_options_keyboard` no existía, los handlers que la usan parsean el callback con `split(":")[3]`, lo cual es un bug. Corregir TODOS los parseos:

### Archivo: `src/handlers/admin/event_creator.py`

Cambiar **4 líneas**:

| Línea actual | Actual | Corregido |
|---|---|---|
| 835 | `cat = callback.data.split(":")[3]` | `cat = callback.data.split(":")[2]` |
| 864 | `cat = callback.data.split(":")[3]` | `cat = callback.data.split(":")[2]` |
| 1803 | `cat = callback.data.split(":")[3]` | `cat = callback.data.split(":")[2]` |
| 1829 | `cat = callback.data.split(":")[3]` | `cat = callback.data.split(":")[2]` |

**Razón:** Con `prefix="ne"` y `callback_data="ne:cat_hidden:Color"`:
- `split(":")` → `["ne", "cat_hidden", "Color"]`
- Índices válidos: 0, 1, 2
- `[3]` → `IndexError`
- `[2]` → `"Color"` ✓

---

## Resumen de cambios

### `src/keyboards/event.py`

1. **Eliminar** la primera definición de `confirm_event_keyboard` (línea 69-77) — la duplicada inferior (línea 429-450) es la correcta
2. **Agregar** función `categories_options_keyboard` (nueva, ~40 líneas)
3. **Mantener** todas las demás funciones sin cambios

### `src/handlers/admin/event_creator.py`

4. **Corregir** 4 líneas de parseo de callback data (`split(":")[3]` → `split(":")[2]`)

---

## Verificación

### Test de compilación

```bash
cd backend
python -m py_compile src/keyboards/event.py && echo "event OK"
python -m py_compile src/handlers/admin/event_creator.py && echo "creator OK"
```

### Test de import

```bash
cd backend
python -c "from src.keyboards.event import categories_options_keyboard; print('OK')"
python -c "from src.handlers.admin.event_creator import event_creator_router; print('OK')"
```

### Test suite

```bash
cd backend
pytest --tb=short -q
```

### Verificar que no hay duplicados

```bash
cd backend
python -c "
import ast
with open('src/keyboards/event.py', encoding='utf-8') as f:
    tree = ast.parse(f.read())
funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
dupes = set(f for f in funcs if funcs.count(f) > 1)
print('Duplicates:', dupes if dupes else 'None')
print('Total functions:', len(funcs))
"
```

---

## Orden de aplicación recomendado

1. Corregir `split(":")[3]` → `split(":")[2]` en `event_creator.py` (4 líneas)
2. Eliminar `confirm_event_keyboard` duplicado en `event.py` (línea 69-77)
3. Agregar `categories_options_keyboard` al final de `event.py`
4. Verificar compilación
5. Ejecutar tests
6. Hacia la Fase 7 (que ya está escrita en el guide anterior de este archivo)
