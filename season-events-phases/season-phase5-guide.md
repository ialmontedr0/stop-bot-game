# Fase 5: `/editevent` y `/toggleevent` — Nuevos comandos

## Resumen
- `/toggleevent` — Pausar/reanudar eventos (simple, 2 estados, 4 handlers)
- `/editevent` — Editar campos de un evento existente (complejo, ~15 estados, ~25 handlers)

## Archivos a modificar

| Archivo | Acción |
|---|---|
| `src/keyboards/event.py` | +3 funciones nuevas |
| `src/handlers/admin/event_creator.py` | +~450 líneas (2 comandos + handlers) |

---

## PARTE 1: `src/keyboards/event.py` — 3 funciones nuevas

Todas las funciones de teclado de Phase 4 ya aceptan `prefix` como parámetro. Solo hay que AÑADIR 3 funciones nuevas.

### 1.1 — `events_edit_list_keyboard(events, prefix)`

```python
def events_edit_list_keyboard(
    events: list[dict], prefix: str = "editevent"
) -> InlineKeyboardMarkup:
    """Teclado de eventos para editar"""
    from datetime import datetime

    buttons = []
    for e in events:
        if e.get("ends_at") is not None:
            ends = (
                e["ends_at"]
                if isinstance(e["ends_at"], datetime)
                else datetime.fromisoformat(str(e["ends_at"]))
            )
            remaining = ends - datetime.utcnow()
            hours = remaining.total_seconds() / 3600
            if hours >= 24:
                time_str = f"{int(hours // 24)}d"
            else:
                time_str = f"{int(hours)}h"
        else:
            time_str = "∞"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {e['name']} (x{e['multiplier']} — {time_str})",
                    callback_data=f"{prefix}:event:{e['id']}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(text="❌ Cancelar", callback_data=f"{prefix}:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

### 1.2 — `event_status_keyboard(events, prefix)`

```python
def event_status_keyboard(
    events: list[dict], prefix: str = "toggleevt"
) -> InlineKeyboardMarkup:
    """Lista de eventos con toggle pausar/reanudar"""
    buttons = []
    for e in events:
        is_paused = e.get("is_paused", False)
        event_type = e.get("event_type", "one_time")
        status_icon = "⏸" if is_paused else "🟢"
        type_icon = {
            "one_time": "🔄",
            "daily_recurring": "🔁",
            "permanent": "♾",
        }.get(event_type, "🔄")

        if is_paused:
            action_text = f"▶️ Reanudar: {e['name']}"
        else:
            action_text = f"⏸ Pausar: {e['name']}"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{status_icon} {type_icon} {e['name']} (x{e['multiplier']})",
                    callback_data=f"{prefix}:info:{e['id']}",
                )
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=action_text,
                    callback_data=f"{prefix}:toggle:{e['id']}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text="❌ Cancelar", callback_data=f"{prefix}:cancel"
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

### 1.3 — `save_event_keyboard(prefix)`

```python
def save_event_keyboard(prefix: str = "editevent") -> InlineKeyboardMarkup:
    """Teclado de guardado para edicion de eventos"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Guardar cambios",
                    callback_data=f"{prefix}:save",
                ),
                InlineKeyboardButton(
                    text="❌ Cancelar",
                    callback_data=f"{prefix}:cancel",
                ),
            ],
        ]
    )
```

---

## PARTE 2: `src/handlers/admin/event_creator.py` — Cambios

### 2.1 — Nuevos imports

Agregar a la importacion existente de `src.keyboards.event`:

```python
from src.keyboards.event import (
    # ... todos los imports existentes de Phase 4 ...
    edit_event_field_keyboard,
    events_edit_list_keyboard,
    event_status_keyboard,
    save_event_keyboard,
)
```

### 2.2 — Nuevos StatesGroups

Agregar DESPUES de `DeleteEventState`:

```python
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
```

### 2.3 — Helper: `_load_event_to_state(event_id, state)`

Carga un evento de la BD al FSM state para edicion.

```python
async def _load_event_to_state(
    event_id: int, state: FSMContext
) -> dict | None:
    """Carga un evento existente al FSM state para edicion."""
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
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
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
```

### 2.4 — Helper: `_build_edit_summary(event_data)`

