# Fase 9: Actualización de visualización

## Estado: ❌ No implementada — Guía de implementación

---

## Resumen de entregables

| Entregable | Archivo | Complejidad |
|---|---|---|
| `_get_event_text()` mejorado | `game_orchestrator.py` | Baja (~30 líneas) |
| `/events` mejorado | `lobby.py` | Media (~40 líneas) |
| `_end_game()` mensaje mejorado | `round_manager.py` | Alta (~50 líneas) |
| `_build_summary()` con reglas del evento | `round_manager.py` | Baja (~15 líneas) |
| Timer message con info del evento | `round_manager.py` | Baja (~10 líneas) |

---

## 1. Mejorar `_get_event_text()` en `game_orchestrator.py`

### Ubicación actual
`game_orchestrator.py:652-665` — método estático de `LobbyManager`.

### Código actual
```python
@staticmethod
def _get_event_text(active_events: list[dict]) -> str:
    if active_events:
        ev = active_events[0]
        return f"🎉 <b>Evento: {ev['name']}</b> - x{ev['multiplier']} XP"
    return ""
```

### Qué hay que hacer
Reemplazar con una versión que muestre reglas clave del evento en el lobby:

**Estrategia:**
- Si `event["rules"]` es un `EventRules` object (lo es, ver `_parse_event_dict` en `event_service.py:344`), usamos sus métodos directamente
- Mostrar solo reglas **no-default** para no saturar
- Priorizar las reglas visualmente impactantes: letra forzada, tiempo override, categorías desactivadas, multiplicadores

### Código nuevo

```python
@staticmethod
def _get_event_text(active_events: list[dict]) -> str:
    if not active_events:
        return ""
    ev = active_events[0]
    rules = ev.get("rules")
    lines = [f"🎉 <b>Evento: {ev['name']}</b> — x{ev['multiplier']} XP"]

    # Usar métodos de EventRules si está disponible
    if rules and hasattr(rules, "get_round_time"):
        rt = rules.get_round_time(None)
        if rt is not None:
            lines.append(f"   ⏱ {rt}s por ronda")
            if rules.time_decreasing:
                lines.append(f"      📉 decreciente -{rules.time_decreasing_amount}s/ronda (mín {rules.time_minimum}s)")

        if rules.is_letter_forced():
            letter = rules.get_letter_for_round(1)
            if letter:
                if rules.letter_sequence:
                    seq = ", ".join(rules.letter_sequence)
                    lines.append(f"   🔤 Secuencia: {seq}")
                else:
                    lines.append(f"   🔤 Letra: {letter}")

        active = rules.get_active_categories()
        disabled = rules.categories_disabled
        if disabled:
            lines.append(f"   🚫 Sin: {', '.join(disabled)}")

        hidden = rules.hidden_categories
        if hidden:
            lines.append(f"   🎭 Ocultas: {', '.join(hidden)}")

        mystery = rules.mystery_category
        if mystery:
            lines.append(f"   🔮 Mystery: {mystery}")

        cat_mults = rules.category_multipliers
        if cat_mults:
            mults = ", ".join(f"{c} x{m}" for c, m in cat_mults.items())
            lines.append(f"   ⚡ Bonus: {mults}")

        if rules.speed_bonus:
            lines.append(f"   🏃 Speed: +{rules.speed_bonus} pts")

        if rules.sudden_death:
            lines.append(f"   💀 Modo Supervivencia")

        if rules.streak_multiplier > 1.0:
            lines.append(f"   🔥 Streak: x{rules.streak_multiplier}")

        if rules.no_stop:
            lines.append(f"   🚫 Sin botón Stop")

        if rules.double_points_last_round:
            lines.append(f"   �2 Última ronda doble")

        if rules.min_words_required:
            lines.append(f"   📝 Mínimo {rules.min_words_required} categorías")

    else:
        # Fallback si rules es dict o None
        _rules = rules or {}
        if _rules.get("time_override"):
            lines.append(f"   ⏱ {_rules['time_override']}s por ronda")
        if _rules.get("forced_letter"):
            lines.append(f"   🔤 Letra: {_rules['forced_letter']}")
        disabled = _rules.get("categories_disabled", [])
        if disabled:
            lines.append(f"   🚫 Sin: {', '.join(disabled)}")
        hidden = _rules.get("hidden_categories", [])
        if hidden:
            lines.append(f"   🎭 Ocultas: {', '.join(hidden)}")
        cat_mults = _rules.get("category_multipliers", {})
        if cat_mults:
            mults = ", ".join(f"{c} x{m}" for c, m in cat_mults.items())
            lines.append(f"   ⚡ Bonus: {mults}")

    return "\n".join(lines)
```

