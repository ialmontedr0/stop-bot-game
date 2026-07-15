# AGENTS.md — 🛑 Stop Bot Game

## 1. Resumen del Proyecto

Juego multijugador de palabras para Telegram ("Stop / Basta / Tutti Frutti"). Los jugadores se unen a una sala en un grupo, reciben una letra y 8 categorías, compiten por llenar todas las categorías, suman puntos por respuestas únicas y compiten durante 5+ rondas. Incluye leaderboards semanales, XP/niveles, rachas, eventos estacionales, validación de respuestas con IA y configuración por grupo.

**Despliegue:** Alwaysdata (via git push).  
**Runtime:** Python 3.11+, aiogram 3.x, PostgreSQL 16, Redis 7.

---

## 2. Tech Stack

| Componente | Tecnología |
|---|---|
| Bot framework | `aiogram 3.x` |
| BD | PostgreSQL 16 + `SQLAlchemy 2.0` (async) + `alembic` |
| Cache / FSM | Redis 7 (fallback a MemoryStorage) |
| Validación | `rapidfuzz` (fuzzy local) + OpenAI/Gemini LLM opcional |
| Imágenes | `Pillow` + `matplotlib` |
| Scheduling | `APScheduler` (cierre semanal leaderboard) |
| Logging | `structlog` (JSON en prod, consola en dev) |
| Métricas | `prometheus_client` (expuesto en `/metrics`) |
| Linting | `ruff` + `mypy` (strict) |
| Tests | `pytest` + `pytest-asyncio` + SQLite in-memory |
| CI | `pre-commit` hooks (ruff, mypy, trailing-whitespace, etc.) |

---

## 3. Arquitectura

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Telegram    │◄───►│  aiogram Bot  │────►│  PostgreSQL  │
│  Usuarios    │     │  (polling)   │     │  (asyncpg)   │
└─────────────┘     │              │     └─────────────┘
                    │  src/bot.py  │     ┌─────────────┐
                    │              │◄───►│  Redis       │
                    └──────┬───────┘     │  (cache/FSM)│
                           │             └─────────────┘
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ Handlers │ │ Services │ │ Repos    │
       │ (routers)│ │ (lógica) │ │ (CRUD BD)│
       └──────────┘ └──────────┘ └──────────┘
