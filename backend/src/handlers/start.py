from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "<b>🛑 Stop Bot</b>\n\n"
        "El juego clásico de <b>Stop / Basta</b> ahora en Telegram.\n\n"
        "<b>Comandos:</b>\n"
        "• /stop — Iniciar una partida en el grupo\n"
        "• /help — Ayuda\n"
        "• /stats — Estadísticas\n"
        "• /weekly — Leaderboard semanal\n\n"
        "¡Añádeme a un grupo y juega con tus amigos!"
    )


@start_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>📖 ¿Cómo jugar?</b>\n\n"
        "1. Ve a un grupo y escribe /stop\n"
        "2. Espera a que se unan jugadores (máx. 10)\n"
        "3. Cuando comience la ronda, escribe palabras para cada categoría\n"
        "4. Sé el primero en completar todas y pulsa ⏹ Stop\n"
        "5. ¡Gana puntos y conviértete en el MVP!\n\n"
        "<b>Puntuación:</b>\n"
        "• Respuesta correcta única → 50 pts\n"
        "• Respuesta duplicada → 50 ÷ N jugadores\n"
        "• Respuesta incorrecta o vacía → 0 pts\n\n"
        "<b>¿Más dudas?</b> Háblale a @perezheredia el sabe como es la vaina."
    )