### Cómo se ve en el lobby

**Sin evento:**
```
🛑 STOP - Sala abierta

👤 Jugadores: 1/10

  1. Juan

⏱ Inicio automático en 30s tras la última incorporación...
```

**Con evento "Batalla de Categorías":**
```
🛑 STOP - Sala abierta

👤 Jugadores: 1/10

  1. Juan

🎉 Evento: 🔥 Batalla de Categorías — x2.0 XP
   ⏱ 45s por ronda
   🚫 Sin: Apellido, Fruta, Artista, Cosa
   ⚡ Bonus: País x3.0, Animal x2.0

⏱ Inicio automático en 30s tras la última incorporación...
```

**Con evento "Velocidad Extrema":**
```
🛑 STOP - Sala abierta

👤 Jugadores: 1/10

  1. Juan

🎉 Evento: ⚡ Velocidad Extrema — x1.5 XP
   ⏱ 15s por ronda
   🏃 Speed: +30 pts
   �2 Última ronda doble

⏱ Inicio automático en 30s tras la última incorporación...
```

---

## 2. Mejorar `/events` en `lobby.py`

### Ubicación actual
`lobby.py:129-162` — handler `cmd_events`.

### Código actual
```python
@game_router.message(Command("events"))
async def cmd_events(message: Message) -> None:
    if message.chat.type == "private":
        msg = await message.answer("❌ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    events = await event_service.get_active_events(message.chat.id)
    if not events:
        await message.answer("📭 No hay eventos activos en este grupo.")
        return

    lines = ["🎉 <b>Eventos activos en este grupo:</b>\n"]
    for e in events:
        event_type = e.get("event_type", "one_time")
        time_str = _format_event_time(e)
        lines.append(f"📌 <b>{e['name']}</b>\n   ⚡ x{e['multiplier']} XP")
        if time_str:
            lines[-1] += f" — ⏱ {time_str}"
        if e.get("description"):
            lines.append(f"   📝 {e['description']}")
        type_labels = {
            "one_time": "🔄 Temporal",
            "daily_recurring": "🔁 Diario recurrente",
            "permanent": "♾ Permanente",
        }
        lines.append(f"   📅 {type_labels.get(event_type, event_type)}")

    await message.answer("\n".join(lines), parse_mode="HTML")
```

### Qué hay que hacer
Añadir visualización de reglas activas del evento (similar a `_get_event_text()` pero por evento, no solo el primero).

### Código nuevo

```python
@game_router.message(Command("events"))
async def cmd_events(message: Message) -> None:
    if message.chat.type == "private":
        msg = await message.answer("❌ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    events = await event_service.get_active_events(message.chat.id)
    if not events:
        await message.answer("📭 No hay eventos activos en este grupo.")
        return

    lines = ["🎉 <b>Eventos activos en este grupo:</b>\n"]
    for e in events:
        event_type = e.get("event_type", "one_time")
        time_str = _format_event_time(e)

        # Línea principal: nombre + XP + tiempo
        lines.append(f"📌 <b>{e['name']}</b>")
        main_line = f"   ⚡ x{e['multiplier']} XP"
        if time_str:
            main_line += f" — ⏱ {time_str}"
        if e.get("is_paused"):
            main_line += " — ⏸ PAUSADO"
        lines.append(main_line)

        # Descripción
        if e.get("description"):
            lines.append(f"   📝 {e['description']}")

        # Tipo de evento
        type_labels = {
            "one_time": "🔄 Temporal",
            "daily_recurring": "🔁 Diario recurrente",
            "permanent": "♾ Permanente",
        }
        type_str = type_labels.get(event_type, event_type)
        if event_type == "daily_recurring":
            days = _format_active_days(e.get("active_days"))
            tz = e.get("timezone", "America/Argentina/Buenos_Aires")
            type_str += f" ({e.get('daily_start_hour', 0):02d}:{e.get('daily_start_minute', 0):02d}-{e.get('daily_end_hour', 23):02d}:{e.get('daily_end_minute', 59):02d}, {days})"
        lines.append(f"   📅 {type_str}")

        # Reglas activas
        rules = e.get("rules")
        if rules and hasattr(rules, "get_round_time"):
            if rules.has_rules():
                rule_parts = []
                rt = rules.get_round_time(None)
                if rt is not None:
                    rule_parts.append(f"⏱ {rt}s")
                if rules.is_letter_forced():
                    letter = rules.get_letter_for_round(1)
                    if letter:
                        rule_parts.append(f"🔤 {letter}")
                disabled = rules.categories_disabled
                if disabled:
                    rule_parts.append(f"🚫 Sin: {','.join(d[:3] for d in disabled)}")
                hidden = rules.hidden_categories
                if hidden:
                    rule_parts.append(f"🎭 {','.join(hidden)}")
                if rules.speed_bonus:
                    rule_parts.append(f"🏃 +{rules.speed_bonus}")
                if rules.sudden_death:
                    rule_parts.append("💀")
                if rules.no_stop:
                    rule_parts.append("🚫🛑")
                if rules.double_points_last_round:
                    rule_parts.append("�2")
                if rule_parts:
                    lines.append(f"   {' | '.join(rule_parts)}")

    await message.answer("\n".join(lines), parse_mode="HTML")
```

### Función helper `_format_active_days`

```python
def _format_active_days(active_days_json: str | None) -> str:
    """Convierte active_days JSON a string legible: 'Lun, Mar, Mié, Jue, Vie'"""
    if not active_days_json:
        return "todos los días"
    try:
        days = json.loads(active_days_json)
    except (json.JSONDecodeError, TypeError):
        return "todos los días"

    DAY_LABELS = {
        "mon": "Lun", "tue": "Mar", "wed": "Mié",
        "thu": "Jue", "fri": "Vie", "sat": "Sáb", "sun": "Dom",
    }
    labels = [DAY_LABELS.get(d, d) for d in days if d in DAY_LABELS]
    if not labels:
        return "todos los días"
    if len(labels) == 7:
        return "todos los días"
    return ", ".join(labels)
```

Añadir `import json` al inicio del archivo si no está.

### Cómo se ve `/events`

**Con 2 eventos:**
```
🎉 Eventos activos en este grupo:

📌 Copa Navideña
   ⚡ x2.0 XP — ⏱ queda 12h 30m
   📝 Torneo épico de Stop
   📅 Temporal
   🔤 M | ⏱ 45s | 🚫 Sin:Cosa

📌 Noche de Países
   ⚡ x5.0 XP — 🏃 queda 2h 15m
   📅 Diario recurrente (20:00-23:00, Mié, Vie)
   ⏱ 30s | 🏃 +30 | �2
```

**Con un evento diario recurrente:**
```
📌 Copa Navideña
   ⚡ x2.0 XP
   📅 Diario recurrente (18:00-22:00, Lun, Mar, Mié, Jue, Vie)
   💀
```

---

## 3. Mejorar `_end_game()` en `round_manager.py`

### Ubicación actual
`round_manager.py:1146-1348` — método `_end_game()`.

### Sección a modificar
`round_manager.py:1266-1311` — construcción del mensaje de fin de juego.

### Código actual
```python
lines = ["<b>🏆 ¡Partida finalizada!</b>", ""]
if winners:
    medals = ["🥇", "🥈", "🥉"]
    for i, (pid, score) in enumerate(winners[:3]):
        name = state.player_names.get(pid, f"Jugador {pid}")
        xp_info = xp_results.get(pid, {})
        xp_text = f" (+{xp_info.get('xp_gained', 0)} XP)" if xp_info else ""
        lines.append(f"{medals[i] if i < 3 else i + 1}. {name} — {score} pts{xp_text}")
        # ... level up ...
else:
    lines.append("  No hay puntuaciones registradas.")

from src.services.event_service import event_service
active_events = await event_service.get_active_events(state.group_chat_id)
for event in active_events:
    lines.append("")
    lines.append(f" <b>Evento en curso: {event['name']}</b> (x{event['multiplier']} XP)")

lines.append("")
lines.append("<i>Gracias por jugar 🛑 Stop!</i>")
```