```

**Decisiones clave de diseño:**
- **Estado del juego en memoria:** LobbyManager y RoundManager mantienen el estado en dicts de Python (no en Redis). El estado se pierde al reiniciar — solo se limpia via `cleanup_stale_games()` al iniciar.
- **Una sola partida por grupo:** Solo una partida activa por `group_chat_id`. Un nuevo `/stop` cancela cualquier lobby existente.
- **Validación IA opcional:** La variable `SPELL_MODE` controla si `SpellCorrector` usa `local`, `ai` o `hybrid`. Se puede sobrescribir por grupo via `/settings`.
- **Respuestas persistidas inmediatamente:** `submit_answers()` escribe a BD en cada mensaje; el puntaje se calcula cuando se cierra la ronda.

---

## 4. Estructura de Directorios

```
├── AGENTS.md                    # ← Este archivo
├── README.md
├── definitions.md               # Spec del producto, listas de palabras (países, colores, frutas)
├── phases/
│   ├── phases.md                # Lista maestra de fases + tabla resumen
│   └── phase{0-8}-guide.md      # Guías detalladas por fase
│
└── backend/
    ├── bot.py                   # Entry point (main())
    ├── pyproject.toml           # Config del proyecto, deps, tool settings
    ├── pytest.ini               # Config pytest
    ├── alembic.ini              # Config Alembic
    ├── .env / .env.example      # Variables de entorno
    ├── .pre-commit-config.yaml  # Git hooks
    │
    ├── assets/                  # Imágenes estáticas, fuentes, backgrounds
    ├── locales/                 # i18n .mo/.po files (es, en, pt)
    ├── migrations/              # Scripts de migración Alembic
    │   └── versions/
    ├── scripts/                 # Scripts utilitarios (seed word lists, smoke tests, etc.)
    ├── tests/                   # Suite de tests pytest (30+ archivos)
    │
    └── src/
        ├── bot.py               # Fábrica de aplicación, setup de middlewares, startup/shutdown
        ├── i18n.py              # Internacionalización con gettext
        ├── image_generator.py   # Generación de imágenes con Pillow (podio, leaderboard, etc.)
        │
        ├── core/
        │   ├── config.py        # Pydantic Settings (variables de entorno)
        │   └── text_utils.py    # normalize_text()
        │
        ├── db/
        │   ├── engine.py        # Engine asíncrono + session factory
        │   ├── models.py        # 13 modelos SQLAlchemy ORM
        │   └── repositories/    # 8 repositorios CRUD
        │
        ├── handlers/            # Routers de aiogram
        │   ├── start.py         # /start, /help
        │   ├── group.py         # bot añadido/eliminado del grupo
        │   ├── admin/
        │   │   └── events.py    # /addevent (stub)
        │   └── game/
        │       ├── lobby.py     # /stop, /cancel, callbacks join/start
        │       ├── round.py     # mensajes de respuesta, callbacks stop/letter/next_round
        │       ├── settings.py  # Flujo del menú /settings
        │       ├── leaderboard.py # /leaderboard, /rank
        │       ├── stats.py     # /stats
        │       ├── profile.py   # /profile
        │       ├── diagnose.py  # /diagnose, /errors, /resolve
        │       ├── clear.py     # /clear
        │       └── clear_stats.py # /clear_stats
        │
        ├── keyboards/
        │   ├── lobby.py         # Botones Unirse/Iniciar
        │   ├── round.py         # Botones Stop, Letra, Inter-ronda
        │   └── settings.py      # Teclados del menú de configuración
        │
        ├── middlewares/
        │   ├── throttling.py    # Rate-limiter (0.5s por usuario)
        │   └── user_exists.py   # Auto-crea Player al interactuar
        │
        ├── monitoring/
        │   ├── health_server.py # Servidor HTTP en puerto 9090 (/health, /metrics)
        │   └── metrics.py       # Definiciones de métricas Prometheus
        │
        └── services/
            ├── game_orchestrator.py # LobbyManager (ciclo de vida del lobby)
            ├── round_manager.py     # RoundManager (ciclo de vida de ronda, puntaje, transiciones)
            ├── score_engine.py      # ScoreEngine (evaluar respuestas, detectar duplicados)
            ├── spell_corrector.py   # SpellCorrector (fuzzy + validación IA)
            ├── leaderboard.py       # LeaderboardService (top semanal / rank consultas)
            ├── xp_service.py        # XPService (XP, niveles, rachas)
            ├── event_service.py     # EventService (eventos estacionales)
            └── error_tracker.py     # ErrorTracker (capturar, diagnosticar, resolver errores)
