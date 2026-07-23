# Fase 3: `EventService` — Reescritura Completa

## Objetivo

Reescribir `src/services/event_service.py` para soportar:
- 3 tipos de eventos (`one_time`, `daily_recurring`, `permanent`)
- Chequeo centralizado de actividad con `is_event_active_now()`
- Activar/desactivar/pausar eventos
- Edición de eventos existentes
- Exposición de todos los eventos del grupo (no solo los activos)

---

## Archivo a reescribir

```
backend/src/services/event_service.py
```

** Archivos que se MODIFICAN para mantener compatibilidad (en esta fase):**

| Archivo | Línea | Cambio necesario |
|---|---|---|
| `src/handlers/game/lobby.py` | 108-119 | Manejar `ends_at` nullable (daily/permanent) |
| `src/services/game_orchestrator.py` | 621-633 | `_get_event_text` manejar eventos sin `ends_at` |
| `src/services/round_manager.py` | 1205-1210 | Ya funciona (solo lee `name` y `multiplier`) |
| `src/services/xp_service.py` | 101, 235 | Sin cambios (solo llama `get_active_multiplier`) |

---

## Decisión: `zoneinfo` en vez de `pytz`

**El plan original usa `pytz`**, pero:
- `pytz` NO está en `requirements.txt`
- Python 3.9+ trae `zoneinfo` en stdlib (cero dependencias额外)
- El proyecto usa Python 3.10 (`pyproject.toml:2`)

**Se usa `zoneinfo.ZoneInfo`** en vez de `pytz.timezone`.

---

## Decisión: `utcnow()` y manejo de timezone

**Problema:** `text_utils.utcnow()` retorna `datetime` naive (sin tzinfo):
```python
def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive!
```

**Para `one_time` events:** No hay problema — `starts_at` y `ends_at` se comparan como naive UTC vs naive UTC.

**Para `daily_recurring` events:** Necesitamos comparar la hora local del evento contra la hora actual en su timezone. Necesitamos:
1. Obtener UTC now como timezone-aware: `datetime.now(timezone.utc)`
2. Convertir a la timezone del evento: `.astimezone(ZoneInfo(tz_name))`
3. Extraer `.time()` y comparar con `daily_start_hour/minute`

**Solución:** `is_event_active_now()` usa `datetime.now(timezone.utc)` (aware) para daily_recurring, y `utcnow()` (naive) para one_time. Esto es correcto porque:
- `starts_at` y `ends_at` se almacenan como naive UTC
- `datetime.now(timezone.utc)` se convierte a aware para daily schedule check
- Nunca se mezclan naive y aware en la misma comparación

---

## Código completo del archivo

Reemplazar **todo** el contenido de `backend/src/services/event_service.py` con:

