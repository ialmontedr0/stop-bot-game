from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

admin_router = Router()


@admin_router.message(Command("addevent"))
async def cmd_add_event(message: Message) -> None:
    # TODO: implementar creación de eventos desde el chat
    await message.reply(
        "⚠️ Comando en desarrollo. Usa la base de datos directamente para crear un evento."
    )
