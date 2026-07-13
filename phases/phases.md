# 🛑 Stop Bot — Development Phases

> **Arquitectura:** Python 3.11+ · `aiogram 3.x` · `PostgreSQL` + `Redis` · `SQLAlchemy 2.0` · `OpenAI API` / `spaCy`  
> **Duración estimada:** 8–10 semanas (tiempo completo)  
> **Versión:** 1.0

---

## Fase 0 — Fundación del proyecto

**Objetivo:** Esqueleto del bot, base de datos, infraestructura core.

### Tareas

- [x] 0.1 Crear repositorio, estructura de directorios y entorno virtual.
- [x] 0.2 Configurar `poetry` o `pip` + `requirements.txt`.
- [x] 0.3 Docker-compose: `postgres:16`, `redis:7`, `app`.
- [x] 0.4 Modelo de datos (SQLAlchemy):
  - `Player(id, telegram_id, username, first_name, last_name, language_code, created_at)`
  - `Game(id, group_chat_id, status, current_round, total_rounds, created_at, finished_at)`
  - `GamePlayer(id, game_id, player_id, score, joined_at)`
  - `Round(id, game_id, round_number, letter, status, started_at, stopped_at)`
  - `Answer(id, round_id, player_id, word_slot, raw_text, normalized_text, is_correct, score)`
  - `WeeklyLeaderboard(id, player_id, week_start, total_score, games_played, rank)`
- [x] 0.5 Migration system con `alembic`.
- [x] 0.6 Fábrica de `Application` de aiogram con `Dispatcher`, `Router`, `FSM` storage en Redis.
- [x] 0.7 Middleware: `Throttling`, `UserExistsMiddleware` (crea Player si no existe).
- [x] 0.8 Estructura de ficheros propuesta:

```
src/
├── bot.py                  # Entry-point
├── config.py               # Pydantic Settings
├── db/
│   ├── engine.py
│   ├── models.py
│   └── repositories/       # CRUDs por entidad
├── middlewares/
├── handlers/
│   ├── start.py
│   ├── group.py
│   └── game/
├── services/
│   ├── game_orchestrator.py
│   ├── score_engine.py
│   ├── spell_corrector.py
│   └── leaderboard.py
├── keyboards/
├── filters/
└── utils/
```

**Entregable:** Bot responde `/start`, `/help`. Base corriendo con Docker.

ESTADO DE LA FASE: LISTA (ver phase0-guide.md)

---

## Fase 1 — Registro de grupos y unión a partidas

**Objetivo:** Unir jugadores a una sala de juego dentro de un grupo.

### Tareas

- [x] 1.1 Detectar cuando el bot es añadido a un grupo (`my_chat_member` → `ChatMemberHandler`).
- [x] 1.2 Comando `/stop` — inicia lobby en el grupo.
- [x] 1.3 Bot genera un mensaje con:
  - Texto animado (editing message) con `"🛑 STOP — Sala abierta"`
  - Contador de jugadores: `👤 X / 10`
  - Botón **«🟢 Unirse»** (inline) — cualquiera en el grupo puede unirse.
  - Botón **«▶️ Iniciar»** (solo visible para el host — primer usuario que ejecutó `/stop`).
- [x] 1.4 Al pulsar «Unirse»:
  - Se añade `GamePlayer` con `joined_at = now()`.
  - Si llega a 10 → **auto-start** (ver Fase 2).
- [x] 1.5 Cada 5s el bot actualiza el mensaje del lobby con el nuevo contador.
- [x] 1.6 Temporizador de expiración: si no se une nadie tras 2 min, el lobby se cierra.
- [x] 1.7 Si se pulsa «Iniciar» (host) → saltar a Fase 2.
- [x] 1.8 Validaciones:
  - No se puede unir una partida ya iniciada.
  - Un jugador no puede unirse dos veces.
  - Solo el host puede iniciar (a menos que se cumpla condición de 10 o timeout).

**Entregable:** Lobby funcional, unión de hasta 10 jugadores, inicio manual/automático.

ESTADO DE LA FASE: LISTA (ver el phase1-guide.md)

---

## Fase 2 — Ciclo de ronda: letra, envío, Stop y evaluación

**Objetivo:** Núcleo del juego — rondas completas con temporizador, Stop, y puntuación.

### Tareas

