# Plan de Fases: Rediseño del Sistema de Eventos de Temporada

## Resumen Ejecutivo

El sistema actual de eventos es demasiado básico: solo permite nombre, descripción, duración y multiplicador. Se rediseñará completamente para soportar **reglas personalizables por evento** (categorías activas/desactivadas, multiplicadores por categoría, tiempo de ronda, letra forzada, bonificaciones), **horarios diarios recurrentes** (hora de inicio/fin + días de semana), **edición de eventos**, **activar/desactivar sin eliminar**, y **selección de modo de juego al llamar `/stop`**.

---

## Fase 1: Modelo de Datos — Columna `rules` JSON + campos de horario diario

### Objetivo
Extender el modelo `SeasonalEvent` con campos para tipo de evento, horarios diarios recurrentes, estado de pausa, y una columna JSON flexible para reglas personalizables.

### Impacto
- **Alcance:** Solo afecta `models.py` y genera una migración de Alembic
- **Riesgo:** Bajo — es aditivo, no modifica campos existentes
- **Dependencias:** Ninguna

### Entregables
- Modelo `SeasonalEvent` actualizado en `src/db/models.py`
- Migración de Alembic: `alembic revision --autogenerate -m "event_type, rules JSON, daily schedule, is_paused"`

### Modelo Actualizado

```python
class SeasonalEvent(Base):
    __tablename__ = "seasonal_events"

    id: Mapped[int]
    group_chat_id: Mapped[int]                    # BigInteger, indexed
    name: Mapped[str]                              # String(64)
    description: Mapped[str | None]                # Text, nullable

    # Tipo de evento
    event_type: Mapped[str]                        # String(20), default="one_time"
    # Valores: "one_time", "daily_recurring", "permanent"

    # Multiplicador base
    multiplier: Mapped[float]                      # default=1.0

    # Horario one-time (nullable para daily_recurring/permanent)
    starts_at: Mapped[datetime | None]
    ends_at: Mapped[datetime | None]

    # Horario diario recurrente (nullable para one_time)
    daily_start_hour: Mapped[int | None]           # 0-23
    daily_start_minute: Mapped[int | None]         # 0-59
    daily_end_hour: Mapped[int | None]             # 0-23
    daily_end_minute: Mapped[int | None]           # 0-59
    active_days: Mapped[str | None]                # Text (JSON): ["mon","tue","wed","thu","fri","sat","sun"]
    timezone: Mapped[str]                          # String(40), default="America/Argentina/Buenos_Aires"

    # Reglas personalizadas (JSON flexible)
    rules: Mapped[str | None]                      # Text (JSON dict)

    # Estado
    active: Mapped[bool]                           # default=False
    is_paused: Mapped[bool]                        # default=False
    created_at: Mapped[datetime]
```

### Estructura del JSON `rules`

```json
{
  "categories_enabled": ["nombre", "color", "pais", "fruta", "animal", "artista", "apellido", "cosa"],
  "categories_disabled": ["cosa"],
  "category_multipliers": {
    "pais": 2.0,
    "color": 1.5
  },
  "hidden_categories": ["cosa"],
  "mystery_category": "artista",
  "category_order": ["pais", "nombre", "color"],
  "time_override": 45,
  "time_decreasing": false,
  "time_decreasing_amount": 5,
  "time_minimum": 15,
  "speed_bonus": 30,
  "speed_bonus_window": 8,
  "forced_letter": "M",
  "excluded_letters": ["A", "E"],
  "letter_sequence": ["M", "R", "S", "P"],
  "vowel_forced": false,
  "no_duplicates_bonus": 25,
  "bonus_all_filled": 50,
  "streak_multiplier": 1.25,
  "penalty_empty": -10,
  "comeback_bonus": 20,
  "perfect_round_bonus": 50,
  "shared_answer_penalty": -15,
  "double_points_last_round": false,
  "min_words_required": 4,
  "min_word_length": 3,
  "proper_nouns_only": false,
  "no_repeat_words": false,
  "require_all_different": false,
  "allow_dots_as_empty": true,
  "sudden_death": false,
  "sudden_death_threshold": 1,
  "max_players": 10,
  "elimination_rounds": [3, 5],
  "collaborative": false,
  "wager_enabled": false,
  "wager_max_pct": 50,
  "answer_reveal": false,
  "no_stop": false,
  "infinite_rounds": false
}
```

**Estado de la fase:** Completada (ver season-phase1-guide.md)

---

## Fase 2: Helper `EventRules` — Parseo y validación de reglas

### Objetivo
Crear una clase dataclass que parsee el JSON `rules` y expone propiedades tipadas, validadas y con defaults correctos.

### Impacto
- **Alcance:** Archivo nuevo, no modifica nada existente
- **Riesgo:** Bajo — clase pura sin dependencias externas
- **Dependencias:** Fase 1 (modelo actualizado)

### Entregables
- Archivo nuevo: `src/services/event_rules.py` (~80 líneas)

### Diseño de la Clase

```python
@dataclass
class EventRules:
    categories_enabled: list[str]
    categories_disabled: list[str]
    category_multipliers: dict[str, float]
    hidden_categories: list[str]
    mystery_category: str | None
    category_order: list[str] | None
    time_override: int | None
    time_decreasing: bool
    time_decreasing_amount: int
    time_minimum: int
    speed_bonus: int
    speed_bonus_window: int
    forced_letter: str | None
    excluded_letters: list[str]
    letter_sequence: list[str] | None
    vowel_forced: bool
    no_duplicates_bonus: int
    bonus_all_filled: int
    streak_multiplier: float
    penalty_empty: int
    comeback_bonus: int
    perfect_round_bonus: int
    shared_answer_penalty: int
    double_points_last_round: bool
    min_words_required: int
    min_word_length: int
    proper_nouns_only: bool
    no_repeat_words: bool
    require_all_different: bool
    allow_dots_as_empty: bool
    sudden_death: bool
    sudden_death_threshold: int
    max_players: int | None
    elimination_rounds: list[int] | None
    collaborative: bool
    wager_enabled: bool
    wager_max_pct: int
    answer_reveal: bool
    no_stop: bool
    infinite_rounds: bool

    @classmethod
    def from_json(cls, json_str: str | None) -> "EventRules":
        """Parsea JSON string a EventRules con defaults correctos."""
        data = json.loads(json_str) if json_str else {}
        return cls(
            categories_enabled=data.get("categories_enabled", ALL_CATEGORIES),
            categories_disabled=data.get("categories_disabled", []),
            # ... todos los campos con defaults apropiados
        )

    def to_json(self) -> str | None:
        """Serializa a JSON string. Retorna None si todas las reglas son default."""
        d = asdict(self)
        # Filtrar valores default para no inflar el JSON
        defaults = EventRules()._asdict()
        non_default = {k: v for k, v in d.items() if v != defaults.get(k)}
        return json.dumps(non_default) if non_default else None

    def get_active_categories(self) -> list[str]:
        """Retorna categorías activas (enabled - disabled)."""
        return [c for c in self.categories_enabled if c not in self.categories_disabled]

    def get_category_multiplier(self, category: str) -> float:
        """Retorna multiplicador para una categoría (default 1.0)."""
        return self.category_multipliers.get(category, 1.0)

    def is_letter_forced(self) -> bool:
        return self.forced_letter is not None

    def get_round_time(self, default: int) -> int:
        """Retorna time_override o el default del grupo."""
        return self.time_override if self.time_override else default

    def get_round_time_for_number(self, round_number: int, default: int) -> int:
        """Si time_decreasing, calcula el tiempo para esta ronda."""
        if not self.time_decreasing:
            return self.get_round_time(default)
        base = self.time_override or default
        calculated = base - (round_number * self.time_decreasing_amount)
        return max(calculated, self.time_minimum)

    def get_letter_for_round(self, round_number: int) -> str | None:
        """Si hay letter_sequence, retorna la letra correspondiente a la ronda."""
        if self.letter_sequence:
            idx = (round_number - 1) % len(self.letter_sequence)
            return self.letter_sequence[idx]
        return self.forced_letter

    def has_rules(self) -> bool:
        """Retorna True si hay alguna regla no-default activa."""
        return self.to_json() is not None
```

