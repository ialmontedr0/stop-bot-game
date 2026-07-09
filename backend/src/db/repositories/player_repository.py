
from sqlalchemy import select

from src.db.models import Player

from .base import BaseRepository


class PlayerRepository(BaseRepository[Player]):
    def __init__(self, session):
        super().__init__(Player, session)

    async def get_by_telegram_id(self, telegram_id: int) -> Player | None:
        stmt = select(Player).where(Player.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str = "",
        last_name: str | None = None,
        language_code: str | None = None,
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
                await self.session.commit()
            return player
        instance = Player(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
        )
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance
