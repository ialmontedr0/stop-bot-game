from typing import Optional

from sqlalchemy import select

from src.db.models import Player

from .base import BaseRepository


class PlayerRepository(BaseRepository[Player]):
    def __init__(self, session):
        super().__init__(Player, session)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Player]:
        stmt = select(Player).where(Player.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: str = "",
        last_name: Optional[str] = None,
        language_code: Optional[str] = None,
    ) -> Player:
        player = await self.get_by_telegram_id(telegram_id)
        if player:
            changed = False
            for field, value in [
                ("username", username),
                ("first_name", first_name),
                ("last_name", last_name),
                ("language_code", language_code),
            ]:
                if value is not None and getattr(player, field) != value:
                    setattr(player, field, value)
                    changed = True
            if changed:
                await self.session.flush()
            return player
        instance = Player(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance
