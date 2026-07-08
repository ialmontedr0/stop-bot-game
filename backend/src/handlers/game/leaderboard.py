import logging
from datetime import date, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.markdown import hbold

from src.services.leaderboard import leaderboard_service

logger = logging.getLogger(__name__)
leaderboard_router = Router()


def _current_week_range() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return f"{monday.strftime('%d/%m')} - {sunday.strftime('%d/%m')}"


@leaderboard_router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message) -> None:
    status_msg = await message.reply("📊 Cargando leaderboard...")

    try:
        rows = await leaderboard_service.get_weekly_top(limit=10)

        if not rows:
            await status_msg.edit_text(
                "📊 <b>Leaderboard Semanal</b>\n\n"
                "Aún no hay datos esta semana.\n"
                "¡Juega una partida para aparecer aquí!"
            )
            return

        lines = [
            f"{hbold('🏆 Leaderboard Semanal')}",
            f"📅 {_current_week_range()}\n",
        ]

        medals = ["🥇", "🥈", "🥉"]
        for entry in rows:
            rank = entry["rank"]
            medal = medals[rank - 1] if rank <= 3 else f"{rank}."
            name = entry["name"]
            score = entry["score"]
            games = entry["games"]
            lines.append(f"{medal} {name} — {score} pts ({games} partidas)")

        text = "\n".join(lines)
        await status_msg.edit_text(text)

    except Exception:
        logger.exception("Error en /leaderboard")
        await status_msg.edit_text(
            "❌ Error al cargar el leaderboard. Intenta de nuevo más tarde."
        )


@leaderboard_router.message(Command("rank"))
async def cmd_rank(message: Message) -> None:
    if not message.from_user:
        return

    data = await leaderboard_service.get_player_rank_by_telegram(
        message.from_user.id
    )
    if not data:
        await message.reply(
            "Aún no apareces en el leaderboard semanal.\n"
            "¡Juega una partida para empezar!"
        )
        return

    medal = ""
    if data["rank"] == 1:
        medal = "🥇 "
    elif data["rank"] == 2:
        medal = "🥈 "
    elif data["rank"] == 3:
        medal = "🥉 "

    await message.reply(
        f"{hbold('📊 Tu Rank Semanal')}\n\n"
        f"{medal}Puesto: #{data['rank']}\n"
        f"⭐ Puntaje: {data['score']} pts\n"
        f"🎮 Partidas: {data['games']}"
    )
