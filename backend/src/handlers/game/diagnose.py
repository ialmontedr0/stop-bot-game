import asyncio
import logging

from aiogram import Bot, Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from src.db.engine import async_session_factory
from src.db.repositories.error_log_repository import ErrorLogRepository
from src.services.error_tracker import error_tracker
from src.utils import delete_after, is_admin

logger = logging.getLogger(__name__)

diagnose_router = Router()


@diagnose_router.message(Command("diagnose"))
async def cmd_diagnose(message: Message, bot: Bot) -> None:
    """Muestra un reporte de diagnóstico de errores."""
    if message.chat.type not in ("group", "supergroup"):
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    if not await is_admin(bot, message.chat.id, message.from_user.id):
        msg = await message.answer("❌ Solo los administradores pueden usar este comando.")
        asyncio.create_task(delete_after(msg))
        return

    game_id = None
    try:
        async with async_session_factory() as session:
            from src.db.repositories import GameRepository
            repo = GameRepository(session)
            game = await repo.get_active_game(message.chat.id)
            if game:
                game_id = game.id
    except Exception:
        logger.exception("Error al obtener juego activo para /diagnose")

    report = await error_tracker.generate_report(
        game_id=game_id,
        minutes=60,
    )

    MAX_LENGTH = 4000
    if len(report) <= MAX_LENGTH:
        await message.reply(report)
    else:
        parts = [report[i:i + MAX_LENGTH] for i in range(0, len(report), MAX_LENGTH)]
        for i, part in enumerate(parts):
            if i == 0:
                msg = await message.reply(part)
            else:
                msg = await message.answer(part)
            asyncio.create_task(delete_after(msg, delay=60))


@diagnose_router.message(Command("resolve"))
async def cmd_resolve(message: Message, command: CommandObject, bot: Bot) -> None:
    """Marca todos los errores no resueltos como resueltos.
    Uso: /resolve [reason opcional]
    """
    if message.chat.type not in ("group", "supergroup"):
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    if not await is_admin(bot, message.chat.id, message.from_user.id):
        msg = await message.answer("❌ Solo los administradores pueden resolver errores.")
        asyncio.create_task(delete_after(msg))
        return

    reason = command.args.strip() if command.args else ""
    if not reason:
        reason = "Resuelto manualmente por el host."

    async with async_session_factory() as session:
        repo = ErrorLogRepository(session)
        errors = await repo.get_unresolved()
        for err in errors:
            await repo.mark_resolved(err.id, resolution=reason)

    msg = await message.reply(f"✅ {len(errors)} error(es) marcado(s) como resuelto(s).")
    asyncio.create_task(delete_after(msg))


@diagnose_router.message(Command("errors"))
async def cmd_errors(message: Message, bot: Bot) -> None:
    """Muestra los últimos errores sin resolver."""
    if message.chat.type not in ("group", "supergroup"):
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    if not await is_admin(bot, message.chat.id, message.from_user.id):
        msg = await message.answer("❌ Solo los administradores pueden ver errores.")
        asyncio.create_task(delete_after(msg))
        return

    async with async_session_factory() as session:
        repo = ErrorLogRepository(session)
        errors = await repo.get_unresolved(limit=20)

    if not errors:
        await message.reply("✅ No hay errores sin resolver.")
        return

    lines = ["<b>📋 Errores sin resolver:</b>", ""]
    for err in errors[:20]:
        ts = err.timestamp.strftime("%H:%M") if err.timestamp else "??:??"
        exc_short = (err.exception_type or "Unknown").split(".")[-1]
        msg_short = (err.exception_message or "")[:60]
        lines.append(f"• <b>#{err.id}</b> [{ts}] <code>{exc_short}</code>")
        if msg_short:
            lines.append(f"  {msg_short}")
        if err.handler:
            lines.append(f"  Handler: {err.handler}")

    await message.reply("\n".join(lines))
