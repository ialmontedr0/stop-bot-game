import asyncio
import logging
import signal
import sys
import threading

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis as AsyncRedis

from src.core.config import settings
from src.db.engine import async_session_factory, engine
from src.db.repositories.leaderboard_repository import LeaderboardRepository
from src.db.repositories.message_log_repository import MessageLogRepository
from src.handlers.admin.events import admin_router
from src.handlers.game import diagnose_router, game_router, round_router
from src.handlers.game.clear import clear_router
from src.handlers.game.clear_stats import clear_stats_router
from src.handlers.game.leaderboard import leaderboard_router
from src.handlers.game.profile import profile_router
from src.handlers.game.settings import settings_router
from src.handlers.game.stats import stats_router
from src.handlers.group import group_router
from src.handlers.start import start_router
from src.middlewares.throttling import ThrottlingMiddleware
from src.middlewares.user_exists import UserExistsMiddleware
from src.monitoring.health_server import run_health_server_sync
from src.monitoring.metrics import redis_connected
from src.services.game_orchestrator import game_orchestrator

# -- Variables globales del modulo --
_redis_client: AsyncRedis | None = None
_log_tasks: set[asyncio.Task] = set()
_scheduler: AsyncIOScheduler | None = None
_health_server = None
dp: Dispatcher | None = None


class LoggedBot(Bot):
    async def send_message(self, chat_id: int, text, **kwargs):
        msg = await super().send_message(chat_id, text, **kwargs)
        task = asyncio.create_task(self._log_message(chat_id, msg.message_id))
        _log_tasks.add(task)
        task.add_done_callback(_log_tasks.discard)
        return msg

    async def _log_message(self, chat_id: int, message_id: int) -> None:
        try:
            async with async_session_factory() as session:
                repo = MessageLogRepository(session)
                await repo.log_message(chat_id, message_id)
                await session.commit()
        except Exception:
            logger.exception("Error en _log_message: chat_id=%s message_id=%s", chat_id, message_id)


def setup_logging() -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    is_production = not sys.stdout.isatty()

    shared_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_production:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(indent=None, sort_keys=True),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger(__name__)


async def on_startup() -> None:
    logger.info("Bot iniciado", version="1.0.0")
    await game_orchestrator.cleanup_stale_games()

    # Cargar word lists de color/fruta/pais desde DB
    from src.services.spell_corrector import get_corrector

    await get_corrector().load_db_word_lists()
    logger.info("Word lists cargadas desde DB")

    # Cleanup old message logs (>7 days)
    async with async_session_factory() as session:
        repo = MessageLogRepository(session)
        await repo.cleanup_old()
        await session.commit()

    # === Scheduler semanal: cerrar leaderboard los lunes 00:00 ===
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        LeaderboardRepository.close_week,
        trigger="cron",
        day_of_week="mon",
        hour=0,
        minute=0,
    )
    _scheduler.start()
    logger.info("Scheduler semanal iniciado (leaderboard close cada lunes 00:00)")


async def _do_shutdown(sig_name: str = "shutdown") -> None:
    logger.info("Ejecutando shutdown graceful (señal: %s)...", sig_name)

    print(f"[SHUTDOWN] Señal {sig_name} recibida, iniciando shutdown...", flush=True)

    if dp is not None:
        logger.info("Deteniendo polling...")
        try:
            await dp.stop_polling()
        except Exception:
            pass

    logger.info("Cancelando partidas activas...")
    try:
        await game_orchestrator.cancel_all_games()
    except Exception:
        logger.exception("Error cancelando partidas")

    if _scheduler:
        logger.info("Deteniendo scheduler...")
        _scheduler.shutdown(wait=False)

    logger.info("Cerrando pool de BD...")
    await engine.dispose()

    if _redis_client:
        logger.info("Cerrando Redis...")
        await _redis_client.close()

    from src.services.spell_corrector import get_corrector

    await get_corrector().close()

    if _health_server:
        logger.info("Deteniendo health server...")
        _health_server.shutdown()

    logger.info("Shutdown completo — señal: %s", sig_name)
    print(f"[SHUTDOWN] Graceful shutdown completado ({sig_name})", flush=True)


async def on_shutdown() -> None:
    await _do_shutdown("aiogram_shutdown")


async def main() -> None:
    global _redis_client, _health_server, dp
    print("[BOOT] Configurando logging...", flush=True)
    setup_logging()
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    # === Iniciar health server en thread separado ===
    print("[BOOT] Iniciando health server en puerto 9090...", flush=True)
    try:
        _health_server = run_health_server_sync(port=9090)
        health_thread = threading.Thread(target=_health_server.serve_forever, daemon=True)
        health_thread.start()
        print("[BOOT] Health server OK en puerto 9090", flush=True)
    except Exception as e:
        print(f"[BOOT] Health server no disponible: {e}", flush=True)

    print("[BOOT] Conectando a Redis...", flush=True)
    try:
        _redis_client = AsyncRedis.from_url(settings.redis_url)
        await _redis_client.ping()
        redis_connected.set(1)
        print("[BOOT] Redis OK", flush=True)
    except Exception as e:
        print(f"[BOOT] ERROR: Redis no disponible: {e}", flush=True)
        print("[BOOT] El bot continuara sin Redis (sin FSM persistente)", flush=True)
        _redis_client = None
        redis_connected.set(0)

    if _redis_client:
        storage = RedisStorage(redis=_redis_client)
    else:
        from aiogram.fsm.storage.memory import MemoryStorage

        storage = MemoryStorage()

    print("[BOOT] Autenticando con Telegram...", flush=True)
    bot = LoggedBot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    print(f"[BOOT] Bot autenticado: @{me.username} (ID: {me.id})", flush=True)

    dp = Dispatcher(storage=storage)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp.include_router(start_router)
    dp.include_router(group_router)
    dp.include_router(game_router)
    dp.include_router(round_router)
    dp.include_router(diagnose_router)
    dp.include_router(settings_router)
    dp.include_router(clear_router)
    dp.include_router(clear_stats_router)
    dp.include_router(stats_router)
    dp.include_router(profile_router)
    dp.include_router(leaderboard_router)
    dp.include_router(admin_router)

    throttle_mw = ThrottlingMiddleware()
    user_exists = UserExistsMiddleware()

    dp.message.middleware(throttle_mw)
    dp.callback_query.middleware(throttle_mw)
    dp.message.middleware(user_exists)
    dp.callback_query.middleware(user_exists)

    # Configurar graceful shutdown
    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(_do_shutdown(signal.Signals(s).name)),
            )
        print("[BOOT] Graceful shutdown configurado (SIGTERM/SIGINT)", flush=True)
    else:
        print("[BOOT] Graceful shutdown: Windows detectado, usando finally", flush=True)

    print("[BOOT] Iniciando polling...", flush=True)
    logger.info("Iniciando polling...")
    try:
        await dp.start_polling(bot, skip_updates=False)
    finally:
        logger.info("Polling finalizado")
        await _do_shutdown("polling_stop")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
