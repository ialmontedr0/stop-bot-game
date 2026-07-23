# Fase 2: Helper `EventRules` — Parseo y Validación de Reglas

## Objetivo

Crear una clase `EventRules` que parsee el JSON de la columna `rules` de `SeasonalEvent` y exponga propiedades tipadas, validadas, con defaults correctos y métodos de conveniencia para que `RoundManager`, `ScoreEngine` y `GameOrchestrator` consuman las reglas sin importar JSON directamente.

---

## Archivo a crear

```
backend/src/services/event_rules.py
```

**No modifica ningún archivo existente.** Solo se crea este archivo nuevo.

---

## Decisión de diseño: `dataclass` vs `pydantic`

Se usa `dataclasses.dataclass` (stdlib) en vez de pydantic porque:

1. **Cero dependencias额外** — no se agrega nada a requirements
2. **Es una clase pura** — solo parseo y defaults, sin validación HTTP/BD
3. **Consistencia** — `RoundState` en `round_manager.py:67` ya usa `@dataclass`
4. **Rendimiento** — más rápido que pydantic para instanciación simple
5. **`asdict()`** — stdlib ya tiene la función para serializar

---

## Convención de nombres de categorías

**PROBLEMA detectado:** Existe inconsistencia de case en el código actual:

| Ubicación | Formato | Ejemplo |
|---|---|---|
| `keyboards/settings.py:ALL_CATEGORIES` | Capitalizado | `"Nombre"`, `"País"` |
| `round_manager.py:CATEGORIES` | Capitalizado | `"Nombre"`, `"País"` |
| `round_manager.py:_PLURAL_MAP` | Capitalizado | `"paises" → "País"` |
| `GroupConfig.categories` (BD) | Lowercase | `"nombre,pais,color"` |
| `spell_corrector.py:DB_CATEGORIES` | Lowercase | `"nombre"`, `"pais"` |

**Decisión: `EventRules` usa el formato CAPITALIZADO** (`"Nombre"`, `"País"`, etc.) porque:
- Es lo que se muestra al usuario en el teclado y en los mensajes
- Es lo que usa `CATEGORIES` en `round_manager.py:38`
- Es lo que se pasa a `start_round(categories=...)` 
- La conversión lowercase→capitalizado ocurre en `GroupConfig` al leer de BD (`game_orchestrator.py:534`)

La constante `ALL_CATEGORIES` se importa de `keyboards/settings.py`.

---

## Constantes del juego (para referencia)

```python
# score_engine.py:15-16
UNIQUE_POINTS = 50
FIRST_COMPLETER_BONUS = 10

# round_manager.py:35-36
TOTAL_ROUNDS = 5
LETTER_TIMEOUT = 15

# round_manager.py:63
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
```

---

## Código completo del archivo

Crear `backend/src/services/event_rules.py` con este contenido exacto:

