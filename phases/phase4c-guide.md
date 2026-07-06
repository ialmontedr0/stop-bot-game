# Phase 4C — Módulo de Feedback Inteligente Local (ErrorTracker)

**Objetivo:** Crear un sistema de tracking de errores local (sin IA externa) que capture todas las excepciones no manejadas del bot, las persista en PostgreSQL, las clasifique contra una lookup table de soluciones conocidas, y exponga un comando `/diagnose` para que el host obtenga un informe con sugerencias de fix.

**Relación con otras fases:**
- Fase 0-3: infraestructura core del bot
- Fase 4A: SpellCorrector con fuzzy matching
- Fase 4B: Word lists en DB
- **Fase 4C: Error tracking + diagnóstico local**

---

## Arquitectura

```
┌──────────────────────────────────────────────────────────────────┐
│                        ErrorTracker (singleton)                    │
│                                                                  │
│  .capture_exception(exc, context) → inserta en DB                │
│                                                                  │
│  .track_errors() → decorador que envuelve handlers               │
│                                                                  │
│  .generate_report(game_id?) → texto con análisis + sugerencias   │
│                                                                  │
│  KNOWN_SOLUTIONS = {                                             │
│    "sqlalchemy.exc.OperationalError": "Revisa PostgreSQL...",    │
│    "redis.exceptions.ConnectionError": "Revisa Redis...",        │
│    ...                                                           │
│  }                                                               │
└──────────────────┬───────────────────────────────────────────────┘
                   │
    ┌──────────────┴──────────────┐
    ▼                             ▼
┌──────────┐               ┌──────────┐
│  Handler │               │Middleware│
│ /diagnose│               │(opcional)│
└──────────┘               └──────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│        PostgreSQL: error_logs          │
│  id | timestamp | level | handler     │
│  user_id | game_id | exception_type   │
│  exception_message | traceback        │
│  context(JSON) | resolved | resolution│
└──────────────────────────────────────┘
```

---

## Implementación paso a paso

### 1. Crear la tabla `ErrorLog` en `src/db/models.py`

Añade al final del archivo, antes de la última línea (o donde prefieras):

```python
class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(default=func.now(), index=True)
    level: Mapped[str] = mapped_column(String(20), default="ERROR")
    handler: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    game_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    exception_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    exception_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    resolved: Mapped[bool] = mapped_column(default=False)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ErrorLog id={self.id} type={self.exception_type}>"
```

**Importante:** Este modelo usa `BigInteger` para `user_id` y `telegram_id`. `user_id` es el `Player.id` de la tabla `players` (entero secuencial), mientras `telegram_id` es el `telegram_id` del usuario (BigInteger de Telegram). Son dos cosas distintas.

### 2. Crear `ErrorLogRepository` en `src/db/repositories/error_log_repository.py`

```python
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ErrorLog


class ErrorLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        level: str,
        handler: Optional[str] = None,
        user_id: Optional[int] = None,
        game_id: Optional[int] = None,
        telegram_id: Optional[int] = None,
        exception_type: Optional[str] = None,
        exception_message: Optional[str] = None,
        traceback: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> ErrorLog:
        log = ErrorLog(
            level=level,
            handler=handler,
            user_id=user_id,
            game_id=game_id,
            telegram_id=telegram_id,
            exception_type=exception_type,
            exception_message=exception_message,
            traceback=traceback,
            context=json.dumps(context) if context else None,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_unresolved(self, limit: int = 50) -> list[ErrorLog]:
        stmt = (
            select(ErrorLog)
            .where(ErrorLog.resolved == False)
            .order_by(ErrorLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_game(self, game_id: int, limit: int = 50) -> list[ErrorLog]:
        stmt = (
            select(ErrorLog)
            .where(ErrorLog.game_id == game_id)
            .order_by(ErrorLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(self, minutes: int = 60, limit: int = 50) -> list[ErrorLog]:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)
        stmt = (
            select(ErrorLog)
            .where(ErrorLog.timestamp >= cutoff)
            .order_by(ErrorLog.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_level(self) -> dict[str, int]:
        stmt = (
            select(ErrorLog.level, func.count(ErrorLog.id))
            .group_by(ErrorLog.level)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result}

    async def count_unresolved(self) -> int:
        stmt = select(func.count(ErrorLog.id)).where(ErrorLog.resolved == False)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def mark_resolved(self, error_id: int, resolution: Optional[str] = None) -> None:
        values: dict[str, Any] = {"resolved": True}
        if resolution:
            values["resolution"] = resolution
        await self.session.execute(
            update(ErrorLog).where(ErrorLog.id == error_id).values(**values)
        )
        await self.session.commit()

    async def get_most_frequent_exception(self, limit: int = 5) -> list[tuple[str, int]]:
        stmt = (
            select(ErrorLog.exception_type, func.count(ErrorLog.id))
            .where(ErrorLog.exception_type.isnot(None))
            .group_by(ErrorLog.exception_type)
            .order_by(func.count(ErrorLog.id).desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result]

    async def get_total_count(self) -> int:
        stmt = select(func.count(ErrorLog.id))
        result = await self.session.execute(stmt)
        return result.scalar() or 0
```

