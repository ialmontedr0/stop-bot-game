import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.db.engine import async_session_factory
from src.db.models import Player, GamePlayer
from src.db.repositories.game_repository import GameRepository
from src.db.repositories.round_repository import RoundRepository
from src.keyboards.round import stop_keyboard, letter_keyboard

logger = logging.getLogger(__name__)

NUM_STOP_BUTTONS = 10
ROUND_DURATION = 60
TOTAL_ROUNDS = 5

CATEGORIES = [
    "Nombre", "Apellido", "Color", "Fruta",
    "País o Ciudad", "Artista o Banda", "Película o Serie", "Cosa",
    "Animal", "Profesión", "Deporte", "Marca",
]

CATEGORIES_DISPLAY = "\n".join(
    f"  <b>{cat}:</b> ..." for cat in CATEGORIES
)

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass
class RoundState:
    game_id: int
    group_chat_id: int
    round_number: int
    letter: str
    categories: list[str]
    message_chat_id: int
    message_id: int
    timer_task: Optional[asyncio.Task] = None
    submitted_player_ids: set[int] = field(default_factory=set)
    complete_player_ids: set[int] = field(default_factory=set)
    first_completer_id: Optional[int] = None
    first_completer_name: Optional[str] = None
    stop_presses: int = 0
    total_players: int = 0
    stop_message_chat_id: Optional[int] = None
    stop_message_id: Optional[int] = None
    player_names: dict[int, str] = field(default_factory=dict)


