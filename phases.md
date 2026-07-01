# 🛑 Stop Bot — Development Phases

> **Arquitectura:** Python 3.11+ · `aiogram 3.x` · `PostgreSQL` + `Redis` · `SQLAlchemy 2.0` · `OpenAI API` / `spaCy`  
> **Duración estimada:** 8–10 semanas (tiempo completo)  
> **Versión:** 1.0

---

## Fase 0 — Fundación del proyecto

**Objetivo:** Esqueleto del bot, base de datos, infraestructura core.

### Tareas

- [ ] 0.1 Crear repositorio, estructura de directorios y entorno virtual.
- [ ] 0.2 Configurar `poetry` o `pip` + `requirements.txt`.
- [ ] 0.3 Docker-compose: `postgres:16`, `redis:7`, `app`.
- [ ] 0.4 Modelo de datos (SQLAlchemy):
  - `Player(id, telegram_id, username, first_name, last_name, language_code, created_at)`
  - `Game(id, group_chat_id, status, current_round, total_rounds, created_at, finished_at)`
  - `GamePlayer(id, game_id, player_id, score, joined_at)`
  - `Round(id, game_id, round_number, letter, status, started_at, stopped_at)`
  - `Answer(id, round_id, player_id, word_slot, raw_text, normalized_text, is_correct, score)`
  - `WeeklyLeaderboard(id, player_id, week_start, total_score, games_played, rank)`
- [ ] 0.5 Migration system con `alembic`.
- [ ] 0.6 Fábrica de `Application` de aiogram con `Dispatcher`, `Router`, `FSM` storage en Redis.
- [ ] 0.7 Middleware: `Throttling`, `UserExistsMiddleware` (crea Player si no existe).
- [ ] 0.8 Estructura de ficheros propuesta:

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

- [ ] 1.1 Detectar cuando el bot es añadido a un grupo (`my_chat_member` → `ChatMemberHandler`).
- [ ] 1.2 Comando `/stop` — inicia lobby en el grupo.
- [ ] 1.3 Bot genera un mensaje con:
  - Texto animado (editing message) con `"🛑 STOP — Sala abierta"`
  - Contador de jugadores: `👤 X / 10`
  - Botón **«🟢 Unirse»** (inline) — cualquiera en el grupo puede unirse.
  - Botón **«▶️ Iniciar»** (solo visible para el host — primer usuario que ejecutó `/stop`).
- [ ] 1.4 Al pulsar «Unirse»:
  - Se añade `GamePlayer` con `joined_at = now()`.
  - Si llega a 10 → **auto-start** (ver Fase 2).
- [ ] 1.5 Cada 5s el bot actualiza el mensaje del lobby con el nuevo contador.
- [ ] 1.6 Temporizador de expiración: si no se une nadie tras 2 min, el lobby se cierra.
- [ ] 1.7 Si se pulsa «Iniciar» (host) → saltar a Fase 2.
- [ ] 1.8 Validaciones:
  - No se puede unir una partida ya iniciada.
  - Un jugador no puede unirse dos veces.
  - Solo el host puede iniciar (a menos que se cumpla condición de 10 o timeout).

**Entregable:** Lobby funcional, unión de hasta 10 jugadores, inicio manual/automático.

ESTADO DE LA FASE:

---

Ahora desarrollemos la siguiente fase completa y avanzada del proyecto por favor:

Fase 1 — Registro de grupos y unión a partidas

**Objetivo:** Unir jugadores a una sala de juego dentro de un grupo.

### Tareas

- [ ] 1.1 Detectar cuando el bot es añadido a un grupo (`my_chat_member` → `ChatMemberHandler`).
- [ ] 1.2 Comando `/stop` — inicia lobby en el grupo.
- [ ] 1.3 Bot genera un mensaje con:
  - Texto animado (editing message) con `"🛑 STOP — Sala abierta"`
  - Contador de jugadores: `👤 X / 10`
  - Botón **«🟢 Unirse»** (inline) — cualquiera en el grupo puede unirse.
  - Botón **«▶️ Iniciar»** (solo visible para el host — primer usuario que ejecutó `/stop`).