### 3. Registrar el repositorio en `src/db/repositories/__init__.py`

```python
from .error_log_repository import ErrorLogRepository

__all__ = [
    # ... existing entries ...
    "ErrorLogRepository",
]
```

### 4. Crear `ErrorTracker` en `src/services/error_tracker.py`

```python
import asyncio
import functools
import json
import logging
import traceback as tb
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypeVar

from src.db.engine import async_session_factory
from src.db.repositories.error_log_repository import ErrorLogRepository

logger = logging.getLogger(__name__)

# ── Lookup table de soluciones conocidas ──────────────────────────────
# Cada entrada mapea: "exception_type" → (solución, gravedad)
KNOWN_SOLUTIONS: dict[str, tuple[str, str]] = {
    # DB / SQLAlchemy
    "sqlalchemy.exc.OperationalError": (
        "Revisa que PostgreSQL esté corriendo. "
        "Verifica DATABASE_URL en .env, "
        "y que el usuario/contraseña sean correctos.",
        "CRITICAL",
    ),
    "sqlalchemy.exc.IntegrityError": (
        "Conflicto de datos duplicados o violación de FK. "
        "Revisa que no haya registros huérfanos en game_players o answers.",
        "HIGH",
    ),
    "sqlalchemy.exc.ProgrammingError": (
        "Error de esquema: alguna tabla no existe o columna incorrecta. "
        "Ejecuta la creación de tablas con Base.metadata.create_all(engine).",
        "CRITICAL",
    ),
    "sqlalchemy.exc.TimeoutError": (
        "Timeout en conexión a PostgreSQL. "
        "Revisa que la BD no esté sobrecargada. Aumenta pool_size en engine.py si es necesario.",
        "MEDIUM",
    ),
    # Redis
    "redis.exceptions.ConnectionError": (
        "Redis no está disponible. "
        "Revisa que redis-server esté corriendo y REDIS_URL en .env.",
        "CRITICAL",
    ),
    "redis.exceptions.TimeoutError": (
        "Timeout conectando a Redis. "
        "Revisa que Redis responda con redis-cli ping.",
        "MEDIUM",
    ),
    # Telegram / aiogram
    "aiogram.exceptions.TelegramBadRequest": (
        "Telegram rechazó la solicitud. "
        "Puede ser: mensaje duplicado, callback_data inválida, "
        "o intento de editar un mensaje inexistente.",
        "LOW",
    ),
    "aiogram.exceptions.TelegramRetryAfter": (
        "Flood control de Telegram. El bot se esperará automáticamente "
        "según lo que indique retry_after.",
        "LOW",
    ),
    "aiogram.exceptions.TelegramForbiddenError": (
        "El bot fue bloqueado por el usuario o no tiene permisos "
        "en el grupo. Revisa que sea administrador del grupo.",
        "MEDIUM",
    ),
    "aiogram.exceptions.TelegramNetworkError": (
        "Error de red al conectar con Telegram API. "
        "Revisa conectividad a internet.",
        "HIGH",
    ),
    # HTTP / API
    "httpx.ConnectError": (
        "Error de conexión a API externa. "
        "Revisa la URL configurada en settings.spell_api_url.",
        "MEDIUM",
    ),
    "httpx.TimeoutException": (
        "Timeout en llamada a API externa. "
        "El servicio podría estar caído o lento.",
        "MEDIUM",
    ),
    # AsyncIO
    "asyncio.TimeoutError": (
        "Timeout en operación asíncrona. "
        "Posible lentitud de BD o red. Revisa logs para más contexto.",
        "MEDIUM",
    ),
    "asyncio.CancelledError": (
        "Tarea cancelada — es normal durante shutdown o "
        "al cancelar timers del juego. Solo preocupa si es recurrente.",
        "LOW",
    ),
    # Core del bot
    "KeyError": (
        "Estado del juego corrompido en memoria. "
        "Posible race condition o estado huérfano en RoundManager. "
        "Revisa _rounds, _letter_pending, _lobbies en el momento del error.",
        "HIGH",
    ),
    "AttributeError": (
        "Acceso a atributo inexistente en objeto de estado. "
        "Revisa que RoundState/LobbyState tenga todos los campos inicializados.",
        "HIGH",
    ),
    "TypeError": (
        "Error de tipo en operación. Revisa que los argumentos pasados "
        "a funciones asíncronas sean del tipo correcto.",
        "MEDIUM",
    ),
    "ValueError": (
        "Valor inválido. Revisa que los IDs/callback_data se estén parseando correctamente.",
        "MEDIUM",
    ),
    # Catch-all genérico
    "Exception": (
        "Error inesperado no clasificado. Revisa el traceback completo.",
        "MEDIUM",
    ),
}


def _get_solution(exception_type: str) -> tuple[str, str]:
    """Busca solución conocida para un tipo de excepción.
    Si no encuentra match exacto, busca por substring (ej: 'sqlalchemy' en 'sqlalchemy.exc.X').
    Si no encuentra nada, retorna la solución genérica.
    """
    # 1. Match exacto
    if exception_type in KNOWN_SOLUTIONS:
        return KNOWN_SOLUTIONS[exception_type]

    # 2. Match por substring: recorrer de más específico a menos
    parts = exception_type.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in KNOWN_SOLUTIONS:
            return KNOWN_SOLUTIONS[prefix]

    # 3. Genérico
    return KNOWN_SOLUTIONS.get("Exception", ("Sin solución conocida.", "MEDIUM"))


F = TypeVar("F", bound=Callable[..., Any])


class ErrorTracker:
    """Rastrea errores del bot en PostgreSQL y ofrece diagnóstico local."""

    def __init__(self) -> None:
        self._captured_count: int = 0

    async def capture_exception(
        self,
        exc: BaseException,
        handler: Optional[str] = None,
        user_id: Optional[int] = None,
        game_id: Optional[int] = None,
        telegram_id: Optional[int] = None,
        context: Optional[dict[str, Any]] = None,
        level: str = "ERROR",
    ) -> Optional[int]:
        """Persiste un error en la tabla error_logs.
        Retorna el ID del log creado, o None si falla la conexión a DB.
        """
        exc_type = f"{type(exc).__module__}.{type(exc).__qualname__}"
        exc_msg = str(exc)[:2000] if str(exc) else "Sin mensaje"
        tb_str = "".join(tb.format_exception(type(exc), exc, exc.__traceback__))[:5000]

        try:
            async with async_session_factory() as session:
                repo = ErrorLogRepository(session)
                log = await repo.create(
                    level=level,
                    handler=handler,
                    user_id=user_id,
                    game_id=game_id,
                    telegram_id=telegram_id,
                    exception_type=exc_type,
                    exception_message=exc_msg,
                    traceback=tb_str,
                    context=context,
                )
                self._captured_count += 1
                logger.info(
                    "Error capturado: id=%s type=%s handler=%s",
                    log.id, exc_type, handler,
                )
                return log.id
        except Exception as db_err:
            logger.error(
                "No se pudo persistir error en DB: %s. Error original: %s",
                db_err, exc_type,
            )
            return None

    def track_errors(
        self,
        handler_name: Optional[str] = None,
        include_user: bool = True,
        include_game: bool = True,
    ) -> Callable[[F], F]:
        """Decorador para funciones handler asíncronas.
        Captura cualquier excepción no manejada, la persiste en DB,
        y la relanza para que el middleware/logging la maneje.

        Uso:
            @error_tracker.track_errors(handler_name="cmd_stop")
            async def cmd_stop(message, player, bot):
                ...
        """
        def decorator(func: F) -> F:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await func(*args, **kwargs)
                except asyncio.CancelledError:
                    # Las tareas canceladas son normales (timers, shutdown)
                    # Solo registramos si no es esperado
                    raise
                except Exception as exc:
                    context: dict[str, Any] = {}
                    user_id = None
                    game_id = None
                    telegram_id = None

                    # Extraer contexto de kwargs (aiogram inyecta 'player', 'callback', 'message')
                    player = kwargs.get("player")
                    if player and include_user:
                        user_id = getattr(player, "id", None)
                        telegram_id = getattr(player, "telegram_id", None)

                    callback = kwargs.get("callback")
                    if callback:
                        # Extraer game_id de callback_data si es posible
                        data = getattr(callback, "data", "")
                        if data and ":" in data:
                            try:
                                game_id = int(data.split(":")[1])
                            except (ValueError, IndexError):
                                pass
                        context["callback_data"] = data

                    message = kwargs.get("message")
                    if message:
                        context["message_text"] = getattr(message, "text", "")
                        context["chat_type"] = getattr(message.chat, "type", "") if message.chat else ""

                    context["handler"] = handler_name or func.__name__

                    await self.capture_exception(
                        exc,
                        handler=handler_name or func.__name__,
                        user_id=user_id,
                        game_id=game_id,
                        telegram_id=telegram_id,
                        context=context,
                    )
                    raise  # Relanzar para que el handler original falle como esperado
            return wrapper  # type: ignore
        return decorator

    async def generate_report(
        self,
        game_id: Optional[int] = None,
        minutes: int = 60,
    ) -> str:
        """Genera un reporte de diagnóstico en texto plano.

        Args:
            game_id: Si se pasa, solo errores de esa partida.
            minutes: Ventana de tiempo hacia atrás (default: 60 min).

        Returns:
            str: Reporte formateado para mostrar al usuario.
        """
        async with async_session_factory() as session:
            repo = ErrorLogRepository(session)

            total = await repo.get_total_count()
            unresolved = await repo.count_unresolved()
            freq = await repo.get_most_frequent_exception(5)

            if game_id:
                errors = await repo.get_by_game(game_id)
            else:
                errors = await repo.get_recent(minutes=minutes)

        lines: list[str] = []
        lines.append("┌──────────────────────────────────────────────")
        lines.append("│  📋 INFORME DE DIAGNÓSTICO")
        lines.append("├──────────────────────────────────────────────")
        lines.append(f"│  Total errores registrados:  {total}")
        lines.append(f"│  No resueltos:              {unresolved}")
        if freq:
            lines.append("│")
            lines.append("│  🔥 Top errores más frecuentes:")
            for exc_type, count in freq:
                sol, severity = _get_solution(exc_type)
                sev_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "ℹ️"}
                lines.append(f"│    {sev_emoji.get(severity, '❓')} {exc_type} ({count} veces)")
        lines.append("│")
        lines.append("│  📄 Últimos errores:")

        if not errors:
            lines.append("│    (ninguno en el período seleccionado)")
        else:
            for err in errors[:10]:
                ts = err.timestamp.strftime("%H:%M:%S") if err.timestamp else "??:??:??"
                exc_short = (err.exception_type or "Unknown").split(".")[-1]
                msg_short = (err.exception_message or "")[:80]
                solucion, _ = _get_solution(err.exception_type or "Exception")

                if err.resolved:
                    icon = "✅"
                else:
                    severity = _get_solution(err.exception_type or "Exception")[1]
                    icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "ℹ️"}.get(severity, "❓")

                lines.append(f"│")
                lines.append(f"│  {icon} [{ts}] {exc_short}")
                if msg_short:
                    lines.append(f"│    Mensaje: {msg_short}")
                if err.handler:
                    lines.append(f"│    Handler: {err.handler}")
                if err.game_id:
                    lines.append(f"│    Partida: #{err.game_id}")
                if not err.resolved:
                    lines.append(f"│    💡 Sugerencia: {solucion}")
                if err.resolved and err.resolution:
                    lines.append(f"│    ✅ Resuelto: {err.resolution}")

        lines.append("└──────────────────────────────────────────────")
        return "\n".join(lines)

    @property
    def captured_count(self) -> int:
        return self._captured_count


# Singleton
error_tracker = ErrorTracker()
```

### 5. Registrar ErrorTracker en `src/services/__init__.py`

```python
from .error_tracker import ErrorTracker, error_tracker

__all__ = [
    # ... existing entries ...
    "ErrorTracker",
    "error_tracker",
]
```

### 6. Crear handler `/diagnose` en `src/handlers/game/diagnose.py`

```python
import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from src.db.engine import async_session_factory
from src.db.repositories.error_log_repository import ErrorLogRepository
from src.services.error_tracker import error_tracker
from src.utils import delete_after

logger = logging.getLogger(__name__)

diagnose_router = Router()


@diagnose_router.message(Command("diagnose"))
async def cmd_diagnose(message: Message) -> None:
    """Muestra un reporte de diagnóstico de errores."""
    if message.chat.type not in ("group", "supergroup"):
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    # Obtener game_id activo si existe
    game_id = None
    try:
        async with async_session_factory() as session:
            from src.db.repositories import GameRepository
            repo = GameRepository(session)
            game = await repo.get_active_game(message.chat.id)
            if game:
                game_id = game.id
    except Exception:
        pass

    report = await error_tracker.generate_report(
        game_id=game_id,
        minutes=60,
    )

    # Si el reporte es muy largo, dividir en partes
    MAX_LENGTH = 4000  # Telegram max message length ~4096
    if len(report) <= MAX_LENGTH:
        await message.reply(report)
    else:
        parts = [report[i:i + MAX_LENGTH] for i in range(0, len(report), MAX_LENGTH)]
        header = await message.reply(parts[0])
        for part in parts[1:]:
            await message.answer(part)
        asyncio.create_task(delete_after(header, delay=60))


@diagnose_router.message(Command("resolve"))
async def cmd_resolve(message: Message) -> None:
    """Marca todos los errores no resueltos como resueltos.
    Uso: /resolve [reason opcional]
    """
    if message.chat.type not in ("group", "supergroup"):
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    reason = message.text.removeprefix("/resolve").strip()
    if not reason:
        reason = "Resuelto manualmente por el host."

    async with async_session_factory() as session:
        repo = ErrorLogRepository(session)
        errors = await repo.get_unresolved()
        for err in errors:
            await repo.mark_resolved(err.id, resolution=reason)

    msg = await message.reply(f"✅ {len(errors)} error(es) marcado(s) como resuelto(s).")
    asyncio.create_task(delete_after(msg))


@diagnose_router.message(Command("errors"))
async def cmd_errors(message: Message) -> None:
    """Muestra los últimos errores sin resolver."""
    if message.chat.type not in ("group", "supergroup"):
        msg = await message.answer("⚠️ Este comando solo funciona en grupos.")
        asyncio.create_task(delete_after(msg))
        return

    async with async_session_factory() as session:
        repo = ErrorLogRepository(session)
        errors = await repo.get_unresolved(limit=20)

    if not errors:
        await message.reply("✅ No hay errores sin resolver.")
        return

    lines = ["<b>📋 Errores sin resolver:</b>", ""]
    for err in errors[:20]:
        ts = err.timestamp.strftime("%H:%M") if err.timestamp else "??:??"
        exc_short = (err.exception_type or "Unknown").split(".")[-1]
        msg_short = (err.exception_message or "")[:60]
        lines.append(f"• <b>#{err.id}</b> [{ts}] <code>{exc_short}</code>")
        if msg_short:
            lines.append(f"  {msg_short}")
        if err.handler:
            lines.append(f"  Handler: {err.handler}")

    await message.reply("\n".join(lines))
```

