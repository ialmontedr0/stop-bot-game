import logging

from sqlalchemy import desc, select

from src.db.engine import async_session_factory
from src.db.models import Player, WeeklyLeaderboard
from src.db.repositories.leaderboard_repository import LeaderboardRepository

logger = logging.getLogger(__name__)


class LeaderboardService:
    @staticmethod
    async def get_weekly_top(group_chat_id: int, limit: int = 10) -> list[dict]:
        entries = await LeaderboardRepository.get_weekly_top(
            group_chat_id=group_chat_id, limit=limit
        )
        if not entries:
            return []

        player_ids = [e.player_id for e in entries]
        async with async_session_factory() as session:
            stmt = select(Player).where(Player.id.in_(player_ids))
            result = await session.execute(stmt)
            players = {p.id: p for p in result.scalars().all()}

        result_list = []
        for i, entry in enumerate(entries):
            player = players.get(entry.player_id)
            result_list.append(
                {
                    "rank": entry.rank or (i + 1),
                    "telegram_id": player.telegram_id if player else None,
                    "name": player.first_name or player.username or f"ID{player.telegram_id}"
                    if player
                    else f"Player#{entry.player_id}",
                    "score": entry.total_score,
                    "games": entry.games_played,
                }
            )
        return result_list

    @staticmethod
    async def get_player_rank_by_telegram(telegram_id: int, group_chat_id: int) -> dict | None:
        """Busca por telegram_id en vez de player.id interno"""
        async with async_session_factory() as session:
            player_stmt = select(Player).where(Player.telegram_id == telegram_id)
            player_result = await session.execute(player_stmt)
            player = player_result.scalar_one_or_none()
            if not player:
                return None

            stmt = select(WeeklyLeaderboard).where(
                WeeklyLeaderboard.player_id == player.id,
                WeeklyLeaderboard.group_chat_id == group_chat_id,
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

    @staticmethod
    async def upsert_player(player_id: int, score_to_add: int, group_chat_id: int = 0) -> None:
        await LeaderboardRepository.upsert_player_week(
            player_id, score_to_add, group_chat_id=group_chat_id
        )


leaderboard_service = LeaderboardService()