### Qué hay que hacer
Mejorar el mensaje de fin de juego para que, si había un evento activo en la partida (`state.event_rules`), muestre:
1. El nombre y multiplicador del evento
2. Los bonus específicos aplicados durante la partida
3. Un detalle por jugador de los puntos extra ganados por el evento

### Estrategia
- Usar `state.event_rules` (NO `event_service.get_active_events()`) porque el evento pudo haber expirado durante la partida
- Recuperar el nombre del evento desde los datos de la ronda. `state.event_rules` no tiene nombre ni multiplier — solo las reglas. Necesitamos una forma de obtener el nombre/multiplier.
- **Solución:** Recordar el nombre del evento en `RoundState`. Añadir campos `event_name` y `event_multiplier`.

### Paso 1: Añadir campos a `RoundState`

```python
event_rules: dict | None = None
event_name: str | None = None       # NUEVO: nombre del evento para display
event_multiplier: float | None = None  # NUEVO: multiplier del evento
round_started_at: float | None = None
speed_bonus_claimed: bool = False
eliminated_player_ids: set[int] = field(default_factory=set)
```

### Paso 2: Pasar nombre y multiplier en `start_round()`

En `game_orchestrator.py:_do_start()`, cuando se llama a `start_round()`, pasar los nuevos campos:

```python
await round_manager.start_round(
    ...
    event_rules=event_rules.to_dict() if event_rules else None,
    event_name=db_event.name if db_event else None,
    event_multiplier=db_event.multiplier if db_event else None,
)
```

Y en `round_manager.py:start_round()`, aceptarlos:

```python
async def start_round(
    self,
    ...
    event_rules: dict | None = None,
    event_name: str | None = None,
    event_multiplier: float | None = None,
) -> None:
```

Y pasarlos al `RoundState`:

```python
state = RoundState(
    ...
    event_rules=event_rules,
    event_name=event_name,
    event_multiplier=event_multiplier,
)
```

**IMPORTANTE:** También hay que propagar estos campos en `_start_next_round_with_letter()` y `handle_letter_selection()` como se hace con `event_rules`.

### Paso 3: Mejorar el mensaje de fin de juego

Reemplazar la sección de eventos en `_end_game()`:

```python
# ── Evento activo: mostrar bonus aplicados ──
if state.event_rules and state.event_name:
    lines.append("")
    mult_text = f" x{state.event_multiplier}" if state.event_multiplier else ""
    lines.append(f"🎉 <b>Evento: {state.event_name}</b>{mult_text}")

    # Detalle de bonus por jugador (desde winners o desde el log)
    lines.append("   ⚡ Bonus aplicados:")
    for pid, score in winners:
        name = state.player_names.get(pid, f"Jugador {pid}")
        # Estos bonus deben haberse registrado en _persist_round_scores
        # y acumulado en state. Podemos agregar un dict opcional:
        # state.event_bonus_summary: dict[int, dict[str, int]]
        # Por ahora, mostrar mensaje genérico:
        lines.append(f"   • {name}: reglas del evento activas durante todas las rondas")
```

Pero esto es muy genérico. Para mostrar bonus reales, necesitamos acumular datos durante la partida.

### Estrategia avanzada: Acumular bonus por jugador

Para mostrar bonus reales en el fin de juego, necesitamos:
1. Acumular en `RoundState` un dict de bonus por jugador
2. En cada `_persist_round_scores()`, sumar los bonus aplicados
3. En `_end_game()`, mostrar el acumulado

**Añadir a RoundState:**
```python
# Acumulado de bonos del evento durante toda la partida (Fase 9)
event_bonus_summary: dict[int, dict[str, int]] = field(default_factory=dict)
# Ej: { player_id: {"category_multiplier": 60, "no_duplicates_bonus": 50} }
```

