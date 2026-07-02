from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.models import Answer, GamePlayer, Player, Round

from .base import BaseRepository


class RoundRepository(BaseRepository[Round]):
    def __init__(self, session):
        super().__init__(Round, session)

    async def create_round(
        self,
        game_id: int,
        round_number: int,
        letter: str,
    ) -> Round:
        r = Round(
            game_id=game_id,
            round_number=round_number,
            letter=letter,
            status="active",
        )
        self.session.add(r)
        await self.session.commit()
        await self.session.refresh(r)
        return r

    async def get_active_round(self, game_id: int) -> Optional[Round]:
        stmt = (
            select(Round)
            .where(Round.game_id == game_id)
            .where(Round.status == "active")
            .order_by(Round.round_number.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        round_id: int,
        status: str,
        stopped_by_player_id: Optional[int] = None,
    ) -> Round:
        r = await self.session.get(Round, round_id)
        if not r:
            raise ValueError(f"Round {round_id} not found")
        r.status = status
        if stopped_by_player_id is not None:
            r.stopped_by_player_id = stopped_by_player_id
        await self.session.commit()
        await self.session.refresh(r)
        return r

    async def save_answers(
        self,
        round_id: int,
        game_id: int,
        player_id: int,
        answers: dict[str, str],
    ) -> list[Answer]:
        stmt = select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.player_id == player_id,
        )
        gp = (await self.session.execute(stmt)).scalar_one_or_none()
        if not gp:
            raise ValueError(
                f"GamePlayer not found for game={game_id} player={player_id}"
            )

        old = await self.session.execute(
            select(Answer).where(
                Answer.round_id == round_id,
                Answer.player_id == player_id,
            )
        )
        for a in old.scalars():
            await self.session.delete(a)
        await self.session.flush()

        result = []
        for slot, value in answers.items():
            a = Answer(
                round_id=round_id,
                player_id=player_id,
                game_player_id=gp.id,
                word_slot=slot,
                raw_text=value,
            )
            self.session.add(a)
            result.append(a)
        await self.session.commit()
        for a in result:
            await self.session.refresh(a)
        return result

    async def get_answers_by_player(self, round_id: int) -> dict[int, list[Answer]]:
        stmt = (
            select(Answer)
            .options(selectinload(Answer.player))
            .where(Answer.round_id == round_id)
            .order_by(Answer.player_id)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        result: dict[int, list[Answer]] = {}
        for a in rows:
            result.setdefault(a.player.telegram_id, []).append(a)
        return result

    async def get_total_rounds(self, game_id: int) -> int:
        stmt = select(Round).where(Round.game_id == game_id)
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    async def update_answer_scores(
        self,
        answer_scores: list[tuple[int, bool, int]],
    ) -> None:
        for answer_id, is_correct, score in answer_scores:
            ans = await self.session.get(Answer, answer_id)
            if ans:
                ans.is_correct = is_correct
                ans.score = score
        await self.session.flush()

    async def get_game_player_by_telegram(
        self, game_id: int, telegram_id: int
    ) -> Optional[GamePlayer]:
        stmt = (
            select(GamePlayer)
            .join(Player, GamePlayer.player_id == Player.id)
            .where(GamePlayer.game_id == game_id, Player.telegram_id == telegram_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