### 7. Registrar el router en `src/handlers/game/__init__.py`

```python
from .diagnose import diagnose_router

__all__ = ["game_router", "round_router", "diagnose_router"]
```

### 8. Integrar el router en `src/bot.py`

En `main()`, después de incluir los otros routers:

```python
from src.handlers.game import game_router, round_router, diagnose_router

dp.include_router(start_router)
dp.include_router(group_router)
dp.include_router(game_router)
dp.include_router(round_router)
dp.include_router(diagnose_router)
```

### 9. Aplicar decorador `@track_errors` a handlers clave (opcional pero recomendado)

Esto captura errores no manejados y los persiste automáticamente.

**En `src/handlers/game/lobby.py`:**

```python
from src.services.error_tracker import error_tracker

@game_router.message(Command("stop"))
@error_tracker.track_errors(handler_name="cmd_stop")
async def cmd_stop(message: Message, player: Player, bot: Bot) -> None:
    # ... código existente ...

@game_router.message(Command("cancel"))
@error_tracker.track_errors(handler_name="cmd_cancel")
async def cmd_cancel(message: Message, player: Player, bot: Bot) -> None:
    # ... código existente ...

@game_router.callback_query(F.data.startswith("join:"))
@error_tracker.track_errors(handler_name="callback_join")
async def callback_join(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    # ... código existente ...

@game_router.callback_query(F.data.startswith("start:"))
@error_tracker.track_errors(handler_name="callback_start")
async def callback_start(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    # ... código existente ...
```

**En `src/handlers/game/round.py`:**

```python
from src.services.error_tracker import error_tracker

@round_router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
@error_tracker.track_errors(handler_name="handle_round_answer")
async def handle_round_answer(message: Message, player: Player, bot: Bot) -> None:
    # ... código existente ...

@round_router.callback_query(F.data.startswith("stop:"))
@error_tracker.track_errors(handler_name="callback_stop")
async def callback_stop(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    # ... código existente ...
# ... repetir para callback_letter, callback_next_round, callback_stop_game
```

**Orden de los decoradores:** En aiogram, los decoradores de ruta (`@game_router.message(...)`) deben ir MÁS ARRIBA (primero) que el decorador `@track_errors`. Aiogram usa el orden de decoradores de abajo hacia arriba: el que está más cerca de la función se aplica primero.

```python
@game_router.message(Command("stop"))     # ← se aplica último (aiogram lo procesa después)
@error_tracker.track_errors()              # ← se aplica primero (envuelve la función)
async def cmd_stop(...):
```

### 10. Captura automática en los middlewares (recomendado, opcional)

En `src/middlewares/user_exists.py`, añadir captura al `except` actual:

```python
except Exception:
    logger.exception("Error al obtener/crear jugador %s", user.id)
    # NUEVO: Capturar en ErrorTracker
    try:
        from src.services.error_tracker import error_tracker
        await error_tracker.capture_exception(
            exc=Exception(),
            handler="UserExistsMiddleware",
            telegram_id=user.id if user else None,
            context={"middleware": "user_exists"},
        )
    except Exception:
        pass
    # ... resto del código ...
```

### 11. Crear tests en `tests/test_error_tracker.py`

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.db.models import ErrorLog
from src.services.error_tracker import ErrorTracker, _get_solution, KNOWN_SOLUTIONS


class TestGetSolution:
    def test_exact_match(self):
        sol, severity = _get_solution("sqlalchemy.exc.OperationalError")
        assert "PostgreSQL" in sol
        assert severity == "CRITICAL"

    def test_substring_match(self):
        sol, severity = _get_solution("sqlalchemy.exc.CustomError")
        # Debe matchear "sqlalchemy" genérico
        assert sol is not None
        # Como no hay "sqlalchemy" genérico en KNOWN_SOLUTIONS, caerá en Exception
        assert sol == KNOWN_SOLUTIONS["Exception"][0]

    def test_unknown_exception(self):
        sol, severity = _get_solution("foo.bar.BazError")
        assert sol == KNOWN_SOLUTIONS["Exception"][0]
        assert severity == "MEDIUM"

    def test_aiogram_bad_request(self):
        sol, severity = _get_solution("aiogram.exceptions.TelegramBadRequest")
        assert "Telegram rechazó" in sol
        assert severity == "LOW"

    def test_redis_connection_error(self):
        sol, severity = _get_solution("redis.exceptions.ConnectionError")
        assert "Redis" in sol
        assert severity == "CRITICAL"


class TestErrorTrackerCapture:
    @pytest.mark.asyncio
    @patch("src.services.error_tracker.async_session_factory")
    async def test_capture_exception_success(self, mock_session_factory):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        tracker = ErrorTracker()
        exc = ValueError("algo salió mal")

        log_id = await tracker.capture_exception(
            exc=exc,
            handler="test_handler",
            user_id=1,
            game_id=42,
            telegram_id=123456789,
            context={"foo": "bar"},
        )

        assert log_id is not None
        assert tracker.captured_count == 1
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.services.error_tracker.async_session_factory")
    async def test_capture_db_failure_does_not_crash(self, mock_session_factory):
        mock_session = AsyncMock()
        mock_session.commit.side_effect = Exception("DB fail")
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        tracker = ErrorTracker()
        exc = RuntimeError("test error")

        # No debe lanzar excepción aunque DB falle
        log_id = await tracker.capture_exception(exc=exc)
        assert log_id is None
        assert tracker.captured_count == 0

    def test_captured_count(self):
        tracker = ErrorTracker()
        assert tracker.captured_count == 0


class TestErrorTrackerTrackErrors:
    @pytest.mark.asyncio
    async def test_decorator_passthrough_on_success(self):
        tracker = ErrorTracker()

        @tracker.track_errors(handler_name="test")
        async def success_func():
            return 42

        result = await success_func()
        assert result == 42

    @pytest.mark.asyncio
    @patch("src.services.error_tracker.ErrorTracker.capture_exception")
    async def test_decorator_captures_and_raises(self, mock_capture):
        tracker = ErrorTracker()

        @tracker.track_errors(handler_name="test")
        async def failing_func():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await failing_func()

        mock_capture.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.services.error_tracker.ErrorTracker.capture_exception")
    async def test_decorator_passes_cancelled(self, mock_capture):
        """CancelledError debe relanzarse sin capturar."""
        tracker = ErrorTracker()

        @tracker.track_errors(handler_name="test")
        async def cancelled_func():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await cancelled_func()

        mock_capture.assert_not_called()


class TestErrorTrackerGenerateReport:
    @pytest.mark.asyncio
    @patch("src.services.error_tracker.async_session_factory")
    async def test_report_format_when_no_errors(self, mock_session_factory):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # Mock del repo
        mock_repo = AsyncMock()
        mock_repo.get_total_count.return_value = 0
        mock_repo.count_unresolved.return_value = 0
        mock_repo.get_most_frequent_exception.return_value = []
        mock_repo.get_recent.return_value = []

        from src.db.repositories.error_log_repository import ErrorLogRepository

        with patch.object(ErrorLogRepository, "__init__", return_value=None):
            with patch.object(ErrorLogRepository, "get_total_count", return_value=0):
                with patch.object(ErrorLogRepository, "count_unresolved", return_value=0):
                    with patch.object(ErrorLogRepository, "get_most_frequent_exception", return_value=[]):
                        with patch.object(ErrorLogRepository, "get_recent", return_value=[]):
                            tracker = ErrorTracker()
                            report = await tracker.generate_report()
                            assert "DIAGNÓSTICO" in report


class TestErrorLogModel:
    def test_error_log_creation(self):
        log = ErrorLog(
            level="ERROR",
            handler="test",
            exception_type="ValueError",
            exception_message="test message",
        )
        assert log.level == "ERROR"
        assert log.exception_type == "ValueError"
        assert log.resolved is False
        assert "ErrorLog" in repr(log)
```

### 12. Crear tests para el repositorio en `tests/test_error_log_repository.py`

```python
import pytest
from datetime import datetime, timezone, timedelta

from src.db.models import ErrorLog
from src.db.repositories.error_log_repository import ErrorLogRepository


class TestErrorLogRepository:
    @pytest.mark.asyncio
    async def test_create_and_retrieve(self, db_session):
        """Requiere fixture db_session con base de datos de prueba."""
        repo = ErrorLogRepository(db_session)
        log = await repo.create(
            level="ERROR",
            handler="test_handler",
            user_id=1,
            exception_type="ValueError",
            exception_message="algo salió mal",
            context={"extra": "data"},
        )
        assert log.id is not None
        assert log.level == "ERROR"
        assert log.handler == "test_handler"

    @pytest.mark.asyncio
    async def test_get_unresolved(self, db_session):
        repo = ErrorLogRepository(db_session)
        await repo.create(level="ERROR", handler="h1")
        await repo.create(level="ERROR", handler="h2")
        await repo.create(level="ERROR", handler="h3_resolved")
        # Marcar el último como resuelto
        all_logs = await repo.get_unresolved()
        assert len(all_logs) >= 2  # al menos 2 sin resolver

    @pytest.mark.asyncio
    async def test_count_by_level(self, db_session):
        repo = ErrorLogRepository(db_session)
        await repo.create(level="ERROR", handler="h1")
        await repo.create(level="WARNING", handler="h2")
        counts = await repo.count_by_level()
        assert counts.get("ERROR", 0) >= 1
        assert counts.get("WARNING", 0) >= 1
```

**Nota:** Los tests de integración requieren una base de datos real o `db_session` fixture. Crea una fixture `db_session` en `conftest.py` que use SQLite in-memory o testcontainers si tienes PostgreSQL disponible:

```python
# En tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.db.models import Base

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()
```

---

## Resumen de archivos a crear/modificar

| Archivo | Acción |
|---------|--------|
| `src/db/models.py` | + `ErrorLog` class |
| `src/db/repositories/error_log_repository.py` | CREAR |
| `src/db/repositories/__init__.py` | + `ErrorLogRepository` |
| `src/services/error_tracker.py` | CREAR |
| `src/services/__init__.py` | + `ErrorTracker`, `error_tracker` |
| `src/handlers/game/diagnose.py` | CREAR |
| `src/handlers/game/__init__.py` | + `diagnose_router` |
| `src/bot.py` | + `diagnose_router.include_router(...)` |
| `src/handlers/game/lobby.py` | + `@error_tracker.track_errors()` en cada handler |
| `src/handlers/game/round.py` | + `@error_tracker.track_errors()` en cada handler |
| `tests/test_error_tracker.py` | CREAR |
| `tests/test_error_log_repository.py` | CREAR |
| `tests/conftest.py` | + `db_session` fixture (si no existe) |

---

## Comandos nuevos del bot

| Comando | Descripción | Quién puede usarlo |
|---------|-------------|-------------------|
| `/diagnose` | Muestra informe de diagnóstico con top errores, soluciones sugeridas | Cualquiera en el grupo |
| `/errors` | Lista los últimos errores sin resolver | Cualquiera en el grupo |
| `/resolve [razón]` | Marca todos los errores como resueltos | Cualquiera en el grupo |

---

## Cómo probar en Telegram

1. **Probar `/diagnose` sin errores** — Debe mostrar "ninguno en el período seleccionado"
2. **Forzar un error** — Desconectar PostgreSQL temporalmente, ejecutar `/stop`, luego `/diagnose` debe mostrar `sqlalchemy.exc.OperationalError` con sugerencia "Revisa que PostgreSQL esté corriendo"
3. **Forzar un error** — Enviar al bot un callback_data inválido (no posible desde UI), pero puedes simularlo modificando temporalmente un handler para que lance `ValueError` y luego verificar que aparece en `/errors`
4. **Probar `/resolve`** — Después de `/errors`, ejecutar `/resolve revisado` y verificar que `/errors` muestra vacío
5. **Verificar que el decorador no rompe handlers exitosos** — Jugar una partida completa, todo debe funcionar normal

---

## Notas importantes

- El decorador `@track_errors()` captura la excepción, la persiste en DB, y **relanza** la excepción. Esto significa que el handler original sigue fallando con el error original. El beneficio es que el error queda registrado para diagnóstico sin cambiar el comportamiento actual.
- `CancelledError` NO se captura (se relanza sin registrar) porque las cancelaciones de tasks son normales en el ciclo de vida del bot.
- La lookup table `KNOWN_SOLUTIONS` usa matching por prefijo: si el tipo exacto no está, busca por partes. Ej: `sqlalchemy.exc.CustomError` → busca `sqlalchemy.exc` → no está → busca `sqlalchemy` → no está genérico → cae en `Exception`.
- Si quieres agregar más soluciones conocidas, solo añade entradas al dict `KNOWN_SOLUTIONS` en `error_tracker.py`.
- El reporte de `/diagnose` se limita a los últimos 60 minutos. Pasa `game_id` automáticamente si hay una partida activa en el grupo.