**En `_persist_round_scores()`**, después de aplicar los bonus, acumular:

```python
# Después de aplicar event_rules scoring modifiers en score_engine.evaluate()
# Los bonus se registran en state.event_bonus_summary
if state.event_rules:
    # Acumular bonus de esta ronda
    for pid in totals:
        if pid not in state.event_bonus_summary:
            state.event_bonus_summary[pid] = {}
        # Aquí sumaríamos los bonus individuales
        # (depende de cómo se implemente el tracking)
```

En realidad, para un tracking preciso, necesitaríamos que `ScoreEngine.evaluate()` retorne el desglose de bonus por jugador. Actualmente el log `score_evaluation` ya incluye `event_bonuses` en `eval_results`, así que podemos usar eso.

Mejor enfoque: **en `_end_game()`**, mostrar el evento y sus reglas, pero sin intentar acumular bonus por jugador (eso es Phase 8+ feature). Simplemente mostrar las reglas del evento que estuvieron activas:

```python
# ── Event info mejorado ──
if state.event_rules and state.event_name:
    lines.append("")
    mult_text = f" x{state.event_multiplier}" if state.event_multiplier else ""
    lines.append(f"🎉 <b>Evento: {state.event_name}</b>{mult_text}")
    try:
        _rules = EventRules.from_json(json.dumps(state.event_rules))
        rule_lines = []
        if _rules.category_multipliers:
            for cat, mult in _rules.category_multipliers.items():
                rule_lines.append(f"• {cat} x{mult}")
        if _rules.no_duplicates_bonus:
            rule_lines.append(f"• Respuesta única +{_rules.no_duplicates_bonus}")
        if _rules.bonus_all_filled:
            rule_lines.append(f"• Llenar todo +{_rules.bonus_all_filled}")
        if _rules.speed_bonus:
            rule_lines.append(f"• Speed bonus +{_rules.speed_bonus}")
        if _rules.double_points_last_round:
            rule_lines.append(f"• Última ronda x2")
        if _rules.sudden_death:
            eliminated = len(state.eliminated_player_ids)
            if eliminated:
                rule_lines.append(f"• 💀 {eliminated} jugador(es) eliminado(s)")
        if rule_lines:
            lines.append("   ⚡ Reglas del evento:")
            for rl in rule_lines:
                lines.append(f"     {rl}")
    except Exception:
        pass  # Si falla, simplemente no mostrar reglas
```

### Cómo se ve el fin de juego mejorado

**Sin evento:**
```
🏆 ¡Partida finalizada!

🥇 Juan — 350 pts (+87 XP)
🥈 María — 280 pts (+65 XP)
🥉 Pedro — 210 pts (+45 XP)

🎉 María ha subido al nivel 5! 🎖Aprendiz

Gracias por jugar 🛑 Stop!
```

**Con evento "Batalla de Categorías":**
```
🏆 ¡Partida finalizada!

🥇 Juan — 350 pts (+87 XP)
🥈 María — 280 pts (+65 XP)
🥉 Pedro — 210 pts (+45 XP)

🎉 Evento: 🔥 Batalla de Categorías x2.0
   ⚡ Reglas del evento:
     País x3.0
     Respuesta única +25
     Llenar todo +75

Gracias por jugar 🛑 Stop!
```

**Con evento "Modo Supervivencia" (con eliminados):**
```
🏆 ¡Partida finalizada!

🥇 Juan — 220 pts (+55 XP)
🥈 María — 180 pts (+40 XP)

🎉 Evento: 💀 Modo Supervivencia x1.5
   ⚡ Reglas del evento:
     Respuesta única +25
     🔥 Streak: x1.25
     💀 1 jugador(es) eliminado(s)

Gracias por jugar 🛑 Stop!
```

---

## 4. Mejorar `_build_summary()` en `round_manager.py`

### Ubicación actual
`round_manager.py:1502-1527` — método `_build_summary()`.

