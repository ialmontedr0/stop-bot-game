"""Utilidades generales."""
import asyncio
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message


async def delete_after(message: Message, delay: int = 20) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass