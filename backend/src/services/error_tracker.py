import asyncio
import functools
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
        "Timeout conectando a Redis. Revisa que Redis responda con redis-cli ping.",
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
        "Error de red al conectar con Telegram API. Revisa conectividad a internet.",
        "HIGH",
    ),
    # HTTP / API
    "httpx.ConnectError": (
        "Error de conexión a API externa. "
        "Revisa la URL configurada en settings.spell_api_url.",
        "MEDIUM",
    ),
    "httpx.TimeoutException": (
        "Timeout en llamada a API externa. El servicio podría estar caído o lento.",
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
        module = type(exc).__module__
        exc_type = (
            type(exc).__qualname__ if module == "builtins"
            else f"{module}.{type(exc).__qualname__}"
        )
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
                    log.id,
                    exc_type,
                    handler,
                )
                return log.id
        except Exception as db_err:
            logger.error(
                "No se pudo persistir error en DB: %s. Error original: %s",
                db_err,
                exc_type,
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
                    raise
                except Exception as exc:
                    context: dict[str, Any] = {}
                    user_id = None
                    game_id = None
                    telegram_id = None

                    player = kwargs.get("player")
                    if player and include_user:
                        user_id = getattr(player, "id", None)
                        telegram_id = getattr(player, "telegram_id", None)

                    callback = kwargs.get("callback")
                    if callback:
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
                        context["chat_type"] = (
                            getattr(message.chat, "type", "") if message.chat else ""
                        )

                    context["handler"] = handler_name or func.__name__

                    await self.capture_exception(
                        exc,
                        handler=handler_name or func.__name__,
                        user_id=user_id,
                        game_id=game_id,
                        telegram_id=telegram_id,
                        context=context,
                    )
                    raise

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
                lines.append(
                    f"│    {sev_emoji.get(severity, '❓')} {exc_type} ({count} veces)"
                )
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
                    icon = {
                        "CRITICAL": "🔴",
                        "HIGH": "🟠",
                        "MEDIUM": "🟡",
                        "LOW": "ℹ️",
                    }.get(severity, "❓")

                lines.append("│")
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

        try:
            from src.services.spell_corrector import get_corrector

            corrector = get_corrector()
            api_metrics = corrector.get_api_metrics()
            if api_metrics["total_calls"] > 0 or api_metrics["failed_calls"] > 0:
                lines.append("│")
                lines.append("│ LLM API Calls (acumuladas):")
                lines.append(f"│    Provider: {api_metrics['provider']}")
                lines.append(f"│    Modo: {api_metrics['mode']}")
                lines.append(f"│    Total: {api_metrics['total_calls']}")
                lines.append(f"│    Fallos: {api_metrics['failed_calls']}")
                lines.append(
                    f"│    Restantes: {api_metrics['remaining']}/{api_metrics['limit']}"
                )

        except Exception:
            logger.warning("No se pudieron obtener métricas de la API de corrección")

        lines.append("└──────────────────────────────────────────────")
        return "\n".join(lines)

    @property
    def captured_count(self) -> int:
        return self._captured_count


# Singleton
error_tracker = ErrorTracker()
