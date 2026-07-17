# 🐛 Bugs, Issues, Improvements & Technical Debt — Stop Bot Game

> Análisis completo del codebase. Fecha: 17-Jul-2026
> Basado en revisión manual de `src/`, `handlers/`, `keyboards/`, `services/`, `bot.py`

---

## 🔴 CRÍTICOS (9)

---

### C1. Race `handle_skip_letter` — no popea `_letter_pending`

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:937-975` |
| **Descripción** | `handle_skip_letter` obtiene el state de `_letter_pending.get(game_id)` pero nunca hace `pop`. El timeout `_letter_timeout` también corre concurrentemente y llama `_start_next_round_with_letter`. |
| **Causa** | Falta `self._letter_pending.pop(game_id, None)` dentro del lock, después de verificar que el state existe. |
| **Consecuencia** | Dos llamadas a `start_round` para el mismo `game_id`: dos `Round` rows en BD, dos mensajes de ronda al grupo, el segundo sobrescribe `_rounds[game_id]`. |
| **Impacto actual** | Partida con rondas duplicadas. Jugadores ven dos imágenes de ronda. El timer de la primera ronda nueva colisiona con la segunda. |
| **Impacto de la resolución** | Elimina rondas duplicadas. El timeout y el skip button son mutuamente excluyentes. |

---

### C2. `_expire_timer` puede cancelar partida durante `_do_start`

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/game_orchestrator.py:311-336` |
| **Descripción** | `_expire_timer` espera `LOBBY_EXPIRE` (120s), luego checkea `state.started`. Si `_do_start` está ejecutándose concurrentemente y aún no ha seteado `state.started = True`, el timer ve `False`, elimina el mensaje del lobby y setea el juego a "cancelled" en BD. |
| **Causa** | `state.started` se setea dentro de `_do_start` bajo `start_lock`, pero `_expire_timer` lo checkea sin adquirir `start_lock`. |
| **Consecuencia** | Juego corrompido: BD muestra "cancelled" pero los jugadores ven la partida activa. Respuestas de ronda guardadas contra juego cancelado. Puntajes perdidos. |
| **Impacto actual** | Pérdida total de partidas que inician cerca del límite de expiración del lobby. |
| **Impacto de la resolución** | Previene la corrupción más destructiva del bot. |

---

### C3. `cancel_game` setea `_cancelled` fuera del lock

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:1398-1434` |
| **Descripción** | `cancel_game` escribe `self._cancelled[game_id] = True` ANTES de adquirir `self._lock_for(game_id)`. `_close_round` y otros handlers checkean `_cancelled` sin lock o con lock distinto. |
| **Causa** | El flag `_cancelled` se escribe como primera operación del método, antes del `async with self._lock_for`. |
| **Consecuencia** | TOCTOU: entre la escritura del flag y la adquisición del lock, otro handler puede leer `_cancelled=True` (y actuar en consecuencia) mientras la operación de cancelación aún no ha comenzado. |
| **Impacto actual** | Decisiones basadas en `_cancelled` pueden ser prematuras. Cancelación parcial. |
| **Impacto de la resolución** | Operación atómica: flag + acciones bajo el mismo lock. |

---

### C4. `join_lobby` race + `IntegrityError` no capturado

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/game_orchestrator.py:162-213` |
| **Descripción** | Dos jugadores llaman `join_lobby` simultáneamente. Ambos pasan las verificaciones (líneas 170-176) porque el state en memoria no se ha actualizado aún. El primero inserta en BD, el segundo recibe `IntegrityError` de la UNIQUE `(game_id, player_id)` — excepción no capturada. |
| **Causa** | No hay lock en `join_lobby`. Las verificaciones en memoria y BD no son atómicas. |
| **Consecuencia** | El estado en memoria (`state.player_telegram_ids.append`) ya se modificó antes de la inserción BD. El player aparece en el lobby pero no en la BD → juega pero no puntúa. Si el error se propaga, el handler muestra error al usuario pero el lobby ya lo registró. |
| **Impacto actual** | Jugador "fantasma" en el lobby. Scores perdidos. Handler puede crashear. |
| **Impacto de la resolución** | Transacción atómica: revertir cambios en memoria si BD falla. |

---

