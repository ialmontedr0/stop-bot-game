import logging
from datetime import date, timedelta

from sqlalchemy import select

from src.db.engine import async_session_factory
from src.db.models import PlayerXP, Streak

logger = logging.getLogger(__name__)

LEVEL_TABLE = [
    (1, 0),
    (2, 100),
    (3, 250),
    (4, 500),
    (5, 800),
    (6, 1200),
    (7, 1700),
    (8, 2300),
    (9, 3000),
    (10, 4000),
    (11, 5000),
    (12, 6500),
    (13, 8000),
    (14, 10000),
    (15, 12500),
    (16, 15000),
    (17, 18000),
    (18, 21000),
    (19, 25000),
    (20, 30000),
]

XP_PER_GAME = 50
XP_PER_WIN = 100
XP_PER_STOP = 25
XP_PER_UNIQUE = 10
XP_STREAK_BONUS = 20

RANK_TITLES = {
    1: "Novato",
    5: "Aprendiz",
    10: "Veterano",
    15: "Maestro",
    20: "Leyenda",
}


def _calculate_level(total_xp: int) -> int:
    level = 1
    for lvl, required in reversed(LEVEL_TABLE):
        if total_xp >= required:
            level = lvl
            break
    return level


def _get_xp_for_next_level(current_level: int) -> int:
    for lvl, required in LEVEL_TABLE:
        if lvl == current_level + 1:
            return required
    return 999999


class XPService:
    @staticmethod
    async def award_game_xp(
        player_id: int,
        final_position: int,
        was_stopper: bool = False,
        unique_answers: int = 0,
    ) -> dict:
        async with async_session_factory() as session:
            stmt = select(PlayerXP).where(PlayerXP.player_id == player_id)
            result = await session.execute(stmt)
            xp_record = result.scalar_one_or_none()
            if not xp_record:
                xp_record = PlayerXP(player_id=player_id)
                session.add(xp_record)
                await session.flush()
                await session.refresh(xp_record)

            old_level = xp_record.level

            xp_gained = XP_PER_GAME
            if final_position == 1:
                xp_gained += XP_PER_WIN
            if was_stopper:
                xp_gained += XP_PER_STOP
            xp_gained += unique_answers * XP_PER_UNIQUE

            streak_stmt = select(Streak).where(Streak.player_id == player_id)
            streak_result = await session.execute(streak_stmt)
            streak = streak_result.scalar_one_or_none()
            if streak and streak.current_streak >= 3:
                xp_gained += XP_STREAK_BONUS

            from src.services.event_service import event_service

            multiplier = await event_service.get_active_multiplier()
            xp_gained = int(xp_gained * multiplier)

            xp_record.xp += xp_gained
            xp_record.total_xp_earned += xp_gained
            xp_record.level = _calculate_level(xp_record.total_xp_earned)

            await session.commit()

            leveled_up = xp_record.level > old_level
            new_title = RANK_TITLES.get(xp_record.level)

            return {
                "xp_gained": xp_gained,
                "total_xp": xp_record.total_xp_earned,
                "level": xp_record.level,
                "leveled_up": leveled_up,
                "title": new_title,
                "multiplier": multiplier,
            }

    @staticmethod
    async def update_streak(player_id: int) -> dict:
        async with async_session_factory() as session:
            stmt = select(Streak).where(Streak.player_id == player_id)
            result = await session.execute(stmt)
            streak = result.scalar_one_or_none()
            if not streak:
                streak = Streak(player_id=player_id, current_streak=0, max_streak=0)
                session.add(streak)

            today = date.today()
            if streak.last_played_date is None:
                streak.current_streak = 1
            elif streak.last_played_date == today:
                pass
            elif streak.last_played_date == today - timedelta(days=1):
                streak.current_streak += 1
            else:
                streak.current_streak = 1

            if streak.current_streak > streak.max_streak:
                streak.max_streak = streak.current_streak
            streak.last_played_date = today

            await session.commit()

            return {
                "current_streak": streak.current_streak,
                "max_streak": streak.max_streak,
            }

    @staticmethod
    async def get_profile(player_id: int) -> dict | None:
        async with async_session_factory() as session:
            stmt = select(PlayerXP).where(PlayerXP.player_id == player_id)
            result = await session.execute(stmt)
            xp_record = result.scalar_one_or_none()

            streak_stmt = select(Streak).where(Streak.player_id == player_id)
            streak_result = await session.execute(streak_stmt)
            streak = streak_result.scalar_one_or_none()

        if not xp_record:
            return {
                "xp": 0,
                "total_xp": 0,
                "level": 1,
                "title": "Novato",
                "next_level_xp": 100,
                "current_level_xp": 0,
                "progress_pct": 0.0,
                "streak": streak.current_streak if streak else 0,
                "max_streak": streak.max_streak if streak else 0,
            }

        next_level_xp = _get_xp_for_next_level(xp_record.level)
        current_level_xp = 0
        for lvl, required in LEVEL_TABLE:
            if lvl == xp_record.level:
                current_level_xp = required
                break

        progress = 0
        if next_level_xp > current_level_xp:
            progress = (
                (xp_record.total_xp_earned - current_level_xp)
                / (next_level_xp - current_level_xp)
                * 100
            )

        return {
            "xp": xp_record.xp,
            "total_xp": xp_record.total_xp_earned,
            "level": xp_record.level,
            "title": RANK_TITLES.get(xp_record.level, ""),
            "next_level_xp": next_level_xp,
            "current_level_xp": current_level_xp,
            "progress_pct": round(progress, 1),
            "streak": streak.current_streak if streak else 0,
            "max_streak": streak.max_streak if streak else 0,
        }


xp_service = XPService()
