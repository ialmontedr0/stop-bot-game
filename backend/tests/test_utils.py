from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from src.utils import delete_after


@pytest.mark.asyncio
async def test_delete_after_waits_and_deletes():
    message = AsyncMock()
    await delete_after(message, delay=0.01)
    message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_after_silent_on_telegram_error():
    message = AsyncMock()
    message.delete.side_effect = TelegramBadRequest(
        method="delete_message",
        message="error",
    )
    await delete_after(message, delay=0.01)
    message.delete.assert_awaited_once()