### C5. `_word_lists` mutado concurrentemente (data race)

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:80-82, 954` |
| **Descripción** | `_word_lists` es `dict[str, set[str]]`. `_track_task` lanza `add_to_word_list_persistent` como fire-and-forget task, que corre `self._word_lists[cat_lower].add(word)`. Concurrentemente, `validate`/`correct` itera `self._word_lists[cat_lower]`. |
| **Causa** | No hay sincronización en las operaciones de lectura/escritura de `_word_lists`. Las fire-and-forget tasks del corrector se ejecutan en el event loop intercaladas con otras coroutines. `set.add` durante `for word in set:` lanza `RuntimeError: Set changed size during iteration`. |
| **Consecuencia** | Evaluación de ronda crashea con `RuntimeError`. La partida termina abruptamente sin scores. |
| **Impacto actual** | Crash intermitente en rondas con validación AI/hybrid cuando el corrector aprende palabras nuevas concurrentemente. |
| **Impacto de la resolución** | Elimina crashes intermitentes. Operaciones sobre `_word_lists` protegidas con `asyncio.Lock`. |

---

### C6. `_track_task` crea 2 tasks por cada task tracked

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:87-101` |
| **Descripción** | `_track_task` recibe un `task` ya creado por el caller (que ya está corriendo en el event loop). Lo añade a `_pending_tasks` y además crea un `wrapper` que hace `await task`. El original corre sin error handling; el wrapper añade error handling pero nunca se añade al set. |
| **Causa** | El método acepta un `asyncio.Task` pre-creado. El caller ya lo puso en marcha con `asyncio.create_task()`. `_track_task` crea otro task que await al original → 2 tasks. |
| **Consecuencia** | Cada fire-and-forget del corrector corre dos tasks simultáneos. El original no tiene error handling. `flush_pending_tasks` espera el original pero el wrapper nunca se espera. |
| **Impacto actual** | El doble de tasks de los necesarios. Excepciones del task original silenciosas (no se loguean). |
| **Impacto de la resolución** | Tasks únicos con error handling. `flush_pending_tasks` realmente espera a los tasks. |

---

### C7. Gemini API endpoint incorrecto

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:422-423, 900-901` |
| **Descripción** | Cuando `spell_ai_provider = "gemini"`, el código postea a `{api_url}/chat/completions` con payload `{"model":..., "messages":...}`. Gemini real usa `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` con payload `{"contents":...}`. |
| **Causa** | El código asume que Gemini tiene API compatible con OpenAI (pasa por proxy). Si el usuario configura `AI_PROVIDER=gemini` sin un proxy compatible, todas las validaciones IA fallan. |
| **Consecuencia** | Validación IA siempre retorna error. Fallback a modo permisivo (acepta todo). Modo `hybrid`/`ai` funciona como `local` sin que el usuario lo sepa. |
| **Impacto actual** | Configuración Gemini no funcional. Usuarios que pagan por Gemini no obtienen validación IA real. |
| **Impacto de la resolución** | Gemini funcional con payload y endpoint correctos. Documentación de qué proxies OpenAI-compatibles funcionan. |

---

### C8. Button text Stop excede límite de Telegram (64 bytes)

| Campo | Detalle |
|---|---|
| **Archivo** | `src/keyboards/round.py:40` |
| **Descripción** | El texto del botón Stop: `"🛑 Stop 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜"` ≈ ~85+ bytes en UTF-8. Límite de Telegram para inline button text: 64 bytes. |
| **Causa** | Cada emoji 🟩/⬜ ocupa 4 bytes en UTF-8. 20 emojis = 80 bytes + "🛑 Stop " (8) + números (2-3) = ~90 bytes. |
| **Consecuencia** | `bot.edit_message_text(... reply_markup=stop_keyboard(...))` lanza `TelegramBadRequest: BUTTON_TEXT_INVALID`. El botón Stop nunca se actualiza. El progreso del contador no se refleja en la UI. |
| **Impacto actual** | El botón Stop se muestra siempre como "🛑 Stop [1/10]" sin cambios, incluso cuando otros jugadores presionan Stop. El jugador no sabe cuántas pulsaciones quedan. |
| **Impacto de la resolución** | Usar emojis más pequeños (⬜ sin variante) o reducir el número de emojis. O usar texto como "🛑 Stop (5/10)". |

---

### C9. Settings accesible por no-admins

| Campo | Detalle |
|---|---|
| **Archivo** | `src/handlers/game/settings.py` (todo el archivo) |
| **Descripción** | El comando `/settings` verifica que el usuario sea admin del grupo (línea 49). Pero los botones inline del menú de settings NO verifican admin. Cualquier jugador puede cambiar rondas, tiempo, categorías, modo de validación. |
| **Causa** | Los 14+ handlers de callback (`set_rounds`, `set_time`, `toggle_cat`, `toggle_n`, `set_mode`, etc.) no llaman a `is_admin` ni verifican permisos. |
| **Consecuencia** | Un jugador malicioso puede cambiar el tiempo a 30s, deshabilitar Ñ, cambiar a modo local (sin IA), o reducir las rondas a 1. Afecta la experiencia de todos los jugadores. |
| **Impacto actual** | Cualquier miembro del grupo puede sabotear la configuración de juego. |
| **Impacto de la resolución** | Solo admins pueden modificar settings. Botones inline verifican permisos antes de aplicar cambios. |

---

## 🟠 GRAVES (6)

---

### G1. `_close_round` invocado múltiples veces concurrentemente

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:444, 502, 1467` |
| **Descripción** | Tres callers pueden ejecutar `_close_round` para el mismo `game_id`: `submit_answers` (all_submitted, línea 444), `press_stop` (stop, línea 502), `_round_timer` (timeout, línea 1467). El pop atómico en línea 511 previene doble ejecución completa, pero `_persist_round_scores` se llama antes del pop en algunos paths. |
| **Causa** | `_close_round` se llama fuera de los locks de los callers. `submit_answers` suelta el lock (línea 432), luego llama `_close_round` (444). Entre medio, otro caller puede disparar el mismo `_close_round`. |
| **Consecuencia** | `_persist_round_scores` ejecutado dos veces → duplicación de rows o error de integridad. Mensajes duplicados al grupo. |
| **Impacto actual** | Posible doble evaluación de ronda. Scores duplicados o error 500. |
| **Impacto de la resolución** | Flag atómico "closing" dentro del lock para que solo un caller ejecute el cierre. |

