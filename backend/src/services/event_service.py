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

        if event.event_type == "permanent":  # noqa: SIM103
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

    @staticmethod
    async def delete_event(event_id: int) -> bool:
        """Elimina un evento permanentemente de la BD.

        Retorna True si se eliminó, False si no existía.
        """
        async with async_session_factory() as session:
            stmt = select(SeasonalEvent).where(SeasonalEvent.id == event_id)
            result = await session.execute(stmt)
            event = result.scalar_one_or_none()
            if not event:
                return False
            await session.delete(event)
            await session.commit()
            return True

    @staticmethod
    async def delete_all_events(group_chat_id: int) -> int:
        """Elimina TODOS los eventos de un grupo.

        Retorna la cantidad de eventos eliminados.
        """
        async with async_session_factory() as session:
            stmt = select(SeasonalEvent).where(
                SeasonalEvent.group_chat_id == group_chat_id
            )
            result = await session.execute(stmt)
            events = result.scalars().all()
            count = len(events)
            for e in events:
                await session.delete(e)
            await session.commit()
            return count

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
            "name",
            "description",
            "multiplier",
            "event_type",
            "starts_at",
            "ends_at",
            "daily_start_hour",
            "daily_start_minute",
            "daily_end_hour",
            "daily_end_minute",
            "active_days",
            "timezone",
            "rules",
            "active",
            "is_paused",
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

        Incluye 'is_now_active' que refleja is_event_active_now()
        para que la UI pueda mostrar el estado real del evento.
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
            "is_now_active": EventService.is_event_active_now(event),
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
                                    "ends_at": e.ends_at.isoformat() if e.ends_at else None,
                                }
                                for e in active_events
                            ],
                        }
                    )
        return result


event_service = EventService()