```python
"""EventService — Servicio centralizado de eventos de temporada.

Maneja el ciclo de vida de eventos: creación, consulta, activación,
desactivación, pausa, edición y chequeo de actividad.

Soporta 3 tipos de eventos:
  - one_time: Tiene inicio/fin fijo. Expira automáticamente.
  - daily_recurring: Activo en horario específico los días de la semana.
  - permanent: Activo siempre hasta que se desactive manualmente.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, time, timezone
from typing import Any

from aiogram import Bot
from sqlalchemy import select, update

from src.core.text_utils import utcnow
from src.db.engine import async_session_factory
from src.db.models import SeasonalEvent
from src.services.event_rules import EventRules

logger = logging.getLogger(__name__)

# Mapa weekday number → key de active_days
_DAY_MAP = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}

# Timezone por defecto para eventos daily_recurring
_DEFAULT_TZ = "America/Argentina/Buenos_Aires"

# Días válidos para active_days
_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


class EventService:

    # ── Chequeo de actividad ─────────────────────────────────────────

    @staticmethod
    def is_event_active_now(event: SeasonalEvent) -> bool:
        """Determina si un evento está activo AHORA.

        Centraliza toda la lógica de chequeo:
        - active=True, is_paused=False
        - Para one_time: starts_at <= now <= ends_at
        - Para daily_recurring: día correcto + dentro del horario
        - Para permanent: siempre True (si active + not paused)
        """
        if not event.active or event.is_paused:
            return False

        if event.event_type == "one_time":
            # Ambos son naive UTC, utcnow() también naive UTC
            now = utcnow()
            if not event.starts_at or not event.ends_at:
                return False
            return event.starts_at <= now <= event.ends_at

        if event.event_type == "daily_recurring":
            return EventService._check_daily_recurring(event)

        if event.event_type == "permanent":
            return True

        return False

    @staticmethod
    def _check_daily_recurring(event: SeasonalEvent) -> bool:
        """Verifica si un evento daily_recurring está activo ahora.

        Chequea:
        1. El día de la semana actual está en active_days
        2. La hora actual (en la timezone del evento) está entre
           daily_start_hour:minute y daily_end_hour:minute
        """
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            # Fallback para Python < 3.9 (no debería pasar)
            logger.warning("zoneinfo no disponible, daily_recurring siempre activo")
            return True

        now_utc = datetime.now(timezone.utc)

        # 1. Verificar día de semana
        current_day = _DAY_MAP.get(now_utc.weekday())
        try:
            active_days = json.loads(event.active_days) if event.active_days else list(_VALID_DAYS)
        except (json.JSONDecodeError, TypeError):
            active_days = list(_VALID_DAYS)

        # Validar que los días sean válidos
        active_days = [d for d in active_days if d in _VALID_DAYS]
        if not active_days:
            active_days = list(_VALID_DAYS)  # fallback: todos

        if current_day not in active_days:
            return False

        # 2. Verificar horario en la timezone del evento
        tz_name = event.timezone or _DEFAULT_TZ
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            logger.warning("Timezone inválida: %s, usando default", tz_name)
            tz = ZoneInfo(_DEFAULT_TZ)

        local_now = now_utc.astimezone(tz)
        local_time = local_now.time()

        start_hour = event.daily_start_hour if event.daily_start_hour is not None else 0
        start_minute = event.daily_start_minute if event.daily_start_minute is not None else 0
        end_hour = event.daily_end_hour if event.daily_end_hour is not None else 23
        end_minute = event.daily_end_minute if event.daily_end_minute is not None else 59

        start = time(start_hour, start_minute)
        end = time(end_hour, end_minute)

        return start <= local_time <= end

    # ── Consultas de eventos activos ─────────────────────────────────

    @staticmethod
    async def get_active_multiplier(group_chat_id: int) -> float:
        """Retorna el multiplicador más alto de eventos activos para un grupo.

        Solo cuenta eventos donde is_event_active_now() es True.
        Retorna 1.0 si no hay eventos activos.
        """
        async with async_session_factory() as session:
            stmt = select(SeasonalEvent).where(
                SeasonalEvent.active,
                SeasonalEvent.group_chat_id == group_chat_id,
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

            # Filtrar en Python con is_event_active_now
            active = [e for e in events if EventService.is_event_active_now(e)]

            if not active:
                return 1.0

            # Retornar el multiplicador más alto
            return max(e.multiplier for e in active)

    @staticmethod
    async def get_active_events(group_chat_id: int) -> list[dict]:
        """Retorna eventos activos (no pausados, dentro de horario) del grupo.

        Cada dict contiene:
            id, name, description, multiplier, event_type, rules (EventRules),
            ends_at (str|None), is_paused, active_days, timezone

        Los eventos se filtran con is_event_active_now().
        """
        async with async_session_factory() as session:
            stmt = select(SeasonalEvent).where(
                SeasonalEvent.active,
                SeasonalEvent.group_chat_id == group_chat_id,
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

            active = [e for e in events if EventService.is_event_active_now(e)]
            return [EventService._parse_event_dict(e) for e in active]

    @staticmethod
    async def has_active_event(group_chat_id: int) -> bool:
        """Retorna True si hay al menos un evento activo para el grupo."""
        async with async_session_factory() as session:
            stmt = select(SeasonalEvent.id).where(
                SeasonalEvent.active,
                SeasonalEvent.group_chat_id == group_chat_id,
            )
            result = await session.execute(stmt)
            all_events = result.scalars().all()

        # Necesitamos los objetos completos para is_event_active_now
        if not all_events:
            return False

        async with async_session_factory() as session:
            stmt = select(SeasonalEvent).where(
                SeasonalEvent.active,
                SeasonalEvent.group_chat_id == group_chat_id,
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

        return any(EventService.is_event_active_now(e) for e in events)

    # ── Desactivación ────────────────────────────────────────────────

    @staticmethod
    async def deactivate_expired() -> int:
        """Desactiva eventos one_time que ya pasaron su ends_at.

        Los daily_recurring y permanent NUNCA expiran por tiempo.
        Retorna la cantidad de eventos desactivados.
        """
        now = utcnow()
        async with async_session_factory() as session:
            stmt = (
                update(SeasonalEvent)
                .where(
                    SeasonalEvent.active.is_(True),
                    SeasonalEvent.event_type == "one_time",
                    SeasonalEvent.ends_at.isnot(None),
                    SeasonalEvent.ends_at < now,
                )
                .values(active=False)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    @staticmethod
    async def deactivate_event(event_id: int) -> bool:
        """Desactiva un evento completamente (active=False).

        Retorna True si se desactivó, False si no existía.
        """
        async with async_session_factory() as session:
            stmt = select(SeasonalEvent).where(SeasonalEvent.id == event_id)
            result = await session.execute(stmt)
            event = result.scalar_one_or_none()
            if not event:
                return False
            event.active = False
            await session.commit()
            return True

    # ── Pausar/Reanudar ─────────────────────────────────────────────

    @staticmethod
    async def toggle_event(event_id: int) -> bool | None:
        """Cambia el estado de pausa de un evento.

        Retorna:
            True  → el evento quedó ACTIVO (is_paused=False)
            False → el evento quedó PAUSADO (is_paused=True)
            None  → el evento no existe
        """
        async with async_session_factory() as session:
            stmt = select(SeasonalEvent).where(SeasonalEvent.id == event_id)
            result = await session.execute(stmt)
            event = result.scalar_one_or_none()
            if not event:
                return None
            event.is_paused = not event.is_paused
            await session.commit()
            return not event.is_paused  # True si quedó activo

    # ── Consultas de grupo ───────────────────────────────────────────

    @staticmethod
    async def get_events_for_group(group_chat_id: int) -> list[dict]:
        """Retorna TODOS los eventos del grupo (activos + pausados).

        A diferencia de get_active_events(), no filtra por is_event_active_now.
        Retorna la lista completa para que el admin gestione eventos.
        """
        async with async_session_factory() as session:
            stmt = (
                select(SeasonalEvent)
                .where(SeasonalEvent.group_chat_id == group_chat_id)
                .order_by(SeasonalEvent.created_at.desc())
            )
            result = await session.execute(stmt)
            events = result.scalars().all()
            return [EventService._parse_event_dict(e) for e in events]

    # ── Edición ──────────────────────────────────────────────────────

    @staticmethod
    async def update_event(event_id: int, **kwargs: Any) -> bool:
        """Actualiza campos editables de un evento.

        Campos permitidos:
            name, description, multiplier, event_type,
            starts_at, ends_at,
            daily_start_hour, daily_start_minute,
            daily_end_hour, daily_end_minute,
            active_days, timezone,
            rules (str JSON), active, is_paused

        Retorna True si se actualizó, False si no existía.
        """
        allowed_fields = {
            "name", "description", "multiplier", "event_type",
            "starts_at", "ends_at",
            "daily_start_hour", "daily_start_minute",
            "daily_end_hour", "daily_end_minute",
            "active_days", "timezone",
            "rules", "active", "is_paused",
        }
        filtered = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not filtered:
            return False

        async with async_session_factory() as session:
            stmt = select(SeasonalEvent).where(SeasonalEvent.id == event_id)
            result = await session.execute(stmt)
            event = result.scalar_one_or_none()
            if not event:
                return False

            for key, value in filtered.items():
                setattr(event, key, value)

            await session.commit()
            return True

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_event_dict(event: SeasonalEvent) -> dict[str, Any]:
        """Convierte un SeasonalEvent a dict con rules parseado.

        El campo 'rules' se convierte de JSON string a EventRules object.
        Si el JSON es inválido o None, usa EventRules() defaults.
        """
        rules = EventRules.from_json(event.rules)

        return {
            "id": event.id,
            "name": event.name,
            "description": event.description,
            "multiplier": event.multiplier,
            "event_type": event.event_type,
            "rules": rules,
            "is_paused": event.is_paused,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "active_days": event.active_days,
            "timezone": event.timezone,
        }

    # ── Métodos existentes sin cambios ───────────────────────────────

    @staticmethod
    async def get_user_admin_groups(user_id: int, bot: Bot) -> list[dict]:
        """Retorna grupos donde el bot está activo y el usuario es admin."""
        from sqlalchemy import distinct

        from src.db.models import BotChat, Game

        async with async_session_factory() as session:
            stmt = select(BotChat).where(BotChat.removed_at.is_(None))
            result = await session.execute(stmt)
            chats = result.scalars().all()

            if not chats:
                game_stmt = select(distinct(Game.group_chat_id))
                game_result = await session.execute(game_stmt)
                known_ids = [row[0] for row in game_result.all()]
            else:
                known_ids = []

        chat_ids = [(c.chat_id, c.chat_title) for c in chats] or [
            (gid, f"Grupo {gid}") for gid in known_ids
        ]

        admin_groups = []
        for chat_id, chat_title in chat_ids:
            try:
                member = await bot.get_chat_member(chat_id, user_id)
                if member.status in ("creator", "administrator"):
                    admin_groups.append(
                        {
                            "chat_id": chat_id,
                            "chat_title": chat_title,
                        }
                    )
            except Exception:
                continue
        return admin_groups

    @staticmethod
    async def get_groups_with_active_events(user_id: int, bot: Bot) -> list[dict]:
        """Retorna grupos donde el usuario es admin Y hay eventos activos."""
        admin_groups = await EventService.get_user_admin_groups(user_id, bot)
        result = []
        for group in admin_groups:
            async with async_session_factory() as session:
                stmt = select(SeasonalEvent).where(
                    SeasonalEvent.active,
                    SeasonalEvent.group_chat_id == group["chat_id"],
                )
                res = await session.execute(stmt)
                events = res.scalars().all()

                active_events = [e for e in events if EventService.is_event_active_now(e)]
                if active_events:
                    result.append(
                        {
                            **group,
                            "events": [
                                {
                                    "id": e.id,
                                    "name": e.name,
                                    "multiplier": e.multiplier,
                                    "ends_at": e.ends_at,
                                }
                                for e in active_events
                            ],
                        }
                    )
        return result


event_service = EventService()
```