**Estado de la fase:** Completada (ver season-phase2-guide.md)


---

## Fase 3: `EventService` — Reescritura completa

### Objetivo
Reescribir `EventService` para soportar los nuevos tipos de eventos, validación de horarios diarios, activar/desactivar, edición, y chequeo de actividad centralizado.

### Impacto
- **Alcance:** Reescritura parcial de `event_service.py` (~200 líneas)
- **Riesgo:** Medio — varios puntos de integración dependen de este servicio
- **Dependencias:** Fase 1 (modelo), Fase 2 (EventRules)

### Entregables
- `src/services/event_service.py` reescrito

### Métodos

| Método | Descripción |
|---|---|
| `get_active_multiplier(group_chat_id)` | Retorna el multiplicador más alto de eventos activos. Verifica `is_paused=False` y para `daily_recurring` verifica horario + día |
| `get_active_events(group_chat_id)` | Retorna todos los eventos activos (no pausados, dentro de horario) con `event_type`, `rules` parseado, `is_paused` |
| `has_active_event(group_chat_id)` | Excluir eventos pausados |
| `deactivate_expired()` | Solo para `one_time` events; los `daily_recurring` nunca expiran por tiempo |
| `deactivate_event(event_id)` → `bool` | Desactiva completamente (`active=False`) |
| `toggle_event(event_id)` → `bool` | **NUEVO:** Cambia `is_paused` entre True/False. Retorna nuevo estado |
| `get_events_for_group(group_chat_id)` → `list[dict]` | **NUEVO:** Retorna todos los eventos del grupo (activos + pausados) con estado |
| `update_event(event_id, **kwargs)` → `bool` | **NUEVO:** Actualiza campos editables (name, description, multiplier, rules, horarios, event_type) |
| `is_event_active_now(event)` → `bool` | **NUEVO:** Lógica central de chequeo |
| `_parse_event_dict(event)` → `dict` | **NUEVO:** Helper que convierte modelo a dict con rules parseado |
| `get_user_admin_groups(user_id, bot)` | Sin cambios |
| `get_groups_with_active_events(user_id, bot)` | Sin cambios |

### Lógica de `is_event_active_now()`

```python
@staticmethod
def is_event_active_now(event: SeasonalEvent) -> bool:
    if not event.active or event.is_paused:
        return False

    now = utcnow()

    if event.event_type == "one_time":
        return event.starts_at <= now <= event.ends_at

    if event.event_type == "daily_recurring":
        # 1. Verificar día de semana
        day_map = {0:"mon", 1:"tue", 2:"wed", 3:"thu", 4:"fri", 5:"sat", 6:"sun"}
        current_day = day_map[now.weekday()]
        active_days = json.loads(event.active_days or '["mon","tue","wed","thu","fri","sat","sun"]')
        if current_day not in active_days:
            return False

        # 2. Verificar horario (con timezone)
        import pytz
        tz = pytz.timezone(event.timezone or "America/Argentina/Buenos_Aires")
        local_now = now.astimezone(tz)
        start = time(event.daily_start_hour or 0, event.daily_start_minute or 0)
        end = time(event.daily_end_hour or 23, event.daily_end_minute or 59)
        return start <= local_now.time() <= end

    if event.event_type == "permanent":
        return True

    return False
```
**Estado de la fase:** Completada 


---

## Fase 4: `event_creator.py` — Reescritura del FSM de creación

### Objetivo
Reescribir el flujo FSM de `/newevent` para soportar los 10 pasos con selección de tipo de evento, horarios, reglas de categorías, tiempo, letra, y bonificaciones.

### Impacto
- **Alcance:** Reescritura completa de `event_creator.py` (~600 líneas)
- **Riesgo:** Medio — es un handler aislado (solo chat privado)
- **Dependencias:** Fase 2 (EventRules), Fase 3 (EventService)

### Entregables
- `src/handlers/admin/event_creator.py` reescrito

### FSM States

```python
class NewEventState(StatesGroup):
    # Sección 1: Información básica
    select_group = State()          # Paso 0
    event_type = State()            # Paso 1: one_time / daily_recurring / permanent
    name = State()                  # Paso 2
    description = State()           # Paso 3
    multiplier = State()            # Paso 4

    # Sección 2: Horario
    schedule_one_time = State()     # Paso 5a: duración (para one_time)
    schedule_daily_hours = State()  # Paso 5b-1: hora inicio/fin (para daily_recurring)
    schedule_daily_days = State()   # Paso 5b-2: días de semana

    # Sección 3: Reglas (opcional, con skip)
    rules_categories = State()      # Paso 6: categorías activas + hidden + mystery
    rules_time_and_letter = State() # Paso 7: tiempo + letra forzada/excluida
    rules_scoring = State()         # Paso 8: bonificaciones y penalizaciones
    confirm = State()               # Paso 9: resumen y confirmar
```

### Descripción de cada paso

#### Paso 0 — Selección de grupo
```
🎉 <b>Crear Evento de Temporada</b>

Selecciona el grupo:
```
Teclado: `[📌 Grupo A]` `[📌 Grupo B]` `[❌ Cancelar]`

#### Paso 1 — Tipo de evento
```
📅 Tipo de Evento

🔄 <b>Temporal</b> — Dura X horas/días desde ahora
🔁 <b>Diario Recurrente</b> — Activo todos los días en horario específico
♾ <b>Permanente</b> — Activo hasta que se desactive manualmente
```
Teclado: `[🔄 Temporal]` `[🔁 Diario]` `[♾ Permanente]`

#### Paso 2 — Nombre del evento
```
✅ Grupo: <b>Grupo A</b>
✅ Tipo: <b>Temporal</b>

Paso 1/8: <b>¿Cómo se llamará el evento?</b>

Ejemplos: Copa Navideña, Torneo de Verano, Noche de Stop

<i>Escribe el nombre (máx. 64 caracteres):</i>
```

#### Paso 3 — Descripción
```
✅ Nombre: <b>Copa Navideña</b>

Paso 2/8: <b>Escribe una descripción del evento</b>

<i>(máx. 500 caracteres):</i>
```

#### Paso 4 — Multiplicador
```
✅ Descripción guardada.

Paso 3/8: <b>¿Cuánto multiplicará el XP?</b>

Selecciona:
```
Teclado: `[x1.5]` `[x2]` `[x3]` `[x5]`

#### Paso 5a — Duración (solo one_time)
```
✅ Multiplicador: <b>x2.0</b>

Paso 4/8: <b>¿Cuánto durará el evento?</b>
```
Teclado: `[1 hora]` `[6 horas]` `[12 horas]` `[24 horas]` `[3 días]` `[7 días]`

#### Paso 5b-1 — Horario diario: hora inicio (solo daily_recurring)
```
✅ Multiplicador: <b>x2.0</b>

Paso 4/8: <b>¿A qué hora inicia el evento cada día?</b>
```
Teclado: `[00:00]` `[06:00]` `[09:00]` `[12:00]` `[15:00]` `[18:00]` `[21:00]`

#### Paso 5b-2 — Horario diario: hora fin
```
✅ Inicio: <b>18:00</b>

Paso 4/8: <b>¿A qué hora termina el evento cada día?</b>
```
Teclado: `[20:00]` `[21:00]` `[22:00]` `[23:00]` `[00:00]` `[02:00]`

#### Paso 5b-3 — Horario diario: días de semana
```
✅ Horario: <b>18:00 - 22:00</b>

Paso 4/8: <b>¿Qué días está activo?</b>

(Toggle: L = activo, — = inactivo)
```
Teclado toggle: `[L ✅]` `[M ✅]` `[X ✅]` `[J ✅]` `[V ✅]` `[S —]` `[D —]` `[✅ Confirmar días]`

#### Paso 6 — Categorías
```
📋 Categorías del Evento

Paso 5/8: <b>Selecciona las categorías activas:</b>

(Las desactivadas no se puntuarán)
```
Teclado toggle:
```
[✅ Nombre]  [✅ Apellido]
[✅ Color]   [✅ Fruta]
[✅ País]    [✅ Artista]
[✅ Animal]  [✅ Cosa]
[🎭 Ocultar: —]  [🔮 Mystery: —]
[⏭ Todas]   [▶️ Siguiente]
```

Callbacks:
- `ne:cat:{name}` — toggle categoría
- `ne:cat_hidden:{name}` — toggle categoría oculta
- `ne:cat_mystery:{name}` — toggle mystery category
- `ne:cat_all` — activar todas
- `ne:rules_next` — siguiente paso

#### Paso 7 — Tiempo y Letra
```
⏱ Tiempo y Letra

Paso 6/8:

<b>Tiempo por ronda:</b>
```
Teclado tiempo:
```
[⚙️ Config grupo]  [⚡ 15s]  [⏱ 30s]
[🕐 45s]  [🕑 60s]  [🕒 90s]
[📉 Decreciente: —]
```

Si se activa decreciente:
```
Tiempo decreciente activado.
Ronda 1: 60s → Ronda 2: 53s → ... (mínimo 15s)

¿Segundos que disminuye por ronda?
```
Teclado: `[-3s]` `[-5s]` `[-7s]` `[-10s]`

Luego selección de letra:
```
<b>Letra:</b>
```
Teclado: `[⏭ Aleatoria]` + 27 letras + `[🚫 Excluir vocal]` `[📜 Secuencia]`

#### Paso 8 — Bonificaciones y penalizaciones
```
⭐ Bonificaciones y Penalizaciones

Paso 7/8:
```
Teclado con botones toggle:
```
[Bonus respuesta única: +0]     [Bonus llenar todo: +0]
[Bonus velocidad: +0]           [Penalización vacío: 0]
[Streak multiplier: x1.0]       [Doble última ronda: OFF]
[Comeback bonus: +0]            [Reveal respuestas: OFF]
[▶️ Siguiente]
```

Cada botón rotó entre valores predefinidos:
- **Bonus respuesta única:** 0 → 15 → 25 → 50 → 100
- **Bonus llenar todo:** 0 → 25 → 50 → 75 → 100
- **Bonus velocidad:** 0 → 10 → 20 → 30 → 50
- **Penalización vacío:** 0 → -5 → -10 → -15 → -20
- **Streak multiplier:** x1.0 → x1.25 → x1.5 → x2.0
- **Comeback bonus:** 0 → 10 → 20 → 30

#### Paso 9 — Confirmación
```
✅ <b>Resumen del Evento</b>

📌 <b>Copa Navideña</b>
📝 Torneo épico de Stop con reglas especiales
📅 Tipo: <b>Temporal</b> — 24 horas
⚡ Multiplicador: <b>x2.0 XP</b>

📋 <b>Categorías activas:</b> Nombre, Color, País, Animal
🚫 <b>Sin:</b> Fruta, Artista, Cosa
🎭 <b>Oculta:</b> Cosa
🔮 <b>Mystery:</b> Artista

⏱ <b>Tiempo:</b> 60s por ronda
🔤 <b>Letra:</b> Aleatoria

⭐ <b>Bonificaciones:</b>
  • Respuesta única: +25 pts
  • Llenar todo: +50 pts
  • Velocidad: +30 pts (primeros 8s)
  • Streak: x1.25
  • Pen vacío: -10 pts
  • Doble última ronda: Sí

📅 Inicio: 22/07/2026 15:00 UTC
📅 Fin: 23/07/2026 15:00 UTC
```
Teclado: `[✅ Confirmar]` `[❌ Cancelar]` `[✏️ Editar]`


**Estado de la fase:** Completada

---

## Fase 5: `/editevent` y `/toggleevent` — Nuevos comandos

### Objetivo
Agregar comandos para editar eventos existentes y activar/desactivar sin eliminar.

### Impacto
- **Alcance:** Extensiones en `event_creator.py` (~300 líneas adicionales)
- **Riesgo:** Bajo — handlers aislados en chat privado
- **Dependencias:** Fase 3 (EventService)

### Entregables
- Comando `/editevent` con FSM de edición por campo
- Comando `/toggleevent` con toggle de pausa/reanudación

### `/editevent` — FSM

```python
class EditEventState(StatesGroup):
    select_group = State()
    select_event = State()
    select_field = State()    # ¿Qué campo editar?
    edit_value = State()      # Nuevo valor
    confirm = State()
```

#### Flujo

1. `/editevent` → Lista de grupos donde el usuario es admin
2. Selecciona grupo → Lista de eventos del grupo
3. Selecciona evento → Menú de campos editables
4. Selecciona campo → Edita valor → Guarda

#### Menú de campos editables

```
✏️ Editar Evento: "Copa Navideña"

Selecciona el campo:
```
Teclado:
```
[📝 Nombre]          [📄 Descripción]
[⚡ Multiplicador]   [📅 Tipo/Horario]
[📋 Categorías]      [⏱ Tiempo/Letra]
[⭐ Bonificaciones]  [✅ Guardar y salir]
```

Cada campo reutiliza la lógica del paso correspondiente del FSM de creación, pero pre-llenando con el valor actual.

### `/toggleevent` — FSM

```python
class ToggleEventState(StatesGroup):
    select_group = State()
    select_event = State()
```

#### Flujo

1. `/toggleevent` → Lista de grupos
2. Selecciona grupo → Lista de eventos con estado

#### Lista con toggle

```
📌 Eventos de "Grupo A":

🟢 <b>Copa Navideña</b> (x2.0) — ACTIVO
   ⏸ Pausar

⏸ <b>Torneo Verano</b> (x1.5) — PAUSADO
   ▶️ Reanudar

🔴 <b>Noche de Stop</b> (x3.0) — INACTIVO (expirado)
```

Teclado:
```
[⏸ Pausar: Copa Navideña]
[▶️ Reanudar: Torneo Verano]
[❌ Cancelar]
```

**Estado de la fase:** 


---

## Fase 6: Teclados de eventos reescritos

### Objetivo
Reescribir `keyboards/event.py` con todos los teclados necesarios para los nuevos flujos de creación, edición y gestión.

### Impacto
- **Alcance:** Reescritura de `keyboards/event.py` (~180 líneas)
- **Riesgo:** Bajo — solo presentación
- **Dependencias:** Ninguna

### Entregables
- `src/keyboards/event.py` reescrito

### Funciones de teclado

| Función | Propósito |
|---|---|
| `event_type_keyboard()` | Selección: temporal / diario / permanente |
| `daily_time_keyboard(prefix)` | Grid de horas para hora inicio/fin |
| `days_of_week_keyboard(active_days, prefix)` | Toggle inline de días (L/M/X/J/V/S/D) |
| `categories_toggle_keyboard(active_categories, prefix)` | Toggle de 8 categorías + "Todas" |
| `categories_options_keyboard(hidden, mystery, prefix)` | Selección de categorías oculta y mystery |
| `round_time_keyboard(prefix)` | Config grupo / 15s / 30s / 45s / 60s / 90s / Decreciente |
| `forced_letter_keyboard(include_n, prefix)` | 27 letras + "Aleatoria" + "Excluir vocal" + "Secuencia" |
| `bonuses_keyboard(rules, prefix)` | Configuración de bonificaciones con toggle de valores |
| `event_list_manage_keyboard(events, prefix)` | Lista con toggle activar/pausar/eliminar |
| `edit_field_keyboard()` | Campos editables |
| `groups_keyboard(groups, prefix)` | Reutilizar el actual |
| `confirm_event_keyboard(prefix)` | Confirmar / Cancelar / Editar |

**Estado de la fase:** Completada

---

## Fase 7: Integración con `/stop` — Selección de modo de juego

### Objetivo
Modificar el flujo de `/stop` para que, si hay eventos activos en el grupo, permita elegir entre modo normal o con evento antes de crear la sala.

### Impacto
- **Alcance:** Modifica `lobby.py` y `game_orchestrator.py`
- **Riesgo:** Alto — modifica el flujo principal del juego
- **Dependencias:** Fase 3 (EventService), Fase 2 (EventRules)

### Entregables
- Callbacks nuevos en `src/handlers/game/lobby.py`
- `LobbyState` con campos `event_id` y `event_rules`
- `create_lobby()` con parámetro `event_id`

### Flujo nuevo de `/stop`

```
Usuario llama /stop
  ↓
Bot verifica si hay eventos activos en el grupo
  ↓
Si NO hay eventos → crea lobby normal (como ahora)
  ↓
Si SÍ hay eventos → responde con inline keyboard:
  "🟢 ¿Cómo quieres jugar?"
  [🎮 Modo Normal] [🎉 Con Evento]
  ↓
Si elige "Modo Normal" → crea lobby normal
  ↓
Si elige "Con Evento" → muestra lista de eventos activos:
  "📌 Selecciona el evento:"
  [🎉 Copa Navideña (x2.0)] [⚡ Batalla de Categorías (x1.5)]
  [❌ Cancelar]
  ↓
Selecciona evento → crea lobby con event_id asociado
```

### Cambios en `LobbyState`

```python
@dataclass
class LobbyState:
    # ... campos existentes ...
    event_id: int | None = None          # ID del evento seleccionado (None = normal)
    event_rules: dict | None = None      # Reglas parseadas del evento
```

### Cambios en `game_orchestrator.py`

| Método | Cambio |
|---|---|
| `create_lobby()` | Añadir parámetro `event_id: int | None = None`. Si se provee, cargar reglas del evento y guardar en `LobbyState` |
| `_do_start()` | Si `state.event_rules` existe, aplicar: `time_override` → round time, `forced_letter` → letra, `categories_enabled/disabled` → categorías |
| `_format_lobby_message()` | Mostrar reglas del evento activo en el lobby |
| `callback_data` para join/start | Añadir soporte para callbacks `select_event:{event_id}` y `mode_normal` |

### Nuevos callbacks en `lobby.py`

```python
@game_router.callback_query(F.data == "mode:normal")
async def callback_mode_normal(callback, ...):
    # Crear lobby sin evento

@game_router.callback_query(F.data == "mode:event")
async def callback_mode_event(callback, ...):
    # Mostrar lista de eventos activos

@game_router.callback_query(F.data.startswith("select_event:"))
async def callback_select_event(callback, ...):
    # Crear lobby con el evento seleccionado
```

**Estado de la fase:** Completada
---

## Fase 8: Propagación de reglas del evento al juego activo

### Objetivo
Hacer que las reglas del evento se propaguen desde el lobby hasta las rondas individuales, afectando: tiempo de ronda, letra, categorías activas, y puntuación.

### Impacto
- **Alcance:** Modifica `round_manager.py` y `score_engine.py`
- **Riesgo:** Alto — modifica la lógica central del juego
- **Dependencias:** Fase 2 (EventRules), Fase 7 (LobbyState con event_rules)

### Entregables
- `RoundState` con campo `event_rules`
- `start_round()` aplicando reglas de tiempo, letra y categorías
- `score_engine.evaluate()` aplicando bonificaciones del evento

### Cambios en `RoundState`

```python
@dataclass
class RoundState:
    # ... campos existentes ...
    event_rules: dict | None = None    # Reglas del evento activo
```

### Cambios en `round_manager.py`

| Punto de integración | Regla aplicada |
|---|---|
| `start_round()` | Si `event_rules.time_override` → usar ese tiempo en vez de config grupo |
| `start_round()` | Si `event_rules.time_decreasing` → calcular tiempo según número de ronda |
| `start_round()` | Si `event_rules.forced_letter` o `letter_sequence` → usar esa letra |
| `start_round()` | Si `event_rules.categories_disabled` → filtrar categorías del round |
| `start_round()` | Si `event_rules.hidden_categories` → ocultar categorías en el mensaje |
| `submit_answers()` | Si `event_rules.min_words_required` → validar mínimo |
| `_end_game()` | Pasar `event_rules` a `score_engine.evaluate()` |

### Cambios en `score_engine.py`

En `evaluate()`:

```python
def evaluate(answers_by_player, num_categories, first_completer_id, spell_corrector, letter, event_rules=None):
    # ... lógica existente de scoring ...

    # NUEVO: Aplicar category_multipliers
    if event_rules:
        cat_multipliers = event_rules.get("category_multipliers", {})
        for cat, mult in cat_multipliers.items():
            if cat in results:
                for player_result in results[cat]:
                    player_result["score"] = int(player_result["score"] * mult)

    # NUEVO: Aplicar no_duplicates_bonus
    if event_rules and event_rules.get("no_duplicates_bonus", 0) > 0:
        for cat, players in unique_answers.items():
            for player_id in players:
                totals[player_id] += event_rules["no_duplicates_bonus"]

    # NUEVO: Aplicar bonus_all_filled
    if event_rules and event_rules.get("bonus_all_filled", 0) > 0:
        for player_id, filled_count in filled_categories.items():
            if filled_count >= len(active_categories):
                totals[player_id] += event_rules["bonus_all_filled"]

    # NUEVO: Aplicar penalty_empty
    if event_rules and event_rules.get("penalty_empty", 0) < 0:
        for player_id, filled_count in filled_categories.items():
            empty_count = len(active_categories) - filled_count
            totals[player_id] += event_rules["penalty_empty"] * empty_count

    # NUEVO: Aplicar comeback_bonus
    if event_rules and event_rules.get("comeback_bonus", 0) > 0:
        if last_place_player_id:
            totals[last_place_player_id] += event_rules["comeback_bonus"]

    # NUEVO: Aplicar shared_answer_penalty
    if event_rules and event_rules.get("shared_answer_penalty", 0) < 0:
        for cat, duplicates in duplicate_groups.items():
            for player_id in duplicates:
                totals[player_id] += event_rules["shared_answer_penalty"]

    return totals, details
```

**Estado de la fase:** Completada
---

## Fase 9: Actualización de visualización

### Objetivo
Actualizar todos los mensajes y visualizaciones para reflejar las reglas del evento activo: lobby, `/events`, fin de juego, y mensajes de ronda.

### Impacto
- **Alcance:** Modifica `game_orchestrator.py`, `lobby.py`, `round_manager.py`
- **Riesgo:** Bajo — solo presentación
- **Dependencias:** Fase 2 (EventRules), Fase 8 (reglas propagadas)

### Entregables
- `_get_event_text()` mejorado en `game_orchestrator.py`
- `/events` mejorado en `lobby.py`
- Mensaje de fin de juego mejorado en `round_manager.py`

### `_get_event_text()` mejorado

```python
@staticmethod
def _get_event_text(event_data: dict | None) -> str:
    if not event_data:
        return ""
    lines = [f"🎉 <b>Evento: {event_data['name']}</b> — x{event_data['multiplier']} XP"]
    rules = event_data.get("rules") or {}
    if rules.get("forced_letter"):
        lines.append(f"   🔤 Letra: {rules['forced_letter']}")
    if rules.get("time_override"):
        lines.append(f"   ⏱ {rules['time_override']}s por ronda")
    disabled = rules.get("categories_disabled", [])
    if disabled:
        lines.append(f"   🚫 Sin: {', '.join(disabled)}")
    hidden = rules.get("hidden_categories", [])
    if hidden:
        lines.append(f"   🎭 Ocultas: {', '.join(hidden)}")
    mystery = rules.get("mystery_category")
    if mystery:
        lines.append(f"   🔮 Mystery: {mystery}")
    cat_mults = rules.get("category_multipliers", {})
    if cat_mults:
        mults = ", ".join(f"{c} x{m}" for c, m in cat_mults.items())
        lines.append(f"   ⚡ Bonus: {mults}")
    if rules.get("speed_bonus"):
        lines.append(f"   🏃 Speed: +{rules['speed_bonus']} pts")
    if rules.get("sudden_death"):
        lines.append(f"   💀 Modo Supervivencia")
    if rules.get("streak_multiplier", 1.0) > 1.0:
        lines.append(f"   🔥 Streak: x{rules['streak_multiplier']}")
    return "\n".join(lines)
```