```

---

## 5. Modelos de Base de Datos (13 tablas)

Todos en `src/db/models.py`, heredan de `Base` (`DeclarativeBase`).

| Modelo | Tabla | Campos Clave | Relaciones |
|---|---|---|---|
| **Player** | `players` | `telegram_id` (único), `username`, `first_name`, `last_name`, `language_code`, `created_at` | game_players, answers, weekly_leaderboards, xp (1:1), streak (1:1) |
| **Game** | `games` | `group_chat_id`, `status` (lobby/playing/finished/cancelled), `current_round`, `total_rounds`, `created_at`, `finished_at` | players (GamePlayer), rounds |
| **GamePlayer** | `game_players` | `game_id` (FK), `player_id` (FK), `score`, `joined_at`, `is_host` | game, player, answers |
| **Round** | `rounds` | `game_id` (FK), `round_number`, `letter`, `status` (active/completed), `started_at`, `stopped_at`, `stopped_by_player_id` | game, answers |
| **Answer** | `answers` | `round_id` (FK), `player_id` (FK), `game_player_id` (FK), `word_slot`, `raw_text`, `normalized_text`, `is_correct`, `score`, `created_at` | round, player, game_player |
| **WeeklyLeaderboard** | `weekly_leaderboards` | `player_id` (FK), `group_chat_id` (BigInteger), `week_start`, `total_score`, `games_played`, `rank` | player |
| **PlayerXP** | `player_xp` | `player_id` (FK, único), `xp`, `level`, `total_xp_earned`, `updated_at` | player |
| **Streak** | `streaks` | `player_id` (FK, único), `current_streak`, `max_streak`, `last_played_date`, `updated_at` | player |
| **SeasonalEvent** | `seasonal_events` | `name` (único), `description`, `multiplier`, `starts_at`, `ends_at`, `active`, `created_at` | — |
| **GroupConfig** | `group_configs` | `group_chat_id` (único), `default_rounds`, `round_time`, `categories`, `include_n`, `language`, `validation_mode` | — |
| **WordListItem** | `word_list_items` | `category`, `word`, `normalized`, `source` (seed/learned), `created_at` | — |
| **ErrorLog** | `error_logs` | `timestamp`, `level`, `handler`, `user_id`, `game_id`, `telegram_id`, `exception_type`, `exception_message`, `traceback`, `context` (JSON), `resolved`, `resolution` | — |
| **MessageLog** | `message_logs` | `chat_id`, `message_id`, `created_at` | — |

**Restricciones de unicidad:**
- `(game_id, player_id)` → `game_players`
- `(player_id, week_start, group_chat_id)` → `weekly_leaderboards`
- `(category, normalized)` → `word_list_items`

---

## 6. Servicios

### 6.1 LobbyManager (`game_orchestrator.py`)
- **Singleton:** `lobby_manager` / `game_orchestrator`
- **Estado:** `_lobbies: dict[group_chat_id -> LobbyState]`
- **Métodos clave:**
  - `create_lobby(group_chat_id, host_player, bot)` — crea Game + GamePlayer en BD, envía mensaje del lobby con teclado inline
  - `join_lobby(game_id, player, callback, bot)` — añade a BD + lista en memoria; dispara auto-start al llegar a 10 jugadores
  - `start_game(game_id, player, callback, bot)` — solo el host; inicia countdown y delega a RoundManager
  - `cancel_game(group_chat_id, player, bot)` — solo el host; cambia estado a cancelled
  - `cancel_all_games()` — graceful shutdown
  - `cleanup_stale_games()` — llamado al iniciar; cancela partidas >24h en lobby/playing
  - `_do_start(state, bot)` — lee `GroupConfig` (validation_mode, round_time, categories, include_n), elige letra aleatoria, llama `round_manager.start_round()`
- **Auto-start:** Después de 30s de inactividad si >= 2 jugadores; inmediato al llegar a 10
- **Lobby expira:** Después de 120s de inactividad
- **Bucle de animación:** Actualiza mensaje del lobby cada 3s con puntos animados

### 6.2 RoundManager (`round_manager.py`)
- **Singleton:** `round_manager`
- **Estado:** `_rounds: dict[game_id -> RoundState]`, `_rounds_by_group`, `_letter_pending`, `_locks`
- **Métodos clave:**
  - `start_round(...)` — crea imagen de ronda, envía mensaje, crea Round en BD, inicia timer de 60s
  - `submit_answers(game_id, player, text, bot)` — parsea respuestas con `parse_answers()`, trata `"..."` como vacío, valida con SpellCorrector (si mode = ai/hybrid), persiste a BD, detecta primer completador, envía botón Stop
  - `press_stop(game_id, player_id, callback, bot)` — requiere 10 pulsaciones del botón Stop para cerrar la ronda
  - `_close_round(game_id, reason, bot)` — saca el estado, persiste puntajes, construye resumen, transiciona a siguiente ronda
  - `_persist_round_scores(round_id, state)` — llama `ScoreEngine.evaluate()`, registra resultados, actualiza BD
  - `handle_letter_selection(...)` — líder elige siguiente letra → inicia siguiente ronda
  - `handle_next_round(...)` — líder avanza desde el menú inter-ronda
  - `handle_stop_game(...)` — anfitrión termina partida desde el menú inter-ronda
  - `_end_game(state, bot)` — cambia estado de game a finished, otorga XP/rachas, actualiza leaderboard semanal, genera imagen de podio
- **Menú inter-ronda:** Timeout de 120s; el líder puede avanzar, el anfitrión puede detener
- **Selección de letra:** Timeout de 15s → letra aleatoria
- **8 categorías por defecto:** Nombre, Apellido, Color, Fruta, País, Artista, Animal, Cosa

### 6.3 ScoreEngine (`score_engine.py`)
- **Constantes clave:** `UNIQUE_POINTS = 50`, `FIRST_COMPLETER_BONUS = 10`
- **`evaluate(answers_by_player, num_categories, first_completer_id, spell_corrector, letter)` → `(totals, details)`**
  - Agrupa respuestas por categoría
  - Para cada categoría, detecta duplicados/clusters fuzzy
  - Respuesta única → 50 pts; compartida → 50//N; vacía/inválida → 0
  - Si la categoría tiene word list en BD (color, fruta, país), valida contra ella primero
  - Añade +10 bonus por primer completador
- **`_determine_answer_scores_fuzzy()`** — clustering via `SpellCorrector.cluster_answers()`
- **`_determine_answer_scores()`** — ruta de coincidencia exacta (fallback)
- **`_is_valid_word(text, letter)`** — regex valida alfanumérico con acentos, verifica letra inicial

### 6.4 SpellCorrector (`spell_corrector.py`)
- **Singleton via `get_corrector()`** — lazy init con configuración
- **Tres modos:** `local`, `ai`, `hybrid`
- **Categorías con BD:** color, fruta, pais, nombre, apellido, artista, animal, cosa
- **Métodos clave:**
  - `normalize(raw)` → via `text_utils.normalize_text()`
  - `fuzzy_match(word, candidates)` → rapidfuzz `token_sort_ratio`, umbral configurable (default 75%)
  - `cluster_answers(answers)` → agrupa player IDs por match exacto luego fusión fuzzy (85% threshold)
  - `correct(word, category, mode)` → pipeline de normalización: word list → fuzzy → IA → fallback
  - `validate(word, category, mode)` → mismo pipeline pero retorna bool
  - `validate_against_list(word, category)` → exacto + fuzzy contra word list (sin IA)
  - `add_to_word_list_persistent(word, category, source)` → guarda palabras aprendidas en BD (tarea en segundo plano)
  - `load_db_word_lists()` → llamado al iniciar; carga todas las palabras desde BD a memoria
  - `get_api_metrics()` → para el reporte de ErrorTracker
- **Caché:** 2 capas (TTLCache en memoria 1h + Redis 1h) para resultados de corrección/validación IA
- **Límite de tasa:** `spell_api_limit` (default 20) llamadas por ronda, reinicio via `reset_api_counter()`

### 6.5 LeaderboardService (`leaderboard.py`)
- **Singleton:** `leaderboard_service`
- **`get_weekly_top(group_chat_id, limit=10)`** → lista de dicts con rank, name, score, games
- **`get_player_rank_by_telegram(telegram_id, group_chat_id)`** → rank/score/games para un jugador
- **`upsert_player(player_id, score_to_add, group_chat_id)`** → delega a `LeaderboardRepository.upsert_player_week()`
- **Nota:** Todas las consultas filtran por `group_chat_id` para leaderboards por grupo.

### 6.6 XPService (`xp_service.py`)
- **Singleton:** `xp_service`
- **`award_game_xp(player_id, final_position, was_stopper, unique_answers)`** → otorga XP según posición, bonus por stop, bonus por racha, multiplicador de evento
- **`update_streak(player_id)`** → seguimiento de racha diaria
- **`get_profile(player_id)`** → XP, nivel, título, progreso %, info de racha
- **Tabla de niveles:** 20 niveles con fórmula `XP_required = 100 * level^1.5` (aproximado)
- **Títulos:** Novato (1), Aprendiz (5), Veterano (10), Maestro (15), Leyenda (20)
- **Constantes XP:** `XP_PER_GAME=50`, `XP_PER_WIN=100`, `XP_PER_STOP=25`, `XP_PER_UNIQUE=10`, `XP_STREAK_BONUS=20`

### 6.7 EventService (`event_service.py`)
- **`get_active_multiplier()`** → retorna multiplicador (default 1.0) desde SeasonalEvent activo
- **`get_active_events()`** → lista de eventos activos con nombre, descripción, multiplicador

### 6.8 ErrorTracker (`error_tracker.py`)
- **Singleton:** `error_tracker`
- **`capture_exception(exc, handler, user_id, game_id, telegram_id, context, level)`** → persiste a `error_logs`
- **`track_errors(handler_name, include_user, include_game)`** → decorador que envuelve handlers para captura automática
- **`generate_report(game_id, minutes=60)`** → diagnóstico formateado con búsqueda de soluciones conocidas
- **`KNOWN_SOLUTIONS`** → 16+ entradas mapeando tipos de excepción a (solución, severidad)
- **Aplicado a:** todos los handlers de lobby (4), ronda (6) y middlewares via `@error_tracker.track_errors()`

---

## 7. Handlers (Routers)

| Archivo Router | Comandos/Callbacks | Descripción |
|---|---|---|
| `start.py` | `/start`, `/help` | Mensajes de bienvenida y ayuda con imágenes |
| `group.py` | `my_chat_member` | Bot añadido/eliminado del grupo |
| `lobby.py` | `/stop`, `/cancel`, `join:`, `start:` | Ciclo de vida del lobby |
| `round.py` | mensajes de texto con `:`, `stop:`, `letter:`, `next_round:`, `stop_game:` | Envío de respuestas, acciones de ronda |
| `settings.py` | `/settings`, todos los callbacks `settings_*` | Menú de configuración por grupo |
| `leaderboard.py` | `/leaderboard`, `/rank` | Leaderboard semanal + rank del jugador |
| `stats.py` | `/stats` | Estadísticas del grupo con gráfico de actividad |
| `profile.py` | `/profile` | Estadísticas personales, XP, nivel, racha |
| `diagnose.py` | `/diagnose`, `/errors`, `/resolve` | Seguimiento y resolución de errores |
| `clear.py` | `/clear` | Eliminar mensajes del bot del grupo |
| `clear_stats.py` | `/clear_stats` | Reiniciar todas las estadísticas del juego |
| `admin/events.py` | `/addevent` | Stub para creación de eventos estacionales |

**Modelo de permisos:** `/settings`, `/clear`, `/clear_stats`, `/diagnose`, `/errors`, `/resolve` requieren ser admin del grupo. `/stop` (crear lobby) está disponible para cualquiera.

---

## 8. Repositorios (8 clases CRUD)

Todos en `src/db/repositories/`. Patrón: métodos async, reciben una sesión de `async_session_factory()`.

| Repositorio | Base | Métodos Clave |
|---|---|---|
| `BaseRepository<ModelType>` | Genérico | `get(id)`, `get_all(**filters)`, `create(**kwargs)`, `update(id, **kwargs)`, `delete(id)` |
| `GameRepository` | `BaseRepository<Game>` | `get_active_game()`, `get_by_id()`, `create_game()`, `add_player_to_game()`, `get_players_for_game()`, `is_player_in_game()`, `update_game_status()`, `get_stale_games()` |
| `RoundRepository` | `BaseRepository<Round>` | `create_round()`, `get_active_round()`, `update_status()`, `save_answers()` (con sobrescritura), `get_answers_by_player()`, `update_answer_scores()`, `get_game_players_by_telegrams()` |
| `PlayerRepository` | `BaseRepository<Player>` | `get_by_telegram_id()`, `get_or_create()` (con auto-actualización de perfil) |
| `LeaderboardRepository` | — | `upsert_player_week()`, `get_weekly_top()`, `recalculate_ranks()`, `close_week()` |
| `GroupConfigRepository` | — | `get_by_group()`, `get_or_create()` |
| `WordListRepository` | — | `get_words_by_category()`, `get_words_with_originals()`, `word_exists()`, `bulk_insert()`, `clear_category()`, `count_by_category()` |
| `ErrorLogRepository` | — | `create()`, `get_unresolved()`, `get_by_game()`, `get_recent()`, `mark_resolved()`, `get_most_frequent_exception()`, `count_unresolved()`, `get_total_count()` |
| `MessageLogRepository` | — | `log_message()`, `get_today_messages()`, `delete_by_message_ids()`, `cleanup_old()` |

---

## 9. Teclados

| Teclado | Ubicación | Botones |
|---|---|---|
| `lobby_keyboard(game_id, is_host)` | `keyboards/lobby.py` | 🟢 Unirse, ▶️ Iniciar (solo host) |
| `stop_keyboard(game_id, stop_number)` | `keyboards/round.py` | 🛑 Stop con barra de progreso (10 pulsaciones) |
| `letter_keyboard(game_id, include_n)` | `keyboards/round.py` | 27 letras en 4 filas (6-7-7-7) |
| `inter_round_keyboard(game_id)` | `keyboards/round.py` | ▶️ Siguiente ronda, ⏹ Detener partida |
| `settings_main_keyboard(...)` | `keyboards/settings.py` | Rondas, Tiempo, Categorías, Ñ, Modo, Cerrar |
| `settings_rounds_keyboard(...)` | `keyboards/settings.py` | 5/10/15 rondas |
| `settings_time_keyboard(...)` | `keyboards/settings.py` | 30/45/60/90 segundos |
| `settings_cats_keyboard(...)` | `keyboards/settings.py` | 8 categorías toggle |
| `settings_mode_keyboard(...)` | `keyboards/settings.py` | Local/AI/Híbrido |

---

## 10. Middlewares

| Middleware | Propósito |
|---|---|
| `ThrottlingMiddleware` | Limita a 1 acción cada 0.5s por usuario (TTLCache en memoria) |
| `UserExistsMiddleware` | Crea automáticamente Player en cualquier mensaje/callback; inyecta `data["player"]` |

**Orden:** Throttling se ejecuta primero, luego UserExists.

---

## 11. Configuración (Variables de Entorno)

Todas definidas en `src/core/config.py` via `pydantic-settings` (lee de `.env`).

| Variable | Default | Descripción |
|---|---|---|
| `BOT_TOKEN` | — | Token del bot de Telegram |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Cadena de conexión PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Cadena de conexión Redis |
| `LOG_LEVEL` | `INFO` | Nivel de logging |
| `SPELL_MODE` | `local` | `local` / `ai` / `hybrid` |
| `SPELL_API_KEY` | `None` | API key para el proveedor LLM |
| `SPELL_API_URL` | `None` | URL base para la API LLM |
| `SPELL_API_LIMIT` | `20` | Máximo de llamadas IA por ronda |
| `SPELL_FUZZY_THRESHOLD` | `75` | Umbral de fuzzy match (0-100) |
| `SPELL_AI_PROVIDER` | `openai` | `openai` / `gemini` |
| `SPELL_AI_MODEL` | `None` | Nombre del modelo (auto por provider si None) |

---

## 12. Tests

- **Framework:** `pytest` con `pytest-asyncio` (`asyncio_mode = auto`)
- **BD:** SQLite in-memory (`sqlite+aiosqlite:///:memory:`) usando fixture `async_session`
- **Mocks:** `asyncio.AsyncMock`, `MagicMock` para sesiones BD (`patch('src.services.round_manager.async_session_factory')`)
- **Umbral de cobertura:** `--cov-fail-under=50` (pytest.ini)
- **Archivos de test:** 30+ archivos en `tests/`

