import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from sqlalchemy import func, select

from src.db.engine import async_session_factory
from src.db.models import Answer, Game, GamePlayer, Player
from src.db.models import Round as RoundModel
from src.services.error_tracker import error_tracker
from src.services.xp_service import xp_service

logger = logging.getLogger(__name__)
profile_router = Router()


@profile_router.message(Command("profile"))
@error_tracker.track_errors(handler_name="cmd_profile")
async def cmd_profile(message: Message, player: Player) -> None:
    if not message.from_user:
        return
    """Muestra estadísticas personales del jugador."""
    status_msg = await message.reply("📊 Cargando tu perfil...")

    try:
        is_group = message.chat.type in ("group", "supergroup")
        xp_data = await xp_service.get_profile(player.id)

        lines = [f"{hbold('👤 Tu Perfil')}\n"]

        if is_group:
            group_chat_id = message.chat.id

            async with async_session_factory() as session:
                total_games_stmt = (
                    select(func.count(GamePlayer.id))
                    .where(GamePlayer.player_id == player.id)
                    .join(Game, GamePlayer.game_id == Game.id)
                    .where(Game.group_chat_id == group_chat_id)
                    .where(Game.status == "finished")
                )
                total_games = (await session.execute(total_games_stmt)).scalar() or 0

                subq = (
                    select(
                        GamePlayer.game_id,
                        func.max(GamePlayer.score).label("max_score"),
                    )
                    .select_from(GamePlayer)
                    .join(Game, GamePlayer.game_id == Game.id)
                    .where(Game.group_chat_id == group_chat_id)
                    .where(Game.status == "finished")
                    .group_by(GamePlayer.game_id)
                    .subquery()
                )
                player_wins_stmt = (
                    select(func.count(GamePlayer.id))
                    .where(GamePlayer.player_id == player.id)
                    .where(GamePlayer.score == subq.c.max_score)
                    .where(GamePlayer.game_id == subq.c.game_id)
                    .where(GamePlayer.score > 0)
                )
                wins_count = (await session.execute(player_wins_stmt)).scalar() or 0

                total_score_stmt = (
                    select(func.coalesce(func.sum(GamePlayer.score), 0))
                    .where(GamePlayer.player_id == player.id)
                    .join(Game, GamePlayer.game_id == Game.id)
                    .where(Game.group_chat_id == group_chat_id)
                    .where(Game.status == "finished")
                )
                total_score = (await session.execute(total_score_stmt)).scalar() or 0

                mvp_stmt = (
                    select(func.count(RoundModel.id))
                    .where(RoundModel.stopped_by_player_id == player.id)
                    .join(Game, RoundModel.game_id == Game.id)
                    .where(Game.group_chat_id == group_chat_id)
                    .where(Game.status == "finished")
                )
                mvp_count = (await session.execute(mvp_stmt)).scalar() or 0

                total_answers_stmt = (
                    select(func.count(Answer.id))
                    .where(Answer.player_id == player.id)
                    .join(RoundModel, Answer.round_id == RoundModel.id)
                    .join(Game, RoundModel.game_id == Game.id)
                    .where(Game.group_chat_id == group_chat_id)
                    .where(Game.status == "finished")
                )
                total_answers = (await session.execute(total_answers_stmt)).scalar() or 0

                correct_answers_stmt = (
                    select(func.count(Answer.id))
                    .where(Answer.player_id == player.id)
                    .where(Answer.is_correct)
                    .join(RoundModel, Answer.round_id == RoundModel.id)
                    .join(Game, RoundModel.game_id == Game.id)
                    .where(Game.group_chat_id == group_chat_id)
                    .where(Game.status == "finished")
                )
                correct_answers = (await session.execute(correct_answers_stmt)).scalar() or 0

                accuracy = (correct_answers / total_answers * 100) if total_answers > 0 else 0

            lines.extend([
                f"🎮 Partidas jugadas: {total_games}",
                f"🏆 Victorias: {wins_count}",
                f"⭐ MVP (Stops): {mvp_count}",
                f"📊 Puntaje total: {total_score} pts",
                f"🎯 Rating de aciertos: {accuracy:.1f}% ({correct_answers}/{total_answers})",
            ])
        else:
            lines.append("💬 Usa este comando en un grupo para ver estadísticas de juego.")
            lines.append("📌 A continuación se muestran tus datos globales:")

        # Seccion XP
        if xp_data:
            title_text = f" ({xp_data['title']})" if xp_data["title"] else ""
            lines.append("")
            lines.append(f"{hbold('⚡ XP y Nivel')}")
            lines.append(f"🎖 Nivel {xp_data['level']}{title_text}")
            lines.append(f"✨ XP total: {xp_data['total_xp']}")
            lines.append(f"📈 Progreso al nivel {xp_data['level'] + 1}: {xp_data['progress_pct']}%")
            bar_len = 10
            filled = int(xp_data["progress_pct"] / 100 * bar_len)
            bar = "🟩" * filled + "⬜" * (bar_len - filled)
            lines.append(f"  {bar}  {xp_data['progress_pct']:.0f}%")

        # Sección racha (siempre visible, D3)
        fire = "🔥"
        streak_val = xp_data["streak"] if xp_data and xp_data["streak"] else 0
        max_streak_val = xp_data["max_streak"] if xp_data and xp_data.get("max_streak") else 0
        if streak_val >= 3:
            fire = "🔥"
        elif streak_val > 0:
            fire = "⭐"
        else:
            fire = "⚪"
        lines.append("")
        lines.append(f"{hbold('📅 Racha')}")
        lines.append(f"{fire} Racha actual: {streak_val} días")
        lines.append(f"🏅 Mejor racha: {max_streak_val} días")

        # Rank semanal (solo en grupo)
        if is_group:
            from src.services.leaderboard import leaderboard_service

            rank_data = await leaderboard_service.get_player_rank_by_telegram(player.telegram_id, message.chat.id)
            if rank_data:
                lines.append("")
                lines.append(f"{hbold('📊 Rank Semanal')}")
                lines.append(f"  Puesto #{rank_data['rank']} — {rank_data['score']} pts")

        text = "\n".join(lines)
        await status_msg.edit_text(text)

    except Exception as e:
        logger.exception("Error en /profile: %s", e)
        await status_msg.edit_text("❌ Error al cargar tu perfil. Intenta de nuevo más tarde.")