### `/events` mejorado

Mostrar también: tipo de evento, horario diario (si aplica), reglas activas, estado (activo/pausado para admins).

```
🎉 <b>Eventos activos en este grupo:</b>

📌 <b>Copa Navideña</b>
   ⚡ x2.0 XP — ⏱ queda 12h 30m
   📝 Torneo épico de Stop
   🔤 Letra: M | ⏱ 45s | 🚫 Sin: Cosa
   📅 Tipo: Temporal

📌 <b>Noche de Países</b>
   ⚡ x5.0 XP — ⏱ queda 2h 15m
   🔤 Solo País | ⏱ 30s
   📅 Tipo: Diario (18:00-22:00, Lun-Vie)

⏸ <b>Torneo Verano</b> (PAUSADO)
   ⚡ x1.5 XP
   📅 Tipo: Permanente
```

### Mensaje de fin de juego mejorado

```
🏆 <b>¡Juego terminado!</b>

🏅 <b>Posiciones:</b>
  1. 🥇 Juan — 350 pts (+87 XP)
  2. 🥈 María — 280 pts (+65 XP)
  3. 🥉 Pedro — 210 pts (+45 XP)

🎉 <b>Evento: Copa Navideña</b> (x2.0 XP)
   ⚡ Bonus aplicados:
   • País x3: Juan +60, María +45
   • Respuesta única: +25 cada uno
   • Llenar todo: +50 Juan
   • Speed bonus: +30 Juan
```

**Estado de la fase:**

Ya completada la fase 8 de esta implementacion, avancemos con el desarrollo profesional, avanzada, sin omisiones de la siguiente fase completa y avanzada del proyecto por favor:

Fase 9: Actualización de visualización

### Objetivo
Actualizar todos los mensajes y visualizaciones para reflejar las reglas del evento activo: lobby, `/events`, fin de juego, y mensajes de ronda.

### Impacto
- **Alcance:** Modifica `game_orchestrator.py`, `lobby.py`, `round_manager.py`
- **Riesgo:** Bajo — solo presentación
- **Dependencias:** Fase 2 (EventRules), Fase 8 (reglas propagadas)

### Entregables
- `_get_event_text()` mejorado en `game_orchestrator.py`
- `/events` mejorado en `lobby.py`
- Mensaje de fin de juego mejorado en `round_manager.py`

### `_get_event_text()` mejorado

```python
@staticmethod
def _get_event_text(event_data: dict | None) -> str:
    if not event_data:
        return ""
    lines = [f"🎉 <b>Evento: {event_data['name']}</b> — x{event_data['multiplier']} XP"]
    rules = event_data.get("rules") or {}
    if rules.get("forced_letter"):
        lines.append(f"   🔤 Letra: {rules['forced_letter']}")
    if rules.get("time_override"):
        lines.append(f"   ⏱ {rules['time_override']}s por ronda")
    disabled = rules.get("categories_disabled", [])
    if disabled:
        lines.append(f"   🚫 Sin: {', '.join(disabled)}")
    hidden = rules.get("hidden_categories", [])
    if hidden:
        lines.append(f"   🎭 Ocultas: {', '.join(hidden)}")
    mystery = rules.get("mystery_category")
    if mystery:
        lines.append(f"   🔮 Mystery: {mystery}")
    cat_mults = rules.get("category_multipliers", {})
    if cat_mults:
        mults = ", ".join(f"{c} x{m}" for c, m in cat_mults.items())
        lines.append(f"   ⚡ Bonus: {mults}")
    if rules.get("speed_bonus"):
        lines.append(f"   🏃 Speed: +{rules['speed_bonus']} pts")
    if rules.get("sudden_death"):
        lines.append(f"   💀 Modo Supervivencia")
    if rules.get("streak_multiplier", 1.0) > 1.0:
        lines.append(f"   🔥 Streak: x{rules['streak_multiplier']}")
    return "\n".join(lines)
```

### `/events` mejorado

Mostrar también: tipo de evento, horario diario (si aplica), reglas activas, estado (activo/pausado para admins).

```
🎉 <b>Eventos activos en este grupo:</b>

📌 <b>Copa Navideña</b>
   ⚡ x2.0 XP — ⏱ queda 12h 30m
   📝 Torneo épico de Stop
   🔤 Letra: M | ⏱ 45s | 🚫 Sin: Cosa
   📅 Tipo: Temporal

📌 <b>Noche de Países</b>
   ⚡ x5.0 XP — ⏱ queda 2h 15m
   🔤 Solo País | ⏱ 30s
   📅 Tipo: Diario (18:00-22:00, Lun-Vie)

⏸ <b>Torneo Verano</b> (PAUSADO)
   ⚡ x1.5 XP
   📅 Tipo: Permanente
```

### Mensaje de fin de juego mejorado

