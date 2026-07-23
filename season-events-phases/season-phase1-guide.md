# Fase 1: Modelo de Datos — Migración de `SeasonalEvent`

## Estado Actual

**El modelo YA tiene todos los campos Phase 1** en `backend/src/db/models.py:180-213`:
- `event_type`, `starts_at` (nullable), `ends_at` (nullable)
- `daily_start_hour`, `daily_start_minute`, `daily_end_hour`, `daily_end_minute`
- `active_days`, `timezone`, `rules`, `is_paused`

**PERO no existe migración para estos campos.** La BD real de producción solo tiene las columnas originales de la migración `72c23fba8cae` + `group_chat_id` de `cc4baf03d26f`.

### Columnas que EXISTEN en la BD (según migraciones)

```
id, group_chat_id, name, description, multiplier, starts_at, ends_at, active, created_at
```

### Columnas que el modelo declara pero NO existen en la BD

```
event_type, daily_start_hour, daily_start_minute, daily_end_hour, daily_end_minute,
active_days, timezone, rules, is_paused
```

Además, `starts_at` y `ends_at` cambiaron de NOT NULL a nullable en el modelo.

---

## Qué se necesita hacer

**Solo una cosa:** Generar y ejecutar la migración de Alembic que sincronice la BD con el modelo.

---

## Paso 1: Generar la migración

```bash
cd backend
alembic revision --autogenerate -m "add_event_type_rules_daily_schedule_is_paused"
```

Esto crea un archivo nuevo en `backend/migrations/versions/`.

**Archivo generado:** `1c78ba01576f_add_event_type_rules_daily_schedule_is_.py`
**Revision ID:** `1c78ba01576f`
**Down revision:** `15998b31dd96`

---

## Paso 2: Revisar el archivo generado

Alembic comparará el modelo contra la BD y generará las operaciones necesarias. El archivo debe:

1. Tener `down_revision = '15998b31dd96'` (el head actual)
2. Agregar 9 columnas nuevas con `server_default` donde aplique
3. Alterar `starts_at` y `ends_at` para hacerlos nullable

**El contenido esperado del `upgrade()` debe ser:**

```python
def upgrade() -> None:
    # Hacer starts_at y ends_at nullable (antes eran NOT NULL)
    op.alter_column('seasonal_events', 'starts_at', nullable=True)
    op.alter_column('seasonal_events', 'ends_at', nullable=True)

    # Agregar columnas nuevas
    op.add_column('seasonal_events', sa.Column('event_type', sa.String(length=20), server_default='one_time', nullable=False))
    op.add_column('seasonal_events', sa.Column('daily_start_hour', sa.Integer(), nullable=True))
    op.add_column('seasonal_events', sa.Column('daily_start_minute', sa.Integer(), nullable=True))
    op.add_column('seasonal_events', sa.Column('daily_end_hour', sa.Integer(), nullable=True))
    op.add_column('seasonal_events', sa.Column('daily_end_minute', sa.Integer(), nullable=True))
    op.add_column('seasonal_events', sa.Column('active_days', sa.Text(), nullable=True))
    op.add_column('seasonal_events', sa.Column('timezone', sa.String(length=40), server_default='America/Argentina/Buenos_Aires', nullable=False))
    op.add_column('seasonal_events', sa.Column('rules', sa.Text(), nullable=True))
    op.add_column('seasonal_events', sa.Column('is_paused', sa.Boolean(), server_default='false', nullable=False))
```

**El `downgrade()` debe ser:**

```python
def downgrade() -> None:
    op.drop_column('seasonal_events', 'is_paused')
    op.drop_column('seasonal_events', 'rules')
    op.drop_column('seasonal_events', 'timezone')
    op.drop_column('seasonal_events', 'active_days')
    op.drop_column('seasonal_events', 'daily_end_minute')
    op.drop_column('seasonal_events', 'daily_end_hour')
    op.drop_column('seasonal_events', 'daily_start_minute')
    op.drop_column('seasonal_events', 'daily_start_hour')
    op.drop_column('seasonal_events', 'event_type')
    op.alter_column('seasonal_events', 'ends_at', nullable=False)
    op.alter_column('seasonal_events', 'starts_at', nullable=False)
```

**Si Alembic no detecta el cambio de nullable** (porque compara contra la BD local que puede no tener la tabla aún), editá manualmente el archivo generado para incluir los `op.alter_column`.

---

## Paso 3: Ejecutar la migración

```bash
cd backend
alembic upgrade head
```

---

## Paso 4: Verificar