```python
"""EventRules — Dataclass para parsear, validar y consumir reglas de eventos.

Este módulo NO tiene dependencias externas. Solo usa stdlib (dataclasses, json).
Se importa desde round_manager, score_engine y game_orchestrator.

La constante ALL_CATEGORIES se importa de keyboards/settings.py para
mantener una sola fuente de verdad de las categorías del juego.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from src.keyboards.settings import ALL_CATEGORIES

logger = logging.getLogger(__name__)

# ── Defaults de cada campo ───────────────────────────────────────────
# Cada default refleja el comportamiento ACTUAL del juego sin eventos.
# Si un campo tiene default None, significa "no activo / usar config del grupo".

_DEFAULTS: dict[str, Any] = {
    # Categorías
    "categories_enabled": list(ALL_CATEGORIES),
    "categories_disabled": [],
    "category_multipliers": {},
    "hidden_categories": [],
    "mystery_category": None,
    "category_order": None,
    # Tiempo
    "time_override": None,
    "time_decreasing": False,
    "time_decreasing_amount": 5,
    "time_minimum": 15,
    "speed_bonus": 0,
    "speed_bonus_window": 0,
    # Letra
    "forced_letter": None,
    "excluded_letters": [],
    "letter_sequence": None,
    "vowel_forced": False,
    # Puntuación
    "no_duplicates_bonus": 0,
    "bonus_all_filled": 0,
    "streak_multiplier": 1.0,
    "penalty_empty": 0,
    "comeback_bonus": 0,
    "perfect_round_bonus": 0,
    "shared_answer_penalty": 0,
    "double_points_last_round": False,
    # Validación
    "min_words_required": 0,
    "min_word_length": 0,
    "proper_nouns_only": False,
    "no_repeat_words": False,
    "require_all_different": False,
    "allow_dots_as_empty": True,
    # Modo de juego
    "sudden_death": False,
    "sudden_death_threshold": 1,
    "max_players": None,
    "elimination_rounds": None,
    "collaborative": False,
    "wager_enabled": False,
    "wager_max_pct": 50,
    "answer_reveal": False,
    "no_stop": False,
    "infinite_rounds": False,
}

# Categorías válidas del juego (para validación en from_json)
_VALID_CATEGORIES = set(ALL_CATEGORIES)

# Vocales para vowel_forced
_VOWELS = set("AEIOU")


@dataclass
class EventRules:
    """Reglas personalizables de un evento de temporada.

    Todos los campos tienen defaults que replican el comportamiento
    normal del juego. Cuando event.rules es NULL en la BD, se usa
    EventRules() y el juego funciona exactamente como antes.
    """

    # ── Categorías ──────────────────────────────────────────────────
    categories_enabled: list[str] = field(default_factory=lambda: list(ALL_CATEGORIES))
    categories_disabled: list[str] = field(default_factory=list)
    category_multipliers: dict[str, float] = field(default_factory=dict)
    hidden_categories: list[str] = field(default_factory=list)
    mystery_category: str | None = None
    category_order: list[str] | None = None

    # ── Tiempo ──────────────────────────────────────────────────────
    time_override: int | None = None
    time_decreasing: bool = False
    time_decreasing_amount: int = 5
    time_minimum: int = 15
    speed_bonus: int = 0
    speed_bonus_window: int = 0

    # ── Letra ───────────────────────────────────────────────────────
    forced_letter: str | None = None
    excluded_letters: list[str] = field(default_factory=list)
    letter_sequence: list[str] | None = None
    vowel_forced: bool = False

    # ── Puntuación ──────────────────────────────────────────────────
    no_duplicates_bonus: int = 0
    bonus_all_filled: int = 0
    streak_multiplier: float = 1.0
    penalty_empty: int = 0
    comeback_bonus: int = 0
    perfect_round_bonus: int = 0
    shared_answer_penalty: int = 0
    double_points_last_round: bool = False

    # ── Validación ──────────────────────────────────────────────────
    min_words_required: int = 0
    min_word_length: int = 0
    proper_nouns_only: bool = False
    no_repeat_words: bool = False
    require_all_different: bool = False
    allow_dots_as_empty: bool = True

    # ── Modo de juego ───────────────────────────────────────────────
    sudden_death: bool = False
    sudden_death_threshold: int = 1
    max_players: int | None = None
    elimination_rounds: list[int] | None = None
    collaborative: bool = False
    wager_enabled: bool = False
    wager_max_pct: int = 50
    answer_reveal: bool = False
    no_stop: bool = False
    infinite_rounds: bool = False

    # ── Serialización ───────────────────────────────────────────────

    @classmethod
    def from_json(cls, json_str: str | None) -> EventRules:
        """Parsea un JSON string a EventRules.

        Si json_str es None o vacío, retorna EventRules() con todos
        los defaults (comportamiento normal del juego).

        Valores no reconocidos en el JSON se ignoran silenciosamente.
        Valores de tipos incorrectos se reemplazan por el default.
        """
        if not json_str:
            return cls()

        try:
            data: dict = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            logger.warning("EventRules: JSON inválido, usando defaults: %s", json_str[:100])
            return cls()

        if not isinstance(data, dict):
            logger.warning("EventRules: JSON no es dict, usando defaults")
            return cls()

        return cls(
            # ── Categorías ──────────────────────────────────────
            categories_enabled=_safe_list_str(
                data, "categories_enabled", _DEFAULTS["categories_enabled"], _VALID_CATEGORIES
            ),
            categories_disabled=_safe_list_str(
                data, "categories_disabled", _DEFAULTS["categories_disabled"], _VALID_CATEGORIES
            ),
            category_multipliers=_safe_dict_float(data, "category_multipliers", _DEFAULTS["category_multipliers"]),
            hidden_categories=_safe_list_str(
                data, "hidden_categories", _DEFAULTS["hidden_categories"], _VALID_CATEGORIES
            ),
            mystery_category=_safe_optional_str_in(
                data, "mystery_category", _VALID_CATEGORIES
            ),
            category_order=_safe_optional_list_str(
                data, "category_order", _VALID_CATEGORIES
            ),
            # ── Tiempo ──────────────────────────────────────────
            time_override=_safe_optional_int_range(data, "time_override", 5, 300),
            time_decreasing=_safe_bool(data, "time_decreasing"),
            time_decreasing_amount=_safe_int_range(data, "time_decreasing_amount", 1, 30, 5),
            time_minimum=_safe_int_range(data, "time_minimum", 5, 60, 15),
            speed_bonus=_safe_int_range(data, "speed_bonus", 0, 200, 0),
            speed_bonus_window=_safe_int_range(data, "speed_bonus_window", 0, 30, 0),
            # ── Letra ───────────────────────────────────────────
            forced_letter=_safe_forced_letter(data),
            excluded_letters=_safe_excluded_letters(data),
            letter_sequence=_safe_optional_list_str(data, "letter_sequence"),
            vowel_forced=_safe_bool(data, "vowel_forced"),
            # ── Puntuación ──────────────────────────────────────
            no_duplicates_bonus=_safe_int_range(data, "no_duplicates_bonus", 0, 200, 0),
            bonus_all_filled=_safe_int_range(data, "bonus_all_filled", 0, 200, 0),
            streak_multiplier=_safe_float_range(data, "streak_multiplier", 1.0, 5.0, 1.0),
            penalty_empty=_safe_int_range(data, "penalty_empty", -200, 0, 0),
            comeback_bonus=_safe_int_range(data, "comeback_bonus", 0, 100, 0),
            perfect_round_bonus=_safe_int_range(data, "perfect_round_bonus", 0, 200, 0),
            shared_answer_penalty=_safe_int_range(data, "shared_answer_penalty", -200, 0, 0),
            double_points_last_round=_safe_bool(data, "double_points_last_round"),
            # ── Validación ──────────────────────────────────────
            min_words_required=_safe_int_range(data, "min_words_required", 0, 8, 0),
            min_word_length=_safe_int_range(data, "min_word_length", 0, 20, 0),
            proper_nouns_only=_safe_bool(data, "proper_nouns_only"),
            no_repeat_words=_safe_bool(data, "no_repeat_words"),
            require_all_different=_safe_bool(data, "require_all_different"),
            allow_dots_as_empty=_safe_bool(data, "allow_dots_as_empty", default=True),
            # ── Modo de juego ───────────────────────────────────
            sudden_death=_safe_bool(data, "sudden_death"),
            sudden_death_threshold=_safe_int_range(data, "sudden_death_threshold", 0, 50, 1),
            max_players=_safe_optional_int_range(data, "max_players", 2, 100),
            elimination_rounds=_safe_optional_list_int(data, "elimination_rounds"),
            collaborative=_safe_bool(data, "collaborative"),
            wager_enabled=_safe_bool(data, "wager_enabled"),
            wager_max_pct=_safe_int_range(data, "wager_max_pct", 1, 100, 50),
            answer_reveal=_safe_bool(data, "answer_reveal"),
            no_stop=_safe_bool(data, "no_stop"),
            infinite_rounds=_safe_bool(data, "infinite_rounds"),
        )

    def to_json(self) -> str | None:
        """Serializa a JSON string, omitiendo campos con valor default.

        Retorna None si TODAS las reglas son default (equivalente a
        no tener reglas personalizadas). Esto mantiene la BD limpia.
        """
        d = asdict(self)
        non_default = {}
        for key, value in d.items():
            default_val = _DEFAULTS.get(key)
            if value != default_val:
                non_default[key] = value
        return json.dumps(non_default, ensure_ascii=False) if non_default else None

    # ── Métodos de conveniencia ─────────────────────────────────────

    def get_active_categories(self) -> list[str]:
        """Categorías efectivas: enabled menos disabled.

        Ejemplo:
            enabled=["Nombre","Color","País","Fruta"]
            disabled=["Fruta"]
            → ["Nombre","Color","País"]
        """
        disabled = set(self.categories_disabled)
        return [c for c in self.categories_enabled if c not in disabled]

    def get_category_multiplier(self, category: str) -> float:
        """Multiplicador de puntos para una categoría (default 1.0)."""
        return self.category_multipliers.get(category, 1.0)

    def is_category_hidden(self, category: str) -> bool:
        """True si la categoría está oculta hasta fin de ronda."""
        return category in self.hidden_categories

    def is_letter_forced(self) -> bool:
        """True si hay letra forzada (manual o por sequence)."""
        return self.forced_letter is not None or self.letter_sequence is not None

    def get_round_time(self, default: int) -> int:
        """Tiempo efectivo de la ronda.

        Si hay time_override, lo usa. Si no, retorna el default del grupo.
        """
        return self.time_override if self.time_override is not None else default

    def get_round_time_for_number(self, round_number: int, default: int) -> int:
        """Tiempo para una ronda específica, considerando time_decreasing.

        Si time_decreasing es False, se comporta igual que get_round_time.
        Si es True, calcula: base - (round_number * amount), con mínimo.

        Ejemplo con base=60, amount=5, minimum=15:
            Ronda 1: 60 - (1*5) = 55
            Ronda 5: 60 - (5*5) = 35
            Ronda 10: 60 - (10*5) = 10 → 15 (mínimo)
        """
        if not self.time_decreasing:
            return self.get_round_time(default)

        base = self.time_override if self.time_override is not None else default
        calculated = base - (round_number * self.time_decreasing_amount)
        return max(calculated, self.time_minimum)

    def get_letter_for_round(self, round_number: int) -> str | None:
        """Letra para una ronda específica.

        Prioridad:
        1. Si hay letter_sequence, usa la letra en esa posición (cíclico)
        2. Si hay forced_letter, retorna esa letra
        3. Si no, retorna None (se elige aleatoria)
        """
        if self.letter_sequence:
            if not self.letter_sequence:
                return None
            idx = (round_number - 1) % len(self.letter_sequence)
            return self.letter_sequence[idx]
        return self.forced_letter

    def get_random_letters_excluded(self) -> list[str]:
        """Letras que deben excluirse de la selección aleatoria.

        Incluye excluded_letters y la forced_letter (si existe, no tiene
        sentido excluirla porque ya está forzada).
        """
        return list(self.excluded_letters)

    def has_rules(self) -> bool:
        """True si hay alguna regla personalizada activa.

        Equivale a: to_json() is not None
        pero más eficiente (no serializa todo el dict).
        """
        return any(
            asdict(self)[key] != _DEFAULTS[key]
            for key in _DEFAULTS
        )

    def merge_with(self, other: EventRules) -> EventRules:
        """Crea un nuevo EventRules combinando esta instancia con otra.

        Los campos de 'other' tienen prioridad sobre los de 'self'
        solo si 'other' tiene un valor no-default para ese campo.

        Útil para: reglas globales + override por grupo.
        """
        base = asdict(self)
        override = asdict(other)
        merged = {}
        for key in _DEFAULTS:
            if override[key] != _DEFAULTS[key]:
                merged[key] = override[key]
            else:
                merged[key] = base[key]
        return EventRules(**merged)


# ── Funciones de parseo seguro ────────────────────────────────────────
# Estas funciones extraen valores de un dict con validación de tipo
# y rango. Si el valor es inválido, retornan el default.
# Se mantienen como funciones privadas del módulo (prefijo _).

def _safe_bool(data: dict, key: str, *, default: bool = False) -> bool:
    val = data.get(key)
    if isinstance(val, bool):
        return val
    return default


def _safe_int_range(data: dict, key: str, min_val: int, max_val: int, default: int) -> int:
    val = data.get(key)
    if isinstance(val, int) and not isinstance(val, bool):
        return max(min_val, min(max_val, val))
    return default


def _safe_float_range(data: dict, key: str, min_val: float, max_val: float, default: float) -> float:
    val = data.get(key)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return max(min_val, min(max_val, float(val)))
    return default


def _safe_optional_int_range(data: dict, key: str, min_val: int, max_val: int) -> int | None:
    val = data.get(key)
    if val is None:
        return None
    if isinstance(val, int) and not isinstance(val, bool):
        return max(min_val, min(max_val, val))
    return None


def _safe_optional_str_in(data: dict, key: str, valid: set[str]) -> str | None:
    val = data.get(key)
    if val is None:
        return None
    if isinstance(val, str) and val in valid:
        return val
    return None


def _safe_list_str(
    data: dict, key: str, default: list[str], valid: set[str] | None = None
) -> list[str]:
    val = data.get(key)
    if not isinstance(val, list):
        return list(default) if not isinstance(default, list) else default
    result = []
    for item in val:
        if isinstance(item, str):
            if valid is None or item in valid:
                result.append(item)
    return result if result else list(default) if not isinstance(default, list) else default


def _safe_optional_list_str(
    data: dict, key: str, valid: set[str] | None = None
) -> list[str] | None:
    val = data.get(key)
    if val is None:
        return None
    if not isinstance(val, list):
        return None
    result = []
    for item in val:
        if isinstance(item, str):
            if valid is None or item in valid:
                result.append(item)
    return result if result else None


def _safe_optional_list_int(data: dict, key: str) -> list[int] | None:
    val = data.get(key)
    if val is None:
        return None
    if not isinstance(val, list):
        return None
    result = []
    for item in val:
        if isinstance(item, int) and not isinstance(item, bool):
            result.append(item)
    return result if result else None


def _safe_dict_float(data: dict, key: str, default: dict[str, float]) -> dict[str, float]:
    val = data.get(key)
    if not isinstance(val, dict):
        return dict(default)
    result = {}
    for k, v in val.items():
        if isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool):
            if valid_category := (k in _VALID_CATEGORIES):
                result[k] = max(0.1, min(10.0, float(v)))
    return result if result else dict(default)


def _safe_forced_letter(data: dict) -> str | None:
    """Extrae y valida forced_letter: debe ser 1 carácter A-Z o Ñ."""
    val = data.get("forced_letter")
    if val is None:
        return None
    if isinstance(val, str) and len(val) == 1 and val.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZÑ":
        return val.upper()
    return None


def _safe_excluded_letters(data: dict) -> list[str]:
    """Extrae y valida excluded_letters: lista de 1 carácter A-Z/Ñ."""
    val = data.get("excluded_letters")
    if not isinstance(val, list):
        return []
    result = []
    for item in val:
        if isinstance(item, str) and len(item) == 1 and item.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZÑ":
            result.append(item.upper())
    return result
```

