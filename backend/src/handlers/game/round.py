import asyncio
from typing import Optional

from aiogram import Bot, Router, F
from aiogram.types import CallbackQuery, Message

from src.db.engine import async_session_factory
from src.db.models import Player
from src.db.repositories.game_repository import GameRepository
from src.services.round_manager import (
    round_manager,
    parse_answers,
    ALPHABET,
)
from src.utils import delete_after

round_router = Router()


@round_router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_round_answer(message: Message, player: Player, bot: Bot) -> None:
    if message.text.startswith("/"):
        return

    state = round_manager.get_active_round_by_group(message.chat.id)
    if not state:
        return

    parsed = parse_answers(message.text, state.categories)
    if not parsed:
        return

    is_first = await round_manager.submit_answers(
        game_id=state.game_id,
        player=player,
        text=message.text,
        bot=bot,
    )

    name = player.first_name or player.username or f"ID{player.telegram_id}"
    filled = len(parsed)
    total = len(state.categories)

    reply = await message.reply(
        f"✅ <b>{name}</b>, recibimos {filled}/{total} categorías."
    )
    asyncio.create_task(delete_after(reply))


@round_router.callback_query(F.data.startswith("stop:"))
async def callback_stop(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    _, game_id_str, stop_str = callback.data.split(":")
    game_id = int(game_id_str)

    await round_manager.press_stop(
        game_id=game_id,
        player_id=player.telegram_id,
        callback=callback,
        bot=bot,
    )


@round_router.callback_query(F.data.startswith("letter:"))
async def callback_letter(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    _, game_id_str, letter = callback.data.split(":")
    game_id = int(game_id_str)

    if letter not in ALPHABET:
        await callback.answer("❌ Letra inválida.", show_alert=True)
        return

    await round_manager.handle_letter_selection(
        game_id=game_id,
        player_id=player.telegram_id,
        letter=letter,
        callback=callback,
        bot=bot,
    )
