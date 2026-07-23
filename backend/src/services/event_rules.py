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
            category_multipliers=_safe_dict_float(
                data, "category_multipliers", _DEFAULTS["category_multipliers"]
            ),
            hidden_categories=_safe_list_str(
                data, "hidden_categories", _DEFAULTS["hidden_categories"], _VALID_CATEGORIES
            ),
            mystery_category=_safe_optional_str_in(data, "mystery_category", _VALID_CATEGORIES),
            category_order=_safe_optional_list_str(data, "category_order", _VALID_CATEGORIES),
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

    def to_dict(self) -> dict:
        """Serializa a dict, omitiendo campos con valor default."""
        d = asdict(self)
        non_default = {}
        for key, value in d.items():
            default_val = _DEFAULTS.get(key)
            if value != default_val:
                non_default[key] = value
        return non_default

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
        return any(asdict(self)[key] != _DEFAULTS[key] for key in _DEFAULTS)

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


def _safe_float_range(
    data: dict, key: str, min_val: float, max_val: float, default: float
) -> float:
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
        if (
            isinstance(item, str)
            and len(item) == 1
            and item.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZÑ"
        ):
            result.append(item.upper())
    return result