---

## Explicación de cada sección

### 1. Constante `_DEFAULTS`

```python
_DEFAULTS: dict[str, Any] = {
    "categories_enabled": list(ALL_CATEGORIES),
    ...
}
```

**Por qué existe:** Es la fuente de verdad de qué valor significa "sin personalización". Se usa en:
- `from_json()` — para cada campo con `data.get("key", _DEFAULTS["key"])`
- `to_json()` — para filtrar valores default y no inflar el JSON
- `has_rules()` — para comparar si hay algo no-default

**Por qué no está dentro de la clase:** Porque `asdict()` no puede compararse contra una instancia (los `field(default_factory=...)` crean nuevas listas cada vez). `_DEFAULTS` es un dict plano que se puede comparar directamente.

### 2. `from_json(json_str)`

```python
@classmethod
def from_json(cls, json_str: str | None) -> EventRules:
```

**Flujo:**
1. Si `json_str` es None/vacío → retorna `cls()` (defaults normales)
2. Intenta `json.loads()` — si falla, log warning y retorna defaults
3. Para cada campo, extrae del dict con validación de tipo y rango
4. Si un valor es inválido, usa el default de `_DEFAULTS`

**Validaciones que aplica:**
- `_safe_bool()` — solo acepta `bool`, no `int`
- `_safe_int_range()` — acepta `int`, no `bool`, clamp a [min, max]
- `_safe_float_range()` — acepta `int | float`, no `bool`, clamp
- `_safe_forced_letter()` — 1 carácter A-Z o Ñ, uppercased
- `_safe_excluded_letters()` — lista de 1 carácter A-Z/Ñ uppercased
- `_safe_list_str()` — filtra items que no son str o no están en `_VALID_CATEGORIES`
- `_safe_dict_float()` — keys deben ser categorías válidas, values clamp a [0.1, 10.0]

