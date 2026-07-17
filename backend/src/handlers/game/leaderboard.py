import logging
from datetime import date, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.markdown import hbold

from src.services.error_tracker import error_tracker
from src.services.leaderboard import leaderboard_service

logger = logging.getLogger(__name__)
leaderboard_router = Router()


def _current_week_range() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return f"{monday.strftime('%d/%m')} - {sunday.strftime('%d/%m')}"


@leaderboard_router.message(Command("leaderboard"))
@error_tracker.track_errors(handler_name="cmd_leaderboard")
async def cmd_leaderboard(message: Message) -> None:
    if message.chat.type == "private":
        await message.reply("❌ Este comando solo funciona en grupos.")
        return

    group_chat_id = message.chat.id
    status_msg = await message.reply("📊 Cargando leaderboard...")

    try:
        rows = await leaderboard_service.get_weekly_top(group_chat_id=group_chat_id, limit=10)

        if not rows:
            await status_msg.edit_text(
                "📊 <b>Leaderboard Semanal</b>\n\n"
                "Aún no hay datos esta semana.\n"
                "¡Juega una partida para aparecer aquí!"
            )
            return

        entries = [(e["rank"], e["name"], e["score"]) for e in rows]

        from src.image_generator import generate_leaderboard_image
        from src.services.photo_cache import photo_cache

        profile_photos = {}
        for entry in rows[:3]:
            rank = entry["rank"]
            telegram_id = entry.get("telegram_id")
            if not telegram_id:
                continue
            photo = await photo_cache.get_photo(message.bot, telegram_id)
            profile_photos[rank] = photo

        img_bytes = generate_leaderboard_image(entries, _current_week_range(), profile_photos)
        if img_bytes:
            from aiogram.types import BufferedInputFile

            photo = BufferedInputFile(img_bytes, filename="leaderboard.png")
            await message.answer_photo(photo=photo)

        else:
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
            await status_msg.edit_text("\n".join(lines))
            return

        await status_msg.delete()

    except Exception:
        logger.exception("Error en /leaderboard")
        await status_msg.edit_text("❌ Error al cargar el leaderboard. Intenta de nuevo más tarde.")


@leaderboard_router.message(Command("rank"))
@error_tracker.track_errors(handler_name="cmd_rank")
async def cmd_rank(message: Message) -> None:
    if not message.from_user:
        return

    if message.chat.type == "private":
        await message.reply("❌ Este comando solo funciona en grupos.")
        return

    group_chat_id = message.chat.id
    data = await leaderboard_service.get_player_rank_by_telegram(
        message.from_user.id, group_chat_id=group_chat_id
    )
    if not data:
        await message.reply(
            "Aún no apareces en el leaderboard semanal.\n¡Juega una partida para empezar!"
        )
        return

    medal = ""
    if data["rank"] == 1:
        medal = "🥇 "
    elif data["rank"] == 2:
        medal = "🥈 "
    elif data["rank"] == 3:
        medal = "🥉 "

    from src.utils import progress_bar

    rank_bar = progress_bar(data["rank"], 10, 10)
    await message.reply(
        f"{hbold('📊 Tu Rank Semanal')}\n\n"
        f"{medal}Puesto: #{data['rank']}\n"
        f"⭐ Puntaje: {data['score']} pts\n"
        f"🎮 Partidas: {data['games']}\n\n"
        f"{rank_bar}"
    )