### Código actual
```python
@staticmethod
def _build_summary(round_scores: dict[int, int], state: RoundState) -> str:
    if not round_scores:
        return f"<b>📊 Ronda {state.round_number} — Resumen</b>\n  No se registraron puntuaciones."

    lines = [
        f"<b>📊 Ronda {state.round_number} — Resumen</b>",
        f"  Letra: <b>{state.letter}</b>",
        "",
    ]

    for pid, score in sorted(round_scores.items(), key=lambda x: x[1], reverse=True):
        name = state.player_names.get(pid, f"Jugador {pid}")
        lines.append(f"  {name}: {score} pts")

    if state.first_completer_name:
        lines.append("")
        lines.append(f"⭐ <b>{state.first_completer_name}</b> fue el primero en completar todas las categorías.")
        lines.append(f"  🏎️ Bonus velocidad: +{FIRST_COMPLETER_BONUS} pts")

    return "\n".join(lines)
```

### Qué hay que hacer
Si el evento tiene `hidden_categories` o `mystery_category`, revelarlas en el resumen.

### Código nuevo
```python
@staticmethod
def _build_summary(round_scores: dict[int, int], state: RoundState) -> str:
    if not round_scores:
        return f"<b>📊 Ronda {state.round_number} — Resumen</b>\n  No se registraron puntuaciones."

    lines = [
        f"<b>📊 Ronda {state.round_number} — Resumen</b>",
        f"  Letra: <b>{state.letter}</b>",
        "",
    ]

    for pid, score in sorted(round_scores.items(), key=lambda x: x[1], reverse=True):
        name = state.player_names.get(pid, f"Jugador {pid}")
        lines.append(f"  {name}: {score} pts")

    # ── Revelar categorías ocultas/mystery ──
    if state.event_rules:
        try:
            _rules = EventRules.from_json(json.dumps(state.event_rules))
            if _rules.hidden_categories or _rules.mystery_category:
                reveal_parts = []
                if _rules.hidden_categories:
                    reveal_parts.append(f"🎭 Ocultas: {', '.join(_rules.hidden_categories)}")
                if _rules.mystery_category:
                    reveal_parts.append(f"🔮 Mystery: {_rules.mystery_category}")
                if reveal_parts:
                    lines.append("")
                    lines.append("  " + " | ".join(reveal_parts))
        except Exception:
            pass

    if state.first_completer_name:
        lines.append("")
        lines.append(f"⭐ <b>{state.first_completer_name}</b> fue el primero en completar todas las categorías.")
        lines.append(f"  🏎️ Bonus velocidad: +{FIRST_COMPLETER_BONUS} pts")

    return "\n".join(lines)
```

---

## 5. Mejorar el timer de ronda con info del evento

### Ubicación actual
`round_manager.py:1726-1731` — `_format_round_message()`.

### Código actual
```python
@staticmethod
def _format_round_message(
    round_number: int, letter: str, categories: list[str], round_time: int
) -> str:
    cats_display = "\n".join(f"  <b>{cat}:</b> ..." for cat in categories)
    return f"⏱ {round_time} segundos\n\nEnvía tus respuestas en este formato:\n\n{cats_display}"
```

### Qué hay que hacer
Si el evento tiene `event_name` y reglas activas, mostrar el nombre del evento en el mensaje de la ronda. Esto requiere pasar el estado de la ronda a `_format_round_message()`.

### Estrategia
- Opción A: Pasar el nombre del evento como parámetro adicional
- Opción B: Convertir a método de instancia y usar `state`

**Opción recomendada (A):** Añadir parámetro opcional `event_display: str = ""`:

```python
@staticmethod
def _format_round_message(
    round_number: int, letter: str, categories: list[str], round_time: int,
    event_display: str = "",
) -> str:
    cats_display = "\n".join(f"  <b>{cat}:</b> ..." for cat in categories)
    lines = []
    if event_display:
        lines.append(event_display)
        lines.append("")
    lines.append(f"⏱ {round_time} segundos")
    lines.append("")
    lines.append("Envía tus respuestas en este formato:")
    lines.append("")
    lines.append(cats_display)
    return "\n".join(lines)
```

Y en `start_round()`, construir el `event_display`:

```python
event_display = ""
if event_name:
    event_display = f"🎉 <b>{event_name}</b>"

text = self._format_round_message(
    round_number, letter, display_categories, round_time,
    event_display=event_display,
)
```