**Ejemplo de JSON inválido manejado:**
```python
EventRules.from_json('{"time_override": "60"}')  # str → default None
EventRules.from_json('{"time_override": 999}')    # 999 > 300 → 300
EventRules.from_json('{"forced_letter": "ABC"}')   # len > 1 → None
EventRules.from_json('not json')                   # JSONDecodeError → defaults
EventRules.from_json(None)                         # None → defaults
```

### 3. `to_json()`

```python
def to_json(self) -> str | None:
```

**Flujo:**
1. Convierte la instancia a dict con `asdict(self)`
2. Compara cada campo contra `_DEFAULTS[key]`
3. Solo incluye campos con valor diferente al default
4. Si no hay nada no-default → retorna `None`

**Ejemplo:**
```python
rules = EventRules(time_override=15, speed_bonus=30)
json_str = rules.to_json()
# → '{"time_override": 15, "speed_bonus": 30}'
# No incluye categories_enabled, no_duplicates_bonus, etc. porque son default
```

**Por qué filtra defaults:** Para mantener la BD limpia. Si un evento solo tiene `time_override=15`, el JSON en la BD es solo `{"time_override":15}` (~25 bytes) en vez de un JSON completo con 40 campos (~800 bytes).

### 4. Métodos de conveniencia

| Método | Retorna | Cuándo se usa |
|---|---|---|
| `get_active_categories()` | `list[str]` | `round_manager.py` al formatear categorías de la ronda |
| `get_category_multiplier(cat)` | `float` | `score_engine.py` al calcular puntos por categoría |
| `is_category_hidden(cat)` | `bool` | `round_manager.py` al mostrar/ocultar categorías |
| `is_letter_forced()` | `bool` | `game_orchestrator.py` al decidir si ofrecer selector de letra |
| `get_round_time(default)` | `int` | `game_orchestrator.py:_do_start()` para pasar a `start_round()` |
| `get_round_time_for_number(n, default)` | `int` | `round_manager.py` cuando `time_decreasing=True` |
| `get_letter_for_round(n)` | `str \| None` | `round_manager.py` al iniciar ronda con `letter_sequence` |
| `has_rules()` | `bool` | `lobby.py` al decidir si mostrar indicador de evento |
| `merge_with(other)` | `EventRules` | Combinar reglas globales con override de grupo |