---

### G2. `has_real_content` threshold = 3 caracteres

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:298` |
| **Descripción** | `all(len(v.strip()) >= 3 for v in parsed.values())` determina si el jugador "completó" todas las categorías. Palabras de 2 letras como "Ñu" (Animal), "Oca" (Animal — 3 letras, OK), "Uva" (Fruta — 3 letras, OK), pero "Al" (Al — 2 letras) o "En" (preposición — 2 letras para Cosa) no pasan. |
| **Causa** | Umbral arbitrario de 3 caracteres. No coincide con `_is_valid_word` que usa >= 2. |
| **Consecuencia** | `first_completer_id` nunca se setea si el jugador completa con palabras cortas. El botón Stop nunca aparece. Nadie recibe el bonus de +10 por primer completador. |
| **Impacto actual** | +10 puntos perdidos en partidas con palabras cortas. Mecánica de Stop no disponible hasta que alguien escribe palabras >= 3 letras. |
| **Impacto de la resolución** | Usar el mismo threshold que `_is_valid_word` (>= 2) o verificar cada respuesta individualmente. |

---

### G3. `validate_batch` cachea rejections falsas

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:676` |
| **Descripción** | `validate_batch` guarda en `_mem_cache` el resultado de validación AI como `"false"` si la IA rechazó la palabra. Si la IA se equivoca y rechaza una palabra válida, el error queda cacheado por 1 hora. Todos los demás jugadores que escriban la misma palabra reciben el rechazo automático sin consultar a la IA de nuevo. |
| **Causa** | Cache no distingue entre "IA dijo False" y "error de validación". El TTL de 1h es demasiado largo para un error de AI. |
| **Consecuencia** | Palabra válida considerada inválida para toda la partida (y hasta 1 hora después) por un error puntual de AI. |
| **Impacto actual** | Falsos negativos en validación de palabras. Jugadores pierden puntos por palabras que deberían ser válidas. |
| **Impacto de la resolución** | No cachear "false" de AI, o usar TTL de 5 minutos. Diferenciar "AI explicit reject" de "AI error/timeout". |

---

### G4. `close()` no flushea pending tasks

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:143-149` |
| **Descripción** | `close()` cierra Redis y HTTP pero no llama `flush_pending_tasks()`. Los fire-and-forget tasks de `add_to_word_list_persistent` pueden estar en mitad de una escritura BD cuando el bot se apaga. |
| **Causa** | El método `close()` fue diseñado para limpiar conexiones pero no considera las tareas de persistencia asíncronas. |
| **Consecuencia** | Word lists en BD pueden quedar inconsistentes (palabra añadida al set en memoria pero no a BD). Excepciones de BD durante shutdown propagándose sin control. |
| **Impacto actual** | Pérdida de palabras aprendidas por el corrector. Posibles errores en shutdown que ocultan otros problemas. |
| **Impacto de la resolución** | `await self.flush_pending_tasks()` al inicio de `close()` + cancelar tasks restantes con `return_exceptions=True`. |

---

### G5. `_end_game` hardcodea `unique_answers = 0`

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:1037` |
| **Descripción** | En `_end_game`, el dict `rankings` se construye con `"unique_answers": 0` fijo. Este valor se pasa a XP service que debería bonificar respuestas únicas. El cálculo real de unicidad nunca se propaga desde ScoreEngine. |
| **Causa** | El ScoreEngine calcula unicidad por ronda (`ScoreEngine.evaluate` detecta duplicados), pero ese dato no se almacena por jugador ni se suma entre rondas. |
| **Consecuencia** | `XP_PER_UNIQUE = 10` (bonus por respuesta única) nunca se otorga. Los jugadores no reciben recompensa por ser originales. |
| **Impacto actual** | Mecánica de "respuesta única" no funcional. Jugadores no tienen incentivo para evitar respuestas comunes. |
| **Impacto de la resolución** | Acumular unique_answers por jugador durante todas las rondas y pasarlo a `award_game_xp`. |

---

