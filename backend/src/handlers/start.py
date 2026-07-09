import asyncio

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from src.utils import delete_after

start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    from aiogram.types import BufferedInputFile

    from src.image_generator import generate_welcome_image

    img_bytes = generate_welcome_image()
    text = (
        "<b>🛑 Stop Bot</b>\n\n"
        "El juego clásico de <b>Stop / Basta</b> ahora en Telegram.\n\n"
        "<b>Comandos para jugar:</b>\n"
        "• /stop — Iniciar una partida en el grupo\n"
        "• /cancel — Cancelar una partida en curso (solo quien creó la sala)\n"
        "• /help — Cómo se juega y puntuación\n\n"
        "<b>Estadísticas y perfil:</b>\n"
        "• /stats — Estadísticas del grupo\n"
        "• /profile — Tu perfil y puntuación personal\n\n"
        "<b>Configuración (solo admins del grupo):</b>\n"
        "• /settings — Configurar rondas, tiempo, categorías y Ñ\n"
        "• /clear — Limpiar mensajes del bot en el grupo\n\n"
        "<b>Diagnóstico (solo admins):</b>\n"
        "• /diagnose — Reporte completo de errores\n"
        "• /errors — Ver errores sin resolver\n"
        "• /resolve — Marcar errores como resueltos\n\n"
        "¡Añádeme a un grupo y juega con tus amigos!"
    )
    if img_bytes:
        photo = BufferedInputFile(img_bytes, filename="welcome.png")
        msg = await message.answer_photo(photo=photo, caption=text)
    else:
        msg = await message.answer(text)
    if message.chat.type in ("group", "supergroup"):
        asyncio.create_task(delete_after(msg))


@start_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    from aiogram.types import BufferedInputFile

    from src.image_generator import generate_help_image

    img_bytes = generate_help_image()
    text = (
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
    if img_bytes:
        photo = BufferedInputFile(img_bytes, filename="help.png")
        msg = await message.answer_photo(photo=photo, caption=text)
    else:
        msg = await message.answer(text)
    if message.chat.type in ("group", "supergroup"):
        asyncio.create_task(delete_after(msg))