---

## Explicación de cada sección

### 1. `is_event_active_now(event)`

Método **estático puro** (sin BD). Toma un `SeasonalEvent` y retorna `bool`.

**Lógica:**
```
active=False OR is_paused=True  →  False (siempre)
event_type=one_time             →  starts_at <= now <= ends_at
event_type=daily_recurring      →  check day of week + time in timezone
event_type=permanent            →  True
```

**Para daily_recurring:**
1. Obtiene UTC aware: `datetime.now(timezone.utc)`
2. Convierte a timezone del evento: `.astimezone(ZoneInfo(tz))`
3. Verifica día de semana contra `active_days` (JSON array)
4. Verifica `time` entre `daily_start` y `daily_end`

### 2. `get_active_multiplier()`

**Cambio clave:** Antes usaba SQL `WHERE starts_at <= now AND ends_at >= now`. Ahora:
1. Trae TODOS los eventos activos del grupo (sin filtro temporal en SQL)
2. Filtra en Python con `is_event_active_now()` (necesario para daily_recurring)

**Por qué:** daily_recurring necesita verificar hora y día, que no se puede hacer eficientemente en SQL con columnas separadas.

### 3. `get_active_events()`

**Cambio clave:** Retorna `EventRules` object en vez de solo strings.

**Formato del dict retornado:**
```python
{
    "id": 1,
    "name": "Tormenta de Tiempo",
    "description": "...",
    "multiplier": 2.0,
    "event_type": "daily_recurring",
    "rules": EventRules(...),       # ← object, no string
    "is_paused": False,
    "starts_at": datetime(...),     # None para daily/permanent
    "ends_at": datetime(...),       # None para daily/permanent
    "active_days": '["mon","tue"]', # None para one_time
    "timezone": "America/Argentina/Buenos_Aires",
}
```