- [x] 2.1 **Selección de letra (primera ronda):**
  - Random con `random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")`.
  - Excluir Ñ (o incluirla según región configurable).
- [x] 2.2 **Temporizador de ronda:** 60s controlado con `asyncio.create_task` + `Redis` expiry como fallback.
- [x] 2.3 **Plantilla de categorías** (8-12 fijas, ej.):
  - Nombre, País/Ciudad, Animal, Comida, Objeto, Profesión, Deporte, Color, Marca, Verbo, Película, Planta.
- [x] 2.4 Bot envía mensaje formateado con la letra y las categorías:
  ```
  🛑 Ronda 1 — Letra: **F**
  ⏱ 60 segundos

  Envía tus respuestas en este formato:

  Nombre: ...
  País/Ciudad: ...
  Animal: ...
  ...
  ```
- [x] 2.5 **Parser de respuestas:**
  - Regex que extrae `categoría: valor`.
  - Ignora mayúsculas/minúsculas, espacios extra.
  - Devuelve `dict[Categoría, str]`.
  - Si el formato no es válido o faltan categorías → respuesta rechazada con botón «Reintentar».
- [x] 2.6 **Normalización y fuzzy matching** (ver Fase 4): en esta fase solo guardamos raw_text.
- [x] 2.7 **Sistema Stop:**
  - Cuando el primer jugador envía una respuesta **completa** (todas las categorías rellenas) → el bot le responde en privado con botón **«⏹ Stop»**.
  - Otros jugadores NO ven este botón.
  - Timeout del botón: 5s.
  - Al pulsar Stop → la ronda se cierra inmediatamente.
  - Si nadie hace Stop → la ronda termina a los 60s.
- [x] 2.8 **Cierre de ronda:**
  - Bot edita el mensaje del grupo: `"⏹ Ronda detenida"` o `"⌛ Tiempo agotado"`.
  - Llama al `ScoreEngine` (Fase 3).
- [x] 2.9 **Mostrar puntuación parcial:** Bot envía resumen de puntos de la ronda.
- [x] 2.10 **Transición a siguiente ronda:**
  - El líder (máximo puntaje acumulado) recibe inline keyboard con el alfabeto.
  - Selecciona letra → 5s countdown → nueva ronda.
  - Si hay empate, elige el primero en llegar a esa posición.

**Entregable:** Ronda completa con temporizador, envío de respuestas, Stop y transición.

ESTADO DE LA FASE: LISTA (ver phase2-guide.md)

---


## Fase 3 — Motor de puntuación (Score Engine)

**Objetivo:** Evaluar respuestas, calcular puntos, detectar duplicados.

### Tareas

- [x] 3.1 `ScoreEngine.evaluate(round_id, answers_by_player)`:
  - Agrupa respuestas por categoría.
  - Para cada categoría detecta **duplicados exactos** (y fuzzy en Fase 4).
  - Asigna puntos:
    - `50` si única y correcta.
    - `50 / N` si N jugadores dieron la misma respuesta (ej: 3 → 16.66 c/u, truncado a entero o 2 decimales).
    - `0` si vacía o incorrecta.
  - Bonus de velocidad: el jugador que hizo Stop recibe `+10` extra.
- [x] 3.2 Criterio de "respuesta correcta":
  - Por ahora: cualquier palabra que no esté vacía y sea alfabética (+ espacios, guiones).
  - En Fase 4 se añade validación semántica con IA.
- [x] 3.3 Persistencia: guardar `Answer.score`, `Answer.is_correct`.
- [x] 3.4 `ScoreEngine.apply_bonus(round_id)`:
  - Si un jugador responde todas las categorías antes que nadie y pulsa Stop → bonus +10.
- [x] 3.5 Al final de cada ronda: actualizar `GamePlayer.score`.
- [x] 3.6 Al final de la partida (5 rondas):
  - Calcular ganador.
  - Persistir `Game.status = finished`, `Game.finished_at`.
  - Resumen final con podio: 🥇 🥈 🥉.

**Entregable:** Puntuación correcta con duplicados, bonus y resumen.

ESTADO DE LA FASE: LISTA (ver phase3-guide.md)


## Fase 4 — Corrector ortográfico con IA / Fuzzy Matching

**Objetivo:** El bot entiende variaciones ortográficas y normaliza respuestas.

### Tareas

- [x] 4.1 **Pipeline de normalización:**
  1. Strip, lower, eliminar tildes (transliteración básica: `á → a`).
  2. Eliminar signos de puntuación redundantes.
  3. Tokenizar.

