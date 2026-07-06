import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.db.engine import async_session_factory
from src.db.repositories import PlayerRepository

logger = logging.getLogger(__name__)


class UserExistsMiddleware(BaseMiddleware):
    """Crea el registro Player si no existe para cualquier interaccion."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = self._resolve_user(event)
        if user is not None and not user.is_bot:
            try:
                async with async_session_factory() as session:
                    repo = PlayerRepository(session)
                    player = await repo.get_or_create(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name or "",
                        last_name=user.last_name,
                        language_code=user.language_code,
                    )
                    data["player"] = player
            except Exception:
                logger.exception("Error al obtener/crear jugador %s", user.id)
                bot = data.get("bot")
                if bot and user:
                    try:
                        await bot.send_message(
                            user.id,
                            "❌ Error de conexión. Intenta de nuevo.",
                        )
                    except Exception:
                        pass
                return
        return await handler(event, data)

    @staticmethod
    def _resolve_user(event: TelegramObject):
        if isinstance(event, Message) and event.from_user:
            return event.from_user
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user
        return None
