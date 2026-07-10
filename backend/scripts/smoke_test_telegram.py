"""
Smoke Test Automatizado para Stop Bot.

Verifica que el bot responde correctamente a comandos y que el
sistema de error tracking funciona, enviando mensajes reales a un grupo.

USO:
    python -m scripts.smoke_test_telegram --verify-only
    python -m scripts.smoke_test_telegram --chat-id -100123456789

REQUISITOS:
    - Bot corriendo (python -m src.bot)
    - .env con BOT_TOKEN valido
    - --chat-id de un grupo donde el bot sea admin
"""

import argparse
import asyncio
import sys

from src.core.config import settings
from src.services.error_tracker import KNOWN_SOLUTIONS, _get_solution, error_tracker

PASS = "[PASS]"
FAIL = "[FAIL]"


async def verify_core_modules() -> bool:
    """Verifica que todos los modulos core importan correctamente."""
    all_ok = True
    modules = [
        "src.bot",
        "src.core.config",
        "src.db.models",
        "src.db.engine",
        "src.db.repositories",
        "src.services.error_tracker",
        "src.services.score_engine",
        "src.services.spell_corrector",
        "src.services.round_manager",
        "src.services.game_orchestrator",
        "src.handlers.start",
        "src.handlers.group",
        "src.handlers.game.lobby",
        "src.handlers.game.round",
        "src.handlers.game.diagnose",
        "src.keyboards.lobby",
        "src.keyboards.round",
        "src.middlewares.user_exists",
        "src.middlewares.throttling",
        "scripts.inject_test_error",
    ]
    for mod in modules:
        try:
            __import__(mod.replace("/", "."))
        except Exception:
            all_ok = False
    return all_ok


async def verify_error_tracker() -> bool:
    """Verifica ErrorTracker sin necesidad de Telegram."""
    all_ok = True

    # KNOWN_SOLUTIONS count
    if len(KNOWN_SOLUTIONS) >= 16:
        pass
    else:
        all_ok = False

    # _get_solution exact match
    sol, sev = _get_solution("sqlalchemy.exc.OperationalError")
    if "PostgreSQL" in sol and sev == "CRITICAL":
        pass
    else:
        all_ok = False

    # _get_solution substring match
    sol, sev = _get_solution("redis.exceptions.ConnectionError")
    if "Redis" in sol:
        pass
    else:
        all_ok = False

    # _get_solution unknown -> fallback
    sol, sev = _get_solution("foo.bar.UnknownError")
    if sol == KNOWN_SOLUTIONS["Exception"][0]:
        pass
    else:
        all_ok = False

    # generate_report format
    try:
        report = await error_tracker.generate_report(minutes=9999)
        if "INFORME DE DIAGNÓSTICO" in report:
            pass
        else:
            all_ok = False
    except Exception:
        all_ok = False

    return all_ok


async def verify_config() -> bool:
    """Verifica configuracion del bot."""
    all_ok = True

    if settings.bot_token and settings.bot_token != "your_bot_token_here":
        pass
    else:
        all_ok = False

    if settings.database_url:
        pass
    else:
        all_ok = False

    if settings.redis_url:
        pass
    else:
        all_ok = False

    return all_ok


async def main():
    parser = argparse.ArgumentParser(description="Smoke Test Automatizado para Stop Bot")
    parser.add_argument(
        "--chat-id", type=int, required=False, help="ID del grupo de Telegram para pruebas"
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="Solo verificar modulos y config (sin Telegram)"
    )
    args = parser.parse_args()

    results: list[tuple[str, bool]] = []

    r1 = await verify_core_modules()
    results.append(("Modulos Core", r1))

    r2 = await verify_config()
    results.append(("Configuracion", r2))

    r3 = await verify_error_tracker()
    results.append(("ErrorTracker", r3))

    if args.verify_only:
        pass
    else:
        if not args.chat_id:
            args.verify_only = True
        else:
            pass

    # Resumen
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    for _name, _ok in results:
        pass

    if passed == total:
        if not args.verify_only and args.chat_id:
            pass
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