- [x] 4.2 **Fuzzy matching entre respuestas de la misma categoría:**
  - Usar `rapidfuzz` (Levenshtein ratio): si `ratio >= 0.75` → considerar misma palabra.
  - Ej: `Fernando`, `Fenando`, `FERNANDO`, `felnando` → misma respuesta.

- [x] 4.3 **Corrección ortográfica por palabra (opcional, nivel IA):**
  - `spaCy` + `symspellpy` para sugerir la palabra canónica.
  - O llamada a OpenAI / Gemini API: `"Corrige esta palabra al español correcto: {word}"`.
  - Cache en Redis de `{raw: corrected}` para evitar llamadas repetidas.

- [x] 4.4 **Validación semántica:**
  - ¿La palabra pertenece realmente a la categoría?
  - Opción A: Usar LLM (`"¿'{word}' es un {categoria}? Responde solo sí o no"`).
  - Opción B: Lista de palabras conocidas por categoría (seed inicial + grow).

- [x] 4.5 **Modo híbrido:**
  - Intentar fuzzy matching local primero.
  - Si match < 0.75, caer en LLM para corrección.
  - Configurable por variable de entorno: `SPELL_MODE=local|ai|hybrid`.

- [x] 4.6 Límite por ronda de llamadas a API externa para control de costes.

**Entregable:** Respuestas corregidas y normalizadas; duplicados detectados fuzzy.

ESTADO DE LA FASE: LISTA (ver phase4-guide.md)

---

## Fase 4B — Word Lists en Base de Datos

**Objetivo:** Migrar las listas de palabras de color, fruta y país desde `SEED_WORDS` hardcodeado a PostgreSQL, cargándolas en memoria al iniciar el bot para validación persistente y escalable.

### Tareas

- [x] 4B.1 Crear modelo `WordListItem` en SQLAlchemy (categoría, palabra, normalized)
- [x] 4B.2 Crear migración Alembic y ejecutarla
- [x] 4B.3 Crear `WordListRepository` (CRUD de palabras por categoría)
- [x] 4B.4 Crear datos semilla completos (~100 colores, ~90 frutas, ~200 países con variantes)
- [x] 4B.5 Crear script `seed_word_lists.py` idempotente
- [x] 4B.6 Añadir a `SpellCorrector`: `load_db_word_lists()`, `validate_against_list()`, `is_db_category()`
- [x] 4B.7 Quitar color/fruta/pais de `SEED_WORDS` (dejar sets vacíos, se cargan desde BD)
- [x] 4B.8 Pasar `category` a `_determine_answer_scores_fuzzy` y validar contra word list
- [x] 4B.9 Llamar `load_db_word_lists()` en `on_startup` del bot
- [x] 4B.10 Tests: repositorio, validate_against_list, score engine con validación

**Entregable:** Color, fruta y país validados contra BD con fuzzy matching; 215+ tests pasando.

ESTADO DE LA FASE: LISTA (ver phase4b-guide.md)

---

## Fase 4C — Módulo de Feedback Inteligente Local (ErrorTracker)

**Objetivo:** Crear un sistema de tracking de errores local (sin IA externa) que capture todas las excepciones no manejadas del bot, las persista en PostgreSQL, las clasifique contra una lookup table de soluciones conocidas, y exponga un comando `/diagnose` para que el host obtenga un informe con sugerencias de fix.

### Tareas

- [x] 4C.1 Crear modelo `ErrorLog` en SQLAlchemy (timestamp, level, handler, user_id, game_id, telegram_id, exception_type, exception_message, traceback, context JSON, resolved, resolution)
- [x] 4C.2 Crear `ErrorLogRepository` con 9 métodos CRUD
- [x] 4C.3 Registrar repositorio en `src/db/repositories/__init__.py`
- [x] 4C.4 Crear `ErrorTracker` singleton con `capture_exception()`, `track_errors()`, `generate_report()`
- [x] 4C.5 Crear `KNOWN_SOLUTIONS` lookup table (16+ entradas con solución + severidad)
- [x] 4C.6 Registrar `ErrorTracker` en `src/services/__init__.py`
- [x] 4C.7 Crear handler `/diagnose` (reporte completo)
- [x] 4C.8 Crear handler `/errors` (lista errores sin resolver)
- [x] 4C.9 Crear handler `/resolve` (marcar como resueltos)
- [x] 4C.10 Registrar `diagnose_router` en `src/bot.py`
- [x] 4C.11 Aplicar `@track_errors` a todos los handlers de lobby (4) y ronda (6)
- [x] 4C.12 Captura automática en `UserExistsMiddleware`
- [x] 4C.13 Tests: error_tracker (13 tests), error_log_repository (3 tests de integración)

