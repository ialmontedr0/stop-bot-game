import asyncio
import contextlib
import logging
import signal
import sys
import threading

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.storage.redis import RedisStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis as AsyncRedis

from src.core.config import settings
from src.db.engine import async_session_factory, engine
from src.db.repositories.leaderboard_repository import LeaderboardRepository
from src.db.repositories.message_log_repository import MessageLogRepository
from src.handlers.admin.event_creator import event_creator_router
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
from src.services.event_service import event_service
from src.services.game_orchestrator import game_orchestrator
from src.services.game_state_store import create_game_state_store

# -- Variables globales del modulo --
_redis_client: AsyncRedis | None = None
_game_state_store = None
_log_tasks: set[asyncio.Task] = set()
_scheduler: AsyncIOScheduler | None = None
_health_server = None
dp: Dispatcher | None = None


class LoggedBot(Bot):
    async def __call__(self, method, request_timeout=None):
        for attempt in range(3):
            try:
                return await super().__call__(method, request_timeout=request_timeout)
            except (TelegramRetryAfter, TelegramNetworkError) as e:
                if attempt < 2:
                    await asyncio.sleep(getattr(e, "retry_after", 1))
                else:
                    raise

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


def _promote_extra(
    _logger: logging.Logger,
    _method_name: str,
    event_dict: dict,
) -> dict:
    """Promueve el dict ``extra`` a la raíz del event_dict para structlog."""
    if "extra" in event_dict and isinstance(event_dict["extra"], dict):
        extra = event_dict.pop("extra")
        event_dict.update(extra)
    return event_dict


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
        structlog.stdlib.ExtraAdder(),
        _promote_extra,
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


async def _seed_bot_chats(bot: "LoggedBot") -> None:
    """Registra en bot_chats los grupos conocidos que no estén ya registrados."""
    from sqlalchemy import distinct, select

    from src.db.models import BotChat, Game

    async with async_session_factory() as session:
        stmt = select(distinct(Game.group_chat_id))
        result = await session.execute(stmt)
        known_group_ids = [row[0] for row in result.all()]

        if not known_group_ids:
            return

        existing_stmt = select(BotChat.chat_id)
        existing_result = await session.execute(existing_stmt)
        existing_ids = {row[0] for row in existing_result.all()}

        new_groups = [gid for gid in known_group_ids if gid not in existing_ids]
        if not new_groups:
            return

        added = 0
        for gid in new_groups:
            try:
                chat = await bot.get_chat(gid)
                title = chat.title or f"Grupo {gid}"
                chat_type = chat.type or "group"
            except Exception:
                title = f"Grupo {gid}"
                chat_type = "group"

            session.add(
                BotChat(
                    chat_id=gid,
                    chat_title=title,
                    chat_type=chat_type,
                )
            )
            added += 1

        await session.commit()
        if added:
            logger.info("BotChats sembrados desde games", extra={"added": added})


async def on_startup(bot: Bot) -> None:
    logger.info("Bot iniciado", version="1.0.0")

    from src.services.photo_cache import photo_cache

    expired = photo_cache.clear_expired()
    logger.info("Profile photo cache limpio", extra={"expired": expired})

    if _game_state_store is not None:
        from src.services.round_manager import round_manager

        restored_lobbies = await game_orchestrator.restore_from_store()
        restored_rounds = await round_manager.restore_from_store()
        logger.info(
            "Estado restaurado desde store",
            extra={"lobbies": restored_lobbies, "rounds": restored_rounds},
        )

    # Limpiar partidas huérfanas DESPUÉS de restaurar el store, para que
    # los lobbies/rondas restaurados sean evaluados correctamente.
    await game_orchestrator.cleanup_stale_games()

    # Sembrar bot_chats desde games conocidos (tablas preexistentes)
    await _seed_bot_chats(bot)

    # Limpieza de eventos expirados
    deactivated = await event_service.deactivate_expired()
    if deactivated:
        logger.info("Eventos expirados desactivados", extra={"count": deactivated})

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

    if dp is not None:
        logger.info("Deteniendo polling...")
        with contextlib.suppress(Exception):
            await dp.stop_polling()

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

    try:
        await get_corrector().close()
    except Exception:
        logger.exception("Error cerrando corrector ortográfico")

    if _health_server:
        logger.info("Deteniendo health server...")
        _health_server.shutdown()

    logger.info("Shutdown completo — señal: %s", sig_name)


async def on_shutdown() -> None:
    await _do_shutdown("aiogram_shutdown")


async def main() -> None:
    global _redis_client, _health_server, dp
    setup_logging()
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    # === Iniciar health server en thread separado ===
    try:
        _health_server = run_health_server_sync(port=9090)
        health_thread = threading.Thread(target=_health_server.serve_forever, daemon=True)
        health_thread.start()
    except Exception:
        pass

    try:
        _redis_client = AsyncRedis.from_url(settings.redis_url)
        await _redis_client.ping()
        redis_connected.set(1)
    except Exception:
        _redis_client = None
        redis_connected.set(0)

    # === Crear GameStateStore (Redis si disponible, sino PostgreSQL) ===
    global _game_state_store
    _game_state_store = await create_game_state_store(_redis_client)
    game_orchestrator.set_store(_game_state_store)
    from src.services.round_manager import round_manager

    round_manager.set_store(_game_state_store)

    if _redis_client:
        storage = RedisStorage(redis=_redis_client)
    else:
        from aiogram.fsm.storage.memory import MemoryStorage

        storage = MemoryStorage()

    bot = LoggedBot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await bot.get_me()

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
    dp.include_router(event_creator_router)

    throttle_mw = ThrottlingMiddleware()
    user_exists = UserExistsMiddleware()

    dp.message.middleware(throttle_mw)
    dp.callback_query.middleware(throttle_mw)
    dp.message.middleware(user_exists)
    dp.callback_query.middleware(user_exists)

    # Configurar graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(_do_shutdown(signal.Signals(s).name)),
            )
        except NotImplementedError:
            # Fallback para Windows: usar signal.signal()
            def _handler(s, frame, sig=sig):
                asyncio.ensure_future(_do_shutdown(signal.Signals(sig).name), loop=loop)

            signal.signal(sig, _handler)

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
