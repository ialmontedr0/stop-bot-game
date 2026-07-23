# Fase 7: Integración con `/stop` — Selección de modo de juego

## Estado: ✅ COMPLETADA

Esta fase ya fue implementada en sesiones anteriores. Este documento documenta el estado actual.

---

## Resumen de lo implementado

| Entregable | Estado | Ubicación |
|---|---|---|
| `LobbyState.event_id` | ✅ | `game_orchestrator.py:62` |
| `create_lobby(event_id=)` | ✅ | `game_orchestrator.py:129` |
| `_do_start()` carga EventRules desde BD | ✅ | `game_orchestrator.py:515-575` |
| `cmd_stop` verifica eventos activos | ✅ | `lobby.py:42-56` |
| `callback_mode_normal` | ✅ | `lobby.py:183-198` |
| `callback_mode_event` | ✅ | `lobby.py:201-213` |
| `callback_select_event` | ✅ | `lobby.py:216-256` |
| `mode_selection_keyboard()` | ✅ | `keyboards/lobby.py:24-42` |
| `event_selection_keyboard()` | ✅ | `keyboards/lobby.py:45-57` |
| `_get_event_text()` | ✅ | `game_orchestrator.py:650-660` |
| Event rules propagadas a `start_round()` | ✅ | `game_orchestrator.py:570-575` |

---

## Arquitectura implementada

### Flujo actual

```
Usuario: /stop
  │
  ├─ cmd_stop() verifica has_active_event()
  │
  ├─ NO hay eventos → create_lobby(event_id=None) → lobby normal
  │
  └─ SÍ hay eventos → "🟢 ¿Cómo quieres jugar?"
           │
           ├─ [🎮 Modo Normal] → callback_mode_normal()
           │   └─ create_lobby(event_id=None) → lobby normal
           │
           └─ [🎉 Con Evento] → callback_mode_event()
                └─ Muestra eventos activos
                     │
                     ├─ [🎉 Evento (x2.0)] → callback_select_event()
                     │   └─ create_lobby(event_id=42) → lobby con evento
                     │
                     └─ [❌ Cancelar] → cierra mensaje
```

### Decisión de diseño: Solo `event_id`, no `event_rules`

El plan original proponía guardar `event_rules: dict | None` en `LobbyState`. Se implementó **solo `event_id: int | None`** y se recargan las reglas desde BD en `_do_start()`. Razones:

1. **Serialización:** `LobbyState` se persiste en Redis via `GameStateStore`. `EventRules` es un dataclass complejo que no serializa directamente.
2. **Robustez:** Si se edita un evento mientras el lobby está abierto, `_do_start()` lee la versión más reciente de BD.
3. **Simplicidad:** Solo se serializa un `int | None` en vez de un dict completo.

### Propagación de reglas

```
_do_start():
  1. Carga event_rules desde BD via EventRules.from_json()
  2. Aplica categorías: event_rules.get_active_categories() → categories
  3. Aplica tiempo: event_rules.get_round_time(default) → round_time
  4. Aplica letra: event_rules.get_letter_for_round(1) → letter
  5. Pasa event_rules.to_dict() a start_round()
```

### Callbacks implementados

#### `cmd_stop` (`lobby.py:30-56`)
```python
@game_router.message(Command("stop"))
async def cmd_stop(message, player, bot):
    has_events = await event_service.has_active_event(message.chat.id)
    if has_events:
        keyboard = mode_selection_keyboard()
        await message.answer("🟢 ¿Cómo quieres jugar?", reply_markup=keyboard)
        return
    result = await lobby_manager.create_lobby(...)
```

#### `callback_mode_normal` (`lobby.py:183-198`)
```python
@game_router.callback_query(F.data == "mode:normal")
async def callback_mode_normal(callback, player, bot):
    result = await lobby_manager.create_lobby(
        group_chat_id=callback.message.chat.id,
        host_player=player, bot=bot, event_id=None,
    )
    # ... send/delete message
```

#### `callback_mode_event` (`lobby.py:201-213`)
```python
@game_router.callback_query(F.data == "mode:event")
async def callback_mode_event(callback, player, bot):
    events = await event_service.get_active_events(callback.message.chat.id)
    keyboard = event_selection_keyboard(events, prefix="select_event")
    await callback.message.edit_text("📌 Selecciona el evento:", reply_markup=keyboard)
```

#### `callback_select_event` (`lobby.py:216-256`)
```python
@game_router.callback_query(F.data.startswith("select_event:"))
async def callback_select_event(callback, player, bot):
    event_id = int(parts[1])
    # Verificar que el evento sigue activo
    events = await event_service.get_active_events(callback.message.chat.id)
    valid_ids = {e["id"] for e in events}
    if event_id not in valid_ids:
        await callback.answer("❌ Este evento ya no está activo.")
        return
    result = await lobby_manager.create_lobby(
        group_chat_id=callback.message.chat.id,
        host_player=player, bot=bot, event_id=event_id,
    )
```

---

## Archivos involucrados

| Archivo | Cambios realizados | Líneas |
|---|---|---|
| `src/handlers/game/lobby.py` | `cmd_stop` modificado + 3 callbacks nuevos + imports | 256 líneas |
| `src/keyboards/lobby.py` | +2 funciones (`mode_selection_keyboard`, `event_selection_keyboard`) | 57 líneas |
| `src/services/game_orchestrator.py` | `LobbyState.event_id`, `create_lobby(event_id=)`, `_do_start()` carga eventos | 694 líneas |

---

## Verificación

### Tests manuales en Telegram
1. **Sin eventos:** `/stop` → lobby se crea directamente
2. **Con 1 evento activo:** `/stop` → keyboard "Modo Normal / Con Evento"
3. **Modo Normal:** Click → lobby sin event_id
4. **Con Evento → seleccionar:** Click evento → lobby con event_id
5. **Con Evento → cancelar:** Click cancelar → se cierra
6. **Auto-start con evento:** 2+ jugadores → auto-start → reglas del evento se aplican

### Tests pytest
```bash
cd backend
pytest tests/test_game_orchestrator.py -v
pytest tests/test_lobby.py -v
pytest -k "event" -v
```

---

## Siguiente fase

**Fase 8:** Propagación de reglas del evento al juego activo (ScoreEngine).

La propagación a `RoundManager` y `start_round()` ya está implementada en esta fase.
Falta la integración con `ScoreEngine` para aplicar bonificaciones del evento.
