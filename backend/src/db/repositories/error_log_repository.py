import json
from datetime import timedelta
from typing import Any

from src.core.text_utils import utcnow

import sqlalchemy as sa
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ErrorLog, Game


class ErrorLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        level: str,
        handler: str | None = None,
        user_id: int | None = None,
        game_id: int | None = None,
        telegram_id: int | None = None,
        exception_type: str | None = None,
        exception_message: str | None = None,
        traceback: str | None = None,
        context: dict[str, Any] | None = None,
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

    async def get_unresolved(self, limit: int = 50, group_chat_id: int | None = None) -> list[ErrorLog]:
        stmt = (
            select(ErrorLog)
            .where(ErrorLog.resolved.is_(False))
            .order_by(ErrorLog.timestamp.desc())
            .limit(limit)
        )
        if group_chat_id is not None:
            subq = select(Game.id).where(Game.group_chat_id == group_chat_id).scalar_subquery()
            stmt = stmt.where(
                sa.or_(ErrorLog.game_id.in_(subq), ErrorLog.game_id.is_(None))
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
        cutoff = utcnow() - timedelta(minutes=minutes)
        stmt = (
            select(ErrorLog)
            .where(ErrorLog.timestamp >= cutoff)
            .order_by(ErrorLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_level(self) -> dict[str, int]:
        stmt = select(ErrorLog.level, func.count(ErrorLog.id)).group_by(ErrorLog.level)
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result}

    async def count_unresolved(self) -> int:
        stmt = select(func.count(ErrorLog.id)).where(ErrorLog.resolved.is_(False))
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def mark_resolved(self, error_id: int, resolution: str | None = None) -> None:
        values: dict[str, Any] = {"resolved": True}
        if resolution:
            values["resolution"] = resolution
        await self.session.execute(update(ErrorLog).where(ErrorLog.id == error_id).values(**values))
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