**Patrones comunes:**
- `conftest.py` proporciona `async_engine`, `async_session`, `player`, `game`, `mock_bot`, `mock_message`, `mock_callback`, `sqlite_in_memory`, `_make_answer()`
- Tests de ScoreEngine: tests unitarios con `_make_answer()` sin BD
- Tests de RoundManager: mock `async_session_factory` para evitar BD
- Tests de repositorios: usan fixture `sqlite_in_memory`

**Ejecutar tests:**
```bash
cd backend
pytest                                      # todos los tests
pytest tests/test_score_engine.py           # archivo específico
pytest -k "test_leaderboard"                # filtro por keyword
pytest --cov=src --cov-report=html          # reporte HTML de cobertura
```

---

## 13. Generación de Imágenes (`image_generator.py`)

Usa `Pillow` + `matplotlib`. Assets almacenados en `assets/`:
- `backgrounds/podium_bg.png`, `backgrounds/round_bg.png`
- `fonts/Montserrat-Bold.ttf`
- `start/stop_it.png`, `help/help.png`
- `leaderboard/profile_placeholder.png`

**Funciones:**
- `generate_round_letter_image(letter, round_number, category_count)` → 256x256 PNG
- `generate_podium_image(winners, game_rounds, profile_photos)` → 400x300 PNG (top 3 con fotos de perfil)
- `generate_leaderboard_image(entries, week_label, profile_photos)` → 600x800 PNG
- `generate_achievement_card(title, description, emoji, color)` → 400x200 PNG
- `generate_activity_chart(daily_data)` → gráfico de barras matplotlib
- `generate_welcome_image()` → 400x300 tarjeta de bienvenida
- `generate_help_image()` → 400x300 tarjeta de ayuda

