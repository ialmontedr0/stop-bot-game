"""Utilidades generales."""

import asyncio
import contextlib
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

logger = logging.getLogger(__name__)


async def delete_after(message: Message, delay: int = 20) -> None:
    try:
        await asyncio.sleep(delay)
        with contextlib.suppress(TelegramBadRequest):
            await message.delete()
    except asyncio.CancelledError:
        pass


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        logger.exception("Error verificando admin status")
        return False


def progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "⬜" * length
    filled = int(current / total * length)
    filled = min(filled, length)
    return "🟩" * filled + "⬜" * (length - filled)


def format_score_table(
    scores: list[tuple[str, int]],
    title: str = "Puntuaciones",
) -> str:
    lines = [f"<b>📊 {title}</b>", ""]
    max_score = max((s[1] for s in scores), default=1)
    for i, (name, score) in enumerate(scores):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i + 1}."
        bar = progress_bar(score, max_score)
        lines.append(f"{medal} <b>{name}</b>  {bar}")
        lines.append(f"     {score} pts")
        lines.append("")
    return "\n".join(lines)
