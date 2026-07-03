import logging

from aiogram import Bot, Router, F
from aiogram.types import CallbackQuery, Message

from src.db.models import Player
from src.services.round_manager import (
    round_manager,
    parse_answers,
    ALPHABET,
)

logger = logging.getLogger(__name__)

round_router = Router()


@round_router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_round_answer(message: Message, player: Player, bot: Bot) -> None:
    if message.text.startswith("/"):
        return

    if message.from_user and message.from_user.is_bot:
        return

    if ":" not in message.text:
        return

    state = round_manager.get_active_round_by_group(message.chat.id)
    if not state:
        return

    parsed = parse_answers(message.text, state.categories)
    if not parsed:
        return

    try:
        await round_manager.submit_answers(
            game_id=state.game_id,
            player=player,
            text=message.text,
            bot=bot,
        )
    except Exception:
        logger.exception("Error al procesar respuesta")


@round_router.callback_query(F.data.startswith("stop:"))
async def callback_stop(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    try:
        _, game_id_str, _ = callback.data.split(":")
        game_id = int(game_id_str)
    except (ValueError, IndexError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    await round_manager.press_stop(
        game_id=game_id,
        player_id=player.telegram_id,
        callback=callback,
        bot=bot,
    )


@round_router.callback_query(F.data.startswith("letter:"))
async def callback_letter(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    try:
        _, game_id_str, letter = callback.data.split(":")
        game_id = int(game_id_str)
    except (ValueError, IndexError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

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


@round_router.callback_query(F.data.startswith("next_round:"))
async def callback_next_round(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    try:
        _, game_id_str = callback.data.split(":")
        game_id = int(game_id_str)
    except (ValueError, IndexError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    await round_manager.handle_next_round(
        game_id=game_id,
        player_id=player.telegram_id,
        callback=callback,
        bot=bot,
    )


@round_router.callback_query(F.data.startswith("stop_game:"))
async def callback_stop_game(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    try:
        _, game_id_str = callback.data.split(":")
        game_id = int(game_id_str)
    except (ValueError, IndexError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    await round_manager.handle_stop_game(
        game_id=game_id,
        player_id=player.telegram_id,
        callback=callback,
        bot=bot,
    )
