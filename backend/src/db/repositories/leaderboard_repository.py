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
        week_start: date | None = None,
    ) -> None:
        ws = week_start or _current_week_start()
        async with async_session_factory() as session:
            stmt = select(WeeklyLeaderboard).where(
                WeeklyLeaderboard.player_id == player_id,
                WeeklyLeaderboard.week_start == ws,
            )
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()

            if entry:
                entry.total_score += score_to_add
                entry.games_played += 1
            else:
                entry = WeeklyLeaderboard(
                    player_id=player_id,
                    week_start=ws,
                    total_score=score_to_add,
                    games_played=1,
                )
                session.add(entry)

            await session.commit()

    @staticmethod
    async def recalculate_ranks(week_start: date | None = None) -> None:
        ws = week_start or _current_week_start()
        async with async_session_factory() as session:
            stmt = (
                select(WeeklyLeaderboard)
                .where(WeeklyLeaderboard.week_start == ws)
                .order_by(desc(WeeklyLeaderboard.total_score))
            )
            result = await session.execute(stmt)
            entries = result.scalars().all()

            for i, entry in enumerate(entries):
                entry.rank = i + 1

            await session.commit()
            logger.info("Ranks recalculados para semana %s: %s entries", ws, len(entries))

    @staticmethod
    async def close_week(week_start: date | None = None) -> None:
        ws = week_start or _current_week_start()
        await LeaderboardRepository.recalculate_ranks(ws)
        logger.info("Semana %s cerrada. Datos preservados como historico.", ws)