- [ ] 1.4 Al pulsar «Unirse»:
  - Se añade `GamePlayer` con `joined_at = now()`.
  - Si llega a 10 → **auto-start** (ver Fase 2).
- [ ] 1.5 Cada 5s el bot actualiza el mensaje del lobby con el nuevo contador.
- [ ] 1.6 Temporizador de expiración: si no se une nadie tras 2 min, el lobby se cierra.
- [ ] 1.7 Si se pulsa «Iniciar» (host) → saltar a Fase 2.
- [ ] 1.8 Validaciones:
  - No se puede unir una partida ya iniciada.
  - Un jugador no puede unirse dos veces.
  - Solo el host puede iniciar (a menos que se cumpla condición de 10 o timeout).

**Entregable:** Lobby funcional, unión de hasta 10 jugadores, inicio manual/automático.

Proporcioname toda la informacion, comandos, datos, codigo, detalles y todas las instrucciones y todo el codigo necesario para esta implementacion, no hagas ninguna implementacion ni ningun cambio tu, dame el codigo y las instrucciones a mi que yo lo hago por favor. Nota: recuerda siempre leer el phases.md y definitions.md para que te retroalimentes cuando necesites informacion de cualquier cosa. Y escribir cualquier informacion en el archivo correspondiente a la fase en desarrollo actual por ejemplo phase0-guide.md. No omitas nada, piensa en todo y selecciona las mejores opciones, arquitecturas, tecnologias, todo que me sea gratis xfa :).


## Fase 2 — Ciclo de ronda: letra, envío, Stop y evaluación

**Objetivo:** Núcleo del juego — rondas completas con temporizador, Stop, y puntuación.

### Tareas

- [ ] 2.1 **Selección de letra (primera ronda):**
  - Random con `random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")`.
  - Excluir Ñ (o incluirla según región configurable).
- [ ] 2.2 **Temporizador de ronda:** 60s controlado con `asyncio.create_task` + `Redis` expiry como fallback.
- [ ] 2.3 **Plantilla de categorías** (8-12 fijas, ej.):
  - Nombre, País/Ciudad, Animal, Comida, Objeto, Profesión, Deporte, Color, Marca, Verbo, Película, Planta.
- [ ] 2.4 Bot envía mensaje formateado con la letra y las categorías:
  ```
  🛑 Ronda 1 — Letra: **F**
  ⏱ 60 segundos

  Envía tus respuestas en este formato:

  Nombre: ...
  País/Ciudad: ...
  Animal: ...
  ...
  ```
- [ ] 2.5 **Parser de respuestas:**
  - Regex que extrae `categoría: valor`.
  - Ignora mayúsculas/minúsculas, espacios extra.
  - Devuelve `dict[Categoría, str]`.
  - Si el formato no es válido o faltan categorías → respuesta rechazada con botón «Reintentar».
- [ ] 2.6 **Normalización y fuzzy matching** (ver Fase 4): en esta fase solo guardamos raw_text.
- [ ] 2.7 **Sistema Stop:**
  - Cuando el primer jugador envía una respuesta **completa** (todas las categorías rellenas) → el bot le responde en privado con botón **«⏹ Stop»**.
  - Otros jugadores NO ven este botón.
  - Timeout del botón: 5s.
  - Al pulsar Stop → la ronda se cierra inmediatamente.
  - Si nadie hace Stop → la ronda termina a los 60s.
- [ ] 2.8 **Cierre de ronda:**
  - Bot edita el mensaje del grupo: `"⏹ Ronda detenida"` o `"⌛ Tiempo agotado"`.
  - Llama al `ScoreEngine` (Fase 3).