**Entregable:** Sistema de error tracking local funcional; 246 tests pasando, 0 failures.

ESTADO DE LA FASE: LISTA (ver phase4c-guide.md)

---

## Fase 4D — Smoke Test Completo en Telegram

**Objetivo:** Validar que todas las funcionalidades del bot funcionan correctamente en un entorno real de Telegram, incluyendo el sistema de error tracking (Phase 4C), antes de considerar el MVP como estable.

### Tareas

- [x] 4D.1 Verificar infraestructura (PostgreSQL, Redis, bot auth, word lists)
- [x] 4D.2 Ejecutar suite de tests automatizados (246 tests, 0 failures)
- [ ] 4D.3 Smoke test básico de comandos (/start, /help, /cancel) — requiere Telegram
- [ ] 4D.4 Smoke test ErrorTracker (/diagnose, /errors, /resolve sin errores) — requiere Telegram
- [ ] 4D.5 Flujo completo de partida (crear lobby, unirse, 5 rondas, podio) — requiere Telegram
- [ ] 4D.6 Verificar líder/transición entre rondas — requiere Telegram
- [ ] 4D.7 Verificar inter-round menu (avanzar/detener) — requiere Telegram
- [ ] 4D.8 Verificar selección de letra y timeout — requiere Telegram
- [x] 4D.9 Prueba de ErrorTracker con errores inyectados en BD
- [ ] 4D.10 Prueba de ErrorTracker forzando caída de PostgreSQL — requiere Docker+Telegram
- [ ] 4D.11 Verificar casos borde (lobby expirado, respuestas inválidas, duplicados, timeouts) — requiere Telegram
- [x] 4D.12 Ejecutar script de smoke test automatizado
- [ ] 4D.13 Completar lista de verificación de regresión (100%) — requiere Telegram

**Entregable:** Bot verificado en Telegram — todos los comandos, flujos y ErrorTracker funcionan correctamente.

ESTADO DE LA FASE: EN GUIA (ver phase4d-guide.md) — chequeos automáticos completados.

---

## Fase 4E — LLM Híbrido (IA + Fuzzy para categorías abiertas)

**Objetivo:** Implementar validación semántica con IA para las 5 categorías abiertas (Nombre, Apellido, Artista, Novela/Serie, Cosa) usando el modo `hybrid` ya soportado por `SpellCorrector`. Cuando el fuzzy matching local no encuentra la palabra en la word list, se consulta a un LLM (OpenAI/Gemini) para determinar si la respuesta es válida. Las respuestas validadas por IA se auto-expanden en la word list para futuros matches exactos.

### Tareas

- [ ] 4E.1 Verificar que `SPELL_MODE=hybrid` funciona correctamente en `SpellCorrector.correct()` y `SpellCorrector.validate()` para las 5 categorías abiertas
- [ ] 4E.2 Implementar caché en Redis de resultados de LLM (`{word+category} → {is_valid, corrected}`) para evitar llamadas repetidas
- [ ] 4E.3 Implementar rate limiting por ronda (límite configurable vía `SPELL_API_LIMIT`)
- [ ] 4E.4 Agregar indicador visual en el scoring: si una respuesta fue validada por IA, mostrarlo en la puntuación
- [ ] 4E.5 Crear tests para modo `hybrid`: fuzzy falla → IA responde sí/no, IA falla → fuzzy como fallback, IA timeout → comportamiento degradado
- [ ] 4E.6 Verificar que `SPELL_MODE=ai` (solo IA, sin fuzzy) funciona como alternativa
- [ ] 4E.7 Documentar configuración de API keys en `.env.example` (OpenAI + Gemini gratis)
- [ ] 4E.8 Agregar al `generate_report` de ErrorTracker métricas de llamadas a API (total, fallos, timeout)

**Entregable:** Las 8 categorías se validan automáticamente — modo fuzzy-local para color/fruta/país, modo híbrido (fuzzy+IA) para nombre/apellido/artista/novela-serie/cosa. Cache en Redis, rate limiting, tests pasando.