### G6. Dict `parsed` omite categorías con valor vacío

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:parse_answers` |
| **Descripción** | `parse_answers` detecta `...` / `…` / `. . .` / `..` y los convierte a `''` (vacío). Pero si el usuario escribe `Color: ` (solo espacio), la categoría no aparece en el dict de respuestas. Otras categorías como `Apellido: ...` sí aparecen con `''`. |
| **Causa** | El parser extrae el valor después de `:` con `(.*)` que puede capturar espacios. Pero si el valor es solo espacio, `LINE_REGEX` (que usa `\s*:\s*`) no matchea o el valor se descarta en el strip posterior. |
| **Consecuencia** | La categoría omitida recibe 0 puntos. Pero `answered_count` cuenta la categoría como respondida (porque aparece en el dict con `''`... o no, dependiendo de si aparece o no). |
| **Impacto actual** | Inconsistencia en el conteo de categorías respondidas vs omitidas. Jugador escribe `Color: ` y el parser no lo detecta como respuesta (ni siquiera como vacía). |
| **Impacto de la resolución** | Forzar que todas las categorías reconocibles aparezcan en el dict, con `''` si el valor está vacío o es solo espacio. |

---

## 🟡 ISSUES DE DISEÑO / PERFORMANCE (13)

---

### D1. `handle_letter_selection` llama `start_round` dentro del lock

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:912` |
| **Descripción** | `handle_letter_selection` adquiere el lock y dentro llama `await self.start_round(...)`. `start_round` envía mensajes Telegram (foto + texto), crea DB round, cancela timers → ~500ms-2s de I/O bloqueante. |
| **Causa** | El código protege la transición de estado (pop de `_letter_pending`) con el lock, pero incluye I/O pesado dentro de la sección crítica. |
| **Consecuencia** | `submit_answers`, `press_stop` y otros handlers que necesitan el mismo lock se bloquean durante 0.5-2s. En partidas de 10 jugadores, todos ven el bot congelado mientras el líder elige letra. |
| **Impacto actual** | Latencia de 0.5-2s en todos los handlers durante la selección de letra. |
| **Solución** | Solo proteger el pop de `_letter_pending` dentro del lock. `start_round` se llama fuera. |

---

### D2. `_do_close_round_telegram` — error en `_transition_next_round` deja el juego en limbo

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:650-668` |
| **Descripción** | `_do_close_round_telegram` llama `_transition_next_round` dentro de un `try:` que captura `Exception`. Si `_transition_next_round` falla (Telegram API, BD), el `except` popea `_letter_pending` y retorna. El juego queda sin estado: ni ronda activa, ni selección de letra, ni finalización. |
| **Causa** | `_letter_pending.pop(game_id)` en el `except` es cleanup ciego sin considerar que `_transition_next_round` podría reintentarse. |
| **Consecuencia** | Juego atascado. Grupo no puede iniciar nueva partida (hay un game "playing" en BD). Solo restart del bot lo rescata. |
| **Impacto actual** | Juego perdido. Jugadores frustrados. Dependencia de reinicio. |
| **Solución** | No popear `_letter_pending` en el except. Reintentar `_transition_next_round` o marcar el juego como "cancelled" en BD. |

---

### D3. `cmd_profile` en chat privado muestra siempre 0

| Campo | Detalle |
|---|---|
| **Archivo** | `src/handlers/game/profile.py:23` |
| **Descripción** | `group_chat_id = message.chat.id`. En chat privado, `message.chat.id` es el ID del chat privado, no un grupo. Todas las consultas BD filtran por este ID → no hay partidas → todo 0. |
| **Causa** | El handler no verifica `message.chat.type`. En chat privado no hay grupo para consultar stats. |
| **Consecuencia** | `/profile` en privado muestra XP y nivel correctos (globales) pero victorias, stops, leaderboard rank y streak como 0. |
| **Impacto actual** | Usuarios que usan `/profile` en privado ven datos incompletos. |
| **Solución** | Si chat es privado, omitir stats de grupo (victorias, stops, rank) y mostrar solo XP/level/streak globales. |

---

### D4. `/resolve` resuelve errores globalmente, sin filtrar por grupo

| Campo | Detalle |
|---|---|
| **Archivo** | `src/handlers/game/diagnose.py:80-86` |
| **Descripción** | `repo.get_unresolved()` no tiene filtro por `group_chat_id`. Un admin del Grupo A ejecuta `/resolve` y marca como resueltos TODOS los errores del sistema, incluyendo los del Grupo B. |
| **Causa** | El método `get_unresolved()` del repositorio no acepta `group_chat_id`. |
| **Consecuencia** | Errores del Grupo B desaparecen sin que su admin los vea. El admin del Grupo B no sabe que hubo errores. |
| **Impacto actual** | Pérdida de visibilidad de errores entre grupos. |
| **Solución** | Filtrar `get_unresolved` por `group_chat_id` y pasar el grupo del comando. |

---

### D5. `LobbyState` no tiene campo `cancelled`

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/game_orchestrator.py:251` |
| **Descripción** | `cancel_all_games` hace `state.cancelled = True` pero `LobbyState` (dataclass, líneas 36-51) no define `cancelled`. Python crea el atributo dinámicamente. `mypy` strict no lo aceptaría. |
| **Causa** | Omisión en la definición de la dataclass. |
| **Consecuencia** | `_expire_timer` no checkea `state.cancelled` → puede dispararse incluso para lobbies cancelados. Atributo dinámico frágil a refactors. |
| **Impacto actual** | Bajo (funciona en runtime) pero rompe type checking y es frágil. |
| **Solución** | Agregar `cancelled: bool = False` al `LobbyState` dataclass. |

