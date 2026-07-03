from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Row, select

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

    async def get_by_id(self, game_id: int) -> Optional[Game]:
        return await self.session.get(Game, game_id)

    async def create_game(self, group_chat_id: int, total_rounds: int = 5) -> Game:
        game = Game(
            group_chat_id=group_chat_id,
            status="lobby",
            total_rounds=total_rounds,
        )
        self.session.add(game)
        await self.session.commit()
        await self.session.refresh(game)
        return game

    async def add_player_to_game(
        self,
        game: Game,
        player: Player,
        is_host: bool = False,
    ) -> GamePlayer:
        gp = GamePlayer(
            game_id=game.id,
            player_id=player.id,
            is_host=is_host,
        )
        self.session.add(gp)
        await self.session.commit()
        await self.session.refresh(gp)
        return gp

    async def get_players_for_game(self, game: Game) -> list[Row]:
        stmt = (
            select(GamePlayer, Player)
            .join(Player, GamePlayer.player_id == Player.id)
            .where(GamePlayer.game_id == game.id)
            .order_by(GamePlayer.joined_at)
        )
        result = await self.session.execute(stmt)
        return result.all()

    async def get_player_count(self, game: Game) -> int:
        stmt = select(GamePlayer).where(GamePlayer.game_id == game.id)
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    async def is_player_in_game(self, game: Game, player: Player) -> bool:
        stmt = (
            select(GamePlayer)
            .where(GamePlayer.game_id == game.id)
            .where(GamePlayer.player_id == player.id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def update_game_status(self, game: Game, status: str) -> Game:
        game.status = status
        await self.session.commit()
        await self.session.refresh(game)
        return game

    async def get_stale_games(self) -> list[Game]:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        stmt = (
            select(Game)
            .where(Game.status.in_(["lobby", "playing"]))
            .where(Game.created_at < cutoff)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