Todas retornan `bytes | None`.

---

## 14. Monitoreo

- **Servidor de salud:** `HTTPServer` en puerto 9090 en un hilo daemon
  - `/health` → JSON `{"status": "ok", "service": "stop-bot-game", "version": "1.0.0"}`
  - `/metrics` → formato texto Prometheus
- **Métricas Prometheus** (definidas en `monitoring/metrics.py`):
  - Contadores: `games_started_total`, `games_finished_total`, `rounds_played_total`, `api_calls_total`, `errors_total`, `messages_sent_total`, `player_joins_total`
  - Histogramas: `round_duration_seconds`, `game_duration_minutes`, `api_call_duration_seconds`
  - Gauges: `active_games`, `active_players`, `db_pool_size`, `redis_connected`
- **Logging:** `structlog` — formato JSON en producción, salida de consola en desarrollo. Timestamps en ISO UTC.
- **Eventos estructurados de juego:** Se emiten 5 eventos clave en formato `extra={}` para análisis de partidas:

  | Evento `event` | Origen | Campos Clave | Descripción |
  |---|---|---|---|
  | `round_result` | `round_manager.py:_persist_round_scores()` | `game_id`, `round_number`, `letter`, `reason`, `validation_mode`, `players[]` (cada uno con `player_id`, `name`, `answers[]` con `category`, `answer`, `correct`, `score`, `validation_source`, y `total`) | Resultado detallado de una ronda al cerrarse |
  | `score_evaluation` | `score_engine.py:evaluate()` | `num_players`, `num_categories`, `first_completer_id`, `results[]` (cada uno con `player_id`, `total`, `categories{}`) | Evaluación interna de puntajes por categoría |
  | `game_finished` | `round_manager.py:_end_game()` | `game_id`, `group_chat_id`, `total_rounds`, `total_players`, `validation_mode`, `first_completer_id`, `standings[]` (cada uno con `position`, `player_id`, `name`, `score`, `xp_gained`, `level`, `leveled_up`) | Resultado final de la partida con XP y niveles |
  | `submit_answers` | `round_manager.py:submit_answers()` | `game_id`, `player_id`, `telegram_id`, `total_categories`, `answered_count`, `all_filled`, `answers{}` | Cada envío de respuestas de un jugador |
  | `ia_rejection` | `round_manager.py:submit_answers()` | `game_id`, `player_id`, `telegram_id`, `category`, `rejected_text` | Respuesta rechazada por validación IA |

  **Uso:** En producción (JSON), grepear por `"event": "round_result"` o `"event": "game_finished"` para analizar partidas completas.

