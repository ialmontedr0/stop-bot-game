import asyncio
import contextlib
import random
import re
import unicodedata
from dataclasses import dataclass, field

import structlog
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from sqlalchemy import func, select

from src.core.text_utils import utcnow
from src.db.engine import async_session_factory
from src.db.models import GamePlayer, Player
from src.db.repositories.game_repository import GameRepository
from src.db.repositories.round_repository import RoundRepository
from src.image_generator import generate_podium_image
from src.keyboards.round import inter_round_keyboard, letter_keyboard, stop_keyboard
from src.services.game_state_store import GameStateStore
from src.services.photo_cache import photo_cache
from src.services.score_engine import FIRST_COMPLETER_BONUS, UNIQUE_POINTS, ScoreEngine
from src.services.spell_corrector import get_corrector
from src.services.xp_service import xp_service

logger = structlog.get_logger(__name__)

NUM_STOP_BUTTONS = 10
ROUND_DURATION = 60
TOTAL_ROUNDS = 5
LETTER_TIMEOUT = 15

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

_PLURAL_MAP: dict[str, str] = {
    "paises": "País",
    "colores": "Color",
    "frutas": "Fruta",
    "animales": "Animal",
    "artistas": "Artista",
    "cosas": "Cosa",
    "nombres": "Nombre",
    "apellidos": "Apellido",
}

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
    def __init__(self, store: GameStateStore | None = None) -> None:
        self._rounds: dict[int, RoundState] = {}
        self._rounds_by_group: dict[int, int] = {}
        self._letter_pending: dict[int, RoundState] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._cancelled: dict[int, bool] = {}
        self._closing: set[int] = set()
        self._unique_answers: dict[int, dict[int, int]] = {}
        self._store = store

    @staticmethod
    def _safe_task(coro) -> asyncio.Task:
        """Crea un task con error logging para fire-and-forget."""
        task = asyncio.create_task(coro)

        async def _log_error(t):
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Fire-and-forget task falló")

        asyncio.create_task(_log_error(task))
        return task

    def get_active_game_ids(self) -> list[int]:
        """Retorna copia de los game_ids con ronda activa (público, thread-safe)."""
        return list(self._rounds.keys())

    def set_store(self, store: GameStateStore) -> None:
        self._store = store

    async def restore_from_store(self) -> int:
        if self._store is None:
            return 0
        rounds = await self._store.get_all_rounds()
        for gid, state in rounds.items():
            self._rounds[gid] = state
        rbg = await self._store.get_all_rounds_by_group()
        self._rounds_by_group.update(rbg)
        pending = await self._store.get_all_letter_pending()
        for gid, state in pending.items():
            self._letter_pending[gid] = state
        count = len(rounds) + len(pending)
        if count:
            logger.info(
                "Restaurados %d rounds + %d letter_pending desde store", len(rounds), len(pending)
            )
        return count

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
        if self._store:
            await self._store.set_round(state)
            await self._store.set_rounds_by_group(group_chat_id, game_id)
        if state.validation_mode in ("ai", "hybrid"):
            get_corrector().reset_api_counter(group_chat_id=group_chat_id, game_id=game_id)
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
        logger.info(
            "submit_answers ENTER game=%s player_tg=%s text_preview=%s",
            game_id,
            player.telegram_id,
            text[:50],
        )
        state = self.get_active_round(game_id)
        if not state:
            logger.info("submit_answers: no active round for game %s", game_id)
            return False

        parsed = parse_answers(text, state.categories)
        if not parsed:
            logger.info("submit_answers: no categories parsed from text")
            return False

        # --- Tratar "..." como respuesta vacia ---
        _EMPTY_SYMBOLS = frozenset({"...", "…", ". . .", ".."})  # noqa: N806
        for slot in list(parsed.keys()):
            val = parsed[slot].strip("., •-")
            if not val or val.lower() in _EMPTY_SYMBOLS:
                parsed[slot] = ""

        # Determinar si todas las categorías tienen contenido real
        # (antes de AI validation, para que first_completer no dependa de la IA)
        has_real_content = all(len(v.strip()) >= 2 for v in parsed.values())

        send_stop = False

        logger.info(
            "submit_answers: fase1 DB save START game=%s player=%s cats=%s",
            game_id,
            player.telegram_id,
            list(parsed.keys()),
        )

        # 1. Persistir respuestas en BD inmediatamente (antes de validacion AI)
        #    para evitar que AI lenta (hybrid mode) pierda las respuestas si
        #    el timer de la ronda expira mientras tanto.
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

        logger.info(
            "submit_answers: fase1 DB save OK game=%s player=%s", game_id, player.telegram_id
        )

        # 2. Validacion IA opcional — batch: 1 llamada para todas las categorias
        from src.services.spell_corrector import get_corrector

        corrector = get_corrector()
        effective_validation_mode = state.validation_mode or corrector.mode
        if effective_validation_mode in ("ai", "hybrid"):
            validation_results = await corrector.validate_batch(
                dict(parsed),
                game_id=game_id,
                mode=effective_validation_mode,
                group_chat_id=state.group_chat_id,
            )
            for slot, is_valid in validation_results.items():
                if not is_valid:
                    raw_text = parsed.get(slot, "")
                    parsed[slot] = ""
                    logger.info(
                        "ia_rejection",
                        extra={
                            "game_id": game_id,
                            "player_id": player.id,
                            "telegram_id": player.telegram_id,
                            "category": slot,
                            "rejected_text": raw_text,
                        },
                    )

        logger.info("submit_answers: fase2 AI done game=%s player=%s", game_id, player.telegram_id)

        # 3. Lock: actualizar estado en memoria
        if self._cancelled.get(game_id):
            return False
        async with self._lock_for(game_id):
            if self._cancelled.get(game_id):
                return False
            if self.get_active_round(game_id) is not state:
                logger.info(
                    "submit_answers: round already closed for game %s - state=%s _rounds_has=%s",
                    game_id,
                    id(state) if state else None,
                    game_id in self._rounds,
                )
                return False
            is_first = player.telegram_id not in state.submitted_player_ids
            state.submitted_player_ids.add(player.telegram_id)
            if is_first:
                state.submission_order.append(player.telegram_id)
            if self._store:
                self._safe_task(self._store.set_round(state))
            self._debounced_update(state, bot)

            all_filled = len(parsed) == len(state.categories) and has_real_content
            logger.info(
                "submit_answers",
                extra={
                    "game_id": game_id,
                    "player_id": player.id,
                    "telegram_id": player.telegram_id,
                    "total_categories": len(state.categories),
                    "answered_count": len(parsed),
                    "all_filled": all_filled,
                    "answers": dict(parsed),
                },
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

            if send_stop:
                try:
                    await self._send_stop_message(state, bot)
                except Exception:
                    logger.exception(
                        "Error enviando stop message para game %s",
                        game_id,
                    )
        # Lock liberado aqui
        result = all_filled and state.first_completer_id == player.telegram_id
        logger.info(
            "submit_answers EXIT game=%s player_tg=%s result=%s send_stop=%s all_submitted=%s",
            game_id,
            player.telegram_id,
            result,
            send_stop,
            all_submitted,
        )
        if all_submitted:
            try:
                await self._close_round(game_id, "all_submitted", bot)
            except Exception:
                logger.exception(
                    "Error cerrando ronda para game %s (all_submitted)",
                    game_id,
                )
        return result

    async def press_stop(
        self,
        game_id: int,
        player_id: int,
        callback,
        bot: Bot,
    ) -> None:
        if self._cancelled.get(game_id):
            await callback.answer("❌ Partida cancelada.", show_alert=True)
            return
        should_close = False
        async with self._lock_for(game_id):
            if self._cancelled.get(game_id):
                await callback.answer("❌ Partida cancelada.", show_alert=True)
                return
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
                should_close = True
                with contextlib.suppress(TelegramBadRequest, TelegramRetryAfter):
                    await bot.edit_message_text(
                        self._format_stop_message(NUM_STOP_BUTTONS),
                        chat_id=state.stop_message_chat_id,
                        message_id=state.stop_message_id,
                    )
            else:
                progress = state.stop_presses
                await callback.answer(f"⏹ Stop {progress}/{NUM_STOP_BUTTONS}", show_alert=False)
                with contextlib.suppress(TelegramBadRequest, TelegramRetryAfter):
                    await bot.edit_message_text(
                        self._format_stop_message(progress),
                        chat_id=state.stop_message_chat_id,
                        message_id=state.stop_message_id,
                        reply_markup=stop_keyboard(game_id, progress + 1),
                    )

        # Lock liberado — cerrar ronda fuera del lock (evita deadlock reentrante)
        if should_close:
            with contextlib.suppress(TelegramBadRequest):
                await callback.answer("⏹ ¡Ronda detenida!", show_alert=False)
            await self._close_round(game_id, "stop", bot)

    async def _close_round(self, game_id: int, reason: str, bot: Bot) -> None:
        if self._cancelled.get(game_id):
            return
        # Flag atómico bajo el lock para evitar doble ejecución (G1)
        async with self._lock_for(game_id):
            if self._cancelled.get(game_id):
                return
            if game_id in self._closing:
                logger.warning("_close_round ya en progreso para game %s, ignorando", game_id)
                return
            self._closing.add(game_id)
        try:
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
        finally:
            self._closing.discard(game_id)

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
            for attempt in range(3):
                try:
                    round_scores = await self._persist_round_scores(
                        round_id,
                        state,
                        reason=reason,
                    )
                    break
                except Exception:
                    logger.exception(
                        "Error en _persist_round_scores (intento %d/3) para game=%s round=%s",
                        attempt + 1,
                        state.game_id,
                        state.round_number,
                    )
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (2**attempt))
            if not round_scores:
                logger.critical(
                    "Fallo permanente en _persist_round_scores "
                    "para game=%s round=%s — cancelando juego",
                    state.game_id,
                    state.round_number,
                )
                state.cancelled = True
                try:  # noqa: SIM105
                    await bot.send_message(
                        state.group_chat_id,
                        "❌ Ocurrió un error al guardar los puntajes. La partida se cancelará.",
                    )
                except Exception:
                    pass
                # Marcar como cancelado en BD para que nadie quede atascado
                try:
                    async with async_session_factory() as session:
                        repo = GameRepository(session)
                        db_game = await repo.get_by_id(state.game_id)
                        if db_game and db_game.status not in ("finished", "cancelled"):
                            db_game.status = "cancelled"
                            db_game.finished_at = utcnow()
                            await session.commit()
                except Exception:
                    logger.exception(
                        "Error adicional al cancelar game %s en BD tras persist_fallback",
                        state.game_id,
                    )
                # Limpiar estado en memoria
                self._rounds.pop(state.game_id, None)
                self._rounds_by_group.pop(state.group_chat_id, None)
                self._letter_pending.pop(state.game_id, None)
                self._locks.pop(state.game_id, None)
                self._unique_answers.pop(state.game_id, None)
                if self._store:
                    asyncio.create_task(self._store.delete_round(state.game_id))
                    asyncio.create_task(self._store.delete_letter_pending(state.game_id))
                return
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
            if self._store:
                await self._store.set_letter_pending(state)
                await self._store.delete_round(state.game_id)
                await self._store.delete_rounds_by_group(state.group_chat_id)
            if state.cancelled:
                self._letter_pending.pop(state.game_id, None)
                if self._store:
                    await self._store.delete_letter_pending(state.game_id)
                return
            await self._transition_next_round(state, bot)
        except TelegramRetryAfter as e:
            logger.warning(
                "TelegramRetryAfter en _do_close_round_telegram: game=%s, retry_after=%d",
                state.game_id,
                e.retry_after,
            )
            await asyncio.sleep(e.retry_after)
        except Exception:
            logger.exception(
                "Error en _do_close_round_telegram para game=%s round=%s",
                state.game_id,
                state.round_number,
            )
            # No popear _letter_pending — el letter_timeout reintentará (D2)
            # Marcar juego como cancelado para evitar estado limbo
            try:
                async with async_session_factory() as session:
                    repo = GameRepository(session)
                    db_game = await repo.get_by_id(state.game_id)
                    if db_game and db_game.status not in ("finished", "cancelled"):
                        db_game.status = "cancelled"
                        db_game.finished_at = utcnow()
                        await session.commit()
            except Exception:
                logger.exception("Error adicional al cancelar game %s en fallback D2", state.game_id)

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
                state.inter_round_timeout_task = asyncio.create_task(
                    self._inter_round_timeout(state, bot)
                )
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
                    attempt,
                    state.game_id,
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
        if self._cancelled.get(game_id):
            await callback.answer("❌ Partida cancelada.", show_alert=True)
            return
        async with self._lock_for(game_id):
            if self._cancelled.get(game_id):
                await callback.answer("❌ Partida cancelada.", show_alert=True)
                return
            state = self._letter_pending.get(game_id)
            if not state:
                active = self._rounds.get(game_id)
                if active:
                    await callback.answer(
                        "⏳ La ronda ya está en curso. Espera a que termine.", show_alert=True
                    )
                else:
                    await callback.answer("❌ Esta partida ya no está activa.", show_alert=True)
                return
            if game_id in self._rounds:
                await callback.answer(
                    "⏳ La ronda ya está en curso. Espera a que termine.",
                    show_alert=True,
                )
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
            with contextlib.suppress(TelegramBadRequest):
                await callback.answer("▶️ Avanzando a la siguiente ronda...", show_alert=False)
            await self._prompt_letter_selection(state, bot)

    async def handle_stop_game(
        self,
        game_id: int,
        player_id: int,
        callback,
        bot: Bot,
    ) -> None:
        if self._cancelled.get(game_id):
            await callback.answer("❌ Partida cancelada.", show_alert=True)
            return
        async with self._lock_for(game_id):
            if self._cancelled.get(game_id):
                await callback.answer("❌ Partida cancelada.", show_alert=True)
                return
            state = self._letter_pending.get(game_id)
            if not state:
                active = self._rounds.get(game_id)
                if active:
                    await callback.answer(
                        "⏳ La ronda ya está en curso. Espera a que termine.", show_alert=True
                    )
                else:
                    await callback.answer("❌ Esta partida ya no está activa.", show_alert=True)
                return
            if game_id in self._rounds:
                await callback.answer(
                    "⏳ La ronda ya está en curso. Espera a que termine.",
                    show_alert=True,
                )
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
            with contextlib.suppress(TelegramBadRequest):
                await callback.answer(
                    "⏹ Partida detenida. Calculando puntuaciones...", show_alert=False
                )

        # Lock liberado - operaciones lentas fuera de la seccion critica
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
        await asyncio.sleep(LETTER_TIMEOUT)
        # Adquirir el lock para verificar/pop atómicamente: si handle_letter_selection
        # ya ganó la carrera, _letter_pending estará vacío y salimos sin acción.
        async with self._lock_for(state.game_id):
            if state.game_id not in self._letter_pending:
                return
            self._letter_pending.pop(state.game_id, None)
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
        if self._cancelled.get(game_id):
            await callback.answer("❌ Partida cancelada.", show_alert=True)
            return
        async with self._lock_for(game_id):
            if self._cancelled.get(game_id):
                await callback.answer("❌ Partida cancelada.", show_alert=True)
                return
            state = self._rounds.get(game_id) or self._letter_pending.get(game_id)
            if not state:
                await callback.answer("❌ Partida no activa.", show_alert=True)
                return

            # Si el state vino de _rounds, es una ronda activa, no una selección de letra pendiente
            if game_id in self._rounds:
                await callback.answer("⏳ Ya hay una ronda en curso.", show_alert=True)
                return

            if letter not in get_alphabet(include_n=state.include_n):
                await callback.answer("❌ Letra inválida.", show_alert=True)
                return

            if player_id != state.leader_id:
                await callback.answer("❌ Solo el líder puede elegir la letra.", show_alert=True)
                return

            # Reclamar ownership atómicamente bajo el lock (D1)
            self._letter_pending.pop(game_id, None)

            if state.letter_timeout_task and not state.letter_timeout_task.done():
                state.letter_timeout_task.cancel()
                state.letter_timeout_task = None

            next_number = state.round_number + 1

        # ── Salimos del lock antes de I/O pesado ──
        with contextlib.suppress(TelegramBadRequest):
            await callback.answer(f"✅ Letra {letter} seleccionada", show_alert=False)

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
            validation_mode=state.validation_mode,
        )

        # Countdown fuera del lock (solo envio de mensajes)
        countdown = await bot.send_message(
            state.group_chat_id,
            f"<b>Letra: {letter}</b>\n⏱ Siguiente ronda en 5 segundos...",
        )
        await asyncio.sleep(5)
        with contextlib.suppress(TelegramBadRequest):
            await countdown.delete()

    async def handle_skip_letter(
        self,
        game_id: int,
        player_id: int,
        callback,
        bot: Bot,
    ) -> None:
        if self._cancelled.get(game_id):
            await callback.answer("❌ Partida cancelada.", show_alert=True)
            return
        async with self._lock_for(game_id):
            if self._cancelled.get(game_id):
                await callback.answer("❌ Partida cancelada.", show_alert=True)
                return
            state = self._letter_pending.get(game_id)
            if not state:
                await callback.answer("❌ No hay selección de letra activa.", show_alert=True)
                return

            self._letter_pending.pop(game_id, None)

            if player_id != state.leader_id:
                await callback.answer("❌ Solo el líder puede saltar.", show_alert=True)
                return

            if state.letter_timeout_task and not state.letter_timeout_task.done():
                state.letter_timeout_task.cancel()
                state.letter_timeout_task = None

            letter = random.choice(get_alphabet(state.include_n))

            with contextlib.suppress(TelegramBadRequest):
                await callback.answer(f"🎲 Letra aleatoria: {letter}", show_alert=False)

            if state.letter_message_id:
                with contextlib.suppress(TelegramBadRequest):
                    await bot.delete_message(
                        chat_id=state.letter_message_chat_id,
                        message_id=state.letter_message_id,
                    )

            await self._start_next_round_with_letter(state, letter, bot)

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
            validation_mode=prev_state.validation_mode,
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
                db_game.finished_at = utcnow()
                await session.commit()

            winners = await self._get_standings(state.game_id)

        # === Otorgar XP, streaks, leaderboard (batch) ===
        xp_results = {}
        telegram_ids = [tid for tid, _ in winners]
        async with async_session_factory() as session:
            stmt = select(Player).where(Player.telegram_id.in_(telegram_ids))
            result = await session.execute(stmt)
            players_map: dict[int, Player] = {p.telegram_id: p for p in result.scalars().all()}

        if players_map:
            rankings = []
            for position, (telegram_id, score) in enumerate(winners):
                player = players_map.get(telegram_id)
                if not player:
                    continue
                rankings.append(
                    {
                        "player_id": player.id,
                        "telegram_id": telegram_id,
                        "position": position + 1,
                        "was_stopper": (
                            telegram_id == state.first_completer_id if state else False
                        ),
                        "unique_answers": self._unique_answers.get(state.game_id, {}).get(telegram_id, 0),
                    }
                )

            xp_results_list = await xp_service.award_all_players(rankings)
            xp_results = {r["telegram_id"]: r for r in xp_results_list}

        # Leaderboard: batch upsert + recalculate ranks en una sola sesión
        async with async_session_factory() as session:
            from datetime import date, timedelta

            from sqlalchemy import desc

            from src.db.models import WeeklyLeaderboard

            ws = date.today() - timedelta(days=date.today().weekday())
            for position, (telegram_id, score) in enumerate(winners):
                player = players_map.get(telegram_id)
                if not player:
                    continue
                stmt = select(WeeklyLeaderboard).where(
                    WeeklyLeaderboard.player_id == player.id,
                    WeeklyLeaderboard.week_start == ws,
                    WeeklyLeaderboard.group_chat_id == state.group_chat_id,
                )
                result = await session.execute(stmt)
                entry = result.scalar_one_or_none()
                if entry:
                    entry.total_score += score
                    entry.games_played += 1
                else:
                    entry = WeeklyLeaderboard(
                        player_id=player.id,
                        group_chat_id=state.group_chat_id,
                        week_start=ws,
                        total_score=score,
                        games_played=1,
                    )
                    session.add(entry)

            stmt = (
                select(WeeklyLeaderboard)
                .where(
                    WeeklyLeaderboard.week_start == ws,
                    WeeklyLeaderboard.group_chat_id == state.group_chat_id,
                )
                .order_by(desc(WeeklyLeaderboard.total_score))
            )
            result = await session.execute(stmt)
            entries = list(result.scalars().all())
            for i, entry in enumerate(entries):
                entry.rank = i + 1

            await session.commit()
            logger.info(
                "Ranks recalculados para semana %s (group=%s): %s entries",
                ws,
                state.group_chat_id,
                len(entries),
            )

        podium_data = [
            (state.player_names.get(pid, f"Jugador {pid}"), score) for pid, score in winners[:5]
        ]

        # Descargar fotos de perfil para top 3

        profile_photos = []
        for pid, _ in winners[:3]:
            photo = await photo_cache.get_photo(bot, pid)
            profile_photos.append(photo)

        podium_bytes = generate_podium_image(podium_data, state.round_number, profile_photos)
        if podium_bytes:
            from aiogram.types import BufferedInputFile

            photo = BufferedInputFile(podium_bytes, filename="podium.png")
            for retry_n in range(3):
                try:
                    await bot.send_photo(state.group_chat_id, photo=photo)
                    break
                except (TelegramRetryAfter, TelegramNetworkError) as exc:
                    if retry_n < 2:
                        await asyncio.sleep(getattr(exc, "retry_after", 1))
                    else:
                        raise

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
                    for retry_n in range(3):
                        try:
                            await bot.send_message(
                                state.group_chat_id,
                                f"🎉 <b>{name} ha subido al nivel {xp_info['level']}!</b>{title_text}",
                            )
                            break
                        except (TelegramRetryAfter, TelegramNetworkError) as exc:
                            if retry_n < 2:
                                await asyncio.sleep(exc.retry_after)
                            else:
                                raise
        else:
            lines.append("  No hay puntuaciones registradas.")

        from src.services.event_service import event_service

        active_events = await event_service.get_active_events()
        for event in active_events:
            lines.append("")
            lines.append(f" <b>Evento en curso: {event['name']}</b> (x{event['multiplier']} XP)")

        lines.append("")
        lines.append("<i>Gracias por jugar 🛑 Stop!</i>")

        for retry_n in range(3):
            try:
                await bot.send_message(state.group_chat_id, "\n".join(lines))
                break
            except (TelegramRetryAfter, TelegramNetworkError) as exc:
                if retry_n < 2:
                    await asyncio.sleep(exc.retry_after)
                else:
                    raise

        # ── Log estructurado de fin de partida ──
        standings_data = []
        for position, (pid, score) in enumerate(winners):
            name = state.player_names.get(pid, f"ID{pid}")
            xp_info = xp_results.get(pid, {})
            standings_data.append(
                {
                    "position": position + 1,
                    "player_id": pid,
                    "name": name,
                    "score": score,
                    "xp_gained": xp_info.get("xp_gained", 0),
                    "level": xp_info.get("level"),
                    "leveled_up": xp_info.get("leveled_up", False),
                }
            )
        logger.info(
            "game_finished",
            extra={
                "game_id": state.game_id,
                "group_chat_id": state.group_chat_id,
                "total_rounds": state.total_rounds,
                "last_round": state.round_number,
                "total_players": state.total_players,
                "validation_mode": state.validation_mode,
                "first_completer_id": state.first_completer_id,
                "standings": standings_data,
            },
        )

        self._letter_pending.pop(state.game_id, None)
        self._rounds_by_group.pop(state.group_chat_id, None)
        if self._store:
            self._safe_task(self._store.delete_letter_pending(state.game_id))
            self._safe_task(self._store.delete_round(state.game_id))
            self._safe_task(self._store.delete_rounds_by_group(state.group_chat_id))

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

    @staticmethod
    def _build_update_snapshot(state: RoundState) -> dict:
        """Snapshot de campos de estado bajo el lock para evitar data race (D8)."""
        return {
            "round_number": state.round_number,
            "letter": state.letter,
            "categories": list(state.categories),
            "round_time": state.round_time,
            "submitted": {
                pid: {
                    "name": state.player_names.get(pid, f"Jugador {pid}"),
                    "completed": pid in state.complete_player_ids,
                }
                for pid in state.submitted_player_ids
            },
            "first_completer_name": state.first_completer_name,
            "first_completer_id": state.first_completer_id,
            "stop_presses": state.stop_presses,
            "chat_id": state.message_chat_id,
            "message_id": state.message_id,
        }

    def _debounced_update(self, state: RoundState, bot: Bot) -> None:
        if state.update_task and not state.update_task.done():
            state.update_task.cancel()
        snapshot = self._build_update_snapshot(state)
        state.update_task = asyncio.create_task(self._do_update_round_message(snapshot, bot))

    async def _do_update_round_message(self, snap: dict, bot: Bot) -> None:
        lines = [
            self._format_round_message(
                snap["round_number"], snap["letter"], snap["categories"], snap["round_time"]
            )
        ]

        if snap["submitted"]:
            lines.append("")
            lines.append("✅ <b>Respondieron:</b>")
            for pid, info in snap["submitted"].items():
                completed = "⭐" if info["completed"] else "⬜"
                lines.append(f"  {completed} {info['name']}")

        if snap["first_completer_id"]:
            name = snap["first_completer_name"] or "Alguien"
            lines.append("")
            lines.append(f"⏹ <b>{name} completó todas las categorías</b>")
            lines.append(f"  Stop: {snap['stop_presses']}/{NUM_STOP_BUTTONS}")

        try:
            await bot.edit_message_text(
                "\n".join(lines),
                chat_id=snap["chat_id"],
                message_id=snap["message_id"],
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
        reason: str | None = None,
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
                game_id=state.game_id,
            )

            # ── Log estructurado de resultados de ronda ──
            players_data = []
            for pid, total in sorted(totals.items(), key=lambda x: x[1], reverse=True):
                pname = state.player_names.get(pid, f"ID{pid}")
                answers_data = []
                for ad in details.get(pid, []):
                    answers_data.append(
                        {
                            "category": ad["word_slot"],
                            "answer": ad["raw_text"],
                            "correct": ad["is_correct"],
                            "score": ad["score"],
                            "validation_source": ad.get("validation_source", "unknown"),
                        }
                    )
                players_data.append(
                    {
                        "player_id": pid,
                        "name": pname,
                        "answers": answers_data,
                        "total": total,
                    }
                )
            logger.info(
                "round_result",
                extra={
                    "game_id": state.game_id,
                    "group_chat_id": state.group_chat_id,
                    "round_number": state.round_number,
                    "letter": state.letter,
                    "reason": reason,
                    "validation_mode": state.validation_mode,
                    "players": players_data,
                },
            )

            # Acumular respuestas únicas por jugador (G5)
            game_uid = self._unique_answers.setdefault(state.game_id, {})
            for pid, answer_list in details.items():
                unique_count = sum(1 for ad in answer_list if ad["score"] >= UNIQUE_POINTS)
                game_uid[pid] = game_uid.get(pid, 0) + unique_count

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
        self._cancelled[game_id] = True
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

            if self._store:
                await self._store.delete_round(game_id)
                await self._store.delete_letter_pending(game_id)
                if state:
                    await self._store.delete_rounds_by_group(state.group_chat_id)
                elif pending:
                    await self._store.delete_rounds_by_group(pending.group_chat_id)

            logger.info("Estado en memoria cancelado para game %s", game_id)
        self._cancelled.pop(game_id, None)

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
                .order_by(func.coalesce(GamePlayer.score, 0).desc())
            )
            rows = await session.execute(stmt)
            return [
                (row.Player.telegram_id, row.GamePlayer.score or 0) for row in rows
            ]

    async def _round_timer(self, state: RoundState, bot: Bot) -> None:
        try:
            round_msg_id = state.message_id
            round_chat_id = state.message_chat_id
            rt = state.round_time
            update_points = {max(5, rt * 2 // 3), max(5, rt // 3), 5}
            for remaining in range(rt, 0, -1):
                if state.game_id not in self._rounds:
                    return

                if remaining in update_points and round_msg_id:
                    try:
                        remaining_str = (
                            f"⏱ <b>{remaining}s restantes</b>\n\n"
                            f"{self._format_categories_only(state.categories)}"
                        )
                        await bot.edit_message_text(
                            remaining_str,
                            chat_id=round_chat_id,
                            message_id=round_msg_id,
                        )
                    except (TelegramBadRequest, TelegramForbiddenError):
                        pass

                await asyncio.sleep(1)

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
    def _format_categories_only(categories: list[str]) -> str:
        return "\n".join(f"  <b>{cat}:</b> ..." for cat in categories)

    @staticmethod
    def _format_stop_message(presses: int) -> str:
        return (
            "⏹ <b>¡Has completado todas las categorías!</b>\n\n"
            "Presiona <b>Stop</b> repetidamente para cerrar la ronda.\n"
            f"Progreso: {presses}/{NUM_STOP_BUTTONS}\n\n"
            "<i>Si todos los jugadores responden, la ronda se cerrará "
            "automáticamente.</i>"
        )


LINE_REGEX = re.compile(r"^\s*(.+?)\s*:\s*(.*?)\s*$")


def _unaccent(s: str) -> str:
    """Elimina tildes/diacriticos de una cadena."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _match_plural(raw_cat: str, cat_map: dict[str, str]) -> str | None:
    if raw_cat.endswith("es"):
        singular = raw_cat[:-2]
        if singular in cat_map:
            return cat_map[singular]
    if raw_cat.endswith("s"):
        singular = raw_cat[:-1]
        if singular in cat_map:
            return cat_map[singular]
    return None


def _extract_inline_categories(
    value: str,
    cat_map: dict[str, str],
    result: dict[str, str],
) -> str | None:
    """Busca patrones ``Categoría: Valor`` dentro de *value*.

    Si encuentra, extrae la(s) sub-categoría(s) en *result* (mutación) y
    retorna el texto restante como valor de la categoría original.
    Retorna ``None`` si no hay categorías inline.
    """
    tokens = sorted(
        set(cat_map.keys()) | set(_PLURAL_MAP.keys()),
        key=len,
        reverse=True,
    )
    inline_re = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in tokens) + r")\s*:",
        re.IGNORECASE,
    )

    m = inline_re.search(value)
    if not m:
        return None

    first_val = value[: m.start()].strip()
    raw_token = m.group(1).lower()

    rest = value[m.end() :].strip()
    second_val = _extract_inline_categories(rest, cat_map, result) or rest

    canonical = (
        cat_map.get(raw_token) or _PLURAL_MAP.get(raw_token) or _match_plural(raw_token, cat_map)
    )
    if canonical:
        if canonical in result:
            logger.warning(
                "Categoría duplicada '%s' en respuestas inline, se sobrescribe",
                canonical,
            )
        result[canonical] = second_val

    return first_val


def parse_answers(text: str, categories: list[str]) -> dict[str, str]:
    # Mapa sin acentos: "pais" → "País", "animal" → "Animal", ...
    cat_map: dict[str, str] = {}
    for cat in categories:
        cat_map[_unaccent(cat.lower())] = cat

    result: dict[str, str] = {}
    seen: set[str] = set()

    for line in text.splitlines():
        match = LINE_REGEX.match(line)
        if not match:
            continue
        raw_cat = _unaccent(match.group(1).strip().lower())
        value = match.group(2).strip()
        if not value:
            continue
        canonical = (
            cat_map.get(raw_cat) or _PLURAL_MAP.get(raw_cat) or _match_plural(raw_cat, cat_map)
        )
        if canonical:
            inline_value = _extract_inline_categories(value, cat_map, result)
            if inline_value is not None:
                value = inline_value
            if canonical in seen:
                logger.warning("Categoría duplicada '%s' en respuestas, se sobrescribe", canonical)
            seen.add(canonical)
            result[canonical] = value

    # Forzar todas las categorías en el dict (G6)
    for cat in categories:
        result.setdefault(cat, "")
    return result


def get_alphabet(include_n: bool = False) -> str:
    base = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if include_n:
        # Insertar Ñ despues de la N
        idx = base.index("N") + 1
        return base[:idx] + "Ñ" + base[idx:]
    return base


round_manager = RoundManager()