ESTADO DE LA FASE: Completada (ver phase4e-guide.md)

---


## Fase 4F — Word Lists Masivas + Expansión + Modo Configurable

**Objetivo:** Seedear las 8 categorías con listas de palabras extensas en PostgreSQL, implementar auto-expansión persistente (las respuestas validadas se guardan en BD), y permitir al usuario elegir el modo de validación (`local`, `ai` o `hybrid`) mediante el comando `/settings` en el grupo, almacenando la preferencia por grupo en `GroupConfig`.

### Tareas

- [ ] 4F.1 Migrar las 5 categorías restantes (nombre, apellido, artista, novela/serie, cosa) de `SEED_WORDS` en memoria a tablas en PostgreSQL
- [ ] 4F.2 Crear listas semilla masivas para cada categoría:
  - Nombre: ~1000 nombres comunes (hispanoamérica + españa)
  - Apellido: ~1000 apellidos comunes
  - Artista: ~500 artistas (músicos, pintores, actores, escritores)
  - Novela/Serie: ~500 obras (libros, series, películas)
  - Cosa: ~2000 sustantivos comunes

- [ ] 4F.3 Implementar auto-expansión persistente: cuando `SPELL_MODE=local` o `hybrid` validan una palabra nueva, guardarla en `word_list_items` en BD (no solo en memoria)

- [ ] 4F.4 Agregar opción de modo al comando `/settings` en el grupo (solo host/admin):
  - `Modo validación: Local | IA | Híbrido`
  - Persistir en `GroupConfig.validation_mode` (nueva columna)

- [ ] 4F.5 Leer `GroupConfig.validation_mode` al iniciar partida y configurar `SpellCorrector.mode` dinámicamente

- [ ] 4F.6 Agregar columna `source` a `word_list_items` (`seed` | `learned`) para distinguir palabras sembradas de las aprendidas

- [ ] 4F.7 Script `seed_all_word_lists.py` idempotente que siembre las 8 categorías completas

- [ ] 4F.8 Tests: seed masivo, auto-expansión persistente, cambio de modo dinámico, lectura de `GroupConfig`

**Entregable:** Las 8 categorías con word lists masivas en BD. Auto-expansión persistente entre reinicios del bot. Modo de validación configurable por grupo vía `/settings`. Tests pasando.

ESTADO DE LA FASE: COMPLETADA (ver phase4f-guide.md)

---

## Fase 5 — Configuración de partida y persistencia

**Objetivo:** Partidas configurables (rondas, categorías, temporizador) y estadísticas.

### Tareas

- [ ] 5.1 `/settings` — menú inline en el grupo (solo host o admin):
  - `Rondas por partida: 5 | 10 | 15`
  - `Tiempo por ronda: 30s | 45s | 60s | 90s`
  - `Categorías personalizadas` (checkbox list, 8-12 disponibles).
  - `Incluir Ñ: Sí / No`

- [ ] 5.2 Persistencia de configuración por grupo:
  - Tabla `GroupConfig(group_chat_id, default_rounds, round_time, categories, include_ñ)`.

- [ ] 5.3 `/stats` — estadísticas del grupo:
  - Total partidas jugadas, top 10 jugadores.
  - Gráfico semanal (generado con `matplotlib` o `pillow`).

- [ ] 5.4 `/profile` — estadísticas personales del jugador:
  - Partidas jugadas, victorias, MVP times, total puntos.
  - Rating de aciertos (%).

- [ ] 5.5 **Multilenguaje:** `aiogram-i18n` + ficheros `locales/`.
  - Español (por defecto), English, Português.
  - Detectar idioma del grupo o del jugador.

**Entregable:** Configuración persistente, estadísticas, i18n.

ESTADO DE LA FASE: COMPLETADA (ver phase5-guide.md)
---

## Fase 6 — Semanal, MVP y recompensas

**Objetivo:** Engagement loop — leaderboards semanales, MVP, recompensas simbólicas.

### Tareas

- [ ] 6.1 **Weekly Leaderboard:**
  - `cron job` (o `APScheduler`) cada lunes 00:00:
    - Calcula leaderboard de la semana anterior.
    - Persiste en `WeeklyLeaderboard`.
    - Envía resumen a cada grupo con top 5.
  - `/weekly` — consultar leaderboard actual.