---

## 15. Internacionalización (`i18n.py`)

- **Motor:** `gettext` con archivos `.mo` en `locales/{lang}/LC_MESSAGES/bot.mo`
- **Idiomas soportados:** `es` (default), `en`, `pt`
- **`get_user_locale(player)`** → mapea `language_code` a locale conocido (es-ar → es, pt-br → pt, etc.)
- **`t(key, locale="es", **kwargs)`** → traduce con argumentos de formato opcionales
- **Uso actual:** Solo `/settings` usa i18n actualmente. La mayoría de textos están hardcodeados en español.

---

## 16. Flujo de Desarrollo

### Setup
```bash
git clone <repo>
cd backend
python -m venv venv
pip install -r requirements/requirements.txt
# Copiar .env.example → .env, llenar BOT_TOKEN
```

### Migraciones de base de datos
```bash
cd backend
alembic revision --autogenerate -m "descripcion"
alembic upgrade head
```

Siempre probar migraciones contra PostgreSQL local antes de desplegar.

### Pre-commit
```bash
pre-commit install   # una vez
pre-commit run --all-files   # ejecución manual
```

Hooks: ruff (lint + format), mypy (strict), trailing-whitespace, end-of-file-fixer, check-yaml, check-json, check-toml, check-added-large-files, check-merge-conflict, detect-private-key.

