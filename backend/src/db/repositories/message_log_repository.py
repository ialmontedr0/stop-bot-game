from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from src.db.models import MessageLog


class MessageLogRepository:
    def __init__(self, session):
        self.session = session

    async def log_message(self, chat_id: int, message_id: int) -> None:
        log = MessageLog(
            chat_id=chat_id,
            message_id=message_id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.session.add(log)

    async def get_today_messages(self, chat_id: int) -> list[int]:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(MessageLog.message_id)
            .where(MessageLog.chat_id == chat_id)
            .where(MessageLog.created_at >= today)
            .order_by(MessageLog.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result]

    async def delete_by_message_ids(self, chat_id: int, message_ids: list[int]) -> None:
        if not message_ids:
            return
        stmt = (
            delete(MessageLog)
            .where(MessageLog.chat_id == chat_id)
            .where(MessageLog.message_id.in_(message_ids))
        )
        await self.session.execute(stmt)

    async def cleanup_old(self, days: int = 7) -> None:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        stmt = delete(MessageLog).where(MessageLog.created_at < cutoff)
        await self.session.execute(stmt)