- [ ] 6.2 **MVP semanal:**
  - Jugador con más puntos en la semana.
  - Rol "MVP" asignado en el grupo (si el bot tiene privilegios de admin).
  - O badge en el perfil del bot.

- [ ] 6.3 **Recompensas sugeridas:**
  - **Rango/título:** Novato → Estrella → Leyenda (según partidas ganadas).
  - **Streak:** Bonus de `+5` puntos por partida consecutiva jugada (misma semana).
  - **Logros (achievements):** 🏆
    - *Rápido*: Hacer Stop en menos de 15s.
    - *Imbatible*: Ganar 3 partidas seguidas.
    - *Creativo*: Ser el único con respuesta correcta en una categoría 5 veces.
    - *Completista*: Responder todas las categorías en todas las rondas de una partida.
    - *Políglota*: Jugar en 3 idiomas distintos.
  - Cada logro tiene un badge emoji y se muestra en `/profile`.

- [ ] 6.4 **Sistema de niveles:**
  - XP por partida + logros.
  - Niveles 1-50 con fórmula: `XP_requerido = 100 * nivel^1.5`.

**Entregable:** Weekly leaderboard, MVP, logros, niveles.


ESTADO DE LA FASE: COMPLETADA (ver phase6-guide.md)
---

## Fase 7 — Experiencia moderna: animaciones, UI, imágenes

**Objetivo:** Hacer el bot visualmente atractivo.

### Tareas

- [ ] 7.1 **Mensajes animados:**
  - Countdown: bot edita el mensaje cada segundo (`"⏰ 5..."`, `"4..."`, etc.).
  - Lobby: puntos suspensivos animados (`"Esperando jugadores"` → `"."` → `".."` → `"..."`).
  - Usar `asyncio.sleep` + `edit_message_text`.

- [ ] 7.2 **Imágenes generadas:**
  - Logo de ronda con letra grande (Pillow): fondo degradado, letra blanca.
  - Podio final: imagen con 🥇🥈🥉 y nombres.
  - Cartas de logros al desbloquear.
  - Tabla semanal como imagen.

- [ ] 7.3 **Botones inline:**
  - Con emojis y estilos limpios.
  - `InlineKeyboardButton` con `callback_data` estructurada.
  - Paginación en menús largos (ej. selección de letra → 2 filas de 13).

- [ ] 7.4 **Efectos visuales:**
  - Spoiler en respuestas hasta el Stop (`parse_mode="HTML"` con `<tg-spoiler>`).
  - Stickers temporales del bot (subir stickers personalizados a @BotFather).

- [ ] 7.5 **Formato de mensajes:**
  - Usar `HTML` parse mode con negritas, itálicas, monoespaciado.
  - Tablas de puntuación con emojis de barras de progreso (`🟩🟩🟩⬜⬜`).

**Entregable:** Bot visualmente moderno con imágenes, animaciones y botones ricos.


ESTADO DE LA FASE: COMPLETADA (ver phase7-guide.md)
---

## Fase 8 — Calidad, testing, despliegue

**Objetivo:** Tests, CI/CD, monitoreo, producción.

### Tareas

- [ ] 8.1 **Tests unitarios:**
  - `ScoreEngine` (duplicados, puntos, bonificaciones).
  - `SpellCorrector` (fuzzy match, normalización).
  - `GameOrchestrator` (transiciones de estado).
  - `AnswerParser` (regex, edge cases).
  - Coverage target: >85%.

- [ ] 8.2 **Tests de integración:**
  - Base de datos con `testcontainers` o SQLite in-memory.
  - Flujo lobby → ronda → stop → evaluación.

- [ ] 8.3 **Linting y tipado:**
  - `ruff` (lint + format).
  - `mypy` strict.
  - `pre-commit` hooks.

- [ ] 8.4 **CI/CD:**
  - GitHub Actions: lint → test → build Docker → push a registry.
  - CD: deploy automático a VPS (o Railway / Render).

- [ ] 8.5 **Monitoreo:**
  - `structlog` para logging estructurado (JSON).
  - `prometheus_client` + métricas: games_played, rounds_played, api_calls, errors.
  - Healthcheck endpoint HTTP (puerto separado).

- [ ] 8.6 **Graceful shutdown:** Capturar `SIGTERM`, cerrar conexiones, finalizar tasks pendientes.

