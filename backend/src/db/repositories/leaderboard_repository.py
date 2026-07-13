import logging
from datetime import date, timedelta

from sqlalchemy import desc, select

from src.db.engine import async_session_factory
from src.db.models import WeeklyLeaderboard

logger = logging.getLogger(__name__)


def _current_week_start() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


class LeaderboardRepository:
    @staticmethod
    async def upsert_player_week(
        player_id: int,
        score_to_add: int,
        group_chat_id: int = 0,
        week_start: date | None = None,
    ) -> None:
        ws = week_start or _current_week_start()
        async with async_session_factory() as session:
            stmt = select(WeeklyLeaderboard).where(
                WeeklyLeaderboard.player_id == player_id,
                WeeklyLeaderboard.week_start == ws,
                WeeklyLeaderboard.group_chat_id == group_chat_id,
            )
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()

            if entry:
                entry.total_score += score_to_add
                entry.games_played += 1
            else:
                entry = WeeklyLeaderboard(
                    player_id=player_id,
                    group_chat_id=group_chat_id,
                    week_start=ws,
                    total_score=score_to_add,
                    games_played=1,
                )
                session.add(entry)

            await session.commit()

    @staticmethod
    async def get_weekly_top(
        group_chat_id: int, limit: int = 10, week_start: date | None = None
    ) -> list[WeeklyLeaderboard]:
        ws = week_start or _current_week_start()
        async with async_session_factory() as session:
            stmt = (
                select(WeeklyLeaderboard)
                .where(
                    WeeklyLeaderboard.week_start == ws,
                    WeeklyLeaderboard.group_chat_id == group_chat_id,
                )
                .order_by(desc(WeeklyLeaderboard.total_score))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @staticmethod
    async def recalculate_ranks(
        group_chat_id: int | None = None, week_start: date | None = None
    ) -> None:
        ws = week_start or _current_week_start()
        async with async_session_factory() as session:
            ws = week_start or _current_week_start()
        async with async_session_factory() as session:
            stmt = select(WeeklyLeaderboard).where(
                WeeklyLeaderboard.week_start == ws,
            )
            if group_chat_id is not None:
                stmt = stmt.where(WeeklyLeaderboard.group_chat_id == group_chat_id)
            stmt = stmt.order_by(desc(WeeklyLeaderboard.total_score))

            result = await session.execute(stmt)
            entries = list(result.scalars().all())

            for i, entry in enumerate(entries):
                entry.rank = i + 1

            await session.commit()
            logger.info(
                "Ranks recalculados para semana %s (group=%s): %s entries",
                ws,
                group_chat_id,
                len(entries),
            )

    @staticmethod
    async def close_week(week_start: date | None = None) -> None:
        ws = week_start or _current_week_start()
        await LeaderboardRepository.recalculate_ranks(group_chat_id=None, week_start=ws)
        logger.info("Semana %s cerrada. Datos preservados como historico.", ws)
