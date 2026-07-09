import asyncio
import logging
import random
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery
from sqlalchemy import select

from src.db.engine import async_session_factory
from src.db.models import GamePlayer, GroupConfig, Player
from src.db.repositories import GameRepository
from src.keyboards.lobby import lobby_keyboard
from src.services.round_manager import (
    PLACEHOLDER,
    TOTAL_ROUNDS,
    get_alphabet,
    round_manager,
)

MAX_PLAYERS = 10
AUTO_START_DELAY = 30  # segundos tras el ultimo join
LOBBY_EXPIRE = 120  # segundos de inactividad total
MIN_PLAYERS_TO_START = 2

STATUS_LOBBY = "lobby"
STATUS_PLAYING = "playing"
STATUS_CANCELLED = "cancelled"

logger = logging.getLogger(__name__)


@dataclass
class LobbyState:
    game_id: int
    group_chat_id: int
    host_telegram_id: int
    host_name: str
    message_chat_id: int
    message_id: int
    player_telegram_ids: list[int] = field(default_factory=list)
    player_display_names: list[str] = field(default_factory=list)
    expire_task: asyncio.Task | None = None
    animation_task: asyncio.Task | None = None
    auto_start_task: asyncio.Task | None = None
    started: bool = False
    start_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class LobbyManager:
    """Gestiona las salas activas en memoria, indexadas por group_chat_id."""

    def __init__(self) -> None:
        self._lobbies: dict[int, LobbyState] = {}

    # --- Consultas ---------------------------------------------------------
    def has_lobby(self, group_chat_id: int) -> bool:
        return group_chat_id in self._lobbies

    def get_lobby(self, group_chat_id: int) -> LobbyState | None:
        return self._lobbies.get(group_chat_id)

    def get_lobby_by_game(self, game_id: int) -> LobbyState | None:
        for state in self._lobbies.values():
            if state.game_id == game_id:
                return state
        return None

    # --- Crear lobby --------------------------------------------------------
    async def create_lobby(
        self, group_chat_id: int, host_player: Player, bot: Bot
    ) -> str | None:
        async with async_session_factory() as session:
            repo = GameRepository(session)

            existing = await repo.get_active_game(group_chat_id)
            if existing:
                if existing.status == STATUS_LOBBY and group_chat_id not in self._lobbies:
                    await repo.update_game_status(existing, STATUS_CANCELLED)
                else:
                    return "⚠️ Ya hay una sala abierta en este grupo."

            game = await repo.create_game(group_chat_id)
            await repo.add_player_to_game(game, host_player, is_host=True)

        host_name = host_player.first_name or host_player.username or f"ID{host_player.telegram_id}"
        text = self._format_lobby_message(
            title="🛑 STOP - Sala abierta", count=1, players=[host_name]
        )
        keyboard = lobby_keyboard(game.id, is_host=True)
        msg = await bot.send_message(group_chat_id, text, reply_markup=keyboard)

        state = LobbyState(
            game_id=game.id,
            group_chat_id=group_chat_id,
            host_telegram_id=host_player.telegram_id,
            host_name=host_name,
            message_chat_id=msg.chat.id,
            message_id=msg.message_id,
            player_telegram_ids=[host_player.telegram_id],
            player_display_names=[host_name],
        )
        state.expire_task = asyncio.create_task(self._expire_timer(state, bot))
        state.animation_task = asyncio.create_task(self._animation_loop(state, bot))
        self._lobbies[group_chat_id] = state

        await self._send_placeholder_dm(host_player, bot)
        return None

    # --- DM placeholder ----------------------------------------------------
    @staticmethod
    async def _send_placeholder_dm(player: Player, bot: Bot) -> None:
        try:
            await bot.send_message(
                player.telegram_id,
                "🎮 Te has unido a una partida de Stop.\n\n"
                "Cuando comience la ronda, el bot mostrará una letra. "
                "Tienes 60 segundos para escribir una palabra con esa letra "
                "en cada categoría.\n\n"
                "Copia el siguiente mensaje y úsalo como plantilla:",
            )
            await bot.send_message(
                player.telegram_id,
                f"{PLACEHOLDER}",
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            logger.warning("No se pudo enviar DM a %s", player.telegram_id)

    # --- Unirse ------------------------------------------------------------
    async def join_lobby(
        self, game_id: int, player: Player, callback: CallbackQuery, bot: Bot
    ) -> None:
        state = self.get_lobby_by_game(game_id)
        if not state:
            await callback.answer("❌ Esta sala ya no existe.", show_alert=True)
            return

        if player.telegram_id in state.player_telegram_ids:
            await callback.answer("✅ Ya estás en la partida", show_alert=False)
            return

        if len(state.player_telegram_ids) >= MAX_PLAYERS:
            await callback.answer(
                f"❌ La partida ya tiene {MAX_PLAYERS} jugadores.", show_alert=True
            )
            return

        async with async_session_factory() as session:
            repo = GameRepository(session)
            db_game = await repo.get_by_id(game_id)
            if not db_game or db_game.status != STATUS_LOBBY:
                await callback.answer("❌ La partida ya inicio.", show_alert=True)
                # Limpiar estado huerfano
                self._cleanup(state)
                return

            # Doble check en DB
            if await repo.is_player_in_game(db_game, player):
                await callback.answer("✅ Ya estas registrado.", show_alert=False)
                return

            await repo.add_player_to_game(db_game, player, is_host=False)

        name = player.first_name or player.username or f"ID{player.telegram_id}"
        state.player_telegram_ids.append(player.telegram_id)
        state.player_display_names.append(name)

        await callback.answer("✅ Te has unido a la partida", show_alert=False)

        await self._send_placeholder_dm(player, bot)

        # Resetear auto-start si hay suficientes jugadores
        self._reset_auto_start(state, bot)

        # Si llega a 10 -> auto-start inmediato
        if len(state.player_telegram_ids) >= MAX_PLAYERS:
            await self._do_start(state, bot)
            return

    # --- Iniciar -----------------------------------------------------------
    async def start_game(
        self, game_id: int, player: Player, callback: CallbackQuery, bot: Bot
    ) -> None:
        state = self.get_lobby_by_game(game_id)
        if not state:
            async with async_session_factory() as session:
                repo = GameRepository(session)
                db_game = await repo.get_by_id(game_id)
                if db_game and db_game.status == STATUS_PLAYING:
                    await callback.answer("❌ La partida ya comenzó.", show_alert=True)
                    return
                if db_game and db_game.status == STATUS_CANCELLED:
                    await callback.answer("❌ Esta partida fue cancelada.", show_alert=True)
                    return
            await callback.answer("❌ Sala no encontrada.", show_alert=True)
            return

        if player.telegram_id != state.host_telegram_id:
            await callback.answer("❌ Solo el host puede iniciar la partida.", show_alert=True)
            return

        if len(state.player_telegram_ids) < MIN_PLAYERS_TO_START:
            await callback.answer(
                f"❌ Se necesitan al menos {MIN_PLAYERS_TO_START} jugadores.",
                show_alert=True,
            )
            return

        await self._do_start(state, bot)

    # --- Cancelar todas (graceful shutdown) ---------------------------------
    async def cancel_all_games(self) -> None:
        for game_id in list(self._lobbies.keys()):
            state = self._lobbies.get(game_id)
            if state:
                state.cancelled = True
                for task in (state.expire_task, state.animation_task, state.auto_start_task):
                    if task and not task.done():
                        task.cancel()
            self._lobbies.pop(game_id, None)
            logger.info("Lobby %s cancelado por shutdown", game_id)

        from src.services.round_manager import round_manager

        for gid in list(round_manager._rounds.keys()):
            await round_manager.cancel_game(gid)

    # --- Detener partida ----------------------------------------------------
    async def cancel_game(self, group_chat_id: int, player: Player, bot: Bot) -> str:
        state = self._lobbies.get(group_chat_id)

        async with async_session_factory() as session:
            repo = GameRepository(session)
            db_game = await repo.get_active_game(group_chat_id)

            if not db_game:
                return "❌ No hay una partida activa en este grupo."

            stmt = (
                select(GamePlayer)
                .where(GamePlayer.game_id == db_game.id)
                .where(GamePlayer.player_id == player.id)
                .where(GamePlayer.is_host)
            )
            result = await session.execute(stmt)
            gp = result.scalar_one_or_none()
            if not gp:
                return "❌ Solo el host puede cancelar la partida."

            await repo.update_game_status(db_game, STATUS_CANCELLED)

            await round_manager.cancel_game(db_game.id)

        if state:
            self._cleanup(state)
            try:
                await bot.delete_message(chat_id=state.message_chat_id, message_id=state.message_id)
            except TelegramBadRequest:
                pass
        return "✅ Partida cancelada."

    # --- Auto-iniciar -------------------------------------------------------
    def _reset_auto_start(self, state: LobbyState, bot: Bot) -> None:
        if state.auto_start_task and not state.auto_start_task.done():
            state.auto_start_task.cancel()
        if len(state.player_telegram_ids) >= MIN_PLAYERS_TO_START:
            state.auto_start_task = asyncio.create_task(self._auto_start_timer(state, bot))

    async def _auto_start_timer(self, state: LobbyState, bot: Bot) -> None:
        try:
            await asyncio.sleep(AUTO_START_DELAY)
            if state.group_chat_id in self._lobbies:
                await self._do_start(state, bot)
        except asyncio.CancelledError:
            pass

    # --- Expiracion por inactividad ------------------------------------------
    async def _expire_timer(self, state: LobbyState, bot: Bot) -> None:
        try:
            await asyncio.sleep(LOBBY_EXPIRE)
            try:
                await bot.delete_message(
                    chat_id=state.message_chat_id,
                    message_id=state.message_id,
                )
            except TelegramBadRequest:
                pass

            async with async_session_factory() as session:
                repo = GameRepository(session)
                db_game = await repo.get_by_id(state.game_id)
                if db_game and db_game.status == STATUS_LOBBY:
                    await repo.update_game_status(db_game, STATUS_CANCELLED)

            try:
                await bot.send_message(
                    state.group_chat_id,
                    "⌛ <b>Lobby cerrado por inactividad.</b>",
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass

            self._cleanup(state)
        except asyncio.CancelledError:
            pass

    # --- Animacion cada 5s ---------------------------------------------------
    async def _animation_loop(self, state: LobbyState, bot: Bot) -> None:
        try:
            dots = 0
            while True:
                await asyncio.sleep(3)
                if state.group_chat_id not in self._lobbies:
                    break
                dots = (dots % 3) + 1
                title = "🛑 STOP - Sala abierta" + "." * dots
                text = self._format_lobby_message(
                    title, len(state.player_telegram_ids), state.player_display_names
                )
                is_host = state.host_telegram_id in state.player_telegram_ids
                keyboard = lobby_keyboard(state.game_id, is_host=is_host)

                try:
                    await bot.edit_message_text(
                        text,
                        chat_id=state.message_chat_id,
                        message_id=state.message_id,
                        reply_markup=keyboard,
                    )
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    logger.warning("Error editando el mensaje lobby", exc_info=e)
        except asyncio.CancelledError:
            pass

    # --- Limpieza global --------------------------------------------------------
    @staticmethod
    async def cleanup_stale_games() -> None:
        logger.info("Limpiando partidas huerfanas...")
        async with async_session_factory() as session:
            repo = GameRepository(session)
            stale = await repo.get_stale_games()
            for game in stale:
                await repo.update_game_status(game, STATUS_CANCELLED)
                logger.info("Partida %s cancelada por stale", game.id)

    @staticmethod
    async def _get_group_config(group_chat_id: int) -> GroupConfig | None:
        async with async_session_factory() as session:
            stmt = select(GroupConfig).where(GroupConfig.group_chat_id == group_chat_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # --- Iniciar partida -------------------------------------------------------
    async def _do_start(self, state: LobbyState, bot: Bot) -> None:
        async with state.start_lock:
            if state.started:
                logger.warning("_do_start llamado múltiples veces para game %s", state.game_id)
                return
            state.started = True
        self._cleanup(state)

        # --- Leer validation_mode del grupo ----------------
        group_config = await self._get_group_config(state.group_chat_id)
        validation_mode = group_config.validation_mode if group_config else "local"

        # --- Leer configuracion de partida -----------------

        # Pasar round_time y categories tambien al start_round
        categories = None
        round_time = 60
        include_n = False
        if group_config:
            if group_config.categories:
                categories = [c.strip() for c in group_config.categories.split(",") if c.strip()]
            round_time = group_config.round_time
            include_n = group_config.include_n

        logger.info("Modo validacion para grupo %s: %s", state.group_chat_id, validation_mode)

        try:
            await bot.delete_message(chat_id=state.message_chat_id, message_id=state.message_id)
        except TelegramBadRequest:
            pass

        player_names = dict(zip(state.player_telegram_ids, state.player_display_names))

        participants = "\n".join(
            f"  {i + 1}. {name}" for i, name in enumerate(state.player_display_names)
        )
        await bot.send_message(
            state.group_chat_id,
            f"🎮 <b>¡Partida iniciada!</b>\n\n"
            f"{len(state.player_telegram_ids)} jugadores:\n"
            f"{participants}\n\n",
        )

        # === Countdown 3-2-1 ===
        count_msg = await bot.send_message(
            state.group_chat_id,
            "⏰ <b>Preparando ronda 1...</b>",
        )
        for i in range(3, 0, -1):
            await asyncio.sleep(1)
            try:
                await count_msg.edit_text(f"<b>{i}...</b>")
            except TelegramBadRequest:
                pass
        try:
            await count_msg.delete()
        except TelegramBadRequest:
            pass
        # === Fin countdoun ===

        async with async_session_factory() as session:
            repo = GameRepository(session)
            db_game = await repo.get_by_id(state.game_id)
            if db_game:
                db_game.current_round = 1
                await repo.update_game_status(db_game, STATUS_PLAYING)

        letter = random.choice(get_alphabet(include_n))

        if group_config:
            total_rounds = group_config.default_rounds
        elif db_game:
            total_rounds = db_game.total_rounds
        else:
            total_rounds = TOTAL_ROUNDS

        await round_manager.start_round(
            game_id=state.game_id,
            group_chat_id=state.group_chat_id,
            round_number=1,
            letter=letter,
            total_players=len(state.player_telegram_ids),
            total_rounds=total_rounds,
            player_names=player_names,
            bot=bot,
            host_telegram_id=state.host_telegram_id,
            round_time=round_time,
            categories=categories,
            include_n=include_n,
            validation_mode=validation_mode,
        )

    # --- Limpieza --------------------------------------------------------------
    def _cleanup(self, state: LobbyState) -> None:
        self._lobbies.pop(state.group_chat_id, None)
        for task in (state.expire_task, state.animation_task, state.auto_start_task):
            if task and not task.done():
                task.cancel()

    # --- Formateo de mensaje ---------------------------------------------------
    @staticmethod
    def _format_lobby_message(
        title: str,
        count: int,
        players: list[str],
    ) -> str:
        lines = [f"<b>{title}</b>", "", f"👤 Jugadores: {count}/{MAX_PLAYERS}", ""]
        if players:
            lines.extend(f"  {i + 1}. {name}" for i, name in enumerate(players))
            lines.append("")
        lines.append(
            f"⏱ Inicio automático en {AUTO_START_DELAY}s tras la última "
            f"incorporación (mín. {MIN_PLAYERS_TO_START} jugadores)."
        )
        lines.append(
            f"El host puede presionar <b>Iniciar</b> o esperar a completar {MAX_PLAYERS} jugadores."
        )
        return "\n".join(lines)


# Singleton
lobby_manager = LobbyManager()
game_orchestrator = lobby_manager
