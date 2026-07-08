import asyncio
import logging

from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message

from src.db.engine import async_session_factory
from src.db.repositories.message_log_repository import MessageLogRepository
from src.utils import delete_after, is_admin

logger = logging.getLogger(__name__)
clear_router = Router()

BATCH_SIZE = 100


@clear_router.message(Command("clear"))
async def cmd_clear(message: Message, bot: Bot) -> None:
    if message.chat.type not in ("group", "supergroup"):
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    if not await is_admin(bot, message.chat.id, message.from_user.id):
        msg = await message.answer("❌ Solo los administradores pueden limpiar mensajes.")
        asyncio.create_task(delete_after(msg))
        return

    status = await message.answer(" Limpiando mensajes del bot...")

    try:
        async with async_session_factory() as session:
            repo = MessageLogRepository(session)
            message_ids = await repo.get_today_messages(message.chat.id)

        if not message_ids:
            await status.edit_text(" No hay mensajes del bot para limpiar hoy.")
            return

        deleted_count = 0
        for i in range(0, len(message_ids), BATCH_SIZE):
            batch = message_ids[i : i + BATCH_SIZE]
            try:
                await bot.delete_messages(message.chat.id, batch)
                deleted_count += len(batch)
            except Exception as e:
                logger.warning("Error eliminando batch: %s", e)

            await asyncio.sleep(0.5)

        # Limpiar el log
        async with async_session_factory() as session:
            repo = MessageLogRepository(session)
            await repo.delete_by_message_ids(message.chat.id, message_ids)
            await session.commit()

        await status.edit_text(f" {deleted_count} mensaje(s) eliminado(s).")

    except Exception as e:
        logger.exception("Error en /clear: %s", e)
        await status.edit_text(
            " Error al limpiar mensajes. "
            "Asegurate de que el bot sea administrador del grupo "
            "con permisos pra eliminar mensajes."
        )