---

### D6. `fuzzy_match` normaliza candidates en cada llamada

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:174-204` |
| **Descripción** | Cada llamada a `fuzzy_match` normaliza `word` y TODOS los `candidates` (que vienen de `_word_lists[cat_lower]`). Los candidates ya están normalizados porque se almacenaron normalizados. |
| **Causa** | `fuzzy_match` fue diseñado para usarse con candidates arbitrarios, pero los callers siempre pasan `_word_lists[cat]` que ya está normalizado. |
| **Consecuencia** | Normalización redundante de N candidates por cada fuzzy_match. Para 8 categorías, 10 jugadores: ~80 normalizaciones innecesarias por ronda. |
| **Impacto actual** | Overhead de CPU despreciable pero fácil de eliminar. |
| **Solución** | Opción `pre_normalized=False` en `fuzzy_match` o normalizar al insertar en `_word_lists`. |

---

### D7. `validate` aprende palabras incluso cuando AI falló

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:550-554` |
| **Descripción** | En el fallback permisivo (cuando API calls se agotaron o modo `local`), el código añade la palabra a `_word_lists` y dispara `add_to_word_list_persistent`. Palabras que la AI hubiera rechazado se "aprenden" permanentemente. |
| **Causa** | El código no distingue entre "modo = local" (siempre aprender) y "modo = hybrid pero API exhaurida temporalmente" (no aprender, solo aceptar para esta ronda). |
| **Consecuencia** | Si la API de AI tiene un outage temporal, palabras inválidas se agregan permanentemente a la word list. |
| **Impacto actual** | Word lists contaminadas con palabras no validadas. Validaciones futuras usando word lists aceptan palabras que deberían rechazar. |
| **Solución** | Flag de "aprendizaje" que solo se activa en modo `local` o cuando la AI validó explícitamente. |

---

### D8. `_debounced_update` creado dentro del lock — data race

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:386` |
| **Descripción** | `_debounced_update(state)` se llama dentro del lock (línea 369). Crea un `asyncio.create_task` que lee `state.submitted_player_ids` (un set de Python) para editar el mensaje de ronda. El task corre concurrentemente mientras el lock está retenido. |
| **Causa** | `_debounced_update` se invoca durante `submit_answers` que retiene el lock. El task interno accede a `state` sin copia ni lock. |
| **Consecuencia** | Data race: task lee `submitted_player_ids` mientras `submit_answers` lo modifica (línea 381). GIL hace que operaciones individuales sean atómicas, pero la iteración del set puede ver estado inconsistente. |
| **Impacto actual** | Bajo (raro que cause problema visible) pero es una race condition documentada. |
| **Solución** | Tomar snapshot de los campos necesarios bajo el lock y pasarlos al task. |

---

### D9. `_AnswerOverride` duck-typed como `Answer`

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/score_engine.py:130` |
| **Descripción** | `_AnswerOverride` es una clase local con `raw_text`, `score`, `correct` y algunos métodos. Se pasa a `cluster_answers` que espera objetos con `raw_text`. Si `cluster_answers` accede a otros campos (`.id`, `.normalized_text`), crashea. |
| **Causa** | Duck typing sin interfaz formal. `cluster_answers` fue diseñado para objetos `Answer` de SQLAlchemy. |
| **Consecuencia** | Si alguien modifica `cluster_answers` para usar más campos de `Answer`, `_AnswerOverride` no los tiene → `AttributeError`. |
| **Impacto actual** | Funciona porque `cluster_answers` solo usa `raw_text`. Frágil a cambios futuros. |
| **Solución** | `_AnswerOverride` podría heredar de una clase base o protocolo. O `cluster_answers` aceptar tuplas `(pid, raw_text)`. |

---

### D10. `_cleanup` no loguea errores del store deletion task

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/game_orchestrator.py:479` |
| **Descripción** | `asyncio.create_task(self._store.delete_lobby(state.group_chat_id))` es fire-and-forget sin error handling. Si el store (PostgreSQL) lanza excepción, el task falla silenciosamente. |
| **Causa** | Se priorizó no bloquear `_cleanup` esperando la operación de store. |
| **Consecuencia** | Lobby no eliminado del store persistente. Al reiniciar el bot, se restaura un lobby fantasma que ya no existe en BD ni en Telegram. |
| **Impacto actual** | Lobbies zombies que reaparecen tras restart. |
| **Solución** | `_safe_task` pattern: `asyncio.create_task(coro).add_done_callback(lambda t: logger.exception(...) if t.exception() else None)`. |

---

### D11. `_round_timer` loop sin check de round activo

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:1462-1469` |
| **Descripción** | El timer loopea `for _remaining in range(state.round_time, 0, -1)` con `await asyncio.sleep(1)`. No verifica si la ronda sigue activa. Si `cancel_game` cancela la ronda, el timer sigue ejecutándose hasta que el `await asyncio.sleep(1)` es interrumpido por el cancel. |
| **Causa** | El diseño asume que el timer es cancelado externamente (task.cancel()). Pero si el cancel falla (task ya estaba despierte), el timer continúa. |
| **Consecuencia** | `_close_round` llamado por timeout incluso después de que `cancel_game` ya cerró la ronda. El pop en `_close_round` retorna `None` y no hace nada, pero la función igual se ejecuta. |
| **Impacto actual** | Inocuo (el pop guard previene daño), pero ejecución innecesaria de código. |
| **Solución** | Check `if game_id not in self._rounds: return` dentro del loop. |