- [ ] 8.7 **Documentación:**
  - `README.md` con instrucciones de despliegue.
  - Comentarios de arquitectura en `docs/ARCHITECTURE.md`.
  - Guía de contribución (`CONTRIBUTING.md`).

**Entregable:** Pipeline CI/CD, tests, monitoreo, deploy.


ESTADO DE LA FASE: EN GUIA (ver phase8-guide.md)

---



## Fase 9 — Extensiones post-MVP

**Objetivo:** Features avanzadas para retener usuarios.

### Tareas

- [ ] 9.1 **Partidas 1v1:** Dos jugadores en chat privado con el bot.

- [ ] 9.2 **Partidas públicas / matchmaking:** Bot busca jugadores para ti.

- [ ] 9.3 **Categorías generadas por IA:** Cada ronda, IA elige categorías temáticas.

- [ ] 9.4 **Modo difícil:** Categorías más específicas, sin duplicados, tiempo reducido.

- [ ] 9.5 **Comando `/top`:** Top global de todas las comunidades.

- [ ] 9.6 **Web panel:** Dashboard para ver estadísticas (FastAPI + React ligero).

- [ ] 9.7 **Notificaciones push:** Bot avisa cuando empieza una partida en grupos donde el jugador está.

**Entregable:** Features opcionales, backlog priorizado.


ESTADO DE LA FASE:

---

Ahora desarrollemos la siguiente fase completa y avanzada del proyecto por favor:



Proporcioname toda la informacion, comandos, datos, codigo, detalles y todas las instrucciones y todo el codigo necesario para esta implementacion, no hagas ninguna implementacion ni ningun cambio tu, dame el codigo y las instrucciones a mi que yo lo hago por favor. Nota: recuerda siempre leer el phases.md y definitions.md para que te retroalimentes cuando necesites informacion de cualquier cosa. Y escribir cualquier informacion en el archivo correspondiente a la fase en desarrollo actual por ejemplo phase0-guide.md. No omitas nada, piensa en todo y selecciona las mejores opciones, arquitecturas, tecnologias, todo que me sea gratis xfa :).

## Resumen de tecnologías

| Componente        | Tecnología                                                                 |
| ----------------- | -------------------------------------------------------------------------- |
| Runtime           | Python 3.11+                                                               |
| Bot framework     | `aiogram 3.x`                                                              |
| Base de datos     | PostgreSQL 16 + `SQLAlchemy 2.0` + `alembic`                               |
| Cache / Session   | Redis 7                                                                    |
| Fuzzy matching    | `rapidfuzz`                                                                |
| NLP / IA          | `spaCy` (es_core_news_sm) + `openai` / `google-genai` (corrección externa) |
| Imágenes          | `Pillow` / `matplotlib`                                                    |
| Task scheduling   | `APScheduler`                                                              |
| Linting           | `ruff`, `mypy`                                                             |
| Testing           | `pytest`, `pytest-asyncio`, `testcontainers`                               |
| Logging           | `structlog`                                                                |
| Metrics           | `prometheus_client`                                                        |
| CI/CD             | GitHub Actions + Docker                                                    |
| Deploy            | Docker Compose en VPS / Railway / Render                                   |

---

## Diagrama de flujo del juego

```
User /stop         Bot crea lobby      Otros se unen
    │                   │                  │
    └───────────────────┴──────────────────┘
                      │
              ¿10 users || host start || 30s?
                      │
                      ▼
              Ronda 1: Letra aleatoria
                      │
              Bot envía plantilla
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
      User 1      User 2      User N
      escribe     escribe     escribe
         │            │            │
         ▼            │            │
  1er completo ───────┴────────────┘
         │
    Bot da botón Stop
         │
    ¿Stop en 5s? ───── No ──→ Timeout 60s
         │                        │
         ▼                        ▼
    Ronda cerrada           Ronda cerrada
         │                        │
         └────────────────────────┘
                      │
              ScoreEngine evalúa
                      │
         Muestra puntuación parcial
                      │
         Líder elige letra → 5s
                      │
                      ▼
                Siguiente ronda
                      │
                      ▼
               ¿5 rondas? (config)
                      │
                      ▼
         🏆 Fin de partida: podio
                      │
              Weekly stats update
```

---

*Documento generado para el desarrollo del Stop Bot v1.0 — todas las fases son acumulativas y cada una presupone la anterior completada.*