```python
def _build_edit_summary(ed: dict) -> str:
    """Resumen del evento que se esta editando."""
    lines = [
        f"✏️ <b>Editando:</b> <b>{ed.get('name', '')}</b>",
        f"📝 {ed.get('description', '')[:80]}",
        f"📅 Tipo: <b>{_TYPE_LABELS.get(ed.get('event_type', 'one_time'), '')}</b>",
        f"⚡ x{ed.get('multiplier', 1.0)}",
    ]
    return "\n".join(lines)
```

---

## PARTE 3: `/toggleevent` — Handlers completos (4 handlers)

### Handler 3.1: `/toggleevent` comando

```python
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
```

### Handler 3.2: Selección de grupo

```python
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
```

### Handler 3.3: Toggle de evento

```python
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

    # Recargar lista de eventos
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
```

### Handler 3.4: Cancelar

```python
@event_creator_router.callback_query(F.data == "toggleevt:cancel")
async def te_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Cancelado.</b>", parse_mode="HTML"
    )
    await callback.answer()
```

---

## PARTE 4: `/editevent` — Handlers completos (~25 handlers)

### Flujo del FSM

```
/editevent
  → select_group → ed:group:{chat_id}
  → select_event → ed:event:{event_id}  (carga evento al state)
  → select_field → ed:field:{field}
    → ed:field:name          → edit_name (texto)
    → ed:field:description   → edit_description (texto)
    → ed:field:multiplier    → edit_multiplier (ee:mult:1.5)
    → ed:field:schedule      → edit_type (ee:type:one_time)
    → ed:field:categories    → edit_rules_categories (ee:cat:{cat})
    → ed:field:time_letter   → edit_rules_time (ee:time:{val})
    → ed:field:scoring       → edit_rules_scoring (ee:bonus:{key})
  → confirm → ee:save / ee:cancel
```

### Handler 4.1: `/editevent` comando

```python
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
```

### Handler 4.2: Selección de grupo

```python
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
```

### Handler 4.3: Selección de evento → cargar al state

```python
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
```

### Handler 4.4: Selección de campo

```python
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
        et = ed.get("event_type", "one_time")
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

    else:
        await callback.answer("❌ Campo desconocido.", show_alert=True)
        return

    await callback.answer()
```

### Handler 4.5: Guardar nombre (texto)

```python
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
```

### Handler 4.6: Guardar descripción (texto)

```python
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
```

### Handler 4.7: Guardar multiplicador

```python
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
```

### Handler 4.8: Guardar tipo de evento

```python
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
```

### Handlers 4.9-4.14: Categorías (reutilizan prefix `ee:`)

```python
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
    cat = callback.data.split(":")[3]
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
    cat = callback.data.split(":")[3]
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
```

### Handlers 4.15-4.18: Tiempo (reutilizan prefix `ee:`)

```python
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
```

### Handlers 4.19-4.21: Bonificaciones (reutilizan prefix `ee:`)

```python
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
```

### Handler 4.22: Guardar cambios (persistir a BD)

```python
@event_creator_router.callback_query(F.data == "editevent:save")
async def ee_save(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    ed = data.get("event_data", {})
    event_id = ed.get("id")

    if not event_id:
        await callback.answer("❌ Error: no hay evento para guardar.", show_alert=True)
        return

    # Construir rules JSON desde rules_data
    rules_data = ed.get("rules_data", {})
    event_rules = EventRules(
        categories_enabled=rules_data.get(
            "categories_enabled", list(_DEFAULT_RULES.categories_enabled)
        ),
        categories_disabled=rules_data.get("categories_disabled", []),
        hidden_categories=rules_data.get("hidden_categories", []),
        mystery_category=rules_data.get("mystery_category"),
        time_override=rules_data.get("time_override"),
        time_decreasing=rules_data.get("time_decreasing", False),
        time_decreasing_amount=rules_data.get("time_decreasing_amount", 5),
        forced_letter=rules_data.get("forced_letter"),
        vowel_forced=rules_data.get("vowel_forced", False),
        no_duplicates_bonus=rules_data.get("no_duplicates_bonus", 0),
        bonus_all_filled=rules_data.get("bonus_all_filled", 0),
        speed_bonus=rules_data.get("speed_bonus", 0),
        speed_bonus_window=rules_data.get("speed_bonus_window", 8),
        streak_multiplier=rules_data.get("streak_multiplier", 1.0),
        penalty_empty=rules_data.get("penalty_empty", 0),
        comeback_bonus=rules_data.get("comeback_bonus", 0),
        double_points_last_round=rules_data.get("double_points_last_round", False),
        answer_reveal=rules_data.get("answer_reveal", False),
    )
    rules_json = event_rules.to_json()

    # Actualizar en BD
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
```

### Handler 4.23: Cancelar

```python
@event_creator_router.callback_query(F.data == "editevent:cancel")
async def ee_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Edición cancelada.</b>", parse_mode="HTML"
    )
    await callback.answer()
```

### Handler 4.24: Volver al menú de campos (via "✅ Guardar y salir")

```python
@event_creator_router.callback_query(F.data == "editevent:save")
# (Ya cubierto en Handler 4.22)
```

---

## PARTE 5: Teclado auxiliar `event_type_keyboard_for_edit()`

Para `/editevent` al cambiar tipo, el teclado necesita usar prefix `ee:` en vez de `ne:`. Opción simple: crear una función wrapper en el handler:

```python
def event_type_keyboard_for_edit() -> InlineKeyboardMarkup:
    """Teclado de tipo de evento para edicion (prefix ee:)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Temporal", callback_data="ee:type:one_time")],
            [InlineKeyboardButton(text="🔁 Diario Recurrente", callback_data="ee:type:daily_recurring")],
            [InlineKeyboardButton(text="♾ Permanente", callback_data="ee:type:permanent")],
        ]
    )
```

Definirla como función local dentro de `event_creator.py` (no en `keyboards/event.py`).

---

## PARTE 6: Tabla resumen de callbacks

### `/toggleevent` callbacks:

| Callback | Handler | Descripción |
|---|---|---|
| `toggleevt:group:{chat_id}` | `te_select_group` | Seleccionar grupo |
| `toggleevt:toggle:{event_id}` | `te_toggle_event` | Pausar/reanudar |
| `toggleevt:cancel` | `te_cancel` | Cancelar |

### `/editevent` callbacks:

| Callback | Handler | Descripción |
|---|---|---|
| `editevent:group:{chat_id}` | `ee_select_group` | Seleccionar grupo |
| `editevent:event:{event_id}` | `ee_select_event` | Seleccionar evento |
| `editevent:field:{field}` | `ee_select_field` | Seleccionar campo |
| `editevent:save` | `ee_save` | Guardar cambios |
| `editevent:cancel` | `ee_cancel` | Cancelar |
| `ee:mult:{val}` | `ee_process_multiplier` | Nuevo multiplicador |
| `ee:type:{type}` | `ee_process_type` | Nuevo tipo |
| `ee:cat:{cat}` | `ee_toggle_category` | Toggle categoría |
| `ee:cat_all` | `ee_select_all_categories` | Todas las categorías |
| `ee:rules_next` | `ee_rules_next` | Avanzar a opciones |
| `ee:cat_hidden:{cat}` | `ee_toggle_hidden` | Toggle hidden |
| `ee:cat_mystery:{cat}` | `ee_toggle_mystery` | Toggle mystery |
| `ee:options_next` | `ee_options_next` | Volver al menú |
| `ee:time:{val}` | `ee_select_time` | Tiempo por ronda |
| `ee:dec:{val}` | `ee_select_decreasing` | Decreciente |
| `ee:dec_confirm` | `ee_confirm_decreasing` | Confirmar decreciente |
| `ee:letter:{val}` | `ee_select_letter` | Letra forzada |
| `ee:bonus:{key}` | `ee_toggle_bonus` | Rotar bonus |
| `ee:bonus_next` | `ee_bonus_next` | Volver al menú |

---

## PARTE 7: Checklist de implementación

- [ ] Añadir `events_edit_list_keyboard()` a `keyboards/event.py`
- [ ] Añadir `event_status_keyboard()` a `keyboards/event.py`
- [ ] Añadir `save_event_keyboard()` a `keyboards/event.py`
- [ ] Añadir `EditEventState` y `ToggleEventState` a `event_creator.py`
- [ ] Añadir helper `_load_event_to_state()` a `event_creator.py`
- [ ] Añadir helper `_build_edit_summary()` a `event_creator.py`
- [ ] Añadir función local `event_type_keyboard_for_edit()` a `event_creator.py`
- [ ] Implementar 4 handlers de `/toggleevent`
- [ ] Implementar ~25 handlers de `/editevent`
- [ ] Añadir imports nuevos
- [ ] Ejecutar `pytest --tb=short`

### Comandos de verificación:
```bash
cd backend
pytest --tb=short -q
```
