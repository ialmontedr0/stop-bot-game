import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.markdown import hbold

from sqlalchemy import select, func, desc

from src.db.engine import async_session_factory
from src.db.models import Game, GamePlayer, Player

logger = logging.getLogger(__name__)
stats_router = Router()


@stats_router.message(Command("stats"))
async def cmd_stats(message: Message, bot: Bot) -> None:
    if message.chat.type == "private":
        await message.reply("❌ Este comando solo funciona en grupos.")
        return

    group_chat_id = message.chat.id
    status_msg = await message.reply("⏳ Generando estadisticas...")

    try:
        async with async_session_factory() as session:
            # Total partidas jugadas
            total_games_stmt = (
                select(func.count(Game.id))
                .where(Game.group_chat_id == group_chat_id)
                .where(Game.status == "finished")
            )
            total_games = (await session.execute(total_games_stmt)).scalar() or 0

            # Top 10 jugadores por puntaje acumulado (todas las partidas)
            top_players_stmt = (
                select(
                    Player.telegram_id,
                    Player.first_name,
                    Player.username,
                    func.sum(GamePlayer.score).label("total_score"),
                    func.count(GamePlayer.game_id.distinct()).label("games_played"),
                )
                .join(GamePlayer, Player.id == GamePlayer.player_id)
                .join(Game, GamePlayer.game_id == Game.id)
                .where(Game.group_chat_id == group_chat_id)
                .where(Game.status == "finished")
                .group_by(
                    Player.id, Player.telegram_id, Player.first_name, Player.username
                )
                .order_by(desc("total_score"))
                .limit(10)
            )
            rows = await session.execute(top_players_stmt)
            top_players = rows.all()

            # Actividad reciente: partidas de los últimos 7 días
            week_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
            recent_games_stmt = (
                select(func.count(Game.id))
                .where(Game.group_chat_id == group_chat_id)
                .where(Game.status == "finished")
                .where(Game.finished_at >= week_ago)
            )
            recent_games = (await session.execute(recent_games_stmt)).scalar() or 0

        # Formatear texto
        lines = [
            f"{hbold('📊 Estadísticas del Grupo')}\n",
            f"🎮 Total partidas jugadas: {total_games}",
            f"📅 Partidas (7 días): {recent_games}\n",
            f"{hbold('🏆 Top 10 Jugadores')}",
        ]

        if top_players:
            medals = ["🥇", "🥈", "🥉"]
            for i, row in enumerate(top_players):
                name = row.first_name or f"ID{row.telegram_id}"
                if row.username:
                    name += f" (@{row.username})"
                medal = medals[i] if i < 3 else f"{i + 1}."
                total = row.total_score or 0
                gp = row.games_played or 0
                lines.append(f"{medal} {name} — {total} pts ({gp} partidas)")
        else:
            lines.append("  (sin datos todavía)")

        text = "\n".join(lines)
        await status_msg.edit_text(text)

    except Exception as e:
        logger.exception("Error en /stats: %s", e)
        await status_msg.edit_text(
            "❌ Error al generar estadísticas. Intenta de nuevo más tarde."
        )