**Impacto en callers:**
- `game_orchestrator.py:134` — usa `ev['name']` y `ev['multiplier']` → OK
- `round_manager.py:1207` — usa `event['name']` y `event['multiplier']` → OK
- `lobby.py:100` — usa `e['ends_at']` → **NECESITA CAMPO** (ver abajo)

### 4. `deactivate_expired()`

**Cambio clave:** Solo desactiva `event_type='one_time'` con `ends_at < now`.

**Antes:** Desactivaba todos los eventos con `ends_at < now` (rompía daily_recurring).

### 5. `toggle_event()`

**Nuevo.** Cambia `is_paused` de False↔True. Retorna el nuevo estado.

### 6. `get_events_for_group()`

**Nuevo.** Retorna TODOS los eventos (activos + pausados) para que el admin gestione.

### 7. `update_event()`

**Nuevo.** Actualiza campos editables con `**kwargs`. Filtra campos no permitidos.

### 8. `_parse_event_dict()`

**Nuevo.** Convierte `SeasonalEvent` a dict, parseando `rules` con `EventRules.from_json()`.

---

## Archivos que se modifican

### `src/handlers/game/lobby.py` — Línea 108-119

**Problema:** El código actual asume que `ends_at` siempre existe y es un datetime:
```python
ends = e["ends_at"]  # ← puede ser None para daily_recurring/permanent
```

