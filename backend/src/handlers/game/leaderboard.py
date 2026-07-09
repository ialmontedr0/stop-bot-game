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

        entries = [(e["rank"], e["name"], e["score"]) for e in rows]
        from src.image_generator import generate_leaderboard_image
        from PIL import Image as PILImage
        from io import BytesIO

        # Descargar fotos de perfil para top 3
        profile_photos = {}
        for entry in rows[:3]:
            rank = entry["rank"]
            telegram_id = entry.get("player_id")
            if not telegram_id:
                continue
            try:
                user_photos = await message.bot.get_user_profile_photos(
                    user_id=telegram_id, limit=1
                )
                if user_photos.total_count > 0:
                    file_id = user_photos.photos[0][-1].file_id
                    file = await message.bot.get_file(file_id)
                    photo_bytes_io = await message.bot.download_file(file.file_path)
                    photo_data = photo_bytes_io.read()
                    profile_photos[rank] = PILImage.open(BytesIO(photo_data)).convert(
                        "RGBA"
                    )
                else:
                    profile_photos[rank] = None
            except Exception:
                profile_photos[rank] = None

        img_bytes = generate_leaderboard_image(
            entries, _current_week_range(), profile_photos
        )
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
        await status_msg.edit_text(
            "❌ Error al cargar el leaderboard. Intenta de nuevo más tarde."
        )


@leaderboard_router.message(Command("rank"))
async def cmd_rank(message: Message) -> None:
    if not message.from_user:
        return

    data = await leaderboard_service.get_player_rank_by_telegram(message.from_user.id)
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

    from src.utils import progress_bar

    rank_bar = progress_bar(data["rank"], 10, 10)
    await message.reply(
        f"{hbold('📊 Tu Rank Semanal')}\n\n"
        f"{medal}Puesto: #{data['rank']}\n"
        f"⭐ Puntaje: {data['score']} pts\n"
        f"🎮 Partidas: {data['games']}\n\n"
        f"{rank_bar}"
    )
