# Fase 8: Propagación de reglas del evento al juego activo

## Estado: ✅ COMPLETADA

---

## Cambios implementados

### 1. `score_engine.py` — Soporte de event_rules en `evaluate()`

**Nuevo parámetro:** `event_rules: dict | None = None` y `standings_before: dict[int, int] | None = None`

**Modificadores de scoring implementados (en `_apply_event_scoring()`):**

| Regla | Cómo se aplica |
|---|---|
| `category_multipliers` | Multiplica el score de cada categoría por el multiplicador. Ej: `{"pais": 3.0}` → cada respuesta de País vale x3 |
| `no_duplicates_bonus` | +N puntos por cada respuesta que fue la única en su categoría (score >= UNIQUE_POINTS) |
| `shared_answer_penalty` | -N puntos por cada respuesta que fue duplicada por otro jugador |
| `bonus_all_filled` | +N puntos si el jugador respondió correctamente todas las categorías |
| `penalty_empty` | -N puntos por cada categoría vacía/incorrecta |
| `comeback_bonus` | +N puntos al jugador que iba en último lugar (según `standings_before` de BD) |
| `perfect_round_bonus` | +N puntos a TODOS si TODOS completaron TODAS las categorías correctamente |

**Nuevo campo en log `score_evaluation`:** `event_bonuses: list[str]` por jugador, con descripción de cada bonus aplicado.

### 2. `round_manager.py` — Reglas de evento aplicadas

**`RoundState` — campos nuevos:**
- `round_started_at: float | None` — timestamp de inicio de ronda (para speed_bonus)
- `speed_bonus_claimed: bool` — si ya se otorgó el speed_bonus en esta ronda
- `eliminated_player_ids: set[int]` — jugadores eliminados por sudden_death

**`start_round()` — cambios:**
- **`time_decreasing`:** Usa `EventRules.get_round_time_for_number(round_number, default)` para calcular el tiempo decreciente por ronda
- **`hidden_categories`:** Las categorías ocultas se filtran del mensaje de la ronda
- **`mystery_category`:** Se reemplaza por `???` en el mensaje de la ronda
- **`round_started_at`:** Se establece con `time.time()` al crear el state

**`submit_answers()` — cambios:**
- **`min_words_required`:** Si el jugador responde menos categorías que el mínimo, no se cuenta como "lleno" y no puede presionar Stop
- **`no_stop`:** Cuando `no_stop=True`, no se envía el botón Stop aunque alguien llene todo

**`press_stop()` — cambios:**
- **`no_stop`:** Si el evento tiene `no_stop=True`, se rechaza el press con mensaje

**`handle_letter_selection()` — cambios:**
- Si `event_rules` tiene `forced_letter` o `letter_sequence`, se fuerza la letra correcta para la siguiente ronda (el líder no puede elegir otra)

**`_letter_timeout()` — cambios:**
- Si timeout y hay letra forzada/sequence, se usa la letra del evento en vez de aleatoria

**`_persist_round_scores()` — cambios:**
- Pasa `event_rules` y `standings_before` a `ScoreEngine.evaluate()`
- **`double_points_last_round`:** Si es la última ronda del evento, duplica todos los scores
- **`speed_bonus`:** Si el primer completador terminó dentro de `speed_bonus_window` segundos desde el inicio, otorga bonus
- **`sudden_death`:** Jugadores con score <= `sudden_death_threshold` se marcan como eliminados

**`_transition_next_round()` — cambios:**
- Si hay sudden_death y todos los jugadores activos fueron eliminados, termina el juego

### 3. `event_rules.py` — Sin cambios

Ya estaba completo con todos los métodos necesarios (`get_round_time_for_number()`, `get_letter_for_round()`, `is_category_hidden()`, etc.)

---

## Reglas NO implementadas (requieren infraestructura adicional)

| Regla | Razón |
|---|---|
| `streak_multiplier` | Requiere tracking de streak entre rondas (cuántas rondas consecutivas con respuesta única). Necesita un dict por jugador que persista entre rondas. |
| `answer_reveal` | Requiere mostrar TODAS las respuestas de TODOS los jugadores al final de cada ronda. Implica cambiar `_build_summary()`. |
| `sudden_death` (eliminación completa) | Implementado parcialmente: marca jugadores como eliminados pero no los remueve del juego. La eliminación completa requiere modificar el flujo de `submit_answers()` para ignorar jugadores eliminados. |

---

## Archivos modificados

| Archivo | Líneas añadidas | Descripción |
|---|---|---|
| `src/services/score_engine.py` | ~120 | `event_rules` param + `_apply_event_scoring()` |
| `src/services/round_manager.py` | ~100 | time_decreasing, hidden/mystery, no_stop, min_words, speed_bonus, comeback, sudden_death, double_points |
| `src/services/event_rules.py` | 0 | Sin cambios |

---

## Tests

```bash
cd backend
pytest tests/ -q                     # 619 passed, 2 pre-existing failures
pytest tests/test_score_engine.py    # Tests unitarios del motor de scoring
pytest tests/test_round_manager.py   # Tests del round manager
pytest -k "event"                    # Tests de eventos
```

**Cobertura:** 60.62% (requerido: 50%)

---

## Siguiente fase

**Fase 9:** Actualización de visualización (lobby, `/events`, fin de juego, mensajes de ronda con info del evento).