### 5. Funciones `_safe_*`

Son funciones privadas del módulo (prefijo `_`) que validan tipos y rangos. No se importan desde afuera.

**Patrón:** `data.get("key")` → isinstance check → clamp si aplica → default si inválido.

---

## Ejemplos de uso

### Ejemplo 1: Parsear JSON de BD

```python
# event_service.py (Fase 3)
event = ...  # SeasonalEvent de la BD
rules = EventRules.from_json(event.rules)
# Si event.rules es None → rules = EventRules() (defaults normales)
```

### Ejemplo 2: Calcular tiempo de ronda decreciente

```python
# round_manager.py (Fase 8)
rules = EventRules.from_json(event.rules)

# Ronda 3 con time_decreasing=True, base=60, amount=5
time = rules.get_round_time_for_number(round_number=3, default=60)
# → 60 - (3 * 5) = 45 segundos
```

### Ejemplo 3: Obtener categorías activas

```python
# round_manager.py (Fase 8)
rules = EventRules.from_json(event.rules)
categories = rules.get_active_categories()
# Si disabled=["Fruta"] → ["Nombre","Apellido","Color","País","Artista","Animal","Cosa"]
```

### Ejemplo 4: Obtener multiplicador de categoría

```python
# score_engine.py (Fase 8)
rules = EventRules.from_json(event.rules)
mult = rules.get_category_multiplier("País")
# Si category_multipliers={"País": 3.0} → 3.0
# Si no está en el dict → 1.0
```