### Ejecución local
```bash
cd backend
# Asegurarse de que PostgreSQL + Redis estén corriendo
python -m src.bot
```

### Patrones comunes
- **Añadir un nuevo comando:** Crear función handler con `@router.message(Command("nombre"))`, registrar router en `bot.py`
- **Añadir un callback:** Definir `@router.callback_query(F.data.startswith("prefijo:"))`, registrar router
- **Añadir un modelo BD:** Agregar clase en `models.py`, crear migración, añadir repositorio si es necesario
- **Añadir un servicio:** Crear archivo en `services/`, implementar patrón singleton, usar `async_session_factory()` para acceso a BD

### Gotchas
- **El estado está en memoria:** Redis solo se usa para almacenamiento FSM y caché IA. El estado del juego (lobbies, rondas) vive en dicts de Python y se pierde al reiniciar.
- **Limpieza de partidas huérfanas:** `cleanup_stale_games()` al iniciar cancela partidas >24h.
- **Race condition de `_letter_pending`:** El dict `_letter_pending` intencionalmente no se elimina en `start_round()` para evitar una race condition entre el `_letter_timeout` de la ronda existente y `handle_letter_selection`. Ver comentario en `round_manager.py:190`.
- **Sobrescritura de respuestas:** `save_answers()` elimina respuestas antiguas del mismo (round, player) antes de insertar nuevas.
- **Botón Stop requiere 10 pulsaciones:** Configurable via `NUM_STOP_BUTTONS = 10`. Esto evita stops accidentales de un solo click.
- **Bonus por primer completador:** +10 pts, otorgado en `ScoreEngine.evaluate()`.
- **Propagación de `validation_mode`:** Debe pasarse explícitamente desde `_do_start()` → `start_round()`, y desde `handle_letter_selection()` / `_start_next_round_with_letter()` → `start_round()` de la siguiente ronda. El default es `"local"`.
- **Manejo de `"..."`:** En `submit_answers()`, `...` / `…` / `. . .` / `..` se tratan como respuestas vacías (cero puntos). Ver `round_manager.py:222-227`.
- **Leaderboard por grupo:** La migración `81b5eee3926f` añadió `group_chat_id` a `weekly_leaderboards`. Todas las consultas filtran por `group_chat_id`. La constraint única cambió de `(player_id, week_start)` a `(player_id, week_start, group_chat_id)`.
- **`SPELL_MODE=local` sin palabras en BD:** Si la BD está vacía (sin word lists sembradas), la validación de palabras cae a default permisivo (acepta todo) para todas las categorías excepto aquellas con seeds hardcodeados (que son sets vacíos). Siempre ejecutar `seed_all_word_lists.py` después de configurar la BD.

