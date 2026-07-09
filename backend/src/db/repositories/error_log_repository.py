import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ErrorLog


class ErrorLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        level: str,
        handler: Optional[str] = None,
        user_id: Optional[int] = None,
        game_id: Optional[int] = None,
        telegram_id: Optional[int] = None,
        exception_type: Optional[str] = None,
        exception_message: Optional[str] = None,
        traceback: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> ErrorLog:
        log = ErrorLog(
            level=level,
            handler=handler,
            user_id=user_id,
            game_id=game_id,
            telegram_id=telegram_id,
            exception_type=exception_type,
            exception_message=exception_message,
            traceback=traceback,
            context=json.dumps(context) if context else None,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_unresolved(self, limit: int = 50) -> list[ErrorLog]:
        stmt = (
            select(ErrorLog)
            .where(ErrorLog.resolved.is_(False))
            .order_by(ErrorLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_game(self, game_id: int, limit: int = 50) -> list[ErrorLog]:
        stmt = (
            select(ErrorLog)
            .where(ErrorLog.game_id == game_id)
            .order_by(ErrorLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(self, minutes: int = 60, limit: int = 50) -> list[ErrorLog]:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)
        stmt = (
            select(ErrorLog)
            .where(ErrorLog.timestamp >= cutoff)
            .order_by(ErrorLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_level(self) -> dict[str, int]:
        stmt = (
            select(ErrorLog.level, func.count(ErrorLog.id))
            .group_by(ErrorLog.level)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result}

    async def count_unresolved(self) -> int:
        stmt = select(func.count(ErrorLog.id)).where(ErrorLog.resolved.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def mark_resolved(self, error_id: int, resolution: Optional[str] = None) -> None:
        values: dict[str, Any] = {"resolved": True}
        if resolution:
            values["resolution"] = resolution
        await self.session.execute(
            update(ErrorLog).where(ErrorLog.id == error_id).values(**values)
        )
        await self.session.commit()

    async def get_most_frequent_exception(self, limit: int = 5) -> list[tuple[str, int]]:
        stmt = (
            select(ErrorLog.exception_type, func.count(ErrorLog.id))
            .where(ErrorLog.exception_type.isnot(None))
            .group_by(ErrorLog.exception_type)
            .order_by(func.count(ErrorLog.id).desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result]

    async def get_total_count(self) -> int:
        stmt = select(func.count(ErrorLog.id))
        result = await self.session.execute(stmt)
        return result.scalar() or 0
