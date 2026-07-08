import logging

from sqlalchemy import select, func, desc

from src.db.engine import async_session_factory
from src.db.models import WeeklyLeaderboard, Player

logger = logging.getLogger(__name__)


class LeaderboardService:
    @staticmethod
    async def get_weekly_top(limit: int = 10) -> list[dict]:
        async with async_session_factory() as session:
            stmt = (
                select(WeeklyLeaderboard, Player)
                .join(Player, WeeklyLeaderboard.player_id == Player.id)
                .order_by(desc(WeeklyLeaderboard.total_score))
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.all()
            return [
                {
                    "rank": row.WeeklyLeaderboard.rank or (i + 1),
                    "player_id": row.Player.telegram_id,
                    "name": row.Player.first_name or row.Player.username or f"ID{row.Player.telegram_id}",
                    "score": row.WeeklyLeaderboard.total_score,
                    "games": row.WeeklyLeaderboard.games_played,
                }
                for i, row in enumerate(rows)
            ]

    @staticmethod
    async def get_player_rank(player_id: int) -> dict | None:
        async with async_session_factory() as session:
            stmt = select(WeeklyLeaderboard).where(
                WeeklyLeaderboard.player_id == player_id
            )
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()
            if not entry:
                return None
            return {
                "rank": entry.rank,
                "score": entry.total_score,
                "games": entry.games_played,
            }


leaderboard_service = LeaderboardService()
