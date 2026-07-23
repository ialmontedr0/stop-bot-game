import asyncio
import json
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.db.models import Player
from src.keyboards.event import groups_keyboard
from src.keyboards.lobby import event_selection_keyboard, mode_selection_keyboard
from src.services.error_tracker import error_tracker
from src.services.event_service import event_service
from src.services.game_orchestrator import lobby_manager
from src.utils import delete_after

logger = logging.getLogger(__name__)

game_router = Router()


@game_router.message(Command("stop"))
@error_tracker.track_errors(handler_name="cmd_stop")
async def cmd_stop(message: Message, player: Player, bot: Bot) -> None:
    if message.chat.type == "private":
        msg = await message.answer("❌ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    has_events = await event_service.has_active_event(message.chat.id)

    if has_events:
        text = (
            f"🟢 <b>¿Cómo quieres jugar?</b>\n\n"
            f"👤 <b>{player.first_name or player.username}</b>, elegí el modo de juego:"
        )
        keyboard = mode_selection_keyboard(player.telegram_id)
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return

    result = await lobby_manager.create_lobby(
        group_chat_id=message.chat.id, host_player=player, bot=bot
    )
    if result is None:
        try:
            await message.delete()
        except Exception:
            logger.warning("No se pudo eliminar el mensaje /stop en %s", message.chat.id)
    else:
        await message.answer(result)


@game_router.message(Command("cancel"))
@error_tracker.track_errors(handler_name="cmd_cancel")
async def cmd_cancel(message: Message, player: Player, bot: Bot) -> None:
    if message.chat.type == "private":
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    result = await lobby_manager.cancel_game(group_chat_id=message.chat.id, player=player, bot=bot)
    msg = await message.answer(result)
    asyncio.create_task(delete_after(msg))


@game_router.callback_query(F.data.startswith("join:"))
@error_tracker.track_errors(handler_name="callback_join")
async def callback_join(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    try:
        game_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return
    try:
        await lobby_manager.join_lobby(
            game_id=game_id,
            player=player,
            callback=callback,
            bot=bot,
        )
    except Exception:
        logger.exception("Error en join_lobby: game_id=%s jugador=%s", game_id, player.telegram_id)
        await callback.answer("❌ Error al unirse a la partida.", show_alert=True)


@game_router.callback_query(F.data.startswith("leave:"))
@error_tracker.track_errors(handler_name="callback_leave")
async def callback_leave(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    try:
        game_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return
    try:
        await lobby_manager.leave_lobby(
            game_id=game_id,
            player=player,
            callback=callback,
            bot=bot,
        )
    except Exception:
        logger.exception("Error en leave_lobby: game_id=%s jugador=%s", game_id, player.telegram_id)
        await callback.answer("❌ Error al salir de la partida.", show_alert=True)


def _format_event_time(event: dict) -> str:
    """Formatea el tiempo restante de un evento para mostrar."""
    event_type = event.get("event_type", "one_time")
    ends_at = event.get("ends_at")

    if event_type == "one_time" and ends_at:
        from datetime import datetime

        if isinstance(ends_at, str):
            ends_at = datetime.fromisoformat(ends_at)
        remaining = ends_at - datetime.utcnow()
        total_hours = remaining.total_seconds() / 3600
        if total_hours >= 24:
            return f"queda {int(total_hours // 24)}d {int(total_hours % 24)}h"
        elif total_hours >= 1:
            return f"queda {int(total_hours)}h {int((total_hours % 1) * 60)}m"
        else:
            return f"queda {int(remaining.total_seconds() / 60)}m"

    if event_type == "daily_recurring":
        return "repite a diario"

    if event_type == "permanent":
        return "siempre activo"

    return ""


def _format_active_days(active_days_json: str | None) -> str:
    if not active_days_json:
        return "todos los d\u00edas"
    try:
        days = json.loads(active_days_json)
    except (json.JSONDecodeError, TypeError):
        return "todos los d\u00edas"
    DAY_LABELS = {
        "mon": "Lun",
        "tue": "Mar",
        "wed": "Mi\u00e9",
        "thu": "Jue",
        "fri": "Vie",
        "sat": "S\u00e1b",
        "sun": "Dom",
    }
    labels = [DAY_LABELS.get(d, d) for d in days if d in DAY_LABELS]
    if not labels or len(labels) == 7:
        return "todos los d\u00edas"
    return ", ".join(labels)


def _format_event_list(events: list[dict]) -> str:
    """Construye un mensaje formateado profesional con la lista de eventos."""
    lines = [
        "╔══════════════════════════╗",
        "║    🎉 EVENTOS ACTIVOS    ║",
        "╚══════════════════════════╝",
        "",
    ]
    for i, e in enumerate(events):
        name = e["name"]
        mult = e.get("multiplier", 1.0)
        event_type = e.get("event_type", "one_time")
        desc = e.get("description")
        is_paused = e.get("is_paused", False)
        rules = e.get("rules")

        # Icono de estado
        if is_paused:
            status = "⏸ PAUSADO"
        else:
            status = "🟢 ACTIVO"

        # Tipo de evento
        type_icons = {
            "one_time": "🔄 Temporal",
            "daily_recurring": "🔁 Diario Recurrente",
            "permanent": "♾ Permanente",
        }
        type_str = type_icons.get(event_type, event_type)

        # Horario para daily_recurring
        if event_type == "daily_recurring":
            days = _format_active_days(e.get("active_days"))
            sh = e.get("daily_start_hour", 0)
            sm = e.get("daily_start_minute", 0)
            eh = e.get("daily_end_hour", 23)
            em = e.get("daily_end_minute", 59)
            type_str += f" | {sh:02d}:{sm:02d}–{eh:02d}:{em:02d} · {days}"

        # Separador entre eventos
        if i > 0:
            lines.append("─" * 32)

        lines.append(f"📌 <b>{name}</b>")
        lines.append(f"   🏆 <b>x{mult} XP</b> · {type_str} · {status}")

        if desc:
            lines.append(f"   📝 {desc}")

        # Reglas activas
        if rules and hasattr(rules, "has_rules") and rules.has_rules():
            rule_parts = []
            rt = rules.get_round_time(None)
            if rt is not None:
                rule_parts.append(f"⏱ {rt}s")
            if rules.is_letter_forced():
                letter = rules.get_letter_for_round(1)
                if letter:
                    rule_parts.append(f"🔤 Letra: {letter}")
            if rules.letter_sequence:
                rule_parts.append(f"🔤 Sec: {''.join(rules.letter_sequence)}")
            if rules.vowel_forced:
                rule_parts.append("🔤 Solo vocales")
            cats_enabled = rules.get_active_categories()
            if cats_enabled and len(cats_enabled) < 8:
                rule_parts.append(f"🎯 {len(cats_enabled)}/8 categorías")
            disabled = rules.categories_disabled
            if disabled:
                short = ",".join(d[:4] for d in disabled)
                rule_parts.append(f"🚫 Sin: {short}")
            if rules.hidden_categories:
                rule_parts.append("🎭 Categorías ocultas")
            if rules.mystery_category:
                rule_parts.append("❓ Categoría misteriosa")
            cm = rules.category_multipliers
            if cm:
                bonus_str = ", ".join(f"{k}×{v}" for k, v in sorted(cm.items()))
                rule_parts.append(f"📈 {bonus_str}")
            if rules.speed_bonus:
                rule_parts.append(
                    f"🏃 +{rules.speed_bonus}pts (primeros {rules.speed_bonus_window})"
                )
            if rules.streak_multiplier != 1.0:
                rule_parts.append(f"🔥 Rachas ×{rules.streak_multiplier}")
            if rules.penalty_empty:
                rule_parts.append(f"💀 Vacío: {rules.penalty_empty}pts")
            if rules.bonus_all_filled:
                rule_parts.append(f"💯 Todo completo: +{rules.bonus_all_filled}pts")
            if rules.no_duplicates_bonus:
                rule_parts.append(f"🦄 Sin repetir: +{rules.no_duplicates_bonus}pts")
            if rules.comeback_bonus:
                rule_parts.append(f"⚡ Remontada: +{rules.comeback_bonus}pts")
            if rules.sudden_death:
                rule_parts.append(f"💀 Muerte súbita (ronda ≤{rules.sudden_death_threshold})")
            if rules.no_stop:
                rule_parts.append("🚫🛑 Sin Stop")
            if rules.double_points_last_round:
                rule_parts.append("2× Última ronda")
            if rules.collaborative:
                rule_parts.append("🤝 Colaborativo")
            if rules.wager_enabled:
                rule_parts.append(f"🎰 Apuesta (máx {rules.wager_max_pct}%)")
            if rules.infinite_rounds:
                rule_parts.append("♾ Infinito")
            if rules.require_all_different:
                rule_parts.append("🔀 Sin repetir respuestas")
            if rules.perfect_round_bonus:
                rule_parts.append(f"🏅 Ronda perfecta: +{rules.perfect_round_bonus}pts")
            if rule_parts:
                lines.append(f"   ⚙️  {' · '.join(rule_parts)}")

    lines.append("")
    lines.append("💡 LLama /stop para iniciar una partida con evento.")
    return "\n".join(lines)


@game_router.message(Command("events"))
@error_tracker.track_errors(handler_name="cmd_events")
async def cmd_events(message: Message, bot: Bot) -> None:
    if message.chat.type == "private":
        user_id = message.from_user.id if message.from_user else 0
        groups = await event_service.get_user_admin_groups(user_id, bot)
        if not groups:
            await message.answer("❌ No eres admin de ningún grupo donde el bot esté presente.")
            return
        await message.answer(
            "📋 <b>Ver Eventos</b>\n\nSelecciona el grupo:",
            parse_mode="HTML",
            reply_markup=groups_keyboard(groups, prefix="events"),
        )
        return

    events = await event_service.get_active_events(message.chat.id)
    if not events:
        await message.answer(
            "📭 No hay eventos activos ahora mismo en este grupo.\n\nRevisá el horario configurado de cada evento con /toggleevent."
        )
        return

    await message.answer(_format_event_list(events), parse_mode="HTML")


@game_router.callback_query(F.data.startswith("events:group:"))
@error_tracker.track_errors(handler_name="callback_events_group")
async def callback_events_group(callback: CallbackQuery) -> None:
    try:
        chat_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌", show_alert=True)
        return

    events = await event_service.get_active_events(chat_id)
    if not events:
        await callback.message.edit_text(
            "📭 No hay eventos activos ahora mismo en este grupo.\n\nRevisa el horario configurado de cada evento con /toggleevent."
        )
        await callback.answer()
        return

    await callback.message.edit_text(_format_event_list(events), parse_mode="HTML")
    await callback.answer()


@game_router.callback_query(F.data.startswith("start:"))
@error_tracker.track_errors(handler_name="callback_start")
async def callback_start(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    try:
        game_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return
    try:
        await lobby_manager.start_game(game_id=game_id, player=player, callback=callback, bot=bot)
    except Exception:
        logger.exception("Error en start_game: game_id=%s jugador=%s", game_id, player.telegram_id)
        await callback.answer("❌ Error al iniciar la partida.", show_alert=True)


@game_router.callback_query(F.data.startswith("mode:normal:"))
@error_tracker.track_errors(handler_name="callback_mode_normal")
async def callback_mode_normal(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    """El usuario eligió modo normal (sin evento). Crear lobby sin event_id."""
    try:
        host_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Error.", show_alert=True)
        return
    if player.telegram_id != host_id:
        await callback.answer("⚠️ Solo el host puede elegir el modo.", show_alert=True)
        return

    result = await lobby_manager.create_lobby(
        group_chat_id=callback.message.chat.id,
        host_player=player,
        bot=bot,
        event_id=None,
    )
    if result is None:
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.message.answer(result)
    await callback.answer()


@game_router.callback_query(F.data.startswith("mode:event:"))
@error_tracker.track_errors(handler_name="callback_mode_event")
async def callback_mode_event(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    """El usuario quiere jugar con evento. Mostrar lista de eventos activos."""
    try:
        host_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Error.", show_alert=True)
        return
    if player.telegram_id != host_id:
        await callback.answer("⚠️ Solo el host puede elegir el modo.", show_alert=True)
        return

    events = await event_service.get_active_events(callback.message.chat.id)
    if not events:
        await callback.answer("📭 No hay eventos activos en este grupo.", show_alert=True)
        return

    text = "📌 <b>Selecciona el evento:</b>"
    keyboard = event_selection_keyboard(events, host_id, prefix="select_event")
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@game_router.callback_query(F.data.startswith("mode:exit:"))
@error_tracker.track_errors(handler_name="callback_mode_exit")
async def callback_mode_exit(callback: CallbackQuery) -> None:
    """El usuario cerró el menú de selección de modo."""
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_text("❌ Menú cerrado.")
    await callback.answer()


@game_router.callback_query(F.data.startswith("select_event:"))
@error_tracker.track_errors(handler_name="callback_select_event")
async def callback_select_event(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    """El usuario seleccionó un evento específico (o canceló)."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    try:
        host_id = int(parts[1])
    except ValueError:
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    if player.telegram_id != host_id:
        await callback.answer("⚠️ Solo el host puede elegir el modo.", show_alert=True)
        return

    event_id_str = parts[2]

    if event_id_str == "cancel":
        await callback.message.delete()
        await callback.answer()
        return

    try:
        event_id = int(event_id_str)
    except ValueError:
        await callback.answer("❌ Datos inválidos.", show_alert=True)
        return

    events = await event_service.get_active_events(callback.message.chat.id)
    valid_ids = {e["id"] for e in events}
    if event_id not in valid_ids:
        await callback.answer("❌ Este evento ya no está activo.", show_alert=True)
        return

    result = await lobby_manager.create_lobby(
        group_chat_id=callback.message.chat.id,
        host_player=player,
        bot=bot,
        event_id=event_id,
    )
    if result is None:
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.message.answer(result)
    await callback.answer()
