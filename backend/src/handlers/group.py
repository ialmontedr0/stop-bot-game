import logging

from aiogram import Bot, Router
from aiogram.filters import IS_MEMBER, IS_NOT_MEMBER, ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated

from src.db.engine import async_session_factory
from src.db.repositories import GameRepository
from src.services.round_manager import round_manager

logger = logging.getLogger(__name__)

group_router = Router()


@group_router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER)
)
async def bot_added_to_group(event: ChatMemberUpdated, bot: Bot) -> None:
    try:
        title = event.chat.title or "este grupo"
        await bot.send_message(
            event.chat.id,
            f"¡Gracias por añadirme a <b>{title}</b>! 🎉\n\n"
            "Escribe /stop para comenzar una partida.",
        )
    except Exception:
        logger.exception("Error al enviar mensaje de bienvenida al grupo %s", event.chat.id)


@group_router.my_chat_member(
    ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER >> IS_NOT_MEMBER)
)
async def bot_removed_from_group(event: ChatMemberUpdated, bot: Bot) -> None:
    try:
        logger.info("Bot eliminado del grupo %s", event.chat.id)
        async with async_session_factory() as session:
            repo = GameRepository(session)
            game = await repo.get_active_game(event.chat.id)
            if game:
                await repo.update_game_status(game, "cancelled")
                round_manager.cancel_game(game.id)
                logger.info("Partida %s cancelada al eliminar el bot", game.id)
    except Exception:
        logger.exception("Error al limpiar datos tras ser eliminado del grupo %s", event.chat.id)
