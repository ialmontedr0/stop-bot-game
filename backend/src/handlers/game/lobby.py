import asyncio
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.utils import delete_after
from src.db.models import Player
from src.services.game_orchestrator import lobby_manager

game_router = Router()


@game_router.message(Command("stop"))
async def cmd_stop(message: Message, player: Player, bot: Bot) -> None:
    if message.chat.type == "private":
        msg = await message.answer("❌ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    result = await lobby_manager.create_lobby(
        group_chat_id=message.chat.id, host_player=player, bot=bot
    )
    if result is None:
        msg = await message.answer("✅ Sala creada. Esperando jugadores...")
        asyncio.create_task(delete_after(msg))
    else:
        await message.answer(result)


@game_router.message(Command("cancel"))
async def cmd_cancel(message: Message, player: Player, bot: Bot) -> None:
    if message.chat.type == "private":
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    result = await lobby_manager.cancel_game(
        group_chat_id=message.chat.id, player=player, bot=bot
    )
    msg = await message.answer(result)
    asyncio.create_task(delete_after(msg))


@game_router.callback_query(F.data.startswith("join:"))
async def callback_join(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    game_id = int(callback.data.split(":")[1])
    await lobby_manager.join_lobby(
        game_id=game_id,
        player=player,
        callback=callback,
        bot=bot,
    )


@game_router.callback_query(F.data.startswith("start:"))
async def callback_start(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    game_id = int(callback.data.split(":")[1])
    await lobby_manager.start_game(
        game_id=game_id, player=player, callback=callback, bot=bot
    )
