from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

admin_router = Router()


@admin_router.message(Command("addevent"))
async def cmd_add_event(message: Message) -> None:
    await message.reply(
        "⚠️ Comando en desarrollo. Usa la base de datos directamente para crear un evento."
    )
