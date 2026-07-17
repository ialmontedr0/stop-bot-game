import asyncio
import logging
import time

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import text

from src.db.engine import async_session_factory
from src.services.error_tracker import error_tracker
from src.utils import delete_after, is_admin

logger = logging.getLogger(__name__)
clear_stats_router = Router()

CONFIRM_TIMEOUT = 15
_pending: dict[int, float] = {}


@clear_stats_router.message(Command("clear_stats"))
@error_tracker.track_errors(handler_name="cmd_clear_stats")
async def cmd_clear_stats(message: Message, bot: Bot, command: CommandObject) -> None:
    if not message.from_user:
        return
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("⚠️ Este comando solo funciona en grupos.")
        return

    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.answer("❌ Solo los administradores pueden borrar estadísticas.")
        return

    user_id = message.from_user.id
    ts = _pending.pop(user_id, 0)
    if ts and time.time() - ts <= CONFIRM_TIMEOUT:
        pass  # confirmado
    else:
        _pending[user_id] = time.time()
        msg = await message.answer(
            "⚠️ <b>¿Estás seguro?</b> Esta acción eliminará TODAS las "
            "estadísticas, XP, niveles y rachas del grupo.\n\n"
            "Escribe /clear_stats de nuevo en los próximos 15 segundos para confirmar."
        )
        asyncio.create_task(delete_after(msg, delay=CONFIRM_TIMEOUT))
        return

    status = await message.answer("🗑️ Borrando todas las estadísticas...")

    try:
        async with async_session_factory() as session:
            await session.execute(text("DELETE FROM message_logs"))
            await session.execute(text("DELETE FROM answers"))
            await session.execute(text("DELETE FROM rounds"))
            await session.execute(text("DELETE FROM game_players"))
            await session.execute(text("DELETE FROM games"))
            await session.execute(text("DELETE FROM weekly_leaderboards"))
            await session.execute(text("DELETE FROM player_xp"))
            await session.execute(text("DELETE FROM streaks"))
            await session.execute(text("ALTER SEQUENCE message_logs_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE answers_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE rounds_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE game_players_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE games_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE weekly_leaderboards_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE player_xp_id_seq RESTART WITH 1"))
            await session.execute(text("ALTER SEQUENCE streaks_id_seq RESTART WITH 1"))
            await session.commit()

        await status.edit_text(
            "✅ Todas las estadísticas han sido borradas.\n\n"
            "Datos eliminados:\n"
            "• XP, niveles y rachas de todos los jugadores\n"
            "• Historial de partidas, rondas y respuestas\n"
            "• Leaderboard semanal\n\n"
            "Los datos de configuración, listas de palabras y "
            "eventos estacionales se conservan."
        )

    except Exception as e:
        logger.exception("Error en /clear_stats: %s", e)
        await status.edit_text("❌ Error al borrar estadísticas.")