### Ejemplo 5: Serializar y guardar

```python
# event_creator.py (Fase 4)
rules = EventRules(
    time_override=15,
    speed_bonus=30,
    excluded_letters=["A", "E", "I", "O", "U"],
)
event.rules = rules.to_json()
# → '{"time_override": 15, "speed_bonus": 30, "excluded_letters": ["A","E","I","O","U"]}'
```

### Ejemplo 6: Letra forzada por secuencia

```python
rules = EventRules(letter_sequence=["M", "R", "S", "P"])

rules.get_letter_for_round(1)  # → "M"
rules.get_letter_for_round(2)  # → "R"
rules.get_letter_for_round(3)  # → "S"
rules.get_letter_for_round(4)  # → "P"
rules.get_letter_for_round(5)  # → "M" (cíclico)
```

---

## Tests a crear

Crear `backend/tests/test_event_rules.py` con este contenido:

```python
"""Tests para EventRules — parseo, defaults, serialización y helpers."""

import json

from src.services.event_rules import EventRules


# ── Defaults ─────────────────────────────────────────────────────────


class TestDefaults:
    def test_default_instance(self):
        rules = EventRules()
        assert rules.time_override is None
        assert rules.forced_letter is None
        assert rules.categories_disabled == []
        assert rules.no_duplicates_bonus == 0
        assert rules.allow_dots_as_empty is True
        assert rules.sudden_death is False
        assert rules.collaborative is False
        assert rules.to_json() is None

    def test_default_categories_match_all_categories(self):
        from src.keyboards.settings import ALL_CATEGORIES
        rules = EventRules()
        assert rules.categories_enabled == list(ALL_CATEGORIES)


# ── from_json ────────────────────────────────────────────────────────


class TestFromJson:
    def test_none_returns_defaults(self):
        rules = EventRules.from_json(None)
        assert rules.time_override is None
        assert rules.to_json() is None

    def test_empty_string_returns_defaults(self):
        rules = EventRules.from_json("")
        assert rules.to_json() is None

    def test_invalid_json_returns_defaults(self):
        rules = EventRules.from_json("not json")
        assert rules.to_json() is None

    def test_invalid_type_returns_defaults(self):
        rules = EventRules.from_json("[]")
        assert rules.to_json() is None

    def test_parses_valid_json(self):
        rules = EventRules.from_json('{"time_override": 30}')
        assert rules.time_override == 30

    def test_parses_multiple_fields(self):
        data = {
            "time_override": 15,
            "speed_bonus": 30,
            "excluded_letters": ["A", "E"],
            "forced_letter": "M",
        }
        rules = EventRules.from_json(json.dumps(data))
        assert rules.time_override == 15
        assert rules.speed_bonus == 30
        assert rules.excluded_letters == ["A", "E"]
        assert rules.forced_letter == "M"

    def test_ignores_unknown_fields(self):
        rules = EventRules.from_json('{"time_override": 30, "foo": "bar"}')
        assert rules.time_override == 30
        assert not hasattr(rules, "foo")

    def test_invalid_type_coerces_to_default(self):
        # time_override debe ser int, no str
        rules = EventRules.from_json('{"time_override": "60"}')
        assert rules.time_override is None  # default

    def test_out_of_range_clamps(self):
        rules = EventRules.from_json('{"time_override": 999}')
        assert rules.time_override == 300  # max

        rules2 = EventRules.from_json('{"time_override": 2}')
        assert rules2.time_override == 5  # min

    def test_forced_letter_uppercased(self):
        rules = EventRules.from_json('{"forced_letter": "m"}')
        assert rules.forced_letter == "M"

    def test_forced_letter_invalid_length(self):
        rules = EventRules.from_json('{"forced_letter": "AB"}')
        assert rules.forced_letter is None

    def test_forced_letter_invalid_char(self):
        rules = EventRules.from_json('{"forced_letter": "1"}')
        assert rules.forced_letter is None

    def test_excluded_letters_uppercased(self):
        rules = EventRules.from_json('{"excluded_letters": ["a", "e"]}')
        assert rules.excluded_letters == ["A", "E"]

    def test_category_multipliers_valid(self):
        data = {"category_multipliers": {"País": 3.0, "Color": 1.5}}
        rules = EventRules.from_json(json.dumps(data))
        assert rules.category_multipliers["País"] == 3.0
        assert rules.category_multipliers["Color"] == 1.5

    def test_category_multipliers_invalid_category_ignored(self):
        data = {"category_multipliers": {"InvalidCat": 2.0, "País": 3.0}}
        rules = EventRules.from_json(json.dumps(data))
        assert "InvalidCat" not in rules.category_multipliers
        assert rules.category_multipliers["País"] == 3.0

    def test_category_multipliers_clamped(self):
        data = {"category_multipliers": {"País": 100.0}}
        rules = EventRules.from_json(json.dumps(data))
        assert rules.category_multipliers["País"] == 10.0  # max

    def test_elimination_rounds(self):
        data = {"elimination_rounds": [3, 5, 7]}
        rules = EventRules.from_json(json.dumps(data))
        assert rules.elimination_rounds == [3, 5, 7]

    def test_max_players_none(self):
        rules = EventRules.from_json('{"max_players": null}')
        assert rules.max_players is None


# ── to_json ──────────────────────────────────────────────────────────


class TestToJson:
    def test_all_default_returns_none(self):
        rules = EventRules()
        assert rules.to_json() is None

    def test_single_field(self):
        rules = EventRules(time_override=30)
        result = json.loads(rules.to_json())
        assert result == {"time_override": 30}

    def test_multiple_fields(self):
        rules = EventRules(time_override=15, speed_bonus=30)
        result = json.loads(rules.to_json())
        assert result["time_override"] == 15
        assert result["speed_bonus"] == 30
        # No debe incluir campos default
        assert "no_duplicates_bonus" not in result

    def test_roundtrip(self):
        data = {
            "time_override": 45,
            "excluded_letters": ["A", "E"],
            "forced_letter": "M",
            "categories_disabled": ["Fruta"],
        }
        json_str = json.dumps(data)
        rules = EventRules.from_json(json_str)
        output = rules.to_json()
        restored = EventRules.from_json(output)
        assert restored.time_override == 45
        assert restored.excluded_letters == ["A", "E"]
        assert restored.forced_letter == "M"
        assert restored.categories_disabled == ["Fruta"]

    def test_ensure_ascii_false(self):
        rules = EventRules(categories_disabled=["Fruta"])
        result = rules.to_json()
        assert "Fruta" in result  # no \uXXXX


# ── get_active_categories ────────────────────────────────────────────


class TestGetActiveCategories:
    def test_all_enabled(self):
        from src.keyboards.settings import ALL_CATEGORIES
        rules = EventRules()
        assert rules.get_active_categories() == list(ALL_CATEGORIES)

    def test_with_disabled(self):
        rules = EventRules(categories_disabled=["Fruta", "Color"])
        cats = rules.get_active_categories()
        assert "Fruta" not in cats
        assert "Color" not in cats
        assert len(cats) == 6

    def test_all_disabled_returns_empty(self):
        from src.keyboards.settings import ALL_CATEGORIES
        rules = EventRules(categories_disabled=list(ALL_CATEGORIES))
        assert rules.get_active_categories() == []


# ── get_category_multiplier ──────────────────────────────────────────


class TestGetCategoryMultiplier:
    def test_default_multiplier(self):
        rules = EventRules()
        assert rules.get_category_multiplier("País") == 1.0

    def test_custom_multiplier(self):
        rules = EventRules(category_multipliers={"País": 3.0})
        assert rules.get_category_multiplier("País") == 3.0

    def test_nonexistent_category(self):
        rules = EventRules(category_multipliers={"País": 3.0})
        assert rules.get_category_multiplier("Color") == 1.0


# ── get_round_time ───────────────────────────────────────────────────


class TestGetRoundTime:
    def test_no_override_uses_default(self):
        rules = EventRules()
        assert rules.get_round_time(60) == 60

    def test_override(self):
        rules = EventRules(time_override=30)
        assert rules.get_round_time(60) == 30

    def test_override_zero(self):
        # time_override=0 debe respetarse (0 no es None)
        rules = EventRules(time_override=5)
        assert rules.get_round_time(60) == 5


# ── get_round_time_for_number ────────────────────────────────────────


class TestGetRoundTimeForNumber:
    def test_no_decreasing(self):
        rules = EventRules(time_override=45)
        assert rules.get_round_time_for_number(1, 60) == 45
        assert rules.get_round_time_for_number(5, 60) == 45

    def test_decreasing(self):
        rules = EventRules(time_override=60, time_decreasing=True, time_decreasing_amount=5, time_minimum=15)
        assert rules.get_round_time_for_number(1, 60) == 55
        assert rules.get_round_time_for_number(5, 60) == 35

    def test_decreasing_hits_minimum(self):
        rules = EventRules(time_override=60, time_decreasing=True, time_decreasing_amount=10, time_minimum=15)
        assert rules.get_round_time_for_number(10, 60) == 15  # 60-100=-40 → 15

    def test_decreasing_no_override_uses_default(self):
        rules = EventRules(time_decreasing=True, time_decreasing_amount=5, time_minimum=15)
        result = rules.get_round_time_for_number(1, 60)
        assert result == 55  # 60 - (1*5)

    def test_first_round(self):
        rules = EventRules(time_override=60, time_decreasing=True, time_decreasing_amount=7, time_minimum=15)
        assert rules.get_round_time_for_number(1, 60) == 53


# ── get_letter_for_round ────────────────────────────────────────────


class TestGetLetterForRound:
    def test_no_letter_rules(self):
        rules = EventRules()
        assert rules.get_letter_for_round(1) is None

    def test_forced_letter(self):
        rules = EventRules(forced_letter="M")
        assert rules.get_letter_for_round(1) == "M"
        assert rules.get_letter_for_round(5) == "M"

    def test_letter_sequence(self):
        rules = EventRules(letter_sequence=["M", "R", "S"])
        assert rules.get_letter_for_round(1) == "M"
        assert rules.get_letter_for_round(2) == "R"
        assert rules.get_letter_for_round(3) == "S"
        assert rules.get_letter_for_round(4) == "M"  # cíclico

    def test_sequence_priority_over_forced(self):
        rules = EventRules(forced_letter="X", letter_sequence=["M", "R"])
        assert rules.get_letter_for_round(1) == "M"  # sequence gana

    def test_empty_sequence(self):
        rules = EventRules(letter_sequence=[])
        assert rules.get_letter_for_round(1) is None


# ── has_rules ────────────────────────────────────────────────────────


class TestHasRules:
    def test_default_no_rules(self):
        assert EventRules().has_rules() is False

    def test_with_override(self):
        assert EventRules(time_override=30).has_rules() is True

    def test_with_disabled_categories(self):
        assert EventRules(categories_disabled=["Fruta"]).has_rules() is True


# ── merge_with ───────────────────────────────────────────────────────


class TestMergeWith:
    def test_other_overrides_self(self):
        base = EventRules(time_override=60)
        override = EventRules(time_override=30)
        merged = base.merge_with(override)
        assert merged.time_override == 30

    def test_other_default_keeps_base(self):
        base = EventRules(time_override=60, speed_bonus=20)
        override = EventRules()  # all defaults
        merged = base.merge_with(override)
        assert merged.time_override == 60
        assert merged.speed_bonus == 20

    def test_partial_override(self):
        base = EventRules(time_override=60, speed_bonus=20)
        override = EventRules(speed_bonus=50)  # solo override speed_bonus
        merged = base.merge_with(override)
        assert merged.time_override == 60  # de base
        assert merged.speed_bonus == 50   # de override
```

