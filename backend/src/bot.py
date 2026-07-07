import asyncio
import logging
import sys

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis as AsyncRedis

from src.core.config import settings
from src.db.engine import engine
from src.handlers.group import group_router
from src.handlers.start import start_router
from src.handlers.game import diagnose_router, game_router, round_router
from src.handlers.game.settings import settings_router
from src.middlewares.throttling import ThrottlingMiddleware
from src.middlewares.user_exists import UserExistsMiddleware
from src.services.game_orchestrator import game_orchestrator

# -- Variables globales del modulo --
_redis_client: AsyncRedis | None = None


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
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


async def on_shutdown() -> None:
    await engine.dispose()
    if _redis_client:
        await _redis_client.close()
    from src.services.spell_corrector import get_corrector

    await get_corrector().close()
    logger.info("Bot detenido")


async def main() -> None:
    global _redis_client
    print("[BOOT] Configurando logging...", flush=True)
    setup_logging()
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    print("[BOOT] Conectando a Redis...", flush=True)
    try:
        _redis_client = AsyncRedis.from_url(settings.redis_url)
        await _redis_client.ping()
        print("[BOOT] Redis OK", flush=True)
    except Exception as e:
        print(f"[BOOT] ERROR: Redis no disponible: {e}", flush=True)
        print("[BOOT] El bot continuará sin Redis (sin FSM persistente)", flush=True)
        _redis_client = None

    if _redis_client:
        storage = RedisStorage(redis=_redis_client)
    else:
        from aiogram.fsm.storage.memory import MemoryStorage

        storage = MemoryStorage()

    print("[BOOT] Autenticando con Telegram...", flush=True)
    bot = Bot(
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

    throttle_mw = ThrottlingMiddleware()
    user_exists = UserExistsMiddleware()

    dp.message.middleware(throttle_mw)
    dp.callback_query.middleware(throttle_mw)
    dp.message.middleware(user_exists)
    dp.callback_query.middleware(user_exists)

    print("[BOOT] Iniciando polling...", flush=True)
    logger.info("Iniciando polling...")
    await dp.start_polling(bot, skip_updates=False)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