- [ ] 2.9 **Mostrar puntuación parcial:** Bot envía resumen de puntos de la ronda.
- [ ] 2.10 **Transición a siguiente ronda:**
  - El líder (máximo puntaje acumulado) recibe inline keyboard con el alfabeto.
  - Selecciona letra → 5s countdown → nueva ronda.
  - Si hay empate, elige el primero en llegar a esa posición.

**Entregable:** Ronda completa con temporizador, envío de respuestas, Stop y transición.

---

## Fase 3 — Motor de puntuación (Score Engine)

**Objetivo:** Evaluar respuestas, calcular puntos, detectar duplicados.

### Tareas

- [ ] 3.1 `ScoreEngine.evaluate(round_id, answers_by_player)`:
  - Agrupa respuestas por categoría.
  - Para cada categoría detecta **duplicados exactos** (y fuzzy en Fase 4).
  - Asigna puntos:
    - `50` si única y correcta.
    - `50 / N` si N jugadores dieron la misma respuesta (ej: 3 → 16.66 c/u, truncado a entero o 2 decimales).
    - `0` si vacía o incorrecta.
  - Bonus de velocidad: el jugador que hizo Stop recibe `+10` extra.
- [ ] 3.2 Criterio de "respuesta correcta":
  - Por ahora: cualquier palabra que no esté vacía y sea alfabética (+ espacios, guiones).
  - En Fase 4 se añade validación semántica con IA.
- [ ] 3.3 Persistencia: guardar `Answer.score`, `Answer.is_correct`.
- [ ] 3.4 `ScoreEngine.apply_bonus(round_id)`:
  - Si un jugador responde todas las categorías antes que nadie y pulsa Stop → bonus +10.
- [ ] 3.5 Al final de cada ronda: actualizar `GamePlayer.score`.
- [ ] 3.6 Al final de la partida (5 rondas):
  - Calcular ganador.
  - Persistir `Game.status = finished`, `Game.finished_at`.
  - Resumen final con podio: 🥇 🥈 🥉.

**Entregable:** Puntuación correcta con duplicados, bonus y resumen.

---

## Fase 4 — Corrector ortográfico con IA / Fuzzy Matching

**Objetivo:** El bot entiende variaciones ortográficas y normaliza respuestas.

### Tareas

- [ ] 4.1 **Pipeline de normalización:**
  1. Strip, lower, eliminar tildes (transliteración básica: `á → a`).
  2. Eliminar signos de puntuación redundantes.
  3. Tokenizar.
- [ ] 4.2 **Fuzzy matching entre respuestas de la misma categoría:**
  - Usar `rapidfuzz` (Levenshtein ratio): si `ratio >= 0.75` → considerar misma palabra.
  - Ej: `Fernando`, `Fenando`, `FERNANDO`, `felnando` → misma respuesta.
- [ ] 4.3 **Corrección ortográfica por palabra (opcional, nivel IA):**
  - `spaCy` + `symspellpy` para sugerir la palabra canónica.
  - O llamada a OpenAI / Gemini API: `"Corrige esta palabra al español correcto: {word}"`.
  - Cache en Redis de `{raw: corrected}` para evitar llamadas repetidas.
- [ ] 4.4 **Validación semántica:**
  - ¿La palabra pertenece realmente a la categoría?
  - Opción A: Usar LLM (`"¿'{word}' es un {categoria}? Responde solo sí o no"`).
  - Opción B: Lista de palabras conocidas por categoría (seed inicial + grow).
- [ ] 4.5 **Modo híbrido:**
  - Intentar fuzzy matching local primero.
  - Si match < 0.75, caer en LLM para corrección.
  - Configurable por variable de entorno: `SPELL_MODE=local|ai|hybrid`.
- [ ] 4.6 Límite por ronda de llamadas a API externa para control de costes.

**Entregable:** Respuestas corregidas y normalizadas; duplicados detectados fuzzy.

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

---

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