```
🏆 <b>¡Juego terminado!</b>

🏅 <b>Posiciones:</b>
  1. 🥇 Juan — 350 pts (+87 XP)
  2. 🥈 María — 280 pts (+65 XP)
  3. 🥉 Pedro — 210 pts (+45 XP)

🎉 <b>Evento: Copa Navideña</b> (x2.0 XP)
   ⚡ Bonus aplicados:
   • País x3: Juan +60, María +45
   • Respuesta única: +25 cada uno
   • Llenar todo: +50 Juan
   • Speed bonus: +30 Juan

Proporcioname todas las instrucciones, informacion, codigo, comandos, datos, detalles y todo lo necesario para esta fase, no hagas ninguna implementacion ni ningun cambio tu, dame las instrucciones, codigo, detalles y todo lo relativo mas estrategias, ejemplos, etc a mi que yo lo hago por favor. Nota: recuerda siempre leer el season-events-plan.md, definitions.md y agents.md para que te retroalimentes cuando necesites informacion de cualquier cosa. Y escribir cualquier informacion en el archivo correspondiente a la fase en desarrollo actual por ejemplo season-events-phases/season-phase9-guide.md. No omitas nada, piensa en todo y selecciona las mejores opciones, arquitecturas, tecnologias, todo que me sea gratis xfa :). 
---

## Resumen de Archivos

| Archivo | Acción | Complejidad | Fase |
|---|---|---|---|
| `src/db/models.py` | Modificar SeasonalEvent | Baja | 1 |
| `src/services/event_rules.py` | **Crear** | Media | 2 |
| `src/services/event_service.py` | Reescritura parcial | Alta | 3 |
| `src/handlers/admin/event_creator.py` | Reescritura + /editevent + /toggleevent | Alta | 4, 5 |
| `src/keyboards/event.py` | Reescritura | Media | 6 |
| `src/handlers/game/lobby.py` | Añadir callbacks de modo | Media | 7 |
| `src/services/game_orchestrator.py` | Modificar create_lobby, _do_start, LobbyState | Alta | 7 |
| `src/services/round_manager.py` | RoundState + propagar reglas | Media | 8, 9 |
| `src/services/score_engine.py` | Aplicar bonificaciones | Media | 8 |
| `migrations/versions/` | Nueva migración | Baja | 1 |

**Total estimado:** ~800-1000 líneas nuevas/modificadas.

---

# Expansión del Sistema de Reglas — Abanico Completo

## Categoría 1: Categorías

| Regla | Tipo | Default | Descripción |
|---|---|---|---|
| `categories_enabled` | `list[str]` | Todas las 8 | Categorías activas para el evento |
| `categories_disabled` | `list[str]` | `[]` | Categorías desactivadas (no se puntuan) |
| `category_multipliers` | `dict[str,float]` | `{}` | Multiplicador extra por categoría. Ej: `{"pais": 3.0}` |
| `hidden_categories` | `list[str]` | `[]` | Categorías ocultas hasta que termine la ronda (modo sorpresa) |
| `mystery_category` | `str \| None` | `null` | Una categoría que se revela solo al puntuar (1 solo) |
| `category_order` | `list[str] \| None` | `null` | Forzar orden específico de categorías (si se define, respeta este orden) |

---

## Categoría 2: Tiempo

| Regla | Tipo | Default | Descripción |
|---|---|---|---|
| `time_override` | `int \| None` | `null` (usa config grupo) | Segundos por ronda fijo |
| `time_decreasing` | `bool` | `false` | Cada ronda dura menos. Fórmula: `max(base - (round * amount), minimum)` |
| `time_decreasing_amount` | `int` | `5` | Segundos que disminuye por ronda (si `time_decreasing=true`) |
| `time_minimum` | `int` | `15` | Mínimo de segundos cuando `time_decreasing=true` |
| `speed_bonus` | `int` | `0` | Puntos extra por ser el primero en completar todas las categorías |
| `speed_bonus_window` | `int` | `0` | Segundos adicionales en los que aplica el bonus de velocidad. Ej: 10 = los primeros 10 segundos |

---

## Categoría 3: Letra

| Regla | Tipo | Default | Descripción |
|---|---|---|---|
| `forced_letter` | `str \| None` | `null` | Letra fija para TODAS las rondas del evento |
| `excluded_letters` | `list[str]` | `[]` | Letras que NO pueden usarse (ej: sin vocales) |
| `letter_sequence` | `list[str] \| None` | `null` | Secuencia predefinida de letras para cada ronda. Ej: `["M","R","S","P"]` = ronda 1=M, ronda 2=R, etc. Si se acaban, se repite |
| `vowel_forced` | `bool` | `false` | Si true, la letra debe ser una vocal (se elige de a,e,i,o,u) |

---

## Categoría 4: Puntuación

| Regla | Tipo | Default | Descripción |
|---|---|---|---|
| `no_duplicates_bonus` | `int` | `0` | Puntos extra por respuesta única (además de los 50 base) |
| `bonus_all_filled` | `int` | `0` | Puntos extra si el jugador llena TODAS las categorías activas |
| `streak_multiplier` | `float` | `1.0` | Multiplicador acumulado por racha de respuestas únicas consecutivas. Ej: 1.5 = +50% por cada ronda consecutiva con al menos 1 respuesta única |
| `penalty_empty` | `int` | `0` | Puntos que se restan por cada categoría vacía/inválida (valor negativo implícito) |
| `comeback_bonus` | `int` | `0` | Puntos extra para el jugador que va en último lugar al inicio de la ronda |
| `perfect_round_bonus` | `int` | `0` | Bonus masivo si TODOS los jugadores tienen TODAS las categorías únicas (ronda perfecta) |
| `shared_answer_penalty` | `int` | `0` | Penalización adicional cuando dos o más jugadores ponen la misma respuesta (se aplica a cada duplicado) |
| `double_points_last_round` | `bool` | `false` | La última ronda del evento da el doble de puntos |

---

## Categoría 5: Validación

| Regla | Tipo | Default | Descripción |
|---|---|---|---|
| `min_words_required` | `int` | `0` | Mínimo de categorías respondidas para que la ronda cuente |
| `min_word_length` | `int` | `0` | Longitud mínima de cada palabra (0 = sin mínimo) |
| `proper_nouns_only` | `bool` | `false` | Solo se aceptan nombres propios (validación estricta) |
| `no_repeat_words` | `bool` | `false` | No se permite usar la misma palabra en diferentes categorías |
| `require_all_different` | `bool` | `false` | Todas las respuestas de un jugador deben ser diferentes entre sí |
| `allow_dots_as_empty` | `bool` | `true` | Tratar "..." como vacío (default actual, configurable) |

---

## Categoría 6: Modo de Juego

| Regla | Tipo | Default | Descripción |
|---|---|---|---|
| `sudden_death` | `bool` | `false` | Si un jugador saca 0 en una ronda, queda eliminado |
| `sudden_death_threshold` | `int` | `0` | Puntaje mínimo para no ser eliminado en sudden death |
| `max_players` | `int \| None` | `null` | Límite de jugadores para el evento |
| `elimination_rounds` | `list[int] \| None` | `null` | Rondas en las que hay eliminación. Ej: `[3, 5]` = eliminación en ronda 3 y 5 |
| `collaborative` | `bool` | `false` | Modo equipos: los jugadores se emparejan y comparten puntaje |
| `wager_enabled` | `bool` | `false` | Los jugadores pueden apostar puntos antes de cada ronda |
| `wager_max_pct` | `int` | `50` | Porcentaje máximo de puntos que se puede apostar (0-100) |
| `answer_reveal` | `bool` | `false` | Al terminar la ronda, se revelan TODAS las respuestas de TODOS los jugadores |
| `no_stop` | `bool` | `false` | El botón Stop no está habilitado; la ronda termina SOLO por tiempo |
| `infinite_rounds` | `bool` | `false` | Las rondas continúan indefinidamente hasta que alguien presione Stop |

---

## Categoría 7: Horario y Recurrencia

| Regla | Tipo | Default | Descripción |
|---|---|---|---|
| `event_type` | `str` | `"one_time"` | `"one_time"` / `"daily_recurring"` / `"permanent"` |
| `daily_start_hour` | `int \| null` | `null` | Hora de inicio diario (0-23) |
| `daily_start_minute` | `int \| null` | `null` | Minuto de inicio (0-59) |
| `daily_end_hour` | `int \| null` | `null` | Hora de fin diario (0-23) |
| `daily_end_minute` | `int \| null` | `null` | Minuto de fin (0-59) |
| `active_days` | `list[str]` | `["mon","tue","wed","thu","fri","sat","sun"]` | Días de la semana activos |
| `timezone` | `str` | `"America/Argentina/Buenos_Aires"` | Zona horaria para cálculos diarios |

---

# 10 Eventos Personalizados — Propuestas Detalladas

---

## Evento 1: 🔥 Batalla de Categorías

> Solo 3-4 categorías activas con multiplicadores altos. Elige tus favoritas.

### Configuración

```json
{
  "categories_enabled": ["nombre", "color", "pais", "animal"],
  "categories_disabled": ["apellido", "fruta", "artista", "cosa"],
  "category_multipliers": {"pais": 3.0, "animal": 2.0},
  "time_override": 45,
  "bonus_all_filled": 75,
  "no_duplicates_bonus": 25
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | 🔥 Batalla de Categorías |
| Multiplicador base | x2.0 |
| Tipo | Temporal (24 horas) |
| Categorías | 4 de 8 activas |
| Tiempo por ronda | 45 segundos |
| Dificultad | ⭐⭐⭐ |

### Reglas especiales
- **País vale x3:** Cada respuesta de país se multiplica por 3额外 (sobre el x2 base del evento)
- **Animal vale x2:** Multiplicador adicional para animal
- **Bonus llenar todo:** +75 puntos si respondes las 4 categorías
- **Bonus única:** +25 puntos por respuesta que nadie más puso

### Estrategia
Concentra tu esfuerzo en País (vale 6x total = 2 base × 3 multiplier × 1 evento). Animal es el segundo más valioso. Color y Nombre son los "relleno" para completar el bonus.

---

## Evento 2: ⚡ Velocidad Extrema

> 15 segundos por ronda. ¡No hay tiempo para pensar!

### Configuración

```json
{
  "time_override": 15,
  "speed_bonus": 30,
  "speed_bonus_window": 8,
  "min_words_required": 4,
  "penalty_empty": -10,
  "double_points_last_round": true
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | ⚡ Velocidad Extrema |
| Multiplicador base | x1.5 |
| Tipo | Temporal (6 horas) |
| Categorías | 8 de 8 activas |
| Tiempo por ronda | 15 segundos |
| Dificultad | ⭐⭐⭐⭐ |

### Reglas especiales
- **15 segundos totales:** Puro reflejo, sin tiempo para搜索
- **Speed bonus:** +30 puntos si eres el primero en completar las 4+ categorías
- **Ventana de speed:** Solo los primeros 8 segundos cuentan para el bonus
- **Penalización vacío:** -10 puntos por cada categoría sin respuesta
- **Mínimo 4:** Debes responder al menos 4 categorías para que la ronda cuente
- **Última ronda doble:** La última ronda del evento vale 2x

### Estrategia
Velocidad pura. Prioriza las categorías que sabes rápido (Color, Fruta). No intentes ser perfecto — es mejor tener 6 respuestas correctas en 15 segundos que 8 con errores.

---

## Evento 3: 🚫 Letra Prohibida

> Las vocales están prohibidas. Solo consonantes.

### Configuración

```json
{
  "excluded_letters": ["A", "E", "I", "O", "U"],
  "categories_enabled": ["nombre", "apellido", "color", "fruta", "pais", "animal", "artista", "cosa"],
  "time_override": 75,
  "no_duplicates_bonus": 50,
  "bonus_all_filled": 100,
  "require_all_different": true
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | 🚫 Letra Prohibida |
| Multiplicador base | x1.0 |
| Tipo | Diario Recurrente (19:00-23:00, Lun-Vie) |
| Categorías | 8 de 8 activas |
| Tiempo por ronda | 75 segundos |
| Dificultad | ⭐⭐⭐⭐⭐ |

### Reglas especiales
- **Sin vocales:** No puedes usar palabras que empiecen con A, E, I, O, U
- **Argentina NO vale** (empieza con A), **Brasil SÍ** (empieza con B)
- **Bonus única enorme:** +50 puntos por respuesta que nadie más puso
- **Bonus llenar todo:** +100 puntos si respondes las 8 categorías
- **Todas diferentes:** No puedes repetir la misma palabra en distintas categorías
- **75 segundos:** Tiempo extra porque es difícil encontrar sin vocales

### Ejemplos válidos
- Nombre: Bruno, Clara, Pedro ✅
- País: Brasil, Chile, Egipto, Fiyi ✅
- Color: Verde, Gris ✅
- Fruta: Plátano, Limón ✅
- **NO:** Ana, Argentina, Azul, Lima ❌ (empiezan con vocal)

### Estrategia
Piensa rápido en países cortos (Chile, Egipto, Fiyi). Los colores con consonante son fáciles (Gris, Negro). Nombres son los más restrictivos — ten una lista mental de nombres sin vocal.

---

## Evento 4: 💀 Modo Supervivencia

> Si sacas 0 en una ronda, quedas eliminado.

### Configuración

```json
{
  "sudden_death": true,
  "sudden_death_threshold": 1,
  "time_override": 60,
  "categories_enabled": ["nombre", "color", "pais", "animal", "fruta", "artista", "apellido", "cosa"],
  "no_duplicates_bonus": 25,
  "streak_multiplier": 1.25
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | 💀 Modo Supervivencia |
| Multiplicador base | x1.5 |
| Tipo | Temporal (12 horas) |
| Categorías | 8 de 8 activas |
| Tiempo por ronda | 60 segundos |
| Dificultad | ⭐⭐⭐⭐ |

### Reglas especiales
- **Sudden death:** Si sacas 0 puntos en una ronda, quedas eliminado del juego
- **Threshold mínimo:** Necesitas al menos 1 punto para sobrevivir
- **Streak acumulativo:** Cada ronda consecutiva con al menos 1 respuesta única da x1.25 adicional
- **Ronda 1:** x1.0 → **Ronda 2:** x1.25 → **Ronda 3:** x1.56 → **Ronda 4:** x1.95

### Estrategia
La regla de oro: **nunca dejes una categoría vacía.** Es mejor poner cualquier cosa que arriesgarse a 0 puntos y la eliminación. El streak es poderoso — si mantienes rachas largas, tus puntos se multiplican exponencialmente.

---

## Evento 5: ⏳ Tormenta de Tiempo

> El tiempo disminuye cada ronda. Empieza en 60s, termina en 15s.

### Configuración

```json
{
  "time_decreasing": true,
  "time_decreasing_amount": 7,
  "time_minimum": 15,
  "categories_enabled": ["nombre", "color", "pais", "animal", "fruta", "artista", "apellido", "cosa"],
  "speed_bonus": 20,
  "speed_bonus_window": 5,
  "double_points_last_round": true
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | ⏳ Tormenta de Tiempo |
| Multiplicador base | x1.5 |
| Tipo | Temporal (8 horas) |
| Categorías | 8 de 8 activas |
| Tiempo por ronda | Decreciente (60s → 15s) |
| Dificultad | ⭐⭐⭐ |

### Progresión del tiempo

| Ronda | Tiempo |
|---|---|
| 1 | 60s |
| 2 | 53s |
| 3 | 46s |
| 4 | 39s |
| 5 | 32s |
| 6 | 25s |
| 7 | 18s |
| 8+ | 15s (mínimo) |

### Reglas especiales
- **Tiempo decreciente:** Cada ronda pierdes 7 segundos
- **Speed bonus:** +20 puntos si completas todo en los primeros 5 segundos
- **Última ronda doble:** La ronda más rápida vale 2x
- **Mínimo 15s:** Nunca baja de 15 segundos

### Estrategia
Las primeras rondas son para acumular puntos con calma. A partir de la ronda 5, la presión es brutal. Ten respuestas "seguras" listas para las rondas rápidas. La última ronda vale doble pero solo tienes 15 segundos — prioriza calidad sobre cantidad.

---

## Evento 6: 🎲 Doble o Nada

> Apostar tus puntos antes de cada ronda. Gana el doble o pierde lo apostado.

### Configuración

```json
{
  "wager_enabled": true,
  "wager_max_pct": 50,
  "time_override": 45,
  "categories_enabled": ["nombre", "color", "pais", "animal"],
  "categories_disabled": ["apellido", "fruta", "artista", "cosa"],
  "category_multipliers": {"pais": 2.0},
  "penalty_empty": -15
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | 🎲 Doble o Nada |
| Multiplicador base | x1.0 |
| Tipo | Temporal (6 horas) |
| Categorías | 4 de 8 activas |
| Tiempo por ronda | 45 segundos |
| Dificultad | ⭐⭐⭐⭐ |

### Reglas especiales
- **Sistema de apuestas:** Antes de cada ronda, apuntas un % de tus puntos actuales
- **Si aciertas (más de 0 pts):** Ganas el doble de lo apostado
- **Si fallas (0 pts):** Pierdes lo apostado
- **Máximo 50%:** No puedes apostar más del 50% de tus puntos
- **Solo 4 categorías:** País vale x2, las demás x1
- **Penalización vacío:** -15 puntos por categoría vacía

### Ejemplo
- Tienes 200 puntos
- Apuestas 50% = 100 puntos
- Si sacas 1+ punto: ganas 200 puntos (total: 300)
- Si sacas 0 puntos: pierdes 100 puntos (total: 100)

### Estrategia
Apuesta alto cuando estás seguro de tus respuestas. Apuesta bajo (o nada) en rondas donde no estás seguro. País vale el doble — si sabes países, apuesta fuerte en esas rondas.

---

## Evento 7: 🎭 Categoría Misteriosa

> Una categoría está oculta hasta que termine la ronda. Adivina cuál es.

### Configuración

```json
{
  "hidden_categories": ["cosa"],
  "mystery_category": "artista",
  "time_override": 60,
  "categories_enabled": ["nombre", "color", "pais", "animal", "fruta", "artista", "apellido", "cosa"],
  "no_duplicates_bonus": 30,
  "bonus_all_filled": 50
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | 🎭 Categoría Misteriosa |
| Multiplicador base | x1.5 |
| Tipo | Temporal (24 horas) |
| Categorías | 7 visibles + 1 oculta + 1 mystery |
| Tiempo por ronda | 60 segundos |
| Dificultad | ⭐⭐⭐ |

### Reglas especiales
- **Categoría oculta (Cosa):** No ves el título "Cosa" en la lista, pero debes escribir algo para ella. Adivina qué categoría es.
- **Categoría mystery (Artista):** Se revela solo al puntuar. Si acertaste (pusiste un artista real), vale x2
- **Bonus única:** +30 puntos por respuesta que nadie más puso
- **Bonus llenar todo:** +50 puntos si respondes las 8 categorías (incluyendo la oculta)

### Ejemplo de mensaje de ronda
```
🔤 Letra: M
⏱ 60 segundos

  1. Nombre: ...
  2. Color: ...
  3. País: ...
  4. Animal: ...
  5. Fruta: ...
  6. Artista: ...
  7. Apellido: ...
  8. ??? (categoría oculta): ...
```

### Estrategia
La categoría oculta suele ser "Cosa" — piensa en objetos que empiecen con la letra. La mystery (Artista) vale x2 — si sabes artistas, es tu oportunidad de brillar.

---

## Evento 8: 🌍 Noche de Países

> Solo la categoría País. Repetido las veces que haga falta.

### Configuración

```json
{
  "categories_enabled": ["pais"],
  "categories_disabled": ["nombre", "apellido", "color", "fruta", "animal", "artista", "cosa"],
  "time_override": 30,
  "category_multipliers": {"pais": 5.0},
  "no_duplicates_bonus": 100,
  "min_word_length": 4,
  "require_all_different": true,
  "infinite_rounds": true,
  "no_stop": false
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | 🌍 Noche de Países |
| Multiplicador base | x1.0 |
| Tipo | Diario Recurrente (20:00-23:00, Mié y Vie) |
| Categorías | Solo País |
| Tiempo por ronda | 30 segundos |
| Dificultad | ⭐⭐ |

### Reglas especiales
- **Solo País:** Cada ronda solo es la categoría País
- **x5 multiplicador:** Cada país válido vale 5x (50 × 5 = 250 puntos base)
- **Bonus única ENORME:** +100 puntos por país que nadie más puso (total: 350 pts)
- **Mínimo 4 letras:** No se aceptan países de 3 letras (ej: "Fiyi" sí, "Oman" sí, "Irán" no)
- **Todos diferentes:** No puedes repetir el mismo país en diferentes rondas
- **Rondas infinitas:** Las rondas continúan hasta que alguien presione Stop
- **30 segundos:** Rápido — solo un país por ronda

### Estrategia
Conocimiento geográfico puro. Los países raros (Fiyi, Nauru, Chad) dan más puntos porque son únicos. Los comunes (Brasil, Chile, México) dan menos porque todos los ponen. Rondas infinitas = el que más aguanta gana.

---

## Evento 9: 🏃 Modo Maratón

> 20 rondas sin parar. Streak masivo. El más resistente gana.

### Configuración

```json
{
  "categories_enabled": ["nombre", "color", "pais", "animal", "fruta", "artista", "apellido", "cosa"],
  "time_override": 45,
  "streak_multiplier": 1.5,
  "no_duplicates_bonus": 15,
  "penalty_empty": -5,
  "double_points_last_round": true,
  "sudden_death": false,
  "answer_reveal": true
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | 🏃 Modo Maratón |
| Multiplicador base | x1.0 |
| Tipo | Temporal (6 horas) |
| Categorías | 8 de 8 activas |
| Tiempo por ronda | 45 segundos |
| Dificultad | ⭐⭐⭐ |

### Reglas especiales
- **20 rondas fijas:** El juego dura exactamente 20 rondas
- **Streak x1.5:** Cada ronda consecutiva con al menos 1 respuesta única da x1.5 adicional
  - Ronda 1-3: x1.0
  - Ronda 4-6: x1.5
  - Ronda 7-9: x2.25
  - Ronda 10-12: x3.37
  - Ronda 13+: exponencial
- **Reveal:** Al final de cada ronda se revelan TODAS las respuestas (modo transparente)
- **Penalización vacío:** -5 puntos por categoría sin respuesta
- **Última ronda doble:** La ronda 20 vale 2x

### Estrategia
Resistencia mental. El streak es la clave — si mantienes rachas largas, tus puntos se disparan exponencialmente. Prioriza constancia sobre perfección. El reveal te permite ver qué ponen tus rivales y ajustar estrategia.

---

## Evento 10: 👥 Modo Equipos (Beta)

> Dos equipos. Cada jugador responde y el puntaje se combina.

### Configuración

```json
{
  "collaborative": true,
  "max_players": 8,
  "categories_enabled": ["nombre", "color", "pais", "animal", "fruta", "artista", "apellido", "cosa"],
  "time_override": 75,
  "no_duplicates_bonus": 50,
  "bonus_all_filled": 100,
  "answer_reveal": true
}
```

### Detalles

| Campo | Valor |
|---|---|
| Nombre | 👥 Modo Equipos (Beta) |
| Multiplicador base | x1.5 |
| Tipo | Temporal (4 horas) |
| Categorías | 8 de 8 activas |
| Tiempo por ronda | 75 segundos |
| Dificultad | ⭐⭐⭐ |
| Máximo jugadores | 8 (4v4) |

### Reglas especiales
- **Equipos de 4:** 8 jugadores se dividen en 2 equipos
- **Puntaje combinado:** Cada jugador responde individualmente pero el puntaje se suma al equipo
- **75 segundos:** Tiempo extra para coordinar mentalmente con tu equipo
- **Bonus llenar todo:** +100 puntos por cada jugador del equipo que llene las 8 categorías
- **Reveal:** Al final de cada ronda se revelan todas las respuestas
- **Bonus única:** +50 puntos por respuesta única (dentro del equipo, no global)

### Cómo funciona
1. Se asignan 2 equipos al azar (o por elección del host)
2. Cada jugador responde individualmente
3. Al final de la ronda, se suman los puntos de cada equipo
4. Gana el equipo con más puntos acumulados después de las rondas

### Estrategia
Coordinación implícita — si tu equipo sabe que la letra es "M", entre todos pueden cubrir más categorías. Los puntos únicos dentro del equipo dan bonus — intenta no duplicar respuestas con tu compañero.

---

## Tabla Resumen: Reglas por Evento

| Evento | Categorías | Tiempo | Letra | Puntuación | Modo | Dificultad |
|---|---|---|---|---|---|---|
| 🔥 Batalla Categorías | 4 de 8 (x2-x3) | 45s | Normal | Bonus llenar todo | Normal | ⭐⭐⭐ |
| ⚡ Velocidad Extrema | 8 | 15s | Normal | Speed bonus, penalty | Normal | ⭐⭐⭐⭐ |
| 🚫 Letra Prohibida | 8 | 75s | Sin vocales | Bonus únicos | Normal | ⭐⭐⭐⭐⭐ |
| 💀 Supervivencia | 8 | 60s | Normal | Streak x1.25 | Sudden death | ⭐⭐⭐⭐ |
| ⏳ Tormenta Tiempo | 8 | Decreciente | Normal | Speed + doble última | Normal | ⭐⭐⭐ |
| 🎲 Doble o Nada | 4 (x2 país) | 45s | Normal | Wager system | Apostar | ⭐⭐⭐⭐ |
| 🎭 Categoría Misteriosa | 7 + 1 oculta | 60s | Normal | Mystery x2 | Normal | ⭐⭐⭐ |
| 🌍 Noche Países | 1 (x5) | 30s | Normal | 100 por única | Normal | ⭐⭐ |
| 🏃 Maratón | 8 | 45s | Normal | Streak x1.5 | Transparente | ⭐⭐⭐ |
| 👥 Equipos | 8 | 75s | Normal | Compartido | Collaborative | ⭐⭐⭐ |
