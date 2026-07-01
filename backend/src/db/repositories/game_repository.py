from typing import Optional

from sqlalchemy import select

from src.db.models import Game, GamePlayer, Player

from .base import BaseRepository


class GameRepository(BaseRepository[Game]):
    def __init__(self, session):
        super().__init__(Game, session)

    async def get_active_game(self, group_chat_id: int) -> Optional[Game]:
        stmt = (
            select(Game)
            .where(Game.group_chat_id == group_chat_id)
            .where(Game.status.in_(["lobby", "playing"]))
            .order_by(Game.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_player_to_game(
        self, game: Game, player: Player, is_host: bool = False
    ) -> GamePlayer:
        gp = GamePlayer(game_id=game.id, player_id=player.id, is_host=is_host)
        self.session.add()
        await self.session.commit()
        await self.session.refresh(gp)
        return gp

    async def get_player_count(self, game: Game) -> int:
        stmt = select(GamePlayer).where(GamePlayer.game_id == game.id)
        result = await self.session.execute(stmt)
        return len(result.scalars().all())
