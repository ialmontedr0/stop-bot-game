import logging
from datetime import datetime, timezone

from sqlalchemy import select

from src.db.engine import async_session_factory
from src.db.models import SeasonalEvent

logger = logging.getLogger(__name__)


class EventService:
    @staticmethod
    async def get_active_multiplier() -> float:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with async_session_factory() as session:
            stmt = (
                select(SeasonalEvent.multiplier)
                .where(SeasonalEvent.active)
                .where(SeasonalEvent.starts_at <= now)
                .where(SeasonalEvent.ends_at >= now)
                .order_by(SeasonalEvent.multiplier.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row if row is not None else 1.0

    @staticmethod
    async def get_active_events() -> list[dict]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with async_session_factory() as session:
            stmt = (
                select(SeasonalEvent)
                .where(SeasonalEvent.active)
                .where(SeasonalEvent.starts_at <= now)
                .where(SeasonalEvent.ends_at >= now)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()
            return [
                {
                    "id": e.id,
                    "name": e.name,
                    "description": e.description,
                    "multiplier": e.multiplier,
                    "ends_at": e.ends_at.isoformat(),
                }
                for e in events
            ]


event_service = EventService()
