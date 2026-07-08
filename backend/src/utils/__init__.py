"""Utilidades generales."""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

logger = logging.getLogger(__name__)


async def delete_after(message: Message, delay: int = 20) -> None:
    try:
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
    except asyncio.CancelledError:
        pass


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Verifica si un usuario es administrador o creador del grupo."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        logger.exception("Error verificando admin status")
        return False