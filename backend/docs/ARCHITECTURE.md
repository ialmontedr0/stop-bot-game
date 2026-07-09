# Arquitectura de Stop Bot Game

## Vision general

El bot es una aplicacion Python asincrona que usa `aiogram 3.x` para interactuar con la API de Telegram.
La arquitectura sigue un patron de servicios con inyeccion de dependencias minima, usando singletons
para los servicios principales.

## Componentes principales

### Core
- **bot.py**: Entry point. Configura logging, Redis, Dispatcher, middlewares y routers.
- **core/config.py**: Configuracion centralizada via Pydantic Settings (`.env`).
- **core/text_utils.py**: Utilidades de texto compartidas.

### Base de datos
- **db/engine.py**: Conexion asincrona a PostgreSQL via SQLAlchemy 2.0 + asyncpg.
- **db/models.py**: Modelos SQLAlchemy (Player, Game, GamePlayer, Round, Answer, etc.).
- **db/repositories/**: CRUDs por entidad con session por operacion.

### Handlers (aiogram routers)
- **handlers/start.py**: `/start`, `/help`
- **handlers/group.py**: Eventos de grupo (bot added, left)
- **handlers/game/**: Logica del juego (lobby, round, settings, stats, profile, leaderboard)

### Servicios
- **services/game_orchestrator.py**: Orquestador de partidas (lobby, inicio, cancelacion)
- **services/round_manager.py**: Gestion de rondas (timer, submissions, stop, transicion)
- **services/score_engine.py**: Motor de puntuacion (duplicados, bonus, puntuacion)
- **services/spell_corrector.py**: Corrector ortografico (fuzzy matching, IA hibrida, word lists)
- **services/xp_service.py**: Sistema de XP, niveles y streaks
- **services/leaderboard.py**: Leaderboard semanal

### Monitoreo
- **monitoring/metrics.py**: Metricas Prometheus (contadores, histogramas, gauges)
- **monitoring/health_server.py**: Servidor HTTP para healthcheck y metrics

## Flujo de datos

```
Telegram API <-> aiogram Dispatcher <-> Routers <-> Services <-> DB (PostgreSQL) + Cache (Redis)
                                              |
                                        Monitoring (Prometheus + Healthcheck)
```

## Patrones

- **Singleton**: Services (game_orchestrator, round_manager, spell_corrector)
- **Repository**: Acceso a datos por entidad
- **Middleware**: Throttling y UserExists en pipeline de aiogram
- **Observer**: Eventos de ronda, lobby, y errores via ErrorTracker