---

## 17. Roadmap de Fases (de `phases/phases.md`)

| Fase | Estado | Descripción |
|---|---|---|
| 0 | ✅ Completada | Fundación: repo, Docker, modelos, migraciones, esqueleto del bot |
| 1 | ✅ Completada | Registro de grupos, lobby, unirse/iniciar partida |
| 2 | ✅ Completada | Ciclo de ronda: letra, respuestas, Stop, evaluación |
| 3 | ✅ Completada | Motor de puntuación: duplicados, puntos, bonificaciones |
| 4 | ✅ Completada | Corrector ortográfico con IA + fuzzy matching |
| 4B | ✅ Completada | Word lists en BD (color, fruta, país) |
| 4C | ✅ Completada | ErrorTracker (tracking de errores local + /diagnose) |
| 4D | 🟡 En progreso | Smoke tests en Telegram |
| 4E | ✅ Completada | Modo híbrido LLM para categorías abiertas |
| 4F | ✅ Completada | Word lists masivas, auto-expansión, modo configurable |
| 5 | ✅ Completada | Config de grupo (/settings), stats, profile, i18n |
| 6 | ✅ Completada | Leaderboard semanal, MVP, logros, XP/niveles |
| 7 | ✅ Completada | Animaciones, imágenes, teclados inline |
| 8 | 🟡 En progreso | Tests, CI/CD, monitoreo, docs |
| 9 | ❌ Por hacer | Post-MVP: 1v1, matchmaking, categorías IA, panel web |

---

## 18. Despliegue (Alwaysdata)

**Proceso de despliegue:**
1. Hacer push a git → Alwaysdata despliega automáticamente
2. SSH a Alwaysdata: `cd ~/stop-bot-game && git pull`
3. Reiniciar el bot desde el panel de administración de Alwaysdata
4. Ejecutar migraciones: `cd backend && alembic upgrade head`
5. Sembrar palabras: `cd backend && python -m scripts.seed_all_word_lists`

**Detalles clave del despliegue:**
- **Servidor de salud:** Puerto 9090 (HTTP)
- **Pool BD:** 10 pool_size, 20 max_overflow, pool_recycle=3600, pool_pre_ping=True
- **Apagado graceful:** Captura SIGTERM/SIGINT, cancela partidas, cierra pool BD, cierra Redis
- **Scheduler:** APScheduler ejecuta `close_week` del leaderboard cada lunes 00:00
- **Lock file:** Si al reiniciar el Scheduled task falla con `exit code: 1` y `flock -n`, ejecutar `rm -f /home/ialmontedr0/python/stop-bot-game/backend/stopbot.lock` en SSH y esperar al próximo minuto

---

## 19. Tareas Comunes

### Añadir una nueva categoría al juego
1. Añadir a `ALL_CATEGORIES` en `keyboards/settings.py`
2. Añadir a `CATEGORIES` en `services/round_manager.py`
3. Añadir a `DB_CATEGORIES` en `services/spell_corrector.py`
4. Añadir a `SEED_WORDS` en `services/spell_corrector.py`
5. Sembrar datos via `scripts/word_list_data.py` + `scripts/seed_word_lists.py`

### Crear una nueva migración
```bash
cd backend
alembic revision --autogenerate -m "add_foo_bar"
# Revisar el archivo generado en migrations/versions/
alembic upgrade head
```

### Depurar un problema de producción
1. Revisar logs en `backend/logs/` o logs de Alwaysdata
2. Ejecutar `/diagnose` en el grupo donde ocurrió el problema
3. Revisar `/errors` para errores sin resolver
4. Usar `/resolve` para marcar issues como resueltos

### Resetear todo (desarrollo)
```bash
# Dropear y recrear BD
dropdb stopbot && createdb stopbot
cd backend && alembic upgrade head
python -m scripts.seed_all_word_lists
python -m scripts.seed_word_lists
```

---

*Este documento se mantiene automáticamente. Actualízalo cada vez que se hagan cambios arquitectónicos significativos al código base.*