---

## Archivos que se modifican en fases futuras (referencia)

| Archivo | Fase | Cómo usa EventRules |
|---|---|---|
| `src/services/round_manager.py` | 8 | `EventRules.from_json(event.rules)` → categorías, tiempo, letra, bonificaciones |
| `src/services/score_engine.py` | 8 | `EventRules.get_category_multiplier()` → multiplicar puntos por categoría |
| `src/services/game_orchestrator.py` | 7 | `EventRules.get_round_time()` → pasar tiempo a `start_round()` |
| `src/handlers/game/lobby.py` | 9 | `EventRules.has_rules()` → mostrar indicador de evento |
| `src/handlers/admin/event_creator.py` | 4 | `EventRules(...)` → construir y guardar reglas |
| `src/keyboards/event.py` | 6 | `EventRules` → teclados de edición de reglas |

---

## Comandos de verificación

```bash
cd backend

# Verificar que el archivo compila
python -c "from src.services.event_rules import EventRules; print('OK')"

# Verificar roundtrip básico
python -c "
from src.services.event_rules import EventRules
r = EventRules(time_override=30, speed_bonus=20)
j = r.to_json()
r2 = EventRules.from_json(j)
assert r2.time_override == 30
assert r2.speed_bonus == 20
print('Roundtrip OK')
"

# Ejecutar tests
pytest tests/test_event_rules.py -v
```

---

## Checklist

- [ ] Crear `backend/src/services/event_rules.py` con el código completo de arriba
- [ ] Crear `backend/tests/test_event_rules.py` con todos los tests
- [ ] Ejecutar `python -c "from src.services.event_rules import EventRules; print('OK')"` → imprime OK
- [ ] Ejecutar `pytest tests/test_event_rules.py -v` → todos pasan
- [ ] Ejecutar `pytest -q --tb=short` → sin regressions (549+ passed)