---

### D12. `_end_game` no incluye jugadores con score NULL en standings

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/round_manager.py:1190-1195` |
| **Descripción** | `_get_standings` filtra `GamePlayer.score.isnot(None)`. Jugadores que nunca enviaron respuestas (score NULL en BD) no aparecen en el podio ni en el log `game_finished`. |
| **Causa** | El query excluye NULL scores. Los jugadores inactivos desaparecen del resultado sin mención. |
| **Consecuencia** | El log `game_finished` reporta `total_players=2` pero `standings[]` tiene 1 entry. Inconsistencia. El jugador ausente no aparece en el podio. |
| **Impacto actual** | Podio y log inconsistentes cuando hay jugadores que nunca respondieron. |
| **Solución** | COALESCE(score, 0) y mostrar al jugador con 0 puntos. |

---

## 🔵 MEJORAS / FEATURES FALTANTES (26)

---

### F1. Botón "Abandonar partida" en lobby

| Campo | Detalle |
|---|---|
| **Descripción** | Jugadores que se unieron al lobby no pueden salir sin esperar 120s (expiración del lobby) o pedirle al host que cancele. |
| **Impacto actual** | Jugador atrapado en un lobby que no quiere jugar. Host no puede iniciar porque espera a ese jugador. |
| **Impacto de la implementación** | Botón "Salir" en el teclado del lobby. Elimina al jugador de BD y del state en memoria. Si era el host, transfiere host al siguiente jugador. |

---

### F2. Confirmación en `/clear_stats` y `/clear`

| Campo | Detalle |
|---|---|
| **Descripción** | Ambos comandos ejecutan inmediatamente sin confirmación. |
| **Impacto actual** | Admin escribe `/clear_stats` por error y pierde XP, niveles, rachas de TODOS los jugadores. Irreversible. |
| **Impacto de la implementación** | FSM state: "¿Estás seguro? Escribe /clear_stats confirmar". Timeout de 10s para cancelar. |

---

### F3. Mostrar tiempo restante en la ronda

| Campo | Detalle |
|---|---|
| **Descripción** | Los jugadores no saben cuánto tiempo les queda. Solo ven la letra y categorías. |
| **Impacto actual** | Jugadores se quedan sin tiempo porque no vieron el countdown. Respuestas incompletas. |
| **Impacto de la implementación** | Editar el mensaje de ronda cada 20s mostrando "⏱ 45s restantes".

---


### F4. Rankings globales (entre grupos)

| Campo | Detalle |
|---|---|
| **Descripción** | El leaderboard es por grupo. No hay competencia entre grupos. |
| **Impacto actual** | Jugadores en grupos pequeños siempre están top 3. No hay incentivo para mejorar contra la comunidad. |
| **Impacto de la implementación** | Leaderboard global semanal sumando puntos de todos los grupos. `/global_rank` para ver posición global. |

---

### F5. Historial de partidas por jugador

| Campo | Detalle |
|---|---|
| **Descripción** | No hay forma de ver respuestas de rondas anteriores. |
| **Impacto actual** | Jugador no puede revisar qué respondió en ronda 2. No hay aprendizaje ni revisión. |
| **Impacto de la implementación** | `/history` → últimas 5 partidas con resumen de rondas. |

---

### F6. Estadísticas de categoría

| Campo | Detalle |
|---|---|
| **Descripción** | `/profile` muestra stats globales pero no por categoría. |
| **Impacto actual** | Jugador no sabe si es bueno en Animales pero malo en Colores. |
| **Impacto de la implementación** | Tabla `player_category_stats` con accuracy por categoría. Mostrar top 3 categorías en perfil. |

---

### F7. Rachas visibles siempre en perfil

| Campo | Detalle |
|---|---|
| **Descripción** | La sección de streak solo se muestra si `streak > 0`. |
| **Impacto actual** | Jugador con racha rota (0) no ve ninguna info de streak. No sabe cuál fue su mejor racha. |
| **Impacto de la implementación** | Siempre mostrar: "🔥 Racha: 0 (máxima: 12)". |

---

### F8. Reset a valores por defecto en `/settings`

| Campo | Detalle |
|---|---|
| **Descripción** | No hay botón "Restablecer valores predeterminados". |
| **Impacto actual** | Admin que cambió config y no recuerda los defaults tiene que adivinarlos. |
| **Impacto de la implementación** | Botón "🔄 Reset" que restaura: 5 rondas, 60s, todas las categorías, ñ=no, modo=local. |

---

### F9. Preview de configuración

| Campo | Detalle |
|---|---|
| **Descripción** | Admin cambia settings pero no sabe cómo se verá el juego. |
| **Impacto actual** | Admin setea 4 categorías sin saber que el mensaje de ronda se verá incompleto. |
| **Impacto de la implementación** | Botón "👁 Vista previa" que envía un mensaje simulado de ronda con la config actual. |

---

### F10. Alerta de errores

| Campo | Detalle |
|---|---|
| **Descripción** | Errores silenciosos pasan desapercibidos hasta que un jugador reporta. |
| **Impacto actual** | Bug puede estar afectando partidas por horas sin que nadie lo sepa. |
| **Impacto de la implementación** | Si `error_rate > threshold` en los últimos 5 minutos, notificar al admin del grupo via DM. |

---

### F11. Endpoint `/debug` para estado interno

| Campo | Detalle |
|---|---|
| **Descripción** | Depurar requiere SSH a Alwaysdata o leer logs. |
| **Impacto actual** | No hay forma rápida de ver lobbies activos, rondas en curso, estado del corrector. |
| **Impacto de la implementación** | `/debug` en el health_server retorna JSON con: `_lobbies`, `_rounds`, `_letter_pending`, API counters, Redis status, pool BD. |

---

### F12. Historial de palabras del jugador

| Campo | Detalle |
|---|---|
| **Descripción** | No hay diccionario personal. |
| **Impacto actual** | Jugador no puede ver qué palabras ha usado antes en cada categoría. |
| **Impacto de la implementación** | Tabla `player_word_history`. `/mywords` muestra las 3 palabras más usadas por categoría. |

---

### F13. Torneos semanales configurables

| Campo | Detalle |
|---|---|
| **Descripción** | No hay eventos automáticos. Solo el leaderboard semanal que es pasivo. |
| **Impacto actual** | No hay razón para jugar en un día específico. La actividad es esporádica. |
| **Impacto de la implementación** | `/schedule_tournament` que permite a los usuarios configurar torneos de partidas dias especificos, rondas y lo que sugieras. Con registro previo. |

---

### F14. Logros desbloqueables visibles

| Campo | Detalle |
|---|---|
| **Descripción** | No hay logros más allá del nivel. |
| **Impacto actual** | Jugador llega a nivel 10 pero no hay hitos intermedios que celebrar. |
| **Impacto de la implementación** | Tabla `achievements`. Logros como "Primera victoria", "Racha de 5", "100 partidas", "Stop maestro (10 stops)", "Políglota (portugués+español)". Mostrar en perfil. |

---

## 🔧 DEUDA TÉCNICA (8)

---

### T1. `_track_task` acepta coroutine, no task pre-creado

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:87-101` |
| **Descripción** | El método debería aceptar `Coroutine` y crear un solo `Task` internamente. Actualmente acepta un `Task` ya creado y crea un wrapper. |
| **Solución** | `def _track_task(self, coro: Coroutine) -> asyncio.Task:` → un solo `task = asyncio.create_task(self._wrap(coro))` con `_wrap` que await + log + discard. |

