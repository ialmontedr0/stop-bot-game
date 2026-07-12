import asyncio
import contextlib
import logging
import random
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramRetryAfter,
)
from sqlalchemy import select

from src.db.engine import async_session_factory
from src.db.models import GamePlayer, Player
from src.db.repositories.game_repository import GameRepository
from src.db.repositories.round_repository import RoundRepository
from src.image_generator import generate_podium_image
from src.keyboards.round import inter_round_keyboard, letter_keyboard, stop_keyboard
from src.services.score_engine import FIRST_COMPLETER_BONUS, ScoreEngine
from src.services.spell_corrector import get_corrector
from src.services.xp_service import xp_service

logger = logging.getLogger(__name__)

NUM_STOP_BUTTONS = 10
ROUND_DURATION = 60
TOTAL_ROUNDS = 5

CATEGORIES = [
    "Nombre",
    "Apellido",
    "Color",
    "Fruta",
    "País",
    "Artista",
    "Animal",
    "Cosa",
]

CATEGORIES_DISPLAY = "\n".join(f"  <b>{cat}:</b> ..." for cat in CATEGORIES)
PLACEHOLDER = "\n".join(f"{cat}: ..." for cat in CATEGORIES)

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
    host_telegram_id: int
    round_time: int = 60
    include_n: bool = False
    timer_task: asyncio.Task | None = None
    submitted_player_ids: set[int] = field(default_factory=set)
    submission_order: list[int] = field(default_factory=list)
    complete_player_ids: set[int] = field(default_factory=set)
    first_completer_id: int | None = None
    first_completer_db_id: int | None = None
    first_completer_name: str | None = None
    leader_id: int | None = None
    letter_timeout_task: asyncio.Task | None = None
    update_task: asyncio.Task | None = None
    stop_presses: int = 0
    total_players: int = 0
    total_rounds: int = TOTAL_ROUNDS
    stop_message_chat_id: int | None = None
    stop_message_id: int | None = None
    letter_message_chat_id: int | None = None
    letter_message_id: int | None = None
    player_names: dict[int, str] = field(default_factory=dict)
    inter_round_message_id: int | None = None
    inter_round_timeout_task: asyncio.Task | None = None
    cancelled: bool = False
    validation_mode: str = "local"