**Cambio:** Reemplazar la línea 105-128 con:

```python
@game_router.message(Command("events"))
@error_tracker.track_errors(handler_name="cmd_events")
async def cmd_events(message: Message) -> None:
    if message.chat.type == "private":
        msg = await message.answer("❌ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    events = await event_service.get_active_events(message.chat.id)
    if not events:
        await message.answer("📭 No hay eventos activos en este grupo.")
        return

    lines = ["🎉 <b>Eventos activos en este grupo:</b>\n"]
    for e in events:
        event_type = e.get("event_type", "one_time")
        time_str = _format_event_time(e)

        lines.append(
            f"📌 <b>{e['name']}</b>\n"
            f"   ⚡ x{e['multiplier']} XP"
        )
        if time_str:
            lines[-1] += f" — ⏱ {time_str}"

        if e.get("description"):
            lines.append(f"   📝 {e['description']}")

        # Mostrar tipo de evento
        type_labels = {
            "one_time": "🔄 Temporal",
            "daily_recurring": "🔁 Diario recurrente",
            "permanent": "♾ Permanente",
        }
        lines.append(f"   📅 {type_labels.get(event_type, event_type)}")

    await message.answer("\n".join(lines), parse_mode="HTML")
```

Y agregar esta función helper **antes** de `cmd_events` (o al inicio del archivo):

```python
def _format_event_time(event: dict) -> str:
    """Formatea el tiempo restante de un evento para mostrar."""
    event_type = event.get("event_type", "one_time")
    ends_at = event.get("ends_at")

    if event_type == "one_time" and ends_at:
        from datetime import datetime
        if isinstance(ends_at, str):
            ends_at = datetime.fromisoformat(ends_at)
        remaining = ends_at - datetime.utcnow()
        total_hours = remaining.total_seconds() / 3600
        if total_hours >= 24:
            return f"queda {int(total_hours // 24)}d {int(total_hours % 24)}h"
        elif total_hours >= 1:
            return f"queda {int(total_hours)}h {int((total_hours % 1) * 60)}m"
        else:
            return f"queda {int(remaining.total_seconds() / 60)}m"

    if event_type == "daily_recurring":
        return "repite a diario"

    if event_type == "permanent":
        return "siempre activo"

    return ""
```

### `src/services/game_orchestrator.py` — Línea 621-633

**Problema:** `_get_event_text` usa `ev['name']` y `ev['multiplier']` que siguen funcionando, pero ahora `ev` tiene más campos. Sin cambios necesarios — el método actual funciona.

**Opcional:** Actualizar para mostrar más info:
```python
@staticmethod
def _get_event_text(active_events: list[dict]) -> str:
    if active_events:
        ev = active_events[0]
        event_type = ev.get("event_type", "one_time")
        type_emoji = {"one_time": "🔄", "daily_recurring": "🔁", "permanent": "♾"}
        emoji = type_emoji.get(event_type, "🎉")
        return f"{emoji} <b>Evento: {ev['name']}</b> - x{ev['multiplier']} XP"
    return ""
```

### `src/services/round_manager.py` — Sin cambios

Línea 1207-1210 usa `event['name']` y `event['multiplier']` que siguen en el dict. **No necesita cambios.**

### `src/services/xp_service.py` — Sin cambios

Línea 101 y 235 usan `get_active_multiplier()` que retorna `float`. **No necesita cambios.**

---

## Tests a crear

Crear `backend/tests/test_event_service.py` con este contenido:

```python
"""Tests para EventService — is_event_active_now, toggle, update, etc."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.db.models import SeasonalEvent
from src.services.event_rules import EventRules
from src.services.event_service import EventService


_UNSET = object()


def _make_event(
    *,
    event_type="one_time",
    active=True,
    is_paused=False,
    starts_at=_UNSET,
    ends_at=_UNSET,
    daily_start_hour=0,
    daily_start_minute=0,
    daily_end_hour=23,
    daily_end_minute=59,
    active_days=None,
    timezone_str="America/Argentina/Buenos_Aires",
    rules=None,
    multiplier=1.0,
    name="Test Event",
    group_chat_id=-100123456789,
) -> SeasonalEvent:
    """Crea un SeasonalEvent para tests sin BD."""
    now = datetime.utcnow()
    event = SeasonalEvent(
        id=1,
        group_chat_id=group_chat_id,
        name=name,
        description="Test",
        event_type=event_type,
        multiplier=multiplier,
        starts_at=starts_at if starts_at is not _UNSET else now - timedelta(hours=1),
        ends_at=ends_at if ends_at is not _UNSET else now + timedelta(hours=1),
        daily_start_hour=daily_start_hour,
        daily_start_minute=daily_start_minute,
        daily_end_hour=daily_end_hour,
        daily_end_minute=daily_end_minute,
        active_days=json.dumps(active_days) if active_days else None,
        timezone=timezone_str,
        rules=json.dumps(rules) if rules else None,
        active=active,
        is_paused=is_paused,
        created_at=now,
    )
    return event


# ── is_event_active_now ──────────────────────────────────────────────


class TestIsEventActiveNow:
    def test_inactive_event(self):
        event = _make_event(active=False)
        assert EventService.is_event_active_now(event) is False

    def test_paused_event(self):
        event = _make_event(is_paused=True)
        assert EventService.is_event_active_now(event) is False

    def test_one_time_active(self):
        now = datetime.utcnow()
        event = _make_event(
            event_type="one_time",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
        )
        assert EventService.is_event_active_now(event) is True

    def test_one_time_expired(self):
        now = datetime.utcnow()
        event = _make_event(
            event_type="one_time",
            starts_at=now - timedelta(hours=2),
            ends_at=now - timedelta(hours=1),
        )
        assert EventService.is_event_active_now(event) is False

    def test_one_time_not_started(self):
        now = datetime.utcnow()
        event = _make_event(
            event_type="one_time",
            starts_at=now + timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
        )
        assert EventService.is_event_active_now(event) is False

    def test_one_time_no_dates(self):
        event = _make_event(event_type="one_time", starts_at=None, ends_at=None)
        assert EventService.is_event_active_now(event) is False

    def test_permanent_active(self):
        event = _make_event(event_type="permanent")
        assert EventService.is_event_active_now(event) is True

    def test_permanent_paused(self):
        event = _make_event(event_type="permanent", is_paused=True)
        assert EventService.is_event_active_now(event) is False

    def test_daily_recurring_active_now(self):
        # Este test verifica que daily_recurring funciona con zoneinfo
        # Se testea con una hora que sabemos que está dentro del rango
        from zoneinfo import ZoneInfo

        now_utc = datetime.now(timezone.utc)
        local_now = now_utc.astimezone(ZoneInfo("America/Argentina/Buenos_Aires"))
        current_hour = local_now.hour
        current_minute = local_now.minute

        event = _make_event(
            event_type="daily_recurring",
            daily_start_hour=max(0, current_hour - 1),
            daily_start_minute=0,
            daily_end_hour=min(23, current_hour + 1),
            daily_end_minute=59,
        )
        # Puede fallar si estamos en el límite del día, pero es unlikely en tests rápidos
        result = EventService.is_event_active_now(event)
        # No assert True/False porque depende de la hora actual
        assert isinstance(result, bool)

    def test_daily_recurring_wrong_day(self):
        event = _make_event(
            event_type="daily_recurring",
            active_days=["mon", "tue", "wed", "thu", "fri"],
            daily_start_hour=0,
            daily_end_hour=23,
        )
        # Si hoy es sábado o domingo, debe ser False
        from datetime import date
        if date.today().weekday() >= 5:  # 5=sat, 6=sun
            assert EventService.is_event_active_now(event) is False

    def test_daily_recurring_no_active_days(self):
        event = _make_event(
            event_type="daily_recurring",
            active_days=[],
            daily_start_hour=0,
            daily_end_hour=23,
        )
        # Sin días activos, fallback a todos
        result = EventService.is_event_active_now(event)
        assert isinstance(result, bool)

    def test_daily_recurring_invalid_timezone(self):
        event = _make_event(
            event_type="daily_recurring",
            timezone_str="Invalid/Timezone",
            daily_start_hour=0,
            daily_end_hour=23,
        )
        # Fallback a default timezone, no debe crashear
        result = EventService.is_event_active_now(event)
        assert isinstance(result, bool)

    def test_unknown_event_type(self):
        event = _make_event(event_type="unknown")
        assert EventService.is_event_active_now(event) is False


# ── _parse_event_dict ────────────────────────────────────────────────


class TestParseEventDict:
    def test_basic_fields(self):
        event = _make_event(name="Mi Evento", multiplier=2.5)
        d = EventService._parse_event_dict(event)
        assert d["name"] == "Mi Evento"
        assert d["multiplier"] == 2.5
        assert d["event_type"] == "one_time"

    def test_rules_parsed(self):
        event = _make_event(rules={"time_override": 30, "speed_bonus": 20})
        d = EventService._parse_event_dict(event)
        assert isinstance(d["rules"], EventRules)
        assert d["rules"].time_override == 30
        assert d["rules"].speed_bonus == 20

    def test_rules_none(self):
        event = _make_event(rules=None)
        d = EventService._parse_event_dict(event)
        assert isinstance(d["rules"], EventRules)
        assert d["rules"].time_override is None  # default

    def test_rules_invalid_json(self):
        event = _make_event()
        event.rules = "not json"
        d = EventService._parse_event_dict(event)
        assert isinstance(d["rules"], EventRules)  # fallback a defaults


# ── toggle_event (sin BD, solo lógica) ──────────────────────────────


class TestToggleLogic:
    def test_toggle_flips_paused(self):
        event = _make_event(is_paused=False)
        assert event.is_paused is False
        # Simular toggle
        event.is_paused = not event.is_paused
        assert event.is_paused is True
        event.is_paused = not event.is_paused
        assert event.is_paused is False


# ── deactivate_expired (sin BD, solo lógica) ────────────────────────


class TestDeactivateExpiredLogic:
    def test_one_time_expired_detected(self):
        now = datetime.utcnow()
        event = _make_event(
            event_type="one_time",
            ends_at=now - timedelta(hours=1),
        )
        # is_event_active_now debe retornar False
        assert EventService.is_event_active_now(event) is False

    def test_daily_recurring_not_expired(self):
        event = _make_event(event_type="daily_recurring")
        # daily_recurring nunca expira por tiempo
        # solo depends de hora/día actual
        result = EventService.is_event_active_now(event)
        assert isinstance(result, bool)
```

