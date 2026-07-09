import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from cachetools import TTLCache


class ThrottlingMiddleware(BaseMiddleware):
    """Rate-Limiter en memoria (max. 1 msg / 0.5s por usuario)"""

    def __init__(self, rate_limit: float = 0.5) -> None:
        self.rate_limit = rate_limit
        self.cache: TTLCache[int, float] = TTLCache(maxsize=10_000, ttl=60)

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id = self._resolve_user_id(event)
        if user_id is not None:
            now = time.time()
            last = self.cache.get(user_id, 0.0)
            if now - last < self.rate_limit:
                if isinstance(event, CallbackQuery):
                    await event.answer("⏳ Demasiado rápido. Espera un momento.", show_alert=False)
                return
            self.cache[user_id] = now
        return await handler(event, data)

    @staticmethod
    def _resolve_user_id(event: TelegramObject) -> int | None:
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        return None