### Cómo se ve con evento:
```
🎉 🔥 Batalla de Categorías

⏱ 45 segundos

Envía tus respuestas en este formato:

  Nombre: ...
  Color: ...
  País: ...
  Animal: ...
```

---

## 6. Importaciones necesarias

### `lobby.py` — añadir al inicio
```python
import json
```

### `round_manager.py` — ya tiene `json`, `EventRules`
Ya importamos `json` y `EventRules` en la Fase 8. Confirmar que estén:
```python
import json
from src.services.event_rules import EventRules
```

### `game_orchestrator.py` — sin cambios
No necesita imports nuevos (ya usa `event_service`).

---

## Resumen de cambios por archivo

| Archivo | Línea | Cambio |
|---|---|---|
| `game_orchestrator.py:652` | ~40 líneas | `_get_event_text()` mejorado con reglas |
| `lobby.py:101` | ~10 líneas | Añadir `import json` |
| `lobby.py:129` | ~50 líneas | `/events` handler mejorado con reglas |
| `lobby.py:163` | ~20 líneas | Nueva función `_format_active_days()` |
| `round_manager.py:66` | +2 campos | `event_name`, `event_multiplier` en `RoundState` |
| `round_manager.py:173` | ~5 líneas | `start_round()` acepta `event_name`, `event_multiplier` |
| `round_manager.py:220` | ~3 líneas | `RoundState()` recibe `event_name`, `event_multiplier` |
| `round_manager.py:1146` | ~35 líneas | `_end_game()` mejora mensaje de evento |
| `round_manager.py:1502` | ~15 líneas | `_build_summary()` revela hidden/mystery |
| `round_manager.py:1726` | ~15 líneas | `_format_round_message()` acepta `event_display` |

---

## Verificación

```bash
cd backend

# Compilar (no runtime, solo syntaxis)
python -c "import ast; ast.parse(open('src/services/game_orchestrator.py').read()); print('game_orchestrator OK')"
python -c "import ast; ast.parse(open('src/handlers/game/lobby.py').read()); print('lobby OK')"
python -c "import ast; ast.parse(open('src/services/round_manager.py').read()); print('round_manager OK')"

# Tests
pytest tests/ -q --tb=short
pytest tests/test_lobby.py -v
pytest tests/test_round_manager.py -v
```

---

## Notas importantes

1. **`event_data["rules"]` es un `EventRules` object**, no un dict. En `_parse_event_dict()` (event_service.py:330-350), el campo `rules` se convierte con `EventRules.from_json()`. Por lo tanto, cuando accedes a `ev["rules"]`, tienes un objeto `EventRules` con métodos como `.get_round_time()`, `.get_active_categories()`, `.is_letter_forced()`, etc. Usa esos métodos en vez de `.get("forced_letter")`.

2. **Campos disponibles en event dict** (de `_parse_event_dict`):
   - `id`, `name`, `description`, `multiplier`, `event_type`
   - `rules` → objeto `EventRules`
   - `is_paused`, `starts_at`, `ends_at`
   - `active_days`, `timezone`

3. **`RoundState.event_rules` es un dict**, no un `EventRules`. En `_do_start()`, se pasa `event_rules.to_dict()` (que solo contiene campos no-default). Para reconstruir un `EventRules` object, usa `EventRules.from_json(json.dumps(state.event_rules))`.

4. **Propagación de `event_name`/`event_multiplier`:** Al igual que `event_rules`, estos campos deben pasarse en:
   - `handle_letter_selection()` → `start_round()`
   - `_start_next_round_with_letter()` → `start_round()`
   - `_start_next_round_with_random()` → `_start_next_round_with_letter()` (ya cubierto)
   - `handle_skip_letter()` → `_start_next_round_with_letter()`

5. **Límite de mensajes de Telegram:** 4096 caracteres. El mensaje de fin de juego con muchos jugadores y bonus podría acercarse. Si pasa de 4000, considera truncar o enviar en múltiples mensajes.

6. **HTML escaping:** Todos los mensajes usan `parse_mode="HTML"`. Asegúrate de escaparr `&`, `<`, `>` en nombres de jugadores y eventos. Usa `html.escape()` si es necesario.