class RoundManager:
    def __init__(self) -> None:
        self._rounds: dict[int, RoundState] = {}
        self._rounds_by_group: dict[int, int] = {}
        self._letter_pending: dict[int, RoundState] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock_for(self, game_id: int) -> asyncio.Lock:
        if game_id not in self._locks:
            self._locks[game_id] = asyncio.Lock()
        return self._locks[game_id]

    def get_active_round(self, game_id: int) -> RoundState | None:
        return self._rounds.get(game_id)

    def get_active_round_by_group(self, group_chat_id: int) -> RoundState | None:
        game_id = self._rounds_by_group.get(group_chat_id)
        if game_id is not None:
            return self._rounds.get(game_id)
        for state in self._rounds.values():
            if state.group_chat_id == group_chat_id:
                self._rounds_by_group[group_chat_id] = state.game_id
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
        total_rounds: int = TOTAL_ROUNDS,
        host_telegram_id: int | None = None,
        round_time: int = 60,
        categories: list[str] | None = None,
        include_n: bool = False,
        validation_mode: str = "local",
    ) -> None:
        # Usar categorias de GroupConfig (o las default)
        effective_categories = categories or CATEGORIES

        text = self._format_round_message(round_number, letter, effective_categories, round_time)

        while True:
            try:
                from src.image_generator import generate_round_letter_image

                img_bytes = generate_round_letter_image(
                    letter=letter,
                    round_number=round_number,
                    category_count=len(effective_categories),
                )
                if img_bytes:
                    from aiogram.types import BufferedInputFile

                    photo = BufferedInputFile(img_bytes, filename=f"round_{round_number}.png")
                    await bot.send_photo(
                        chat_id=group_chat_id,
                        photo=photo,
                        caption=f"🛑 <b>Ronda: {round_number} - Letra: {letter}</b>",
                    )

                msg = await bot.send_message(group_chat_id, text)
                break
            except TelegramRetryAfter as e:
                logger.warning("Flood al iniciar ronda, esperando %ss", e.retry_after)
                await asyncio.sleep(e.retry_after)

        state = RoundState(
            game_id=game_id,
            group_chat_id=group_chat_id,
            round_number=round_number,
            letter=letter,
            categories=effective_categories,
            message_chat_id=msg.chat.id,
            message_id=msg.message_id,
            total_players=total_players,
            total_rounds=total_rounds,
            player_names=player_names,
            host_telegram_id=host_telegram_id or 0,
            round_time=round_time,
            include_n=include_n,
            validation_mode=validation_mode,
        )

        async with async_session_factory() as session:
            repo = RoundRepository(session)
            await repo.create_round(game_id=game_id, round_number=round_number, letter=letter)

        # Cancelar timer anterior si existe (evita timers huérfanos)
        old_state = self._rounds.get(game_id)
        if old_state:
            if old_state.timer_task and not old_state.timer_task.done():
                old_state.timer_task.cancel()
            if old_state.letter_timeout_task and not old_state.letter_timeout_task.done():
                old_state.letter_timeout_task.cancel()
            if old_state.inter_round_timeout_task and not old_state.inter_round_timeout_task.done():
                old_state.inter_round_timeout_task.cancel()

        self._rounds[game_id] = state
        self._rounds_by_group[group_chat_id] = game_id
        # No popear _letter_pending — evita race condition con handle_letter_selection
        # self._letter_pending.pop(game_id, None)
        if state.validation_mode in ("ai", "hybrid"):
            get_corrector().reset_api_counter()
        state.timer_task = asyncio.create_task(self._round_timer(state, bot))
        logger.info(
            "Ronda iniciada",
            extra={
                "game_id": game_id,
                "round": round_number,
                "letter": letter,
            },
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
            logger.info("submit_answers: no active round for game %s", game_id)
            return False

        parsed = parse_answers(text, state.categories)
        if not parsed:
            logger.info("submit_answers: no categories parsed from text")
            return False

        # NUEVO: validar respuestas con SpellCorrector en modo hybrid/ai
        # Las respuestas invalidas semanticamente se vacian (0 puntos)

        from src.services.spell_corrector import get_corrector

        corrector = get_corrector()
        effective_validation_mode = state.validation_mode or corrector.mode
        if effective_validation_mode in ("ai", "hybrid"):

            async def _validate_slot(slot: str, raw_text: str) -> tuple[str, str, bool]:
                if raw_text and raw_text.strip():
                    is_valid = await corrector.validate(raw_text, slot, mode=effective_validation_mode)
                    return slot, raw_text, is_valid
                return slot, raw_text, True

            tasks = [_validate_slot(slot, raw_text) for slot, raw_text in list(parsed.items())]
            results = await asyncio.gather(*tasks)
            for slot, raw_text, is_valid in results:
                if not is_valid:
                    parsed[slot] = ""
                    logger.info(
                        "Respuesta rechazada por IA: %s=%s (player=%s)",
                        slot,
                        raw_text,
                        player.id,
                    )

        try:
            async with async_session_factory() as session:
                repo = RoundRepository(session)
                db_round = await repo.get_active_round(game_id)
                if not db_round:
                    logger.info("submit_answers: no active round in DB for game %s", game_id)
                    return False
                await repo.save_answers(
                    round_id=db_round.id,
                    game_id=game_id,
                    player_id=player.id,
                    answers=parsed,
                )
        except Exception:
            logger.exception(
                "Error al guardar respuestas en DB: game_id=%s player_id=%s",
                game_id,
                player.id,
            )
            return False

        send_stop = False
        async with self._lock_for(game_id):
            is_first = player.telegram_id not in state.submitted_player_ids
            state.submitted_player_ids.add(player.telegram_id)
            if is_first:
                state.submission_order.append(player.telegram_id)
            self._debounced_update(state, bot)

            all_filled = len(parsed) == len(state.categories)
            logger.info(
                "submit_answers: categories=%s parsed=%s all_filled=%s",
                len(state.categories),
                len(parsed),
                all_filled,
            )

            if all_filled:
                state.complete_player_ids.add(player.telegram_id)

                if state.first_completer_id is None:
                    state.first_completer_id = player.telegram_id
                    state.first_completer_db_id = player.id
                    name = player.first_name or player.username or f"ID{player.telegram_id}"
                    state.first_completer_name = name

                    logger.info(
                        "Enviando botón Stop para game %s, player %s",
                        game_id,
                        player.telegram_id,
                    )
                    send_stop = True
                else:
                    logger.info(
                        "first_completer_id ya era %s, no se envía otro Stop",
                        state.first_completer_id,
                    )

            all_submitted = await self._check_all_submitted(state)
        # Lock liberado aqui
        if send_stop:
            await self._send_stop_message(state, bot)
        if all_submitted:
            await self._close_round(game_id, "all_submitted", bot)
        return all_filled and state.first_completer_id == player.telegram_id

    async def press_stop(
        self,
        game_id: int,
        player_id: int,
        callback,
        bot: Bot,
    ) -> None:
        async with self._lock_for(game_id):
            state = self.get_active_round(game_id)
            if not state:
                await callback.answer("❌ Esta ronda ya terminó.", show_alert=False)
                return

            if player_id != state.first_completer_id:
                await callback.answer(
                    "❌ Solo puedes usar Stop si completaste todas las categorías.",
                    show_alert=False,
                )
                return

            state.stop_presses += 1

            if state.stop_presses >= NUM_STOP_BUTTONS:
                with contextlib.suppress(TelegramBadRequest, TelegramRetryAfter):
                    await bot.edit_message_text(
                        self._format_stop_message(NUM_STOP_BUTTONS),
                        chat_id=state.stop_message_chat_id,
                        message_id=state.stop_message_id,
                    )
                await callback.answer("⏹ ¡Ronda detenida!", show_alert=False)
                await self._close_round(game_id, "stop", bot)
                return

        progress = state.stop_presses
        await callback.answer(f"⏹ Stop {progress}/{NUM_STOP_BUTTONS}", show_alert=False)

        with contextlib.suppress(TelegramBadRequest, TelegramRetryAfter):
            await bot.edit_message_text(
                self._format_stop_message(progress),
                chat_id=state.stop_message_chat_id,
                message_id=state.stop_message_id,
                reply_markup=stop_keyboard(game_id, progress + 1),
            )

    async def _close_round(self, game_id: int, reason: str, bot: Bot) -> None:
        # Pop del state y cancelación de timers bajo el lock
        async with self._lock_for(game_id):
            state = self._rounds.pop(game_id, None)
            if not state:
                return
            if state.timer_task and not state.timer_task.done() and reason != "timeout":
                state.timer_task.cancel()
            if state.letter_timeout_task and not state.letter_timeout_task.done():
                state.letter_timeout_task.cancel()
                state.letter_timeout_task = None
            self._rounds_by_group.pop(state.group_chat_id, None)

        # A partir de aquí NO hay lock — operaciones lentas de Telegram
        await self._do_close_round_telegram(state, reason, bot)

    async def _do_close_round_telegram(self, state: RoundState, reason: str, bot: Bot) -> None:
        reason_texts = {
            "stop": "⏹ <b>Ronda detenida</b>",
            "timeout": "⌛ <b>Tiempo agotado</b>",
            "all_submitted": "✅ <b>¡Todos respondieron!</b>",
        }
        reason_text = reason_texts.get(reason, "⏹ <b>Ronda cerrada</b>")

        # DB + scoring (rápido, no requiere lock porque el state ya está popped)
        round_id: int | None = None
        async with async_session_factory() as session:
            repo = RoundRepository(session)
            db_round = await repo.get_active_round(state.game_id)
            if db_round:
                round_id = db_round.id
                stopped_by = None
                if reason == "stop" and state.first_completer_db_id:
                    stopped_by = state.first_completer_db_id
                await repo.update_status(
                    db_round.id,
                    status="completed",
                    stopped_by_player_id=stopped_by,
                )

        round_scores: dict[int, int] = {}
        if round_id is not None:
            try:
                round_scores = await self._persist_round_scores(round_id, state)
            except Exception:
                logger.exception(
                    "Error en _persist_round_scores para game=%s round=%",
                    state.game_id,
                    state.round_number,
                )
        # Asegurar que todas las palabras aprendidas se persistan antes de continuar
        try:
            from src.services.spell_corrector import get_corrector
            await get_corrector().flush_pending_tasks()
        except Exception:
            logger.exception("Error en flush_pending_tasks")
        try:
            if round_scores:
                unique_scores = len(set(round_scores.values()))
                if unique_scores == 1 and state.submission_order:
                    for pid in state.submission_order:
                        if pid in round_scores:
                            state.leader_id = pid
                            break
                else:
                    state.leader_id = max(round_scores, key=round_scores.get)
            else:
                state.leader_id = None
                if state.player_names:
                    state.leader_id = random.choice(list(state.player_names.keys()))

            # Telegram sends — todo sin lock
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
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)

            if state.stop_message_id:
                try:
                    await bot.edit_message_text(
                        f"{reason_text}\n\nLa ronda ha finalizado.",
                        chat_id=state.stop_message_chat_id,
                        message_id=state.stop_message_id,
                    )
                except TelegramBadRequest:
                    pass
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)

            summary = self._build_summary(round_scores, state)
            for attempt in range(3):
                try:
                    await bot.send_message(state.group_chat_id, summary)
                    break
                except TelegramRetryAfter as e:
                    if attempt < 2:
                        await asyncio.sleep(e.retry_after)
                    else:
                        logger.warning(
                            "No se pudo enviar resumen tras 3 intentos: game=%s",
                            state.game_id,
                        )

            self._letter_pending[state.game_id] = state
            if state.cancelled:
                self._letter_pending.pop(state.game_id, None)
                return
            await self._transition_next_round(state, bot)
        except TelegramRetryAfter as e:
            logger.warning(
                "TelegramRetryAfter en _do_close_round_telegram: game=%s, retry_after=%d",
                state.game_id, e.retry_after,
            )
            await asyncio.sleep(e.retry_after)
        except Exception:
            logger.exception(
                "Erro ren _do_close_round_telegram para game=%s round=%s",
                state.game_id,
                state.round_number,
            )

    async def _transition_next_round(
        self,
        state: RoundState,
        bot: Bot,
    ) -> None:
        if state.cancelled:
            return
        if state.round_number >= state.total_rounds:
            await self._end_game(state, bot)
            return

        await self._show_inter_round_menu(state, bot)

    async def _show_inter_round_menu(self, state: RoundState, bot: Bot) -> None:
        for attempt in range(3):
            try:
                msg = await bot.send_message(
                    state.group_chat_id,
                    f"🔄 <b>Ronda {state.round_number} completada</b>\n\n"
                    f"⏱ La siguiente ronda comenzará automáticamente en 2 minutos.\n\n"
                    f"<b>Opciones:</b>\n"
                    f"  ▶️ <i>Siguiente ronda</i> — solo el líder puede avanzar\n"
                    f"  ⏹ <i>Detener partida</i> — solo el anfitrión puede finalizar",
                    reply_markup=inter_round_keyboard(state.game_id),
                )
                state.inter_round_message_id = msg.message_id
                state.inter_round_timeout_task = asyncio.create_task(self._inter_round_timeout(state, bot))
                return
            except TelegramRetryAfter as e:
                if attempt < 2:
                    await asyncio.sleep(e.retry_after)
                else:
                    logger.warning(
                        "No se pudo enviar menu inter-round tras 3 intentos: game=%s",
                        state.game_id,
                    )
            except Exception:
                logger.warning(
                    "Error inesperado en _show_inter_round_menu attempt %d: game=%s",
                    attempt, state.game_id,
                )
                if attempt < 2:
                    await asyncio.sleep(5)

    async def _inter_round_timeout(self, state: RoundState, bot: Bot) -> None:
        await asyncio.sleep(120)
        if state.inter_round_message_id:
            with contextlib.suppress(TelegramBadRequest):
                await bot.delete_message(state.group_chat_id, state.inter_round_message_id)
        await self._prompt_letter_selection(state, bot)

    async def handle_next_round(
        self,
        game_id: int,
        player_id: int,
        callback,
        bot: Bot,
    ) -> None:
        async with self._lock_for(game_id):
            state = self._letter_pending.get(game_id)
            if not state:
                active = self._rounds.get(game_id)
                if active:
                    await callback.answer("⏳ La ronda ya está en curso. Esperá a que termine.", show_alert=True)
                else:
                    await callback.answer("❌ Esta partida ya no está activa.", show_alert=True)
                return
            if player_id != state.leader_id:
                await callback.answer(
                    "❌ Solo el líder puede avanzar a la siguiente ronda.",
                    show_alert=True,
                )
                return
            if state.inter_round_timeout_task and not state.inter_round_timeout_task.done():
                state.inter_round_timeout_task.cancel()
            if state.inter_round_message_id:
                with contextlib.suppress(TelegramBadRequest):
                    await bot.delete_message(state.group_chat_id, state.inter_round_message_id)
            await callback.answer("▶️ Avanzando a la siguiente ronda...", show_alert=False)
            await self._prompt_letter_selection(state, bot)

    async def handle_stop_game(
        self,
        game_id: int,
        player_id: int,
        callback,
        bot: Bot,
    ) -> None:
        async with self._lock_for(game_id):
            state = self._letter_pending.get(game_id)
            if not state:
                active = self._rounds.get(game_id)
                if active:
                    await callback.answer("⏳ La ronda ya está en curso. Esperá a que termine.", show_alert=True)
                else:
                    await callback.answer("❌ Esta partida ya no está activa.", show_alert=True)
                return
            if player_id != state.host_telegram_id:
                await callback.answer(
                    "❌ Solo el anfitrión puede detener la partida.",
                    show_alert=True,
                )
                return
            if state.inter_round_timeout_task and not state.inter_round_timeout_task.done():
                state.inter_round_timeout_task.cancel()
            if state.inter_round_message_id:
                with contextlib.suppress(TelegramBadRequest):
                    await bot.delete_message(state.group_chat_id, state.inter_round_message_id)
            await callback.answer(
                "⏹ Partida detenida. Calculando puntuaciones...", show_alert=False
            )
            await self._end_game(state, bot)

    async def _prompt_letter_selection(self, state: RoundState, bot: Bot) -> None:
        if state.first_completer_id:
            leader_id = state.first_completer_id
        else:
            # Sin primer completador: usar el de mayor puntaje de esta ronda
            leader_id = state.leader_id or await self._get_leader_telegram_id(state.game_id)
        if not leader_id:
            await self._start_next_round_with_random(state, bot)
            return

        state.leader_id = leader_id
        name = state.player_names.get(leader_id, "El líder")
        await asyncio.sleep(1)
        while True:
            try:
                msg = await bot.send_message(
                    state.group_chat_id,
                    f"🏆 <b>{name}, elige la letra de la siguiente ronda:</b>",
                    reply_markup=letter_keyboard(state.game_id, state.include_n),
                )
                break
            except TelegramRetryAfter as e:
                logger.warning("Flood al enviar teclado letras, esperando %ss", e.retry_after)
                await asyncio.sleep(e.retry_after)
        if state.letter_timeout_task and not state.letter_timeout_task.done():
            state.letter_timeout_task.cancel()
        state.letter_message_chat_id = msg.chat.id
        state.letter_message_id = msg.message_id
        state.letter_timeout_task = asyncio.create_task(self._letter_timeout(msg, bot, state))

    async def _letter_timeout(self, msg, bot, state):
        await asyncio.sleep(15)
        with contextlib.suppress(TelegramBadRequest, TelegramRetryAfter):
            await msg.delete()
        letter = random.choice(get_alphabet(state.include_n))
        await self._start_next_round_with_letter(state, letter, bot)

    async def handle_letter_selection(
        self,
        game_id: int,
        player_id: int,
        letter: str,
        callback,
        bot: Bot,
    ) -> None:
        async with self._lock_for(game_id):
            state = self._rounds.get(game_id) or self._letter_pending.get(game_id)
            if not state:
                await callback.answer("❌ Partida no activa.", show_alert=True)
                return

            # Si el state vino de _rounds, es una ronda activa, no una selección de letra pendiente
            if game_id in self._rounds:
                await callback.answer("⏳ Ya hay una ronda en curso.", show_alert=True)
                return

            if player_id != state.leader_id:
                await callback.answer("❌ Solo el líder puede elegir la letra.", show_alert=True)
                return

            if state.letter_timeout_task and not state.letter_timeout_task.done():
                state.letter_timeout_task.cancel()
                state.letter_timeout_task = None

            next_number = state.round_number + 1

            await callback.answer(f"✅ Letra {letter} seleccionada", show_alert=False)

            # Eliminar el teclado de letras
            if state.letter_message_id:
                with contextlib.suppress(TelegramBadRequest):
                    await bot.delete_message(
                        chat_id=state.letter_message_chat_id,
                        message_id=state.letter_message_id,
                    )

            await self.start_round(
                game_id=game_id,
                group_chat_id=state.group_chat_id,
                round_number=next_number,
                letter=letter,
                total_players=state.total_players,
                total_rounds=state.total_rounds,
                player_names=state.player_names,
                bot=bot,
                host_telegram_id=state.host_telegram_id,
                round_time=state.round_time,
                categories=state.categories,
                include_n=state.include_n,
            )

        # Countdown fuera del lock (solo envio de mensajes)
        countdown = await bot.send_message(
            state.group_chat_id,
            f"<b>Letra: {letter}</b>\n⏱ Siguiente ronda en 5 segundos...",
        )
        await asyncio.sleep(5)
        with contextlib.suppress(TelegramBadRequest):
            await countdown.delete()

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
            total_rounds=prev_state.total_rounds,
            player_names=prev_state.player_names,
            bot=bot,
            host_telegram_id=prev_state.host_telegram_id,
            round_time=prev_state.round_time,
            categories=prev_state.categories,
            include_n=prev_state.include_n,
        )

    async def _start_next_round_with_random(self, state, bot):
        letter = random.choice(get_alphabet(state.include_n))
        await self._start_next_round_with_letter(state, letter, bot)

    # Finalizar juego
    async def _end_game(self, state: RoundState, bot: Bot) -> None:
        async with async_session_factory() as session:
            repo = GameRepository(session)
            db_game = await repo.get_by_id(state.game_id)
            if db_game:
                db_game.status = "finished"
                db_game.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.commit()

            winners = await self._get_standings(state.game_id)

        # === Otorgar XP, streaks, leaderboard ===
        xp_results = {}
        for position, (telegram_id, score) in enumerate(winners):
            # Buscar player_id interno
            async with async_session_factory() as session:
                stmt = select(Player).where(Player.telegram_id == telegram_id)
                result = await session.execute(stmt)
                player = result.scalar_one_or_none()
                if not player:
                    continue

            # Streaks
            await xp_service.update_streak(player.id)

            # XP
            was_stopper = telegram_id == state.first_completer_id if state else False
            # unique_answers: contar respuestas unicas de ese jugador en la ultima ronda
            unique_answers = 0  # Simplificado idealmente contar desde details
            xp_info = await xp_service.award_game_xp(
                player_id=player.id,
                final_position=position + 1,
                was_stopper=was_stopper,
                unique_answers=unique_answers,
            )
            xp_results[telegram_id] = xp_info

            # Leaderboard semanal
            from src.services.leaderboard import leaderboard_service

            await leaderboard_service.upsert_player(
                player_id=player.id,
                score_to_add=score,
            )

        # === Recalcular ranks semanales ===
        from src.db.repositories.leaderboard_repository import LeaderboardRepository

        await LeaderboardRepository.recalculate_ranks()

        podium_data = [
            (state.player_names.get(pid, f"Jugador {pid}"), score) for pid, score in winners[:5]
        ]

        # Descargar fotos de perfil para top 3
        from io import BytesIO

        from PIL import Image as PILImage

        profile_photos = []
        for pid, _ in winners[:3]:
            try:
                user_photos = await bot.get_user_profile_photos(user_id=pid, limit=1)
                if user_photos.total_count > 0:
                    file_id = user_photos.photos[0][-1].file_id
                    file = await bot.get_file(file_id)
                    photo_bytes_io = await bot.download_file(file.file_path)
                    photo_data = photo_bytes_io.read()
                    profile_photos.append(PILImage.open(BytesIO(photo_data)).convert("RGBA"))
                else:
                    profile_photos.append(None)
            except Exception:
                profile_photos.append(None)

        podium_bytes = generate_podium_image(podium_data, state.round_number, profile_photos)
        if podium_bytes:
            from aiogram.types import BufferedInputFile

            photo = BufferedInputFile(podium_bytes, filename="podium.png")
            await bot.send_photo(state.group_chat_id, photo=photo)

        lines = ["<b>🏆 ¡Partida finalizada!</b>", ""]
        if winners:
            medals = ["🥇", "🥈", "🥉"]
            for i, (pid, score) in enumerate(winners[:3]):
                name = state.player_names.get(pid, f"Jugador {pid}")
                xp_info = xp_results.get(pid, {})
                xp_text = f" (+{xp_info.get('xp_gained', 0)} XP)" if xp_info else ""
                lines.append(f"{medals[i] if i < 3 else i + 1}. {name} — {score} pts{xp_text}")

                if xp_info.get("leveled_up"):
                    title = xp_info.get("title", "")
                    title_text = f" | 🎖{title}" if title else ""
                    await bot.send_message(
                        state.group_chat_id,
                        f"🎉 <b>{name} ha subido al nivel {xp_info['level']}!</b>{title_text}",
                    )
        else:
            lines.append("  No hay puntuaciones registradas.")

        from src.services.event_service import event_service

        active_events = await event_service.get_active_events()
        for event in active_events:
            lines.append("")
            lines.append(f" <b>Evento en curso: {event['name']}</b> (x{event['multiplier']} XP)")

        lines.append("")
        lines.append("<i>Gracias por jugar 🛑 Stop!</i>")

        await bot.send_message(state.group_chat_id, "\n".join(lines))
        self._letter_pending.pop(state.game_id, None)
        self._rounds_by_group.pop(state.group_chat_id, None)

    async def _check_all_submitted(self, state: RoundState) -> bool:
        return len(state.submitted_player_ids) >= state.total_players

    async def _send_stop_message(self, state: RoundState, bot: Bot) -> None:
        name = state.first_completer_name or "Alguien"
        text = (
            f"⏹ <b>{name} completó todas las categorías</b>\n\n"
            f"Solo {name} puede presionar el botón Stop."
        )
        for attempt in range(3):
            try:
                stop_msg = await bot.send_message(
                    state.group_chat_id,
                    text,
                    reply_markup=stop_keyboard(state.game_id, 1),
                )
                state.stop_message_chat_id = stop_msg.chat.id
                state.stop_message_id = stop_msg.message_id
                logger.info(
                    "Botón Stop enviado a group_chat_id=%s msg_id=%s",
                    state.group_chat_id,
                    stop_msg.message_id,
                )
                break
            except TelegramRetryAfter as e:
                if attempt < 2:
                    logger.warning("Flood control en stop msg, esperando %ss", e.retry_after)
                    await asyncio.sleep(min(e.retry_after, 5))
                else:
                    logger.warning(
                        "No se pudo enviar stop msg tras 3 intentos: game=%s",
                        state.game_id,
                    )
            except Exception:
                logger.exception(
                    "Error al enviar botón Stop a group_chat_id=%s", state.group_chat_id
                )
                break

        self._debounced_update(state, bot)

    def _debounced_update(self, state: RoundState, bot: Bot) -> None:
        if state.update_task and not state.update_task.done():
            state.update_task.cancel()
        state.update_task = asyncio.create_task(self._do_update_round_message(state, bot))

    async def _do_update_round_message(self, state: RoundState, bot: Bot) -> None:
        lines = [
            self._format_round_message(
                state.round_number, state.letter, state.categories, state.round_time
            )
        ]

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
            lines.append(f"  Stop: {state.stop_presses}/{NUM_STOP_BUTTONS}")

        try:
            await bot.edit_message_text(
                "\n".join(lines),
                chat_id=state.message_chat_id,
                message_id=state.message_id,
            )
        except asyncio.CancelledError:
            pass
        except TelegramBadRequest:
            pass
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)

    async def _persist_round_scores(
        self,
        round_id: int,
        state: RoundState,
    ) -> dict[int, int]:
        async with async_session_factory() as session:
            repo = RoundRepository(session)
            answers_by_player = await repo.get_answers_by_player(round_id)

            engine = ScoreEngine()
            totals, details = engine.evaluate(
                answers_by_player,
                len(state.categories),
                first_completer_id=state.first_completer_id,
                spell_corrector=get_corrector(),
                letter=state.letter,
            )

            # ── LOG TEMPORAL: muestra que respuestas fueron correctas/incorrectas ──
            logger.info(
                "=== RESULTADOS RONDA %s (letra=%s) ===",
                state.round_number,
                state.letter,
            )
            for pid, answer_list in details.items():
                pname = state.player_names.get(pid, f"ID{pid}")
                for ad in answer_list:
                    status = "✅" if ad["is_correct"] else "❌"
                    logger.info(
                        "  %s %s | %s: '%s' → %d pts",
                        status,
                        pname,
                        ad["word_slot"],
                        ad["raw_text"],
                        ad["score"],
                    )
            if details:
                logger.info("  --- Totales ---")
                for pid, total in sorted(totals.items(), key=lambda x: x[1], reverse=True):
                    pname = state.player_names.get(pid, f"ID{pid}")
                    logger.info("  %s: %d pts", pname, total)
            logger.info("=== FIN RESULTADOS RONDA %s ===", state.round_number)

            # Persistir Answer.score y Answer.is_correct (batch)
            all_updates = []
            for pid, answer_list in details.items():
                for ad in answer_list:
                    all_updates.append(
                        (
                            ad["answer_id"],
                            ad["is_correct"],
                            ad["score"],
                        )
                    )
            if all_updates:
                await repo.update_answer_scores(all_updates)

            # Persistir GamePlayer.score (acumulado) — batch
            if totals:
                telegram_ids = list(totals.keys())
                gps = await repo.get_game_players_by_telegrams(state.game_id, telegram_ids)
                for tid, round_score in totals.items():
                    gp = gps.get(tid)
                    if gp:
                        gp.score = (gp.score or 0) + round_score

            await session.commit()

            return totals

    @staticmethod
    def _build_summary(round_scores: dict[int, int], state: RoundState) -> str:
        if not round_scores:
            return (
                f"<b>📊 Ronda {state.round_number} — Resumen</b>\n  No se registraron puntuaciones."
            )

        lines = [
            f"<b>📊 Ronda {state.round_number} — Resumen</b>",
            f"  Letra: <b>{state.letter}</b>",
            "",
        ]

        for pid, score in sorted(round_scores.items(), key=lambda x: x[1], reverse=True):
            name = state.player_names.get(pid, f"Jugador {pid}")
            lines.append(f"  {name}: {score} pts")

        if state.first_completer_name:
            lines.append("")
            lines.append(
                f"⭐ <b>{state.first_completer_name}</b> fue el primero "
                f"en completar todas las categorías."
            )
            lines.append(f"  🏎️ Bonus velocidad: +{FIRST_COMPLETER_BONUS} pts")

        return "\n".join(lines)

    async def cancel_game(self, game_id: int) -> None:
        async with self._lock_for(game_id):
            state = self._rounds.pop(game_id, None)
            if state:
                state.cancelled = True
                for task in (
                    state.timer_task,
                    state.letter_timeout_task,
                    state.update_task,
                    state.inter_round_timeout_task,
                ):
                    if task and not task.done():
                        task.cancel()
                self._rounds_by_group.pop(state.group_chat_id, None)

            pending = self._letter_pending.pop(game_id, None)
            if pending and pending is not state:
                pending.cancelled = True
                for task in (
                    pending.letter_timeout_task,
                    pending.inter_round_timeout_task,
                ):
                    if task and not task.done():
                        task.cancel()
                self._rounds_by_group.pop(pending.group_chat_id, None)

            self._locks.pop(game_id, None)
            logger.info("Estado en memoria cancelado para game %s", game_id)

    async def _get_leader_telegram_id(self, game_id: int) -> int | None:
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

    async def _get_standings(self, game_id: int) -> list[tuple[int, int]]:
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
            for _remaining in range(state.round_time, 0, -1):
                if state.timer_task and state.timer_task.done():
                    return
                try:
                    await asyncio.wait_for(asyncio.get_event_loop().create_future(), timeout=1)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    return

            await self._close_round(state.game_id, "timeout", bot)
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _format_round_message(
        round_number: int, letter: str, categories: list[str], round_time: int
    ) -> str:
        cats_display = "\n".join(f"  <b>{cat}:</b> ..." for cat in categories)
        return f"⏱ {round_time} segundos\n\nEnvía tus respuestas en este formato:\n\n{cats_display}"

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


def _unaccent(s: str) -> str:
    """Elimina tildes/diacriticos de una cadena."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def parse_answers(text: str, categories: list[str]) -> dict[str, str]:
    # Mapa sin acentos: "pais" → "País", "animal" → "Animal", ...
    cat_map: dict[str, str] = {}
    for cat in categories:
        cat_map[_unaccent(cat.lower())] = cat

    result: dict[str, str] = {}

    for match in ANSWER_REGEX.finditer(text):
        raw_cat = _unaccent(match.group(1).strip().lower())
        value = match.group(2).strip()
        if not value:
            continue
        if raw_cat in cat_map:
            canonical = cat_map[raw_cat]
            if canonical in result:
                logger.warning("Categoría duplicada '%s' en respuestas, se sobrescribe", canonical)
            result[canonical] = value

    return result


def get_alphabet(include_n: bool = False) -> str:
    base = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if include_n:
        # Insertar Ñ despues de la N
        idx = base.index("N") + 1
        return base[:idx] + "Ñ" + base[idx:]
    return base


round_manager = RoundManager()