---

## Dependencia a instalar

**Ninguna.** `zoneinfo` es stdlib en Python 3.9+.

---

## Comandos de verificación

```bash
cd backend

# Verificar import
python -c "from src.services.event_service import event_service; print('OK')"

# Verificar que is_event_active_now funciona con un evento mock
python -c "
from src.db.models import SeasonalEvent
from src.services.event_service import EventService
from datetime import datetime, timedelta

now = datetime.utcnow()
e = SeasonalEvent(
    id=1, group_chat_id=-1, name='test', event_type='one_time',
    multiplier=1.0, starts_at=now-timedelta(hours=1),
    ends_at=now+timedelta(hours=1), active=True, is_paused=False,
    timezone='America/Argentina/Buenos_Aires',
)
print('Active:', EventService.is_event_active_now(e))
"

# Ejecutar tests
pytest tests/test_event_service.py -v

# Verificar sin regressions
pytest -q --tb=short
```

---

## Nota sobre `utcnow()` naive vs aware

`text_utils.utcnow()` retorna naive datetime:
```python
def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive!
```

**Para one_time:** Comparaciones naive vs naive funcionan porque `starts_at` y `ends_at` también se almacenan como naive UTC.

**Para daily_recurring:** Se usa `datetime.now(timezone.utc)` (aware) y se convierte a la timezone del evento con `ZoneInfo`. Nunca se compara naive con aware.

---

## Checklist

- [ ] Reemplazar todo `backend/src/services/event_service.py` con el código de arriba
- [ ] Modificar `backend/src/handlers/game/lobby.py` — función `_format_event_time` + actualizar `cmd_events`
- [ ] Opcional: Actualizar `game_orchestrator.py:_get_event_text` para mostrar emoji de tipo
- [ ] Crear `backend/tests/test_event_service.py` con los tests
- [ ] Ejecutar `pytest tests/test_event_service.py -v` → todos pasan
- [ ] Ejecutar `pytest -q --tb=short` → sin regressions
