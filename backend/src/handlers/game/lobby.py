import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.db.models import Player
from src.services.error_tracker import error_tracker
from src.services.game_orchestrator import lobby_manager
from src.utils import delete_after

logger = logging.getLogger(__name__)

game_router = Router()


@game_router.message(Command("stop"))
@error_tracker.track_errors(handler_name="cmd_stop")
async def cmd_stop(message: Message, player: Player, bot: Bot) -> None:
    if message.chat.type == "private":
        msg = await message.answer("❌ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    result = await lobby_manager.create_lobby(
        group_chat_id=message.chat.id, host_player=player, bot=bot
    )
    if result is None:
        try:
            await message.delete()
        except Exception:
            logger.warning("No se pudo eliminar el mensaje /stop en %s", message.chat.id)
    else:
        await message.answer(result)


@game_router.message(Command("cancel"))
@error_tracker.track_errors(handler_name="cmd_cancel")
async def cmd_cancel(message: Message, player: Player, bot: Bot) -> None:
    if message.chat.type == "private":
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    result = await lobby_manager.cancel_game(group_chat_id=message.chat.id, player=player, bot=bot)
    msg = await message.answer(result)
    asyncio.create_task(delete_after(msg))


@game_router.callback_query(F.data.startswith("join:"))
@error_tracker.track_errors(handler_name="callback_join")
async def callback_join(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    try:
        game_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return
    try:
        await lobby_manager.join_lobby(
            game_id=game_id,
            player=player,
            callback=callback,
            bot=bot,
        )
    except Exception:
        logger.exception("Error en join_lobby: game_id=%s jugador=%s", game_id, player.telegram_id)
        await callback.answer("❌ Error al unirse a la partida.", show_alert=True)


@game_router.callback_query(F.data.startswith("start:"))
@error_tracker.track_errors(handler_name="callback_start")
async def callback_start(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    try:
        game_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return
    try:
        await lobby_manager.start_game(game_id=game_id, player=player, callback=callback, bot=bot)
    except Exception:
        logger.exception("Error en start_game: game_id=%s jugador=%s", game_id, player.telegram_id)
        await callback.answer("❌ Error al iniciar la partida.", show_alert=True)
