import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.markdown import hbold
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.db.engine import async_session_factory
from src.db.models import Player, GroupConfig
from src.services.error_tracker import error_tracker
from sqlalchemy import select

logger = logging.getLogger(__name__)
settings_router = Router()

VALIDATION_MODES = {
    "local": "🔤 Local (solo fuzzy match)",
    "ai": "🤖 IA (Siempre IA)",
    "hybrid": "🔀 Hibrido (fuzzy + IA)",
}


async def _get_group_config(group_chat_id: int) -> GroupConfig:
    """Obtiene o crea la configuracion del grupo

    Args:
        group_chat_id (int): ID del chat

    Returns:
        GroupConfig: Configuracion o la crea
    """
    async with async_session_factory() as session:
        stmt = select(GroupConfig).where(GroupConfig.group_chat_id == group_chat_id)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        if config is None:
            config = GroupConfig(group_chat_id=group_chat_id)
            session.add(config)
            await session.commit()
            await session.refresh(config)
        return config


def _is_admin_or_host(message: Message) -> bool:
    """Verifica si el usuario es admin del grupo.

    Args:
        message (Message): Mensaje enviado por el usuario

    Returns:
        bool: True o False
    """
    return message.chat.type in ("group", "supergroup")


@settings_router.message(Command("settings"))
@error_tracker.track_errors(handler_name="cmd_settings")
async def cmd_settings(message: Message, player: Player) -> None:
    if message.chat.type == "private":
        await message.reply("❌ Este comando solo funciona en grupos.")
        return

    config = await _get_group_config(message.chat.id)
    current_mode = config.validation_mode or "local"
    mode_label = VALIDATION_MODES.get(current_mode, current_mode)

    # Solo el hosto o admin puede cambiar settings
    # Por implicidad, cualquier miembro puede ver
    text = (
        f"{hbold('⚙️ Configuracion del Grupo')}\n\n"
        f"Modo validacion actual: {mode_label}\n\n"
        f"Selecciona el modo de validacion de palabras:"
    )

    buttons = []
    for mode_key, mode_desc in VALIDATION_MODES.items():
        selected = "• " if mode_key == current_mode else ""
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{selected}{mode_desc}",
                    callback_data=f"set_mode:{mode_key}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="🔙 Cerrar", callback_data="settings_close")]
    )

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply(text, reply_markup=markup)


@settings_router.callback_query(F.data.startswith("set_mode:"))
async def set_mode_callback(callback: CallbackQuery) -> None:
    mode = callback.data.split(":", 1)[1]
    if mode not in VALIDATION_MODES:
        await callback.answer("❌ Modo invalido.", show_alert=True)
        return

    group_chat_id = callback.message.chat.id

    async with async_session_factory() as session:
        stmt = select(GroupConfig).where(GroupConfig.group_chat_id == group_chat_id)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        if config is None:
            config = GroupConfig(group_chat_id=group_chat_id)
            session.add(config)
        config.validation_mode = mode
        await session.commit()

    # Actualizar el mensaje
    mode_label = VALIDATION_MODES[mode]

    buttons = []
    for m_key, m_desc in VALIDATION_MODES.items():
        selected = "• " if m_key == mode else ""
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{selected}{m_desc}", callback_data=f"set_mode:{m_key}"
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="🔙 Cerrar", callback_data="settings_close")]
    )

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"{hbold('⚙️ Configuracion del Grupo')}\n\n"
        f"Modo validacion actual: {mode_label}\n\n"
        "✅ Modo actualizado.",
        reply_markup=markup,
    )
    await callback.answer(f"✅ Modo cambiado a {mode_label}")


@settings_router.callback_query(F.data == "settings_close")
async def settings_close_callback(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer()