```bash
cd backend
python -c "
from src.db.models import SeasonalEvent
cols = [c.name for c in SeasonalEvent.__table__.columns]
print(f'Total columnas: {len(cols)}')
for c in cols:
    print(f'  - {c}')
"
```

Debe imprimir 18 columnas.

---

## Impacto en datos existentes

Los eventos que ya existen en `seasonal_events` en producción:

| Campo | Antes | Después de migración | Nota |
|---|---|---|---|
| `event_type` | (no existía) | `'one_time'` | server_default |
| `starts_at` | NOT NULL, tiene valor | nullable, mantiene valor | Sin cambio de datos |
| `ends_at` | NOT NULL, tiene valor | nullable, mantiene valor | Sin cambio de datos |
| `daily_*` | (no existían) | NULL | Correcto, solo aplica a daily_recurring |
| `active_days` | (no existía) | NULL | Correcto |
| `timezone` | (no existía) | `'America/Argentina/Buenos_Aires'` | server_default |
| `rules` | (no existía) | NULL | Correcto, sin reglas custom |
| `is_paused` | (no existía) | `False` | server_default |

**Ningún dato existente se pierde o modifica.**

---

## Archivos que referencian `SeasonalEvent`

Ninguno necesita cambios en Fase 1. Se adaptan en sus fases correspondientes:

| Archivo | Fase de adaptación |
|---|---|
| `src/services/event_service.py` | Fase 3 |
| `src/handlers/admin/event_creator.py` | Fase 4 |
| `src/keyboards/event.py` | Fase 6 |
| `src/services/round_manager.py` | Fase 8 |
| `src/handlers/game/lobby.py` | Fase 9 |

---

## Especificación del JSON `rules`

El campo `rules` almacena un JSON string con reglas personalizables. Estructura completa:

```json
{
  "categories_enabled": ["nombre", "apellido", "color", "fruta", "pais", "artista", "animal", "cosa"],
  "categories_disabled": [],
  "category_multipliers": {},
  "hidden_categories": [],
  "mystery_category": null,
  "category_order": null,
  "time_override": null,
  "time_decreasing": false,
  "time_decreasing_amount": 5,
  "time_minimum": 15,
  "speed_bonus": 0,
  "speed_bonus_window": 0,
  "forced_letter": null,
  "excluded_letters": [],
  "letter_sequence": null,
  "vowel_forced": false,
  "no_duplicates_bonus": 0,
  "bonus_all_filled": 0,
  "streak_multiplier": 1.0,
  "penalty_empty": 0,
  "comeback_bonus": 0,
  "perfect_round_bonus": 0,
  "shared_answer_penalty": 0,
  "double_points_last_round": false,
  "min_words_required": 0,
  "min_word_length": 0,
  "proper_nouns_only": false,
  "no_repeat_words": false,
  "require_all_different": false,
  "allow_dots_as_empty": true,
  "sudden_death": false,
  "sudden_death_threshold": 1,
  "max_players": null,
  "elimination_rounds": null,
  "collaborative": false,
  "wager_enabled": false,
  "wager_max_pct": 50,
  "answer_reveal": false,
  "no_stop": false,
  "infinite_rounds": false
}
```

**Las 8 categorías válidas:** `nombre`, `apellido`, `color`, `fruta`, `pais`, `artista`, `animal`, `cosa`

**Serialización en Python:**
```python
import json
event.rules = json.dumps(my_dict)   # guardar
rules = json.loads(event.rules) if event.rules else {}  # leer
```

---

## Ejemplos de `rules` para eventos predefinidos

| Evento | Reglas clave |
|---|---|
| Batalla de Categorías | Solo 4 categorías, multipliers en pais/animal |
| Velocidad Extrema | 15s, speed_bonus 30pts |
| Letra Prohibida | Sin vocales, 75s |
| Modo Supervivencia | sudden_death true |
| Tormenta de Tiempo | time_decreasing true, 7s por ronda |
| Doble o Nada | wager_enabled true |
| Categoría Misteriosa | hidden_categories + mystery_category |
| Noche de Países | Solo categoría pais, multiplier 5x |
| Modo Maratón | streak_multiplier 1.5x |
| Modo Equipos | collaborative true |

---

## Checklist

- [ ] Ejecutar `alembic revision --autogenerate`
- [ ] Verificar `down_revision = '15998b31dd96'`
- [ ] Verificar que el upgrade tiene `alter_column` para starts_at/ends_at + 9 `add_column`
- [ ] Ejecutar `alembic upgrade head`
- [ ] Verificar 19 columnas con el script de Python
- [ ] Ejecutar `pytest -q --tb=short` para confirmar sin regressions