class RoundManager:
    def __init__(self) -> None:
        self._rounds: dict[int, RoundState] = {}

    def get_active_round(self, game_id: int) -> Optional[RoundState]:
        return self._rounds.get(game_id)

    def get_active_round_by_group(self, group_chat_id: int) -> Optional[RoundState]:
        for state in self._rounds.values():
            if state.group_chat_id == group_chat_id:
                return state
        return None

    async def start_round(
        self,
        game_id: int,
        group_chat_id: int,
        round_number: int,
        letter: str,
        total_players: int,
        player_names: dict[int, str],
        bot: Bot,
    ) -> None:
        text = self._format_round_message(round_number, letter)

        msg = await bot.send_message(group_chat_id, text)

        state = RoundState(
            game_id=game_id,
            group_chat_id=group_chat_id,
            round_number=round_number,
            letter=letter,
            categories=CATEGORIES,
            message_chat_id=msg.chat.id,
            message_id=msg.message_id,
            total_players=total_players,
            player_names=player_names,
        )

        state.timer_task = asyncio.create_task(
            self._round_timer(state, bot)
        )
        self._rounds[game_id] = state
        logger.info(
            "Ronda iniciada",
            extra=dict(
                game_id=game_id,
                round=round_number,
                letter=letter,
            ),
        )

    async def submit_answers(
        self,
        game_id: int,
        player: Player,
        text: str,
        bot: Bot,
    ) -> bool:
        state = self.get_active_round(game_id)
        if not state:
            return False

        parsed = parse_answers(text, state.categories)
        if not parsed:
            return False

        async with async_session_factory() as session:
            repo = RoundRepository(session)
            db_round = await repo.get_active_round(game_id)
            if not db_round:
                return False
            await repo.save_answers(
                round_id=db_round.id,
                game_id=game_id,
                player_id=player.id,
                answers=parsed,
            )

        state.submitted_player_ids.add(player.telegram_id)
        self._update_round_message(state, bot)

        all_filled = len(parsed) == len(state.categories)

        if all_filled:
            state.complete_player_ids.add(player.telegram_id)

            if state.first_completer_id is None:
                state.first_completer_id = player.telegram_id
                name = player.first_name or player.username or f"ID{player.telegram_id}"
                state.first_completer_name = name

                await self._send_stop_message(state, bot)

        await self._check_all_submitted(state, bot)
        return all_filled and state.first_completer_id == player.telegram_id

    async def press_stop(
        self,
        game_id: int,
        player_id: int,
        callback,
        bot: Bot,
    ) -> None:
        state = self.get_active_round(game_id)
        if not state:
            await callback.answer("❌ Esta ronda ya terminó.", show_alert=True)
            return

        if player_id != state.first_completer_id:
            await callback.answer(
                "❌ Solo puedes usar Stop si completaste todas las categorías.",
                show_alert=True,
            )
            return

        state.stop_presses += 1

        if state.stop_presses >= NUM_STOP_BUTTONS:
            await callback.answer("⏹ ¡Ronda detenida!", show_alert=False)
            await self._close_round(game_id, "stop", bot)
            return

        progress = state.stop_presses
        await callback.answer(
            f"⏹ Stop {progress}/{NUM_STOP_BUTTONS}", show_alert=False
        )

        try:
            await bot.edit_message_text(
                self._format_stop_message(progress),
                chat_id=state.stop_message_chat_id,
                message_id=state.stop_message_id,
                reply_markup=stop_keyboard(game_id, progress + 1),
            )
        except TelegramBadRequest:
            pass

    async def _close_round(
        self,
        game_id: int,
        reason: str,
        bot: Bot,
    ) -> None:
        state = self._rounds.pop(game_id, None)
        if not state:
            return

        if state.timer_task and not state.timer_task.done():
            state.timer_task.cancel()

        reason_texts = {
            "stop": "⏹ <b>Ronda detenida</b>",
            "timeout": "⌛ <b>Tiempo agotado</b>",
            "all_submitted": "✅ <b>¡Todos respondieron!</b>",
        }
        reason_text = reason_texts.get(reason, "⏹ <b>Ronda cerrada</b>")

        async with async_session_factory() as session:
            repo = RoundRepository(session)
            db_round = await repo.get_active_round(game_id)
            if db_round:
                stopped_by = None
                if reason == "stop" and state.first_completer_id:
                    stopped_by = state.first_completer_id
                await repo.update_status(
                    db_round.id,
                    status="completed",
                    stopped_by_player_id=stopped_by,
                )

        try:
            await bot.edit_message_text(
                f"{reason_text}\n\n"
                f"<b>Ronda {state.round_number}</b> — Letra: <b>{state.letter}</b>\n\n"
                f"<i>Calculando puntuaciones...</i>",
                chat_id=state.message_chat_id,
                message_id=state.message_id,
            )
        except TelegramBadRequest:
            pass

        if state.stop_message_id:
            try:
                await bot.edit_message_text(
                    f"{reason_text}\n\nLa ronda ha finalizado.",
                    chat_id=state.stop_message_chat_id,
                    message_id=state.stop_message_id,
                )
            except TelegramBadRequest:
                pass

        summary = await self._build_summary(game_id, state)
        await bot.send_message(state.group_chat_id, summary)

        await self._transition_next_round(state, bot)

    async def _transition_next_round(
        self,
        state: RoundState,
        bot: Bot,
    ) -> None:
        if state.round_number >= TOTAL_ROUNDS:
            await self._end_game(state, bot)
            return

        leader_id = await self._get_leader_telegram_id(state.game_id)
        if not leader_id:
            leader_id = state.first_completer_id
        if not leader_id:
            await self._start_next_round_with_random(state, bot)
            return

        name = state.player_names.get(leader_id, "El líder")
        msg = await bot.send_message(
            state.group_chat_id,
            f"🏆 <b>{name}, elige la letra de la siguiente ronda:</b>",
            reply_markup=letter_keyboard(state.game_id),
        )
        asyncio.create_task(self._letter_timeout(msg, bot, state))

    async def _letter_timeout(self, msg, bot, state):
        await asyncio.sleep(15)
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        letter = random.choice(ALPHABET)
        await self._start_next_round_with_letter(state, letter, bot)

    async def handle_letter_selection(
        self,
        game_id: int,
        player_id: int,
        letter: str,
        callback,
        bot: Bot,
    ) -> None:
        state = self._rounds.get(game_id)
        if not state:
            await callback.answer("❌ Partida no activa.", show_alert=True)
            return

        next_number = state.round_number + 1

        await callback.answer(f"✅ Letra {letter} seleccionada", show_alert=False)

        countdown = await bot.send_message(
            state.group_chat_id,
            f"<b>Letra: {letter}</b>\n"
            f"⏱ Siguiente ronda en 5 segundos...",
        )
        await asyncio.sleep(5)
        try:
            await countdown.delete()
        except TelegramBadRequest:
            pass

        await self.start_round(
            game_id=game_id,
            group_chat_id=state.group_chat_id,
            round_number=next_number,
            letter=letter,
            total_players=state.total_players,
            player_names=state.player_names,
            bot=bot,
        )

    async def _start_next_round_with_letter(
        self,
        prev_state: RoundState,
        letter: str,
        bot: Bot,
    ) -> None:
        await self.start_round(
            game_id=prev_state.game_id,
            group_chat_id=prev_state.group_chat_id,
            round_number=prev_state.round_number + 1,
            letter=letter,
            total_players=prev_state.total_players,
            player_names=prev_state.player_names,
            bot=bot,
        )

    async def _start_next_round_with_random(self, state, bot):
        letter = random.choice(ALPHABET)
        await self._start_next_round_with_letter(state, letter, bot)

    async def _end_game(self, state: RoundState, bot: Bot) -> None:
        async with async_session_factory() as session:
            repo = GameRepository(session)
            db_game = await repo.get_by_id(state.game_id)
            if db_game:
                await repo.update_game_status(db_game, "finished")

            winners = await self._get_standings(state.game_id)
        lines = ["<b>🏆 ¡Partida finalizada!</b>", ""]
        for i, (pid, score) in enumerate(winners[:3]):
            medals = ["🥇", "🥈", "🥉"]
            name = state.player_names.get(pid, f"Jugador {pid}")
            lines.append(f"{medals[i] if i < 3 else i + 1}. {name} — {score} pts")
        lines.append("")
        lines.append("<i>Gracias por jugar 🛑 Stop!</i>")
        await bot.send_message(state.group_chat_id, "\n".join(lines))

    async def _check_all_submitted(self, state: RoundState, bot: Bot) -> None:
        if len(state.submitted_player_ids) >= state.total_players:
            await asyncio.sleep(0.5)
            asyncio.create_task(
                self._close_round(state.game_id, "all_submitted", bot)
            )

    async def _send_stop_message(self, state: RoundState, bot: Bot) -> None:
        text = self._format_stop_message(0)
        stop_msg = await bot.send_message(
            state.first_completer_id,
            text,
            reply_markup=stop_keyboard(state.game_id, 1),
        )
        state.stop_message_chat_id = stop_msg.chat.id
        state.stop_message_id = stop_msg.message_id

        self._update_round_message(state, bot)

    def _update_round_message(self, state: RoundState, bot: Bot) -> None:
        asyncio.create_task(self._do_update_round_message(state, bot))

    async def _do_update_round_message(
        self, state: RoundState, bot: Bot
    ) -> None:
        lines = [self._format_round_message(state.round_number, state.letter)]

        if state.submitted_player_ids:
            lines.append("")
            lines.append("✅ <b>Respondieron:</b>")
            for pid in state.submitted_player_ids:
                name = state.player_names.get(pid, f"Jugador {pid}")
                completed = "⭐" if pid in state.complete_player_ids else "⬜"
                lines.append(f"  {completed} {name}")

        if state.first_completer_id:
            name = state.first_completer_name or "Alguien"
            lines.append("")
            lines.append(f"⏹ <b>{name} completó todas las categorías</b>")
            lines.append(
                f"  Stop: {state.stop_presses}/{NUM_STOP_BUTTONS}"
            )

        try:
            await bot.edit_message_text(
                "\n".join(lines),
                chat_id=state.message_chat_id,
                message_id=state.message_id,
            )
        except TelegramBadRequest:
            pass

    async def _build_summary(
        self, game_id: int, state: RoundState
    ) -> str:
        async with async_session_factory() as session:
            repo = RoundRepository(session)
            db_round = await repo.get_active_round(game_id)
            if db_round:
                await repo.update_status(db_round.id, "scored")
            all_rounds_answers = await repo.get_answers_by_player(
                db_round.id if db_round else 0
            )

        lines = [
            f"<b>📊 Ronda {state.round_number} — Resumen</b>",
            f"  Letra: <b>{state.letter}</b>",
            "",
        ]

        scores = {}
        for pid, answers in all_rounds_answers.items():
            filled = sum(1 for a in answers if a.raw_text.strip())
            scores[pid] = filled

        for pid, score in sorted(
            scores.items(), key=lambda x: x[1], reverse=True
        ):
            name = state.player_names.get(
                pid, f"Jugador {pid}"
            )
            total = len(state.categories)
            lines.append(
                f"  {name}: {score}/{total} categorías"
            )

        if state.first_completer_name:
            lines.append("")
            lines.append(
                f"⭐ <b>{state.first_completer_name}</b> fue el primero "
                f"en completar todas las categorías."
            )

        return "\n".join(lines)

    async def _get_leader_telegram_id(self, game_id: int) -> Optional[int]:
        async with async_session_factory() as session:
            stmt = (
                select(GamePlayer, Player)
                .join(Player, GamePlayer.player_id == Player.id)
                .where(GamePlayer.game_id == game_id)
                .order_by(GamePlayer.score.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.one_or_none()
            if row:
                return row.Player.telegram_id
            return None

    async def _get_standings(
        self, game_id: int
    ) -> list[tuple[int, int]]:
        async with async_session_factory() as session:
            stmt = (
                select(GamePlayer, Player)
                .join(Player, GamePlayer.player_id == Player.id)
                .where(GamePlayer.game_id == game_id)
                .order_by(GamePlayer.score.desc())
            )
            rows = await session.execute(stmt)
            return [(row.Player.telegram_id, row.GamePlayer.score) for row in rows]

    async def _round_timer(self, state: RoundState, bot: Bot) -> None:
        try:
            await asyncio.sleep(ROUND_DURATION)
            await self._close_round(state.game_id, "timeout", bot)
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _format_round_message(round_number: int, letter: str) -> str:
        return (
            f"🛑 <b>Ronda {round_number} — Letra: {letter}</b>\n"
            f"⏱ {ROUND_DURATION} segundos\n\n"
            f"Envía tus respuestas en este formato:\n\n"
            f"{CATEGORIES_DISPLAY}"
        )

    @staticmethod
    def _format_stop_message(presses: int) -> str:
        return (
            "⏹ <b>¡Has completado todas las categorías!</b>\n\n"
            "Presiona <b>Stop</b> repetidamente para cerrar la ronda.\n"
            f"Progreso: {presses}/{NUM_STOP_BUTTONS}\n\n"
            "<i>Si todos los jugadores responden, la ronda se cerrará "
            "automáticamente.</i>"
        )


ANSWER_REGEX = re.compile(r"^\s*(.+?)\s*:\s*(.*?)\s*$", re.MULTILINE)


def parse_answers(text: str, categories: list[str]) -> dict[str, str]:
    cat_map = {cat.lower(): cat for cat in categories}
    result = {}

    for match in ANSWER_REGEX.finditer(text):
        raw_cat = match.group(1).strip().lower()
        value = match.group(2).strip()
        if raw_cat in cat_map:
            result[cat_map[raw_cat]] = value

    return result


round_manager = RoundManager()
