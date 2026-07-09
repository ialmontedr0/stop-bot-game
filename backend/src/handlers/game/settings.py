import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.markdown import hbold

from src.db.engine import async_session_factory
from src.db.models import GroupConfig, Player
from src.db.repositories.group_config_repository import GroupConfigRepository
from src.i18n import get_user_locale, t
from src.keyboards.settings import (
    ALL_CATEGORIES,
    settings_cats_keyboard,
    settings_main_keyboard,
    settings_mode_keyboard,
    settings_rounds_keyboard,
    settings_time_keyboard,
)
from src.utils import is_admin

logger = logging.getLogger(__name__)
settings_router = Router()


async def _get_config(group_chat_id: int) -> GroupConfig:
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        return await repo.get_or_create(group_chat_id)


def _parse_categories(raw: str | None) -> list[str]:
    if not raw:
        return list(ALL_CATEGORIES)  # por defecto todas
    return [c.strip() for c in raw.split(",") if c.strip()]


def _serialize_categories(cats: list[str]) -> str:
    return ",".join(cats)


@settings_router.message(Command("settings"))
async def cmd_settings(message: Message, player: Player, bot: Bot) -> None:

    if message.chat.type == "private":
        await message.reply("❌ Este comando solo funciona en grupos.")
        return

    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("❌ Solo los administradores del grupo pueden usar este comando.")
        return

    config = await _get_config(message.chat.id)
    cats = _parse_categories(config.categories)

    locale = get_user_locale(player)
    text = f"{hbold(t('settings_title', locale=locale))}\n\nSelecciona una opción para cambiar:"
    markup = settings_main_keyboard(
        current_rounds=config.default_rounds,
        current_time=config.round_time,
        current_categories=cats,
        include_n=config.include_n,
        current_mode=config.validation_mode or "local",
    )
    await message.reply(text, reply_markup=markup)


# ─── Menú principal ────────────────────────────────────────────────


@settings_router.callback_query(F.data == "settings_main")
async def back_to_main(callback: CallbackQuery) -> None:
    config = await _get_config(callback.message.chat.id)
    cats = _parse_categories(config.categories)
    markup = settings_main_keyboard(
        current_rounds=config.default_rounds,
        current_time=config.round_time,
        current_categories=cats,
        include_n=config.include_n,
        current_mode=config.validation_mode or "local",
    )
    await callback.message.edit_text(
        f"{hbold('⚙️ Configuración del Grupo')}\n\nSelecciona una opción para cambiar:",
        reply_markup=markup,
    )
    await callback.answer()


# ─── Rondas ────────────────────────────────────────────────────────


@settings_router.callback_query(F.data == "settings_rondas")
async def show_rounds(callback: CallbackQuery) -> None:
    config = await _get_config(callback.message.chat.id)
    markup = settings_rounds_keyboard(config.default_rounds)
    await callback.message.edit_text(
        f"{hbold('🎯 Rondas por partida')}\n\n"
        f"Actual: {config.default_rounds}\n\n"
        f"Selecciona el número de rondas:",
        reply_markup=markup,
    )
    await callback.answer()


@settings_router.callback_query(F.data.startswith("set_rondas:"))
async def set_rounds(callback: CallbackQuery) -> None:
    value = int(callback.data.split(":", 1)[1])
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(callback.message.chat.id)
        config.default_rounds = value
        await session.commit()
    await callback.answer(f"✅ Rondas cambiado a {value}")
    # Volver al submenú de rondas
    await show_rounds(callback)


# ─── Tiempo ────────────────────────────────────────────────────────


@settings_router.callback_query(F.data == "settings_tiempo")
async def show_time(callback: CallbackQuery) -> None:
    config = await _get_config(callback.message.chat.id)
    markup = settings_time_keyboard(config.round_time)
    await callback.message.edit_text(
        f"{hbold('⏱ Tiempo por ronda')}\n\n"
        f"Actual: {config.round_time}s\n\n"
        f"Selecciona el tiempo límite:",
        reply_markup=markup,
    )
    await callback.answer()


@settings_router.callback_query(F.data.startswith("set_tiempo:"))
async def set_time(callback: CallbackQuery) -> None:
    value = int(callback.data.split(":", 1)[1])
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(callback.message.chat.id)
        config.round_time = value
        await session.commit()
    await callback.answer(f"✅ Tiempo cambiado a {value}s")
    await show_time(callback)


# ─── Categorías ────────────────────────────────────────────────────


@settings_router.callback_query(F.data == "settings_cats")
async def show_cats(callback: CallbackQuery) -> None:
    config = await _get_config(callback.message.chat.id)
    selected = _parse_categories(config.categories)
    markup = settings_cats_keyboard(ALL_CATEGORIES, selected)
    await callback.message.edit_text(
        f"{hbold('📋 Categorías disponibles')}\n\n"
        f"Marca las categorías que quieres incluir "
        f"(mínimo 4 obligatorio):",
        reply_markup=markup,
    )
    await callback.answer()


@settings_router.callback_query(F.data.startswith("toggle_cat:"))
async def toggle_cat(callback: CallbackQuery) -> None:
    cat = callback.data.split(":", 1)[1]
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(callback.message.chat.id)
        selected = _parse_categories(config.categories)

        if cat in selected:
            if len(selected) <= 4:
                await callback.answer("❌ Mínimo 4 categorías requeridas.", show_alert=True)
                return
            selected.remove(cat)
        else:
            selected.append(cat)

        config.categories = _serialize_categories(selected)
        await session.commit()

    # Refrescar menú
    config = await _get_config(callback.message.chat.id)
    selected = _parse_categories(config.categories)
    markup = settings_cats_keyboard(ALL_CATEGORIES, selected)
    await callback.message.edit_text(
        f"{hbold('📋 Categorías disponibles')}\n\n"
        f"Marca las categorías que quieres incluir "
        f"(mínimo 4 obligatorio):",
        reply_markup=markup,
    )
    await callback.answer()


# ─── Ñ ─────────────────────────────────────────────────────────────


@settings_router.callback_query(F.data == "toggle_n")
async def toggle_n(callback: CallbackQuery) -> None:
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(callback.message.chat.id)
        config.include_n = not config.include_n
        await session.commit()

    # Refrescar menú principal
    await back_to_main(callback)


# ─── Modo de validación ──────────────────────────────────────────


@settings_router.callback_query(F.data == "settings_mode")
async def show_mode(callback: CallbackQuery) -> None:
    config = await _get_config(callback.message.chat.id)
    current = config.validation_mode or "local"
    markup = settings_mode_keyboard(current)
    await callback.message.edit_text(
        f"{hbold('⚡ Modo de validación')}\n\n"
        f"Actual: <b>{current}</b>\n\n"
        f"• 💻 <b>Local</b> — solo fuzzy matching + word lists\n"
        f"• 🤖 <b>AI</b> — siempre consulta IA\n"
        f"• 🔀 <b>Híbrido</b> — fuzzy primero, IA como fallback",
        reply_markup=markup,
    )
    await callback.answer()


@settings_router.callback_query(F.data.startswith("set_mode:"))
async def set_mode(callback: CallbackQuery) -> None:
    value = callback.data.split(":", 1)[1]
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(callback.message.chat.id)
        config.validation_mode = value
        await session.commit()
    await callback.answer(f"✅ Modo cambiado a {value}")
    await show_mode(callback)


# ─── Cerrar ────────────────────────────────────────────────────────


@settings_router.callback_query(F.data == "settings_close")
async def settings_close(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer()