---

### T2. `_is_valid_word` importado dentro de `cluster_answers`

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:224` |
| **Descripción** | `from src.services.score_engine import _is_valid_word` dentro de la función. Ejecutado en cada llamada. |
| **Solución** | Mover al tope del archivo. Si hay circular import, extraer `_is_valid_word` a `src/core/text_utils.py`. |

---

### T3. `reset_api_counter` no llama `reset_validation_source`

| Campo | Detalle |
|---|---|
| **Archivo** | `src/services/spell_corrector.py:105` |
| **Descripción** | `reset_api_counter` resetea contadores pero no limpia `_validation_source`. El fix A2 (por game_id) agregó `reset_validation_source(game_id)` que debe llamarse explícitamente en `start_round`. |
| **Solución** | Resetear `_validation_source` dentro de `reset_api_counter` o documentar que debe llamarse a `reset_validation_source` por separado. |

---

### T4. 7 handlers sin `@error_tracker.track_errors`

| Campo | Detalle |
|---|---|
| **Archivo** | `leaderboard.py`, `stats.py`, `profile.py`, `settings.py`, `clear.py`, `clear_stats.py`, `diagnose.py` |
| **Descripción** | Errores en estos handlers no se registran en `error_logs`. `/diagnose` no los ve. |
| **Solución** | Agregar `@error_tracker.track_errors(handler_name=...)` a todos los handlers. |

---

### T5. `strftime("%a")` depende del locale del servidor

| Campo | Detalle |
|---|---|
| **Archivo** | `src/handlers/game/stats.py:81` |
| **Descripción** | `row.day.strftime("%a")` retorna "Mon" en servidor inglés, "lun" en español. |
| **Solución** | Usar `calendar.day_name` con locale forzado al español, o mapear manualmente `{0: "lun", 1: "mar", ...}`. |

---

### T6. Handlers sin guard `message.from_user`

| Campo | Detalle |
|---|---|
| **Archivo** | `stats.py:25`, `profile.py:18`, `settings.py:49`, `clear.py:25`, `clear_stats.py:21` |
| **Descripción** | Estos handlers acceden a `message.from_user.id` sin verificar que `from_user` no sea `None`. En canales anónimos, `from_user` puede ser `None`. |
| **Solución** | `if not message.from_user: return` al inicio del handler. |

---

### T7. Typos

| Campo | Detalle |
|---|---|
| **Archivo** | `clear.py:65` |
| **Descripción** | `"pra"` debería ser `"para"`. |
| **Solución** | `s/pra/para/` |

---

### T8. Typos en estadísticas

| Campo | Detalle |
|---|---|
| **Archivo** | `stats.py:26`, `clear_stats.py:25` |
| **Descripción** | `"estadisticas"` debería ser `"estadísticas"` (con acento). |
| **Solución** | Agregar acento en la i. |

---

## 📊 PRIORIDAD SUGERIDA

| Prioridad | Item | Esfuerzo | Impacto | Área |
|---|---|---|---|---|
| 1 | **C2** — `_expire_timer` cancela partida durante `_do_start` | 3 líneas | Elimina corrupción de partidas | Race condition |
| 2 | **C5** — `_word_lists` data race (crashes) | 10 líneas | Elimina crash intermitente | Race condition |
| 3 | **C1** — `handle_skip_letter` no popea `_letter_pending` | 1 línea | Elimina rondas duplicadas | Race condition |
| 4 | **C9** — Settings accesible por no-admins | 20 líneas | Seguridad del grupo | Auth bypass |
| 5 | **C8** — Stop button excede 64 bytes | 1 línea | Botón funcional | Bug UI |
| 6 | **C4** — `join_lobby` race + IntegrityError | 15 líneas | Previene jugador fantasma | Race condition |
| 7 | **G2** — `has_real_content` threshold 3 chars | 1 línea | Stop funciona con palabras cortas | Bug scoring |
| 8 | **G5** — `unique_answers = 0` hardcodeado | 20 líneas | XP por originalidad funciona | Missing feature |
| 9 | **G1** — `_close_round` llamado múltiples veces | 5 líneas | Previene doble evaluación | Race condition |
| 10 | **F4** — Confirmación en /clear_stats | 30 líneas | Previene borrado accidental | UX safety |


🐛 G1-G6: Bugs
- ✅ G1 — Doble cierre de ronda
- ✅ G2 — ":" con texto vacío se cuenta como vacío
- ✅ G3 — Modo AI no cachea falsos positivos
- ✅ G4 — /diagnose muestra métricas API sin error
- ✅ G5 — XP/rachas con valores correctos
- ✅ G6 — 8 categorías parseadas siempre (faltantes como vacío)

🎨 D1-D12: Diseño
- ✅ D1 — Sin race condition al elegir letra
- ✅ D2 — Error de Telegram cancela partida en BD
- ✅ D3 — /profile en privado funciona
- ✅ D4 — /resolve solo marca errores del grupo
- ✅ D5 — Cancelar partida → cancelled = True
- ✅ D6 — Fuzzy match funciona (kasa → casa)
- ✅ D7 — Modo AI sin API → acepta sin aprender
- ✅ D8 — Puntuaciones consistentes
- ✅ D10 — Shutdown sin warnings de tareas
- ✅ D11 — Timer expira justo al cerrar ronda → no crashea
- ✅ D12 — Score NULL → 0 pts

🧹 T1-T8: Tech Debt
- ✅ T4 — Todos los handlers decorados con @error_tracker
- ✅ T6 — Handler no crashea sin from_user

✨ F1-F3, F8-F11: Features

F1 — Salir del lobby
✅ - Botón "🚪 Salir" visible en lobby
✅ - ❌ Host sale → transferencia de host → CORREGIDO (faltaba .values(is_host=True))
✅ - Sin jugadores → lobby se cancela

F2 — Confirmación clear/clear_stats
- ✅ /clear pide confirmación
- ✅ /clear confirmar funciona
- ✅ /clear confirmar expirado → "tiempo expirado"
- ✅ /clear_stats pide confirmación
- ✅ /clear_stats confirmar funciona

F3 — Countdown en rondas
- ✅ Mensaje se actualiza a los 40s, 20s y 5s restantes

F8 — Reset settings
- ✅ Botón "🔄 Resetear" visible en /settings
- ✅ Vuelve a valores default

F9 — Preview settings
- ✅ Botón "👁 Ver configuración" visible
- ✅ Muestra resumen completo

F10 — Alertas de error a admins
- ✅ Forzar error crítico → admin recibe DM

F11 — /debug
- ✅ /debug muestra estado interno del bot
- ✅ No-admin es rechazado