"""Flujo FSM para crear/borrar eventos — solo chat privado.

FSM de 12 pasos para /newevent:
  0.  Selección de grupo
  1.  Tipo de evento (one_time / daily_recurring / permanent)
  2.  Nombre
  3.  Descripción
  4.  Multiplicador
  5.  Horario (duración para one_time, hora inicio/fin/días para daily)
  6.  Categorías activas + hidden + mystery
  6c. Multiplicadores por categoría (category_multipliers)
  7.  Tiempo por ronda + letra forzada
  7d. Letras excluidas + secuencia
  8.  Bonificaciones y penalizaciones
  8b. Modo de juego (sudden_death, wager, collaborative, etc.)
  9.  Confirmación y creación
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.core.text_utils import utcnow
from src.db.engine import async_session_factory
from src.db.models import SeasonalEvent
from src.keyboards.event import (
    bonuses_keyboard,
    category_multipliers_keyboard,
    categories_options_keyboard,
    categories_toggle_keyboard,
    confirm_delete_keyboard,
    confirm_event_keyboard,
    daily_end_keyboard,
    daily_start_keyboard,
    days_of_week_keyboard,
    decreasing_time_keyboard,
    delete_action_keyboard,
    delete_all_confirm_keyboard,
    duration_keyboard,
    edit_event_field_keyboard,
    event_type_keyboard,
    event_status_keyboard,
    events_edit_list_keyboard,
    events_list_keyboard,
    excluded_letters_keyboard,
    forced_letter_keyboard,
    game_mode_keyboard,
    groups_keyboard,
    letter_sequence_keyboard,
    multiplier_keyboard,
    round_time_keyboard,
    save_event_keyboard,
)
from src.services.event_rules import EventRules
from src.services.event_service import event_service

logger = logging.getLogger(__name__)

event_creator_router = Router()

_VALID_CATEGORIES = {
    "Nombre", "Apellido", "Color", "Fruta",
    "País", "Artista", "Animal", "Cosa",
}

_DEFAULT_RULES = EventRules()

_TYPE_LABELS = {
    "one_time": "Temporal",
    "daily_recurring": "Diario Recurrente",
    "permanent": "Permanente",
}


# ─── FSM States ────────────────────────────────────────────────────


class NewEventState(StatesGroup):
    select_group = State()
    event_type = State()
    name = State()
    description = State()
    multiplier = State()

    schedule_one_time = State()
    schedule_daily_hours = State()
    schedule_daily_days = State()

    rules_categories = State()
    rules_categories_options = State()
    rules_cat_multipliers = State()
    rules_time_and_letter = State()
    rules_decreasing = State()
    rules_advanced_letter = State()
    rules_scoring = State()
    rules_game_mode = State()

    confirm = State()


class DeleteEventState(StatesGroup):
    select_group = State()
    select_event = State()
    confirm = State()
    confirm_delete = State()


class EditEventState(StatesGroup):
    select_group = State()
    select_event = State()
    select_field = State()
    edit_name = State()
    edit_description = State()
    edit_multiplier = State()
    edit_type = State()
    edit_schedule_one_time = State()
    edit_schedule_daily_hours = State()
    edit_schedule_daily_days = State()
    edit_rules_categories = State()
    edit_rules_categories_options = State()
    edit_rules_time = State()
    edit_rules_decreasing = State()
    edit_rules_letter = State()
    edit_rules_scoring = State()
    confirm = State()


class ToggleEventState(StatesGroup):
    select_group = State()
    select_event = State()


class DeleteAllEventsState(StatesGroup):
    select_group = State()
    confirm = State()


# ─── Helpers ───────────────────────────────────────────────────────


def _build_summary_text(data: dict) -> str:
    """Construye el texto de resumen del estado actual del evento."""
    lines = []

    if "group_title" in data:
        lines.append(f"✅ Grupo: <b>{data['group_title']}</b>")
    if "event_type" in data:
        lines.append(
            f"✅ Tipo: <b>{_TYPE_LABELS.get(data['event_type'], data['event_type'])}</b>"
        )
    if "name" in data:
        lines.append(f"✅ Nombre: <b>{data['name']}</b>")
    if "description" in data:
        lines.append(f"✅ Descripción: <b>{data['description']}</b>")
    if "multiplier" in data:
        lines.append(f"✅ Multiplicador: <b>x{data['multiplier']}</b>")

    event_type = data.get("event_type", "one_time")

    if event_type == "one_time" and "duration_hours" in data:
        hours = data["duration_hours"]
        if hours == 1:
            dur_label = "1 hora"
        elif hours < 24:
            dur_label = f"{hours} horas"
        elif hours % 24 == 0:
            dur_label = f"{hours // 24} días"
        else:
            dur_label = f"{hours}h"
        lines.append(f"✅ Duración: <b>{dur_label}</b>")

    if event_type == "daily_recurring":
        start_h = data.get("daily_start_hour")
        start_m = data.get("daily_start_minute", 0)
        end_h = data.get("daily_end_hour")
        end_m = data.get("daily_end_minute", 0)
        if start_h is not None and end_h is not None:
            lines.append(
                f"✅ Horario: <b>{start_h:02d}:{start_m:02d}"
                f" - {end_h:02d}:{end_m:02d}</b>"
            )
        active_days = data.get("active_days", [])
        if active_days:
            day_names = {
                "mon": "L", "tue": "M", "wed": "X",
                "thu": "J", "fri": "V", "sat": "S", "sun": "D",
            }
            day_str = " ".join(day_names.get(d, d) for d in active_days)
            lines.append(f"✅ Días: <b>{day_str}</b>")

    if event_type == "permanent":
        lines.append("✅ Duración: <b>Permanente</b>")

    return "\n".join(lines)


def _build_full_summary_text(data: dict) -> str:
    """Construye el texto completo de resumen para el Paso 9."""
    lines = ["✅ <b>Resumen del Evento</b>", ""]

    lines.append(f"📌 <b>{data.get('name', 'Sin nombre')}</b>")
    lines.append(f"📝 {data.get('description', 'Sin descripción')}")

    event_type = data.get("event_type", "one_time")
    type_label = _TYPE_LABELS.get(event_type, event_type)

    if event_type == "one_time":
        hours = data.get("duration_hours", 1)
        if hours == 1:
            dur = "1 hora"
        elif hours < 24:
            dur = f"{hours} horas"
        elif hours % 24 == 0:
            dur = f"{hours // 24} días"
        else:
            dur = f"{hours}h"
        lines.append(f"📅 Tipo: <b>{type_label}</b> — {dur}")
    elif event_type == "daily_recurring":
        s_h = data.get("daily_start_hour", 0)
        s_m = data.get("daily_start_minute", 0)
        e_h = data.get("daily_end_hour", 23)
        e_m = data.get("daily_end_minute", 59)
        lines.append(
            f"📅 Tipo: <b>{type_label}</b>"
            f" — {s_h:02d}:{s_m:02d} - {e_h:02d}:{e_m:02d}"
        )
        active_days = data.get("active_days", [])
        if active_days:
            day_names = {
                "mon": "Lun", "tue": "Mar", "wed": "Mié",
                "thu": "Jue", "fri": "Vie", "sat": "Sáb", "sun": "Dom",
            }
            day_str = ", ".join(day_names.get(d, d) for d in active_days)
            lines.append(f"📅 Días: <b>{day_str}</b>")
    else:
        lines.append(f"📅 Tipo: <b>{type_label}</b>")

    lines.append(f"⚡ Multiplicador: <b>x{data.get('multiplier', 1.0)}</b>")
    lines.append("")

    rules_data = data.get("rules_data", {})
    enabled = list(rules_data.get("categories_enabled", list(_DEFAULT_RULES.categories_enabled)))
    disabled = list(rules_data.get("categories_disabled", []))
    hidden = list(rules_data.get("hidden_categories", []))
    mystery = rules_data.get("mystery_category")

    active_cats = [c for c in enabled if c not in disabled]
    if active_cats:
        lines.append(f"📋 <b>Categorías activas:</b> {', '.join(active_cats)}")
    if disabled:
        lines.append(f"🚫 <b>Sin:</b> {', '.join(disabled)}")
    if hidden:
        lines.append(f"🎭 <b>Oculta:</b> {', '.join(hidden)}")
    if mystery:
        lines.append(f"🔮 <b>Mystery:</b> {mystery}")
    lines.append("")

    time_override = rules_data.get("time_override")
    if time_override:
        lines.append(f"⏱ <b>Tiempo:</b> {time_override}s por ronda")
    else:
        lines.append("⏱ <b>Tiempo:</b> Config del grupo")

    if rules_data.get("time_decreasing"):
        dec = rules_data.get("time_decreasing_amount", 5)
        lines.append(f"📉 <b>Decreciente:</b> -{dec}s por ronda")

    forced = rules_data.get("forced_letter")
    vowel_forced = rules_data.get("vowel_forced", False)
    seq = rules_data.get("letter_sequence")

    if seq:
        lines.append(f"🔤 <b>Letra:</b> Secuencia ({', '.join(seq)})")
    elif forced:
        lines.append(f"🔤 <b>Letra:</b> {forced}")
    elif vowel_forced:
        lines.append("🔤 <b>Letra:</b> Solo vocales")
    else:
        lines.append("🔤 <b>Letra:</b> Aleatoria")

    excluded = rules_data.get("excluded_letters", [])
    if excluded:
        lines.append(f"🔇 <b>Excluidas:</b> {', '.join(excluded)}")
    lines.append("")

    # Multiplicadores por categoría
    cat_mults = rules_data.get("category_multipliers", {})
    if cat_mults:
        mults_str = ", ".join(f"{c} x{m}" for c, m in sorted(cat_mults.items()))
        lines.append(f"⚡ <b>Multiplicadores:</b> {mults_str}")
        lines.append("")

    # Modo de juego
    game_mode_parts = []
    if rules_data.get("sudden_death"):
        thresh = rules_data.get("sudden_death_threshold", 1)
        game_mode_parts.append(f"💀 Muerte súbita (≥{thresh} pts)")
    if rules_data.get("wager_enabled"):
        pct = rules_data.get("wager_max_pct", 50)
        game_mode_parts.append(f"🎲 Apuestas (máx {pct}%)")
    if rules_data.get("collaborative"):
        mx = rules_data.get("max_players")
        game_mode_parts.append(f"👥 Equipos{' (máx '+str(mx)+')' if mx else ''}")
    if rules_data.get("infinite_rounds"):
        game_mode_parts.append("♾ Rondas infinitas")
    if rules_data.get("no_stop"):
        game_mode_parts.append("🚫 Sin botón Stop")
    if rules_data.get("require_all_different"):
        game_mode_parts.append("🚫 Todas diferentes")
    if rules_data.get("min_words_required", 0) > 0:
        game_mode_parts.append(f"📝 Mínimo {rules_data['min_words_required']} palabras")
    if rules_data.get("min_word_length", 0) > 0:
        game_mode_parts.append(f"📏 Mínimo {rules_data['min_word_length']} letras")
    if rules_data.get("shared_answer_penalty", 0) < 0:
        game_mode_parts.append(f"🤝 Penalización dup: {rules_data['shared_answer_penalty']}")
    if rules_data.get("perfect_round_bonus", 0) > 0:
        game_mode_parts.append(f"⭐ Ronda perfecta: +{rules_data['perfect_round_bonus']}")
    if game_mode_parts:
        lines.append("🎮 <b>Modo de juego:</b>")
        for part in game_mode_parts:
            lines.append(f"  • {part}")
        lines.append("")

    bonuses = []
    no_dup = rules_data.get("no_duplicates_bonus", 0)
    if no_dup > 0:
        bonuses.append(f"  • Respuesta única: +{no_dup} pts")
    bonus_all = rules_data.get("bonus_all_filled", 0)
    if bonus_all > 0:
        bonuses.append(f"  • Llenar todo: +{bonus_all} pts")
    speed = rules_data.get("speed_bonus", 0)
    speed_win = rules_data.get("speed_bonus_window", 8)
    if speed > 0:
        bonuses.append(f"  • Velocidad: +{speed} pts ({speed_win}s)")
    streak = rules_data.get("streak_multiplier", 1.0)
    if streak > 1.0:
        bonuses.append(f"  • Streak: x{streak}")
    pen = rules_data.get("penalty_empty", 0)
    if pen < 0:
        bonuses.append(f"  • Pen vacío: {pen} pts")
    double_last = rules_data.get("double_points_last_round", False)
    if double_last:
        bonuses.append("  • Doble última ronda: Sí")
    comeback = rules_data.get("comeback_bonus", 0)
    if comeback > 0:
        bonuses.append(f"  • Comeback: +{comeback} pts")

    if bonuses:
        lines.append("⭐ <b>Bonificaciones:</b>")
        lines.extend(bonuses)
    else:
        lines.append("⭐ <b>Bonificaciones:</b> Ninguna")
    lines.append("")

    if event_type == "one_time":
        starts = data.get("starts_at")
        ends = data.get("ends_at")
        if starts and ends:
            lines.append(f"📅 Inicio: {starts}")
            lines.append(f"📅 Fin: {ends}")
    elif event_type == "permanent":
        lines.append("📅 <b>Activo hasta que se desactive manualmente</b>")

    return "\n".join(lines)


async def _load_event_to_state(
    event_id: int, state: FSMContext
) -> dict | None:
    """Carga un evento existente al FSM state para edición."""
    async with async_session_factory() as session:
        from sqlalchemy import select as sa_select

        stmt = sa_select(SeasonalEvent).where(SeasonalEvent.id == event_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            return None

    rules = EventRules.from_json(event.rules)
    rules_data = {
        "categories_enabled": list(rules.categories_enabled),
        "categories_disabled": list(rules.categories_disabled),
        "hidden_categories": list(rules.hidden_categories),
        "mystery_category": rules.mystery_category,
        "time_override": rules.time_override,
        "time_decreasing": rules.time_decreasing,
        "time_decreasing_amount": rules.time_decreasing_amount,
        "forced_letter": rules.forced_letter,
        "vowel_forced": rules.vowel_forced,
        "no_duplicates_bonus": rules.no_duplicates_bonus,
        "bonus_all_filled": rules.bonus_all_filled,
        "speed_bonus": rules.speed_bonus,
        "speed_bonus_window": rules.speed_bonus_window,
        "streak_multiplier": rules.streak_multiplier,
        "penalty_empty": rules.penalty_empty,
        "comeback_bonus": rules.comeback_bonus,
        "double_points_last_round": rules.double_points_last_round,
        "answer_reveal": rules.answer_reveal,
    }

    event_data = {
        "id": event.id,
        "name": event.name,
        "description": event.description or "",
        "event_type": event.event_type,
        "multiplier": event.multiplier,
        "group_chat_id": event.group_chat_id,
        "group_title": "",
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "daily_start_hour": event.daily_start_hour,
        "daily_start_minute": event.daily_start_minute,
        "daily_end_hour": event.daily_end_hour,
        "daily_end_minute": event.daily_end_minute,
        "active_days": (
            json.loads(event.active_days)
            if event.active_days
            else ["mon", "tue", "wed", "thu", "fri"]
        ),
        "rules_data": rules_data,
    }

    await state.update_data(event_data=event_data)
    return event_data


def _build_edit_summary(ed: dict) -> str:
    """Resumen del evento que se está editando."""
    lines = [
        f"✏️ <b>Editando:</b> <b>{ed.get('name', '')}</b>",
        f"📝 {ed.get('description', '')[:80]}",
        f"📅 Tipo: <b>{_TYPE_LABELS.get(ed.get('event_type', 'one_time'), '')}</b>",
        f"⚡ x{ed.get('multiplier', 1.0)}",
    ]
    return "\n".join(lines)


def event_type_keyboard_for_edit() -> InlineKeyboardMarkup:
    """Teclado de tipo de evento para edición (prefix ee:)"""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Temporal", callback_data="ee:type:one_time")],
            [InlineKeyboardButton(text="🔁 Diario Recurrente", callback_data="ee:type:daily_recurring")],
            [InlineKeyboardButton(text="♾ Permanente", callback_data="ee:type:permanent")],
        ]
    )


# ─── /newevent ─────────────────────────────────────────────────────


@event_creator_router.message(F.text.startswith("/newevent"))
async def cmd_new_event(message: Message, bot: Bot, state: FSMContext) -> None:
    if not message.chat or message.chat.type != "private":
        await message.reply("⚠️ Usa este comando en tu chat privado con el bot.")
        return

    user_id = message.from_user.id if message.from_user else 0
    groups = await event_service.get_user_admin_groups(user_id, bot)

    if not groups:
        await message.reply(
            "❌ No eres admin de ningún grupo donde el bot esté presente.\n\n"
            "Añade el bot a un grupo y pide que te hagan admin para crear eventos."
        )
        return

    await state.set_state(NewEventState.select_group)
    await state.update_data(groups=groups)
    await message.reply(
        "🎉 <b>Crear Evento de Temporada</b>\n\n"
        "Selecciona el grupo donde quieres crear el evento:",
        parse_mode="HTML",
        reply_markup=groups_keyboard(groups, prefix="ne"),
    )


# ─── Paso 0 → 1: Selección de grupo ───────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:group:"))
async def ne_select_group(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        chat_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    data = await state.get_data()
    groups = data.get("groups", [])
    selected = next((g for g in groups if g["chat_id"] == chat_id), None)
    if not selected:
        await callback.answer("❌ Grupo no encontrado.", show_alert=True)
        return

    await state.update_data(group_chat_id=chat_id, group_title=selected["chat_title"])
    await state.set_state(NewEventState.event_type)
    await callback.message.edit_text(
        "📅 <b>Tipo de Evento</b>\n\n"
        "🔄 <b>Temporal</b> — Dura X horas/días desde ahora\n"
        "🔁 <b>Diario Recurrente</b> — Activo todos los días en horario específico\n"
        "♾ <b>Permanente</b> — Activo hasta que se desactive manualmente\n\n"
        "<i>Selecciona el tipo:</i>",
        parse_mode="HTML",
        reply_markup=event_type_keyboard(),
    )
    await callback.answer()


# ─── Paso 1 → 2: Tipo de evento ──────────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:type:"))
async def ne_select_type(callback: CallbackQuery, state: FSMContext) -> None:
    event_type = callback.data.split(":")[2]
    if event_type not in {"one_time", "daily_recurring", "permanent"}:
        await callback.answer("❌ Tipo inválido.", show_alert=True)
        return

    await state.update_data(event_type=event_type)
    data = await state.get_data()
    await state.set_state(NewEventState.name)

    summary = _build_summary_text(data)
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 1/8: <b>¿Cómo se llamará el evento?</b>\n\n"
        "Ejemplos: Copa Navideña, Torneo de Verano, Noche de Stop\n\n"
        "<i>Escribe el nombre (máx. 64 caracteres):</i>",
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Paso 2: Nombre (texto) ──────────────────────────────────────


@event_creator_router.message(NewEventState.name)
async def ne_process_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 3:
        await message.reply("❌ Mínimo 3 caracteres. Intenta de nuevo:")
        return
    if len(name) > 64:
        await message.reply("❌ Máximo 64 caracteres. Intenta de nuevo:")
        return

    data = await state.get_data()
    async with async_session_factory() as session:
        from sqlalchemy import and_, select

        stmt = select(SeasonalEvent).where(
            and_(
                SeasonalEvent.name == name,
                SeasonalEvent.group_chat_id == data["group_chat_id"],
            )
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none():
            await message.reply(
                "❌ Ya existe un evento con ese nombre en este grupo. Elige otro:"
            )
            return

    await state.update_data(name=name)
    data = await state.get_data()
    await state.set_state(NewEventState.description)

    summary = _build_summary_text(data)
    await message.reply(
        f"{summary}\n\n"
        "Paso 2/8: <b>Escribe una descripción del evento</b>\n\n"
        "<i>(máx. 500 caracteres):</i>",
        parse_mode="HTML",
    )


# ─── Paso 3: Descripción (texto) ─────────────────────────────────


@event_creator_router.message(NewEventState.description)
async def ne_process_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if len(desc) < 5:
        await message.reply("❌ Mínimo 5 caracteres:")
        return
    if len(desc) > 500:
        await message.reply("❌ Máximo 500 caracteres:")
        return

    await state.update_data(description=desc)
    data = await state.get_data()
    await state.set_state(NewEventState.multiplier)

    summary = _build_summary_text(data)
    await message.reply(
        f"{summary}\n\n"
        "Paso 3/8: <b>¿Cuánto multiplicará el XP?</b>\n\n"
        "Selecciona:",
        parse_mode="HTML",
        reply_markup=multiplier_keyboard(prefix="ne"),
    )


# ─── Paso 4: Multiplicador ───────────────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:mult:"))
async def ne_process_multiplier(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        multiplier = float(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    if multiplier < 1.0 or multiplier > 10.0:
        await callback.answer("❌ Entre 1.0 y 10.0.", show_alert=True)
        return

    await state.update_data(multiplier=multiplier)
    data = await state.get_data()
    event_type = data.get("event_type", "one_time")
    summary = _build_summary_text(data)

    if event_type == "one_time":
        await state.set_state(NewEventState.schedule_one_time)
        await callback.message.edit_text(
            f"{summary}\n\n"
            "Paso 4/8: <b>¿Cuánto durará el evento?</b>",
            parse_mode="HTML",
            reply_markup=duration_keyboard(prefix="ne"),
        )
    elif event_type == "daily_recurring":
        await state.set_state(NewEventState.schedule_daily_hours)
        await callback.message.edit_text(
            f"{summary}\n\n"
            "Paso 4/8: <b>¿A qué hora inicia el evento cada día?</b>",
            parse_mode="HTML",
            reply_markup=daily_start_keyboard(prefix="ne"),
        )
    else:
        rules = list(_DEFAULT_RULES.categories_enabled)
        await state.update_data(rules_data={"categories_enabled": rules})
        await state.set_state(NewEventState.rules_categories)
        summary2 = _build_summary_text(await state.get_data())
        await callback.message.edit_text(
            f"{summary2}\n\n"
            "Paso 5/8: <b>Selecciona las categorías activas:</b>\n\n"
            "<i>Las desactivadas no se puntuarán.</i>",
            parse_mode="HTML",
            reply_markup=categories_toggle_keyboard(rules, prefix="ne"),
        )
    await callback.answer()


# ─── Paso 5a: Duración (one_time) ────────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:dur:"))
async def ne_process_duration(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        hours = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    if hours < 1 or hours > 168:
        await callback.answer("❌ Entre 1 y 168 horas.", show_alert=True)
        return

    starts_at = utcnow()
    ends_at = starts_at + timedelta(hours=hours)

    await state.update_data(
        duration_hours=hours,
        starts_at=starts_at.strftime("%d/%m/%Y %H:%M UTC"),
        ends_at=ends_at.strftime("%d/%m/%Y %H:%M UTC"),
        _starts_at_iso=starts_at.isoformat(),
        _ends_at_iso=ends_at.isoformat(),
    )

    rules = list(_DEFAULT_RULES.categories_enabled)
    await state.update_data(rules_data={"categories_enabled": rules})
    await state.set_state(NewEventState.rules_categories)

    data = await state.get_data()
    summary = _build_summary_text(data)
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 5/8: <b>Selecciona las categorías activas:</b>\n\n"
        "<i>Las desactivadas no se puntuarán.</i>",
        parse_mode="HTML",
        reply_markup=categories_toggle_keyboard(rules, prefix="ne"),
    )
    await callback.answer()


# ─── Paso 5b-1: Hora inicio diaria ───────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:dstart:"))
async def ne_daily_start(callback: CallbackQuery, state: FSMContext) -> None:
    time_str = callback.data.split(":", 2)[2]
    try:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        await callback.answer("❌ Hora inválida.", show_alert=True)
        return

    await state.update_data(daily_start_hour=hour, daily_start_minute=minute)
    summary = _build_summary_text(await state.get_data())
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 4/8: <b>¿A qué hora termina el evento cada día?</b>",
        parse_mode="HTML",
        reply_markup=daily_end_keyboard(prefix="ne"),
    )
    await callback.answer()


# ─── Paso 5b-2: Hora fin diaria ──────────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:dend:"))
async def ne_daily_end(callback: CallbackQuery, state: FSMContext) -> None:
    time_str = callback.data.split(":", 2)[2]
    try:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        await callback.answer("❌ Hora inválida.", show_alert=True)
        return

    await state.update_data(daily_end_hour=hour, daily_end_minute=minute)
    default_days = ["mon", "tue", "wed", "thu", "fri"]
    await state.update_data(active_days=default_days)
    await state.set_state(NewEventState.schedule_daily_days)

    summary = _build_summary_text(await state.get_data())
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 4/8: <b>¿Qué días está activo?</b>\n\n"
        "(Toggle: ✅ = activo, — = inactivo)",
        parse_mode="HTML",
        reply_markup=days_of_week_keyboard(default_days, prefix="ne"),
    )
    await callback.answer()


# ─── Paso 5b-3: Días de semana (toggle) ──────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:day:"))
async def ne_toggle_day(callback: CallbackQuery, state: FSMContext) -> None:
    day = callback.data.split(":")[2]
    if day not in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
        await callback.answer("❌ Día inválido.", show_alert=True)
        return

    data = await state.get_data()
    active_days = list(data.get("active_days", ["mon", "tue", "wed", "thu", "fri"]))

    if day in active_days:
        active_days.remove(day)
    else:
        active_days.append(day)

    await state.update_data(active_days=active_days)
    summary = _build_summary_text(await state.get_data())
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 4/8: <b>¿Qué días está activo?</b>\n\n"
        "(Toggle: ✅ = activo, — = inactivo)",
        parse_mode="HTML",
        reply_markup=days_of_week_keyboard(active_days, prefix="ne"),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:days_confirm")
async def ne_confirm_days(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    active_days = data.get("active_days", [])
    if not active_days:
        await callback.answer("❌ Selecciona al menos un día.", show_alert=True)
        return

    rules = list(_DEFAULT_RULES.categories_enabled)
    await state.update_data(rules_data={"categories_enabled": rules})
    await state.set_state(NewEventState.rules_categories)

    summary = _build_summary_text(await state.get_data())
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Paso 5/8: <b>Selecciona las categorías activas:</b>\n\n"
        "<i>Las desactivadas no se puntuarán.</i>",
        parse_mode="HTML",
        reply_markup=categories_toggle_keyboard(rules, prefix="ne"),
    )
    await callback.answer()


# ─── Paso 6: Categorías (toggle) ─────────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:cat:"))
async def ne_toggle_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    if cat not in _VALID_CATEGORIES:
        await callback.answer("❌ Categoría inválida.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    enabled = list(
        rules_data.get("categories_enabled", list(_DEFAULT_RULES.categories_enabled))
    )

    if cat in enabled:
        enabled.remove(cat)
    else:
        enabled.append(cat)

    rules_data["categories_enabled"] = enabled
    await state.update_data(rules_data=rules_data)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=categories_toggle_keyboard(enabled, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:cat_all")
async def ne_select_all_categories(callback: CallbackQuery, state: FSMContext) -> None:
    all_cats = list(_DEFAULT_RULES.categories_enabled)
    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    rules_data["categories_enabled"] = all_cats
    await state.update_data(rules_data=rules_data)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=categories_toggle_keyboard(all_cats, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:rules_next")
async def ne_rules_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    enabled = rules_data.get("categories_enabled", list(_DEFAULT_RULES.categories_enabled))

    if not enabled:
        await callback.answer("❌ Selecciona al menos una categoría.", show_alert=True)
        return

    hidden = rules_data.get("hidden_categories", [])
    mystery = rules_data.get("mystery_category")

    await state.set_state(NewEventState.rules_categories_options)
    await callback.message.edit_text(
        "📋 <b>Categorías avanzadas</b>\n\n"
        "Opcional: selecciona categorías ocultas o mystery.\n"
        "Si no necesitas, pulsa Siguiente.",
        parse_mode="HTML",
        reply_markup=categories_options_keyboard(hidden, mystery, prefix="ne"),
    )
    await callback.answer()


# ─── Paso 6+: Categorías opciones avanzadas ───────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:cat_hidden:"))
async def ne_toggle_hidden(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    if cat not in _VALID_CATEGORIES:
        await callback.answer("❌ Categoría inválida.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    hidden = list(rules_data.get("hidden_categories", []))

    if cat in hidden:
        hidden.remove(cat)
    else:
        hidden.append(cat)

    rules_data["hidden_categories"] = hidden
    await state.update_data(rules_data=rules_data)

    mystery = rules_data.get("mystery_category")
    try:
        await callback.message.edit_reply_markup(
            reply_markup=categories_options_keyboard(hidden, mystery, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ne:cat_mystery:"))
async def ne_toggle_mystery(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    if cat not in _VALID_CATEGORIES:
        await callback.answer("❌ Categoría inválida.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    if rules_data.get("mystery_category") == cat:
        rules_data["mystery_category"] = None
    else:
        rules_data["mystery_category"] = cat

    await state.update_data(rules_data=rules_data)

    hidden = rules_data.get("hidden_categories", [])
    mystery = rules_data.get("mystery_category")
    try:
        await callback.message.edit_reply_markup(
            reply_markup=categories_options_keyboard(hidden, mystery, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:options_next")
async def ne_options_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    cat_mults = rules_data.get("category_multipliers", {})
    await state.set_state(NewEventState.rules_cat_multipliers)
    await callback.message.edit_text(
        "⚡ <b>Multiplicadores por Categoría</b>\n\n"
        "Paso 6/10: <b>Asigna multiplicadores extra</b> (opcional)\n"
        "Pulsa cada categoría para cambiar su valor:\n"
        "OFF → x1.5 → x2 → x3 → x5\n\n"
        "<i>Si no necesitas, pulsa Siguiente.</i>",
        parse_mode="HTML",
        reply_markup=category_multipliers_keyboard(cat_mults, prefix="ne"),
    )
    await callback.answer()


# ─── Paso 6c: Multiplicadores por categoría ──────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:catmult:"))
async def ne_toggle_cat_mult(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    if cat not in _VALID_CATEGORIES:
        await callback.answer("❌ Categoría inválida.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    cat_mults = dict(rules_data.get("category_multipliers", {}))

    current = cat_mults.get(cat)
    cycle = [None, 1.5, 2.0, 3.0, 5.0]
    try:
        idx = cycle.index(current)
        next_val = cycle[(idx + 1) % len(cycle)]
    except ValueError:
        next_val = 1.5

    if next_val is None:
        cat_mults.pop(cat, None)
    else:
        cat_mults[cat] = next_val

    rules_data["category_multipliers"] = cat_mults
    await state.update_data(rules_data=rules_data)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=category_multipliers_keyboard(cat_mults, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:catmult_next")
async def ne_catmult_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    await state.set_state(NewEventState.rules_time_and_letter)
    await callback.message.edit_text(
        "⏱ <b>Tiempo y Letra</b>\n\n"
        "Paso 7/10: <b>Tiempo por ronda:</b>",
        parse_mode="HTML",
        reply_markup=round_time_keyboard(
            rules_data.get("time_override"), prefix="ne"
        ),
    )
    await callback.answer()


# ─── Paso 7: Tiempo por ronda ────────────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:time:"))
async def ne_select_time(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        time_val = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    if time_val == 0:
        rules_data.pop("time_override", None)
    else:
        rules_data["time_override"] = time_val

    await state.update_data(rules_data=rules_data)
    await state.set_state(NewEventState.rules_decreasing)

    dec_amount = rules_data.get("time_decreasing_amount", 5)
    time_label = f"{time_val}s" if time_val > 0 else "Config grupo"
    await callback.message.edit_text(
        f"⏱ Tiempo: <b>{time_label}</b>\n\n"
        "¿Quieres tiempo decreciente?\n\n"
        "<i>El tiempo disminuye cada ronda.</i>",
        parse_mode="HTML",
        reply_markup=decreasing_time_keyboard(dec_amount, prefix="ne"),
    )
    await callback.answer()


# ─── Paso 7: Tiempo decreciente ──────────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:dec:"))
async def ne_select_decreasing(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        amount = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    rules_data["time_decreasing"] = True
    rules_data["time_decreasing_amount"] = amount
    await state.update_data(rules_data=rules_data)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=decreasing_time_keyboard(amount, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:dec_confirm")
async def ne_confirm_decreasing(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    if "time_decreasing" not in rules_data:
        rules_data["time_decreasing"] = False
    await state.update_data(rules_data=rules_data)

    await callback.message.edit_text(
        "🔤 <b>Letra para el evento:</b>",
        parse_mode="HTML",
        reply_markup=forced_letter_keyboard(prefix="ne"),
    )
    await callback.answer()


# ─── Paso 7: Selección de letra ──────────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:letter:"))
async def ne_select_letter(callback: CallbackQuery, state: FSMContext) -> None:
    letter = callback.data.split(":")[2]
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    if letter == "RANDOM":
        rules_data.pop("forced_letter", None)
        rules_data.pop("letter_sequence", None)
        rules_data["vowel_forced"] = False
    elif letter == "EXCLUDE_VOWELS":
        rules_data.pop("forced_letter", None)
        rules_data.pop("letter_sequence", None)
        rules_data["vowel_forced"] = True
    elif letter == "SEQUENCE":
        rules_data.pop("forced_letter", None)
        rules_data["letter_sequence"] = None
        rules_data["vowel_forced"] = False
    else:
        rules_data["forced_letter"] = letter
        rules_data.pop("letter_sequence", None)
        rules_data["vowel_forced"] = False

    await state.update_data(rules_data=rules_data)

    excluded = rules_data.get("excluded_letters", [])
    await state.set_state(NewEventState.rules_advanced_letter)
    await callback.message.edit_text(
        "🔇 <b>Letras Excluidas</b>\n\n"
        "Paso 8/10: <b>Selecciona letras que NO pueden usarse</b> (opcional)\n"
        "Pulsa cada letra para excluirla.\n\n"
        "<i>Si no necesitas, pulsa Siguiente.</i>",
        parse_mode="HTML",
        reply_markup=excluded_letters_keyboard(excluded, prefix="ne"),
    )
    await callback.answer()


# ─── Paso 7d: Letras excluidas ──────────────────────────────────


@event_creator_router.callback_query(F.data.startswith("ne:excl:"))
async def ne_toggle_excluded(callback: CallbackQuery, state: FSMContext) -> None:
    letter = callback.data.split(":")[2]
    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    excluded = list(rules_data.get("excluded_letters", []))

    if letter in excluded:
        excluded.remove(letter)
    else:
        excluded.append(letter)

    rules_data["excluded_letters"] = excluded
    await state.update_data(rules_data=rules_data)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=excluded_letters_keyboard(excluded, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:excl_next")
async def ne_excl_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    seq = rules_data.get("letter_sequence")

    await state.set_state(NewEventState.rules_scoring)
    await callback.message.edit_text(
        "⭐ <b>Bonificaciones y Penalizaciones</b>\n\n"
        "Paso 9/10: <b>Configura los bonos (pulsa para rotar valores):</b>",
        parse_mode="HTML",
        reply_markup=bonuses_keyboard(rules_data, prefix="ne"),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:letter_seq")
async def ne_letter_seq(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewEventState.rules_advanced_letter)
    await state.update_data(_awaiting_seq=True)
    await callback.message.edit_text(
        "📜 <b>Secuencia de Letras</b>\n\n"
        "Escribe las letras separadas por comas, ej:\n"
        "<code>M,R,S,P</code>\n\n"
        "<i>O escribe /skip para omitir:</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@event_creator_router.message(NewEventState.rules_advanced_letter)
async def ne_process_sequence(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    data = await state.get_data()
    if not data.get("_awaiting_seq"):
        return

    rules_data = data.get("rules_data", {})

    if text == "/skip":
        rules_data.pop("letter_sequence", None)
    else:
        letters = [l.strip().upper() for l in text.split(",")]
        valid = []
        for l in letters:
            if len(l) == 1 and l in "ABCDEFGHIJKLMNOPQRSTUVWXYZÑ":
                valid.append(l)
        if valid:
            rules_data["letter_sequence"] = valid
        else:
            await message.reply("❌ Letras inválidas. Usa formato: M,R,S,P")
            return

    await state.update_data(rules_data=rules_data, _awaiting_seq=False)
    excluded = rules_data.get("excluded_letters", [])
    await state.set_state(NewEventState.rules_scoring)
    await message.reply(
        "✅ Secuencia guardada. Continuando con bonificaciones...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
    )
    await message.bot.send_message(
        message.chat.id,
        "⭐ <b>Bonificaciones y Penalizaciones</b>\n\n"
        "Paso 9/10: <b>Configura los bonos (pulsa para rotar valores):</b>",
        parse_mode="HTML",
        reply_markup=bonuses_keyboard(rules_data, prefix="ne"),
    )


# ─── Paso 8: Bonificaciones (toggle) ─────────────────────────────


_BONUS_CYCLES = {
    "no_duplicates_bonus": [0, 15, 25, 50, 100],
    "bonus_all_filled": [0, 25, 50, 75, 100],
    "speed_bonus": [0, 10, 20, 30, 50],
    "penalty_empty": [0, -5, -10, -15, -20],
    "streak_multiplier": [1.0, 1.25, 1.5, 2.0],
    "comeback_bonus": [0, 10, 20, 30],
}


@event_creator_router.callback_query(F.data.startswith("ne:bonus:"))
async def ne_toggle_bonus(callback: CallbackQuery, state: FSMContext) -> None:
    bonus_key = callback.data.split(":")[2]
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    if bonus_key in _BONUS_CYCLES:
        cycle = _BONUS_CYCLES[bonus_key]
        current = rules_data.get(bonus_key, cycle[0])
        try:
            idx = cycle.index(current)
            rules_data[bonus_key] = cycle[(idx + 1) % len(cycle)]
        except ValueError:
            rules_data[bonus_key] = cycle[0]
    elif bonus_key == "double_points_last_round":
        rules_data["double_points_last_round"] = not rules_data.get(
            "double_points_last_round", False
        )
    elif bonus_key == "answer_reveal":
        rules_data["answer_reveal"] = not rules_data.get("answer_reveal", False)
    else:
        await callback.answer("❌ Bonus desconocido.", show_alert=True)
        return

    await state.update_data(rules_data=rules_data)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=bonuses_keyboard(rules_data, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:bonus_next")
async def ne_bonus_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    rules_data = data.get("rules_data", {})

    await state.set_state(NewEventState.rules_game_mode)
    await callback.message.edit_text(
        "🎮 <b>Modo de Juego</b>\n\n"
        "Paso 10/10: <b>Configura reglas avanzadas</b> (opcional)\n"
        "Pulsa para activar/desactivar o cambiar valores.\n\n"
        "<i>Si no necesitas, pulsa Siguiente.</i>",
        parse_mode="HTML",
        reply_markup=game_mode_keyboard(rules_data, prefix="ne"),
    )
    await callback.answer()


# ─── Paso 8b: Modo de juego ──────────────────────────────────────

_GAME_MODE_CYCLES = {
    "min_words_required": [0, 2, 3, 4, 5, 6],
    "min_word_length": [0, 2, 3, 4, 5, 6],
    "shared_answer_penalty": [0, -5, -10, -15, -20],
    "perfect_round_bonus": [0, 25, 50, 75, 100],
}

_CYCLES_MAP = {
    "gm_cycle_minwords": "min_words_required",
    "gm_cycle_minlen": "min_word_length",
    "gm_cycle_shared": "shared_answer_penalty",
    "gm_cycle_perfect": "perfect_round_bonus",
}


@event_creator_router.callback_query(F.data.startswith("ne:gm_toggle_"))
async def ne_toggle_gm_flag(callback: CallbackQuery, state: FSMContext) -> None:
    flag = callback.data.split("ne:gm_toggle_")[1]
    FIELD_MAP = {
        "sudden": "sudden_death",
        "wager": "wager_enabled",
        "collab": "collaborative",
        "infinite": "infinite_rounds",
        "nostop": "no_stop",
        "alldiff": "require_all_different",
    }
    field = FIELD_MAP.get(flag)
    if not field:
        await callback.answer("❌ Opción desconocida.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    current = rules_data.get(field, False)
    rules_data[field] = not current
    await state.update_data(rules_data=rules_data)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=game_mode_keyboard(rules_data, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ne:gm_cycle_"))
async def ne_cycle_gm_value(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[1]
    field = _CYCLES_MAP.get(key)
    if not field:
        await callback.answer("❌ Opción desconocida.", show_alert=True)
        return

    data = await state.get_data()
    rules_data = data.get("rules_data", {})
    cycle = _GAME_MODE_CYCLES[field]
    current = rules_data.get(field, cycle[0])
    try:
        idx = cycle.index(current)
        rules_data[field] = cycle[(idx + 1) % len(cycle)]
    except ValueError:
        rules_data[field] = cycle[0]

    await state.update_data(rules_data=rules_data)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=game_mode_keyboard(rules_data, prefix="ne")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:gm_next")
async def ne_gm_next(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewEventState.confirm)
    data = await state.get_data()
    summary = _build_full_summary_text(data)

    await callback.message.edit_text(
        summary,
        parse_mode="HTML",
        reply_markup=confirm_event_keyboard(prefix="ne"),
    )
    await callback.answer()


# ─── Paso 9: Confirmación ────────────────────────────────────────


@event_creator_router.callback_query(F.data == "ne:confirm")
async def ne_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    event_type = data.get("event_type", "one_time")

    rules_data = data.get("rules_data", {})
    event_rules = EventRules(
        categories_enabled=rules_data.get(
            "categories_enabled", list(_DEFAULT_RULES.categories_enabled)
        ),
        categories_disabled=rules_data.get("categories_disabled", []),
        category_multipliers=rules_data.get("category_multipliers", {}),
        hidden_categories=rules_data.get("hidden_categories", []),
        mystery_category=rules_data.get("mystery_category"),
        time_override=rules_data.get("time_override"),
        time_decreasing=rules_data.get("time_decreasing", False),
        time_decreasing_amount=rules_data.get("time_decreasing_amount", 5),
        forced_letter=rules_data.get("forced_letter"),
        vowel_forced=rules_data.get("vowel_forced", False),
        letter_sequence=rules_data.get("letter_sequence"),
        excluded_letters=rules_data.get("excluded_letters", []),
        no_duplicates_bonus=rules_data.get("no_duplicates_bonus", 0),
        bonus_all_filled=rules_data.get("bonus_all_filled", 0),
        speed_bonus=rules_data.get("speed_bonus", 0),
        speed_bonus_window=rules_data.get("speed_bonus_window", 8),
        streak_multiplier=rules_data.get("streak_multiplier", 1.0),
        penalty_empty=rules_data.get("penalty_empty", 0),
        comeback_bonus=rules_data.get("comeback_bonus", 0),
        double_points_last_round=rules_data.get("double_points_last_round", False),
        answer_reveal=rules_data.get("answer_reveal", False),
        # Nuevos: modo de juego
        sudden_death=rules_data.get("sudden_death", False),
        sudden_death_threshold=rules_data.get("sudden_death_threshold", 1),
        wager_enabled=rules_data.get("wager_enabled", False),
        wager_max_pct=rules_data.get("wager_max_pct", 50),
        collaborative=rules_data.get("collaborative", False),
        max_players=rules_data.get("max_players"),
        infinite_rounds=rules_data.get("infinite_rounds", False),
        no_stop=rules_data.get("no_stop", False),
        require_all_different=rules_data.get("require_all_different", False),
        min_words_required=rules_data.get("min_words_required", 0),
        min_word_length=rules_data.get("min_word_length", 0),
        shared_answer_penalty=rules_data.get("shared_answer_penalty", 0),
        perfect_round_bonus=rules_data.get("perfect_round_bonus", 0),
    )
    rules_json = event_rules.to_json()

    starts_at = None
    ends_at = None
    if event_type == "one_time":
        starts_str = data.get("_starts_at_iso")
        ends_str = data.get("_ends_at_iso")
        if starts_str and ends_str:
            starts_at = datetime.fromisoformat(starts_str)
            ends_at = datetime.fromisoformat(ends_str)

    event_kwargs: dict = {
        "group_chat_id": data["group_chat_id"],
        "name": data["name"],
        "description": data.get("description", ""),
        "event_type": event_type,
        "multiplier": data.get("multiplier", 1.0),
        "starts_at": starts_at,
        "ends_at": ends_at,
        "active": True,
        "rules": rules_json,
        "timezone": "America/Argentina/Buenos_Aires",
    }

    if event_type == "daily_recurring":
        event_kwargs["daily_start_hour"] = data.get("daily_start_hour", 0)
        event_kwargs["daily_start_minute"] = data.get("daily_start_minute", 0)
        event_kwargs["daily_end_hour"] = data.get("daily_end_hour", 23)
        event_kwargs["daily_end_minute"] = data.get("daily_end_minute", 59)
        event_kwargs["active_days"] = json.dumps(
            data.get("active_days", ["mon", "tue", "wed", "thu", "fri"])
        )

    async with async_session_factory() as session:
        event = SeasonalEvent(**event_kwargs)
        session.add(event)
        await session.commit()

    await state.clear()
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>¡Evento creado!</b>",
        parse_mode="HTML",
    )
    try:
        await callback.answer("🎉 Evento creado", show_alert=True)
    except TelegramBadRequest:
        pass

    try:
        if event_type == "one_time":
            notification = (
                "🎉 <b>¡Nuevo Evento de Temporada!</b>\n\n"
                f"📌 <b>{data['name']}</b>\n"
                f"📝 {data.get('description', '')}\n"
                f"⚡ Multiplicador: <b>x{data.get('multiplier', 1.0)} XP</b>\n"
                f"⏱ Termina: {data.get('ends_at', '')}\n\n"
                "<i>¡Juega Stop y gana más experiencia!</i>"
            )
        elif event_type == "daily_recurring":
            s_h = data.get("daily_start_hour", 0)
            s_m = data.get("daily_start_minute", 0)
            e_h = data.get("daily_end_hour", 23)
            e_m = data.get("daily_end_minute", 59)
            notification = (
                "🎉 <b>¡Nuevo Evento de Temporada!</b>\n\n"
                f"📌 <b>{data['name']}</b>\n"
                f"📝 {data.get('description', '')}\n"
                f"⚡ Multiplicador: <b>x{data.get('multiplier', 1.0)} XP</b>\n"
                f"⏰ Horario: {s_h:02d}:{s_m:02d} - {e_h:02d}:{e_m:02d}\n\n"
                "<i>¡Juega Stop y gana más experiencia!</i>"
            )
        else:
            notification = (
                "🎉 <b>¡Nuevo Evento de Temporada!</b>\n\n"
                f"📌 <b>{data['name']}</b>\n"
                f"📝 {data.get('description', '')}\n"
                f"⚡ Multiplicador: <b>x{data.get('multiplier', 1.0)} XP</b>\n\n"
                "<i>¡Juega Stop y gana más experiencia!</i>"
            )
        await bot.send_message(
            data["group_chat_id"], notification, parse_mode="HTML"
        )
    except Exception:
        logger.exception(
            "Error notificando grupo %s sobre nuevo evento",
            data["group_chat_id"],
        )


@event_creator_router.callback_query(F.data == "ne:edit")
async def ne_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewEventState.name)
    data = await state.get_data()
    summary = _build_summary_text(data)
    await callback.message.edit_text(
        f"{summary}\n\n"
        "<b>Edita el nombre del evento:</b>\n\n"
        "<i>Escribe el nuevo nombre (máx. 64 caracteres):</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "ne:cancel")
async def ne_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Creación cancelada.</b>", parse_mode="HTML"
    )
    await callback.answer()


# ─── /deleteevent ──────────────────────────────────────────────────


@event_creator_router.message(F.text.startswith("/deleteevent"))
async def cmd_delete_event(message: Message, bot: Bot, state: FSMContext) -> None:
    if not message.chat or message.chat.type != "private":
        await message.reply("⚠️ Usa este comando en tu chat privado con el bot.")
        return

    user_id = message.from_user.id if message.from_user else 0
    groups = await event_service.get_groups_with_active_events(user_id, bot)

    if not groups:
        await message.reply("📭 No hay eventos activos en tus grupos.")
        return

    await state.set_state(DeleteEventState.select_group)
    await state.update_data(groups=groups)
    await message.reply(
        "🗑 <b>Borrar Evento</b>\n\nSelecciona el grupo:",
        parse_mode="HTML",
        reply_markup=groups_keyboard(groups, prefix="delevent"),
    )


@event_creator_router.callback_query(F.data.startswith("delevent:group:"))
async def de_select_group(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        chat_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌", show_alert=True)
        return

    data = await state.get_data()
    groups = data.get("groups", [])
    selected = next((g for g in groups if g["chat_id"] == chat_id), None)
    if not selected:
        await callback.answer("❌", show_alert=True)
        return

    await state.update_data(group_chat_id=chat_id)
    await state.set_state(DeleteEventState.select_event)
    await callback.message.edit_text(
        f"📌 <b>{selected['chat_title']}</b>\n\nSelecciona el evento a borrar:",
        parse_mode="HTML",
        reply_markup=events_list_keyboard(selected["events"], prefix="delevent"),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("delevent:event:"))
async def de_select_event(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        event_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌", show_alert=True)
        return

    data = await state.get_data()
    groups = data.get("groups", [])
    group_chat_id = data.get("group_chat_id")
    group = next((g for g in groups if g["chat_id"] == group_chat_id), None)
    ev = next(
        (e for g in groups for e in g.get("events", []) if e["id"] == event_id),
        None,
    )
    ev_name = ev["name"] if ev else "Evento"

    await state.update_data(event_id=event_id)
    await state.set_state(DeleteEventState.confirm)
    await callback.message.edit_text(
        f"⚠️ <b>¿Qué quieres hacer con \"{ev_name}\"?</b>\n\n"
        "🛑 <b>Desactivar</b> — El evento se pausa. Se puede reactivar con /toggleevent\n"
        "🗑 <b>Eliminar</b> — Se borra permanentemente. No se puede recuperar.",
        parse_mode="HTML",
        reply_markup=delete_action_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "delevent:action:deactivate")
async def de_confirm_deactivate(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    event_id = data.get("event_id")
    group_chat_id = data.get("group_chat_id")

    success = await event_service.deactivate_event(event_id)
    if not success:
        await callback.answer("❌ Evento no encontrado.", show_alert=True)
        await state.clear()
        return

    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Evento desactivado.</b>\n\n"
        "Puedes reactivarlo más tarde con /toggleevent.",
        parse_mode="HTML",
    )
    try:
        await callback.answer("✅ Desactivado", show_alert=True)
    except TelegramBadRequest:
        pass

    try:
        await bot.send_message(
            group_chat_id,
            "⏸ <b>Un evento de temporada ha sido desactivado.</b>",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception(
            "Error notificando grupo %s sobre evento desactivado", group_chat_id
        )


@event_creator_router.callback_query(F.data == "delevent:action:delete")
async def de_confirm_delete(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    groups = data.get("groups", [])
    group_chat_id = data.get("group_chat_id")
    event_id = data.get("event_id")
    ev = next(
        (e for g in groups for e in g.get("events", []) if e["id"] == event_id),
        None,
    )
    ev_name = ev["name"] if ev else "Evento"

    await state.set_state(DeleteEventState.confirm_delete)
    await callback.message.edit_text(
        f"⚠️ <b>¿Eliminar \"{ev_name}\" permanentemente?</b>\n\n"
        "Esta acción <b>NO</b> se puede deshacer. "
        "El evento será borrado de la base de datos.",
        parse_mode="HTML",
        reply_markup=confirm_delete_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "delevent:confirm_delete")
async def de_do_delete(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    event_id = data.get("event_id")
    group_chat_id = data.get("group_chat_id")

    success = await event_service.delete_event(event_id)
    if not success:
        await callback.answer("❌ Evento no encontrado.", show_alert=True)
        await state.clear()
        return

    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Evento eliminado permanentemente.</b>", parse_mode="HTML"
    )
    try:
        await callback.answer("✅ Eliminado", show_alert=True)
    except TelegramBadRequest:
        pass

    try:
        await bot.send_message(
            group_chat_id,
            "🗑 <b>Un evento de temporada ha sido eliminado permanentemente.</b>",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception(
            "Error notificando grupo %s sobre evento eliminado", group_chat_id
        )


@event_creator_router.callback_query(F.data.startswith("delevent:cancel"))
async def de_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Cancelado.</b>", parse_mode="HTML"
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "delevent:back")
async def de_back(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    user_id = callback.from_user.id
    groups = await event_service.get_groups_with_active_events(user_id, bot)
    if not groups:
        await callback.message.edit_text("📭 No hay eventos activos.")
        await state.clear()
        await callback.answer()
        return

    await state.set_state(DeleteEventState.select_group)
    await state.update_data(groups=groups)
    await callback.message.edit_text(
        "🗑 <b>Borrar Evento</b>\n\nSelecciona el grupo:",
        parse_mode="HTML",
        reply_markup=groups_keyboard(groups, prefix="delevent"),
    )
    await callback.answer()


# ─── /toggleevent ───────────────────────────────────────────────────


@event_creator_router.message(F.text.startswith("/toggleevent"))
async def cmd_toggle_event(message: Message, bot: Bot, state: FSMContext) -> None:
    if not message.chat or message.chat.type != "private":
        await message.reply("⚠️ Usa este comando en tu chat privado con el bot.")
        return

    user_id = message.from_user.id if message.from_user else 0
    groups = await event_service.get_user_admin_groups(user_id, bot)

    if not groups:
        await message.reply(
            "❌ No eres admin de ningún grupo donde el bot esté presente."
        )
        return

    await state.set_state(ToggleEventState.select_group)
    await state.update_data(groups=groups)
    await message.reply(
        "🔄 <b>Gestionar Eventos</b>\n\nSelecciona el grupo:",
        parse_mode="HTML",
        reply_markup=groups_keyboard(groups, prefix="toggleevt"),
    )


@event_creator_router.callback_query(F.data.startswith("toggleevt:group:"))
async def te_select_group(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        chat_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    data = await state.get_data()
    groups = data.get("groups", [])
    selected = next((g for g in groups if g["chat_id"] == chat_id), None)
    if not selected:
        await callback.answer("❌ Grupo no encontrado.", show_alert=True)
        return

    events = await event_service.get_events_for_group(chat_id)

    await state.update_data(group_chat_id=chat_id)
    await state.set_state(ToggleEventState.select_event)

    if not events:
        await callback.message.edit_text(
            f"📌 <b>{selected['chat_title']}</b>\n\n📭 No hay eventos en este grupo.",
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            f"📌 <b>{selected['chat_title']}</b>\n\n"
            "Selecciona el evento para pausar/reanudar:",
            parse_mode="HTML",
            reply_markup=event_status_keyboard(events, prefix="toggleevt"),
        )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("toggleevt:toggle:"))
async def te_toggle_event(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    try:
        event_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    result = await event_service.toggle_event(event_id)
    if result is None:
        await callback.answer("❌ Evento no encontrado.", show_alert=True)
        return

    data = await state.get_data()
    group_chat_id = data.get("group_chat_id")

    if result:
        await callback.answer("✅ Evento reanudado", show_alert=True)
        status_text = "🟢 <b>Evento reanudado</b>"
        group_msg = "🟢 <b>Un evento de temporada ha sido reanudado.</b>"
    else:
        await callback.answer("⏸ Evento pausado", show_alert=True)
        status_text = "⏸ <b>Evento pausado</b>"
        group_msg = "⏸ <b>Un evento de temporada ha sido pausado.</b>"

    if group_chat_id:
        events = await event_service.get_events_for_group(group_chat_id)
        if events:
            await callback.message.edit_text(
                f"{status_text}\n\nSelecciona otro evento:",
                parse_mode="HTML",
                reply_markup=event_status_keyboard(events, prefix="toggleevt"),
            )
        else:
            await callback.message.edit_text(
                f"{status_text}\n\n📭 No hay más eventos en este grupo.",
                parse_mode="HTML",
            )
        try:
            await bot.send_message(group_chat_id, group_msg, parse_mode="HTML")
        except Exception:
            logger.exception("Error notificando grupo %s", group_chat_id)
    else:
        await callback.message.edit_text(status_text, parse_mode="HTML")


@event_creator_router.callback_query(F.data == "toggleevt:cancel")
async def te_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Cancelado.</b>", parse_mode="HTML"
    )
    await callback.answer()


# ─── /editevent ─────────────────────────────────────────────────────


@event_creator_router.message(F.text.startswith("/editevent"))
async def cmd_edit_event(message: Message, bot: Bot, state: FSMContext) -> None:
    if not message.chat or message.chat.type != "private":
        await message.reply("⚠️ Usa este comando en tu chat privado con el bot.")
        return

    user_id = message.from_user.id if message.from_user else 0
    groups = await event_service.get_user_admin_groups(user_id, bot)

    if not groups:
        await message.reply(
            "❌ No eres admin de ningún grupo donde el bot esté presente."
        )
        return

    await state.set_state(EditEventState.select_group)
    await state.update_data(groups=groups)
    await message.reply(
        "✏️ <b>Editar Evento</b>\n\nSelecciona el grupo:",
        parse_mode="HTML",
        reply_markup=groups_keyboard(groups, prefix="editevent"),
    )


@event_creator_router.callback_query(F.data.startswith("editevent:group:"))
async def ee_select_group(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        chat_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    data = await state.get_data()
    groups = data.get("groups", [])
    selected = next((g for g in groups if g["chat_id"] == chat_id), None)
    if not selected:
        await callback.answer("❌ Grupo no encontrado.", show_alert=True)
        return

    events = await event_service.get_events_for_group(chat_id)
    await state.update_data(group_chat_id=chat_id, group_title=selected["chat_title"])
    await state.set_state(EditEventState.select_event)

    if not events:
        await callback.message.edit_text(
            f"📌 <b>{selected['chat_title']}</b>\n\n📭 No hay eventos en este grupo.",
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            f"📌 <b>{selected['chat_title']}</b>\n\nSelecciona el evento a editar:",
            parse_mode="HTML",
            reply_markup=events_edit_list_keyboard(events, prefix="editevent"),
        )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("editevent:event:"))
async def ee_select_event(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        event_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    event_data = await _load_event_to_state(event_id, state)
    if not event_data:
        await callback.answer("❌ Evento no encontrado.", show_alert=True)
        return

    await state.set_state(EditEventState.select_field)
    summary = _build_edit_summary(event_data)
    await callback.message.edit_text(
        f"{summary}\n\n"
        "Selecciona el campo a editar:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("editevent:field:"))
async def ee_select_field(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":")[2]
    data = await state.get_data()
    ed = data.get("event_data", {})

    if field == "name":
        await state.set_state(EditEventState.edit_name)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            f"<b>Nombre actual:</b> {ed.get('name', '')}\n\n"
            "<i>Escribe el nuevo nombre (máx. 64 caracteres):</i>",
            parse_mode="HTML",
        )

    elif field == "description":
        await state.set_state(EditEventState.edit_description)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            f"<b>Descripción actual:</b> {ed.get('description', '')}\n\n"
            "<i>Escribe la nueva descripción (máx. 500 caracteres):</i>",
            parse_mode="HTML",
        )

    elif field == "multiplier":
        await state.set_state(EditEventState.edit_multiplier)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            "<b>Nuevo multiplicador:</b>",
            parse_mode="HTML",
            reply_markup=multiplier_keyboard(prefix="ee"),
        )

    elif field == "schedule":
        await state.set_state(EditEventState.edit_type)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            "<b>Nuevo tipo de evento:</b>",
            parse_mode="HTML",
            reply_markup=event_type_keyboard_for_edit(),
        )

    elif field == "categories":
        rules_data = ed.get("rules_data", {})
        enabled = rules_data.get("categories_enabled", list(_DEFAULT_RULES.categories_enabled))
        await state.set_state(EditEventState.edit_rules_categories)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            "<b>Categorías activas:</b>",
            parse_mode="HTML",
            reply_markup=categories_toggle_keyboard(enabled, prefix="ee"),
        )

    elif field == "time_letter":
        rules_data = ed.get("rules_data", {})
        await state.set_state(EditEventState.edit_rules_time)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            "<b>Tiempo por ronda:</b>",
            parse_mode="HTML",
            reply_markup=round_time_keyboard(
                rules_data.get("time_override"), prefix="ee"
            ),
        )

    elif field == "scoring":
        rules_data = ed.get("rules_data", {})
        await state.set_state(EditEventState.edit_rules_scoring)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            "<b>Bonificaciones:</b>",
            parse_mode="HTML",
            reply_markup=bonuses_keyboard(rules_data, prefix="ee"),
        )

    elif field == "cat_multipliers":
        rules_data = ed.get("rules_data", {})
        cat_mults = rules_data.get("category_multipliers", {})
        await state.set_state(EditEventState.edit_rules_categories)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            "<b>Multiplicadores por categoría:</b>\n"
            "Pulsa para cambiar: OFF → x1.5 → x2 → x3 → x5",
            parse_mode="HTML",
            reply_markup=category_multipliers_keyboard(cat_mults, prefix="ee"),
        )

    elif field == "excluded_letters":
        rules_data = ed.get("rules_data", {})
        excluded = rules_data.get("excluded_letters", [])
        await state.set_state(EditEventState.edit_rules_time)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            "<b>Letras excluidas:</b>\n"
            "Pulsa para excluir/incluir cada letra.",
            parse_mode="HTML",
            reply_markup=excluded_letters_keyboard(excluded, prefix="ee"),
        )

    elif field == "game_mode":
        rules_data = ed.get("rules_data", {})
        await state.set_state(EditEventState.edit_rules_scoring)
        await callback.message.edit_text(
            f"{_build_edit_summary(ed)}\n\n"
            "<b>Modo de juego:</b>\n"
            "Pulsa para configurar.",
            parse_mode="HTML",
            reply_markup=game_mode_keyboard(rules_data, prefix="ee"),
        )

    else:
        await callback.answer("❌ Campo desconocido.", show_alert=True)
        return

    await callback.answer()


@event_creator_router.message(EditEventState.edit_name)
async def ee_process_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 3:
        await message.reply("❌ Mínimo 3 caracteres:")
        return
    if len(name) > 64:
        await message.reply("❌ Máximo 64 caracteres:")
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    ed["name"] = name
    await state.update_data(event_data=ed)

    await state.set_state(EditEventState.select_field)
    await message.reply(
        f"{_build_edit_summary(ed)}\n\n"
        "Nombre actualizado. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )


@event_creator_router.message(EditEventState.edit_description)
async def ee_process_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if len(desc) < 5:
        await message.reply("❌ Mínimo 5 caracteres:")
        return
    if len(desc) > 500:
        await message.reply("❌ Máximo 500 caracteres:")
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    ed["description"] = desc
    await state.update_data(event_data=ed)

    await state.set_state(EditEventState.select_field)
    await message.reply(
        f"{_build_edit_summary(ed)}\n\n"
        "Descripción actualizada. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )


@event_creator_router.callback_query(F.data.startswith("ee:mult:"))
async def ee_process_multiplier(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        multiplier = float(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    ed["multiplier"] = multiplier
    await state.update_data(event_data=ed)

    await state.set_state(EditEventState.select_field)
    await callback.message.edit_text(
        f"{_build_edit_summary(ed)}\n\n"
        "Multiplicador actualizado. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:type:"))
async def ee_process_type(callback: CallbackQuery, state: FSMContext) -> None:
    event_type = callback.data.split(":")[2]
    if event_type not in {"one_time", "daily_recurring", "permanent"}:
        await callback.answer("❌ Tipo inválido.", show_alert=True)
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    ed["event_type"] = event_type
    await state.update_data(event_data=ed)

    await state.set_state(EditEventState.select_field)
    await callback.message.edit_text(
        f"{_build_edit_summary(ed)}\n\n"
        "Tipo actualizado. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:cat:"))
async def ee_toggle_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    if cat not in _VALID_CATEGORIES:
        await callback.answer("❌ Categoría inválida.", show_alert=True)
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    enabled = list(
        rules_data.get("categories_enabled", list(_DEFAULT_RULES.categories_enabled))
    )

    if cat in enabled:
        enabled.remove(cat)
    else:
        enabled.append(cat)
    rules_data["categories_enabled"] = enabled
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=categories_toggle_keyboard(enabled, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ee:cat_all")
async def ee_select_all_categories(callback: CallbackQuery, state: FSMContext) -> None:
    all_cats = list(_DEFAULT_RULES.categories_enabled)
    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    rules_data["categories_enabled"] = all_cats
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=categories_toggle_keyboard(all_cats, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ee:rules_next")
async def ee_rules_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    hidden = rules_data.get("hidden_categories", [])
    mystery = rules_data.get("mystery_category")

    await state.set_state(EditEventState.edit_rules_categories_options)
    await callback.message.edit_text(
        "📋 <b>Categorías avanzadas</b>\n\n"
        "Opcional: categorías ocultas o mystery.\n"
        "Si no necesitas, pulsa Siguiente.",
        parse_mode="HTML",
        reply_markup=categories_options_keyboard(hidden, mystery, prefix="ee"),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:cat_hidden:"))
async def ee_toggle_hidden(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    hidden = list(rules_data.get("hidden_categories", []))

    if cat in hidden:
        hidden.remove(cat)
    else:
        hidden.append(cat)
    rules_data["hidden_categories"] = hidden
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    mystery = rules_data.get("mystery_category")
    try:
        await callback.message.edit_reply_markup(
            reply_markup=categories_options_keyboard(hidden, mystery, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:cat_mystery:"))
async def ee_toggle_mystery(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})

    if rules_data.get("mystery_category") == cat:
        rules_data["mystery_category"] = None
    else:
        rules_data["mystery_category"] = cat
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    hidden = rules_data.get("hidden_categories", [])
    mystery = rules_data.get("mystery_category")
    try:
        await callback.message.edit_reply_markup(
            reply_markup=categories_options_keyboard(hidden, mystery, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ee:options_next")
async def ee_options_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ed = data.get("event_data", {})
    await state.set_state(EditEventState.select_field)
    await callback.message.edit_text(
        f"{_build_edit_summary(ed)}\n\n"
        "Categorías actualizadas. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:catmult:"))
async def ee_toggle_cat_mult(callback: CallbackQuery, state: FSMContext) -> None:
    cat = callback.data.split(":")[2]
    if cat not in _VALID_CATEGORIES:
        await callback.answer("❌ Categoría inválida.", show_alert=True)
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    cat_mults = dict(rules_data.get("category_multipliers", {}))

    current = cat_mults.get(cat)
    cycle = [None, 1.5, 2.0, 3.0, 5.0]
    try:
        idx = cycle.index(current)
        next_val = cycle[(idx + 1) % len(cycle)]
    except ValueError:
        next_val = 1.5

    if next_val is None:
        cat_mults.pop(cat, None)
    else:
        cat_mults[cat] = next_val

    rules_data["category_multipliers"] = cat_mults
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=category_multipliers_keyboard(cat_mults, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ee:catmult_next")
async def ee_catmult_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ed = data.get("event_data", {})
    await state.set_state(EditEventState.select_field)
    await callback.message.edit_text(
        f"{_build_edit_summary(ed)}\n\n"
        "Multiplicadores actualizados. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:time:"))
async def ee_select_time(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        time_val = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})

    if time_val == 0:
        rules_data.pop("time_override", None)
    else:
        rules_data["time_override"] = time_val
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    await state.set_state(EditEventState.edit_rules_decreasing)
    dec_amount = rules_data.get("time_decreasing_amount", 5)
    await callback.message.edit_text(
        f"⏱ Tiempo: <b>{time_val}s</b>\n\n"
        "¿Tiempo decreciente?",
        parse_mode="HTML",
        reply_markup=decreasing_time_keyboard(dec_amount, prefix="ee"),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:dec:"))
async def ee_select_decreasing(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        amount = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Valor inválido.", show_alert=True)
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    rules_data["time_decreasing"] = True
    rules_data["time_decreasing_amount"] = amount
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=decreasing_time_keyboard(amount, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ee:dec_confirm")
async def ee_confirm_decreasing(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    if "time_decreasing" not in rules_data:
        rules_data["time_decreasing"] = False
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    await state.set_state(EditEventState.edit_rules_letter)
    await callback.message.edit_text(
        "🔤 <b>Letra para el evento:</b>",
        parse_mode="HTML",
        reply_markup=forced_letter_keyboard(prefix="ee"),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:letter:"))
async def ee_select_letter(callback: CallbackQuery, state: FSMContext) -> None:
    letter = callback.data.split(":")[2]
    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})

    if letter == "RANDOM":
        rules_data.pop("forced_letter", None)
        rules_data["vowel_forced"] = False
    elif letter == "EXCLUDE_VOWELS":
        rules_data.pop("forced_letter", None)
        rules_data["vowel_forced"] = True
    elif letter == "SEQUENCE":
        rules_data.pop("forced_letter", None)
        rules_data["vowel_forced"] = False
    else:
        rules_data["forced_letter"] = letter
        rules_data["vowel_forced"] = False

    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    await state.set_state(EditEventState.select_field)
    await callback.message.edit_text(
        f"{_build_edit_summary(ed)}\n\n"
        "Tiempo/letra actualizados. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:excl:"))
async def ee_toggle_excluded(callback: CallbackQuery, state: FSMContext) -> None:
    letter = callback.data.split(":")[2]
    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    excluded = list(rules_data.get("excluded_letters", []))

    if letter in excluded:
        excluded.remove(letter)
    else:
        excluded.append(letter)

    rules_data["excluded_letters"] = excluded
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=excluded_letters_keyboard(excluded, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ee:excl_next")
async def ee_excl_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ed = data.get("event_data", {})
    await state.set_state(EditEventState.select_field)
    await callback.message.edit_text(
        f"{_build_edit_summary(ed)}\n\n"
        "Letras excluidas actualizadas. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:bonus:"))
async def ee_toggle_bonus(callback: CallbackQuery, state: FSMContext) -> None:
    bonus_key = callback.data.split(":")[2]
    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})

    if bonus_key in _BONUS_CYCLES:
        cycle = _BONUS_CYCLES[bonus_key]
        current = rules_data.get(bonus_key, cycle[0])
        try:
            idx = cycle.index(current)
            rules_data[bonus_key] = cycle[(idx + 1) % len(cycle)]
        except ValueError:
            rules_data[bonus_key] = cycle[0]
    elif bonus_key == "double_points_last_round":
        rules_data["double_points_last_round"] = not rules_data.get(
            "double_points_last_round", False
        )
    elif bonus_key == "answer_reveal":
        rules_data["answer_reveal"] = not rules_data.get("answer_reveal", False)
    else:
        await callback.answer("❌ Bonus desconocido.", show_alert=True)
        return

    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=bonuses_keyboard(rules_data, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ee:bonus_next")
async def ee_bonus_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ed = data.get("event_data", {})
    await state.set_state(EditEventState.select_field)
    await callback.message.edit_text(
        f"{_build_edit_summary(ed)}\n\n"
        "Bonificaciones actualizadas. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:gm_toggle_"))
async def ee_toggle_gm_flag(callback: CallbackQuery, state: FSMContext) -> None:
    flag = callback.data.split("ee:gm_toggle_")[1]
    FIELD_MAP = {
        "sudden": "sudden_death",
        "wager": "wager_enabled",
        "collab": "collaborative",
        "infinite": "infinite_rounds",
        "nostop": "no_stop",
        "alldiff": "require_all_different",
    }
    field = FIELD_MAP.get(flag)
    if not field:
        await callback.answer("❌ Opción desconocida.", show_alert=True)
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    current = rules_data.get(field, False)
    rules_data[field] = not current
    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=game_mode_keyboard(rules_data, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data.startswith("ee:gm_cycle_"))
async def ee_cycle_gm_value(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":")[1]
    field = _CYCLES_MAP.get(key)
    if not field:
        await callback.answer("❌ Opción desconocida.", show_alert=True)
        return

    data = await state.get_data()
    ed = data.get("event_data", {})
    rules_data = ed.get("rules_data", {})
    cycle = _GAME_MODE_CYCLES[field]
    current = rules_data.get(field, cycle[0])
    try:
        idx = cycle.index(current)
        rules_data[field] = cycle[(idx + 1) % len(cycle)]
    except ValueError:
        rules_data[field] = cycle[0]

    ed["rules_data"] = rules_data
    await state.update_data(event_data=ed)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=game_mode_keyboard(rules_data, prefix="ee")
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@event_creator_router.callback_query(F.data == "ee:gm_next")
async def ee_gm_next(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ed = data.get("event_data", {})
    await state.set_state(EditEventState.select_field)
    await callback.message.edit_text(
        f"{_build_edit_summary(ed)}\n\n"
        "Modo de juego actualizado. Selecciona otro campo o Guarda:",
        parse_mode="HTML",
        reply_markup=edit_event_field_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "editevent:save")
async def ee_save(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    ed = data.get("event_data", {})
    event_id = ed.get("id")

    if not event_id:
        await callback.answer("❌ Error: no hay evento para guardar.", show_alert=True)
        return

    rules_data = ed.get("rules_data", {})
    event_rules = EventRules(
        categories_enabled=rules_data.get(
            "categories_enabled", list(_DEFAULT_RULES.categories_enabled)
        ),
        categories_disabled=rules_data.get("categories_disabled", []),
        category_multipliers=rules_data.get("category_multipliers", {}),
        hidden_categories=rules_data.get("hidden_categories", []),
        mystery_category=rules_data.get("mystery_category"),
        time_override=rules_data.get("time_override"),
        time_decreasing=rules_data.get("time_decreasing", False),
        time_decreasing_amount=rules_data.get("time_decreasing_amount", 5),
        forced_letter=rules_data.get("forced_letter"),
        vowel_forced=rules_data.get("vowel_forced", False),
        letter_sequence=rules_data.get("letter_sequence"),
        excluded_letters=rules_data.get("excluded_letters", []),
        no_duplicates_bonus=rules_data.get("no_duplicates_bonus", 0),
        bonus_all_filled=rules_data.get("bonus_all_filled", 0),
        speed_bonus=rules_data.get("speed_bonus", 0),
        speed_bonus_window=rules_data.get("speed_bonus_window", 8),
        streak_multiplier=rules_data.get("streak_multiplier", 1.0),
        penalty_empty=rules_data.get("penalty_empty", 0),
        comeback_bonus=rules_data.get("comeback_bonus", 0),
        double_points_last_round=rules_data.get("double_points_last_round", False),
        answer_reveal=rules_data.get("answer_reveal", False),
        sudden_death=rules_data.get("sudden_death", False),
        sudden_death_threshold=rules_data.get("sudden_death_threshold", 1),
        wager_enabled=rules_data.get("wager_enabled", False),
        wager_max_pct=rules_data.get("wager_max_pct", 50),
        collaborative=rules_data.get("collaborative", False),
        max_players=rules_data.get("max_players"),
        infinite_rounds=rules_data.get("infinite_rounds", False),
        no_stop=rules_data.get("no_stop", False),
        require_all_different=rules_data.get("require_all_different", False),
        min_words_required=rules_data.get("min_words_required", 0),
        min_word_length=rules_data.get("min_word_length", 0),
        shared_answer_penalty=rules_data.get("shared_answer_penalty", 0),
        perfect_round_bonus=rules_data.get("perfect_round_bonus", 0),
    )
    rules_json = event_rules.to_json()

    success = await event_service.update_event(
        event_id,
        name=ed.get("name"),
        description=ed.get("description", ""),
        multiplier=ed.get("multiplier", 1.0),
        event_type=ed.get("event_type", "one_time"),
        rules=rules_json,
    )

    if not success:
        await callback.answer("❌ Error al guardar.", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Evento actualizado correctamente.</b>",
        parse_mode="HTML",
    )
    await callback.answer("✅ Guardado", show_alert=True)


@event_creator_router.callback_query(F.data == "editevent:cancel")
async def ee_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Edición cancelada.</b>", parse_mode="HTML"
    )
    await callback.answer()


# ─── /deleteallevents ──────────────────────────────────────────────


@event_creator_router.message(F.text.startswith("/deleteallevents"))
async def cmd_delete_all_events(message: Message, bot: Bot, state: FSMContext) -> None:
    if not message.chat or message.chat.type != "private":
        await message.reply("⚠️ Usa este comando en tu chat privado con el bot.")
        return

    user_id = message.from_user.id if message.from_user else 0
    groups = await event_service.get_user_admin_groups(user_id, bot)

    if not groups:
        await message.reply(
            "❌ No eres admin de ningún grupo donde el bot esté presente."
        )
        return

    await state.set_state(DeleteAllEventsState.select_group)
    await state.update_data(groups=groups)
    await message.reply(
        "🗑 <b>Eliminar TODOS los Eventos</b>\n\n"
        "Selecciona el grupo del cual quieres borrar todos los eventos:",
        parse_mode="HTML",
        reply_markup=groups_keyboard(groups, prefix="delevtall"),
    )


@event_creator_router.callback_query(F.data.startswith("delevtall:group:"))
async def da_select_group(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        chat_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌", show_alert=True)
        return

    data = await state.get_data()
    groups = data.get("groups", [])
    selected = next((g for g in groups if g["chat_id"] == chat_id), None)
    if not selected:
        await callback.answer("❌", show_alert=True)
        return

    await state.update_data(group_chat_id=chat_id)
    await state.set_state(DeleteAllEventsState.confirm)
    await callback.message.edit_text(
        f"⚠️ <b>¿Eliminar TODOS los eventos de \"{selected['chat_title']}\"?</b>\n\n"
        "Esta acción <b>NO</b> se puede deshacer. "
        "Todos los eventos de temporada de este grupo serán borrados permanentemente.",
        parse_mode="HTML",
        reply_markup=delete_all_confirm_keyboard(),
    )
    await callback.answer()


@event_creator_router.callback_query(F.data == "delevtall:confirm")
async def da_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    group_chat_id = data.get("group_chat_id")
    groups = data.get("groups", [])
    group = next((g for g in groups if g["chat_id"] == group_chat_id), None)
    group_title = group["chat_title"] if group else "Grupo"

    count = await event_service.delete_all_events(group_chat_id)

    await state.clear()
    await callback.message.edit_text(
        f"✅ <b>Eventos eliminados.</b>\n\n"
        f"Se eliminaron {count} evento(s) de <b>{group_title}</b>.",
        parse_mode="HTML",
    )
    try:
        await callback.answer(f"✅ {count} evento(s) eliminados", show_alert=True)
    except TelegramBadRequest:
        pass

    if count > 0:
        try:
            await bot.send_message(
                group_chat_id,
                f"🗑 <b>Todos los eventos de temporada han sido eliminados permanentemente.</b>",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception(
                "Error notificando grupo %s sobre eliminación de eventos", group_chat_id
            )


@event_creator_router.callback_query(F.data == "delevtall:cancel")
async def da_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Cancelado.</b>", parse_mode="HTML"
    )
    await callback.answer()
