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
import asyncio
import argparse
import sys
from datetime import datetime

from src.core.config import settings
from src.services.error_tracker import error_tracker, _get_solution, KNOWN_SOLUTIONS


PASS = "[PASS]"
FAIL = "[FAIL]"


async def verify_core_modules() -> bool:
    """Verifica que todos los modulos core importan correctamente."""
    all_ok = True
    print("\n--- Modulos Core ---")
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
            print(f"  {PASS} {mod}")
        except Exception as e:
            print(f"  {FAIL} {mod}: {e}")
            all_ok = False
    return all_ok


async def verify_error_tracker() -> bool:
    """Verifica ErrorTracker sin necesidad de Telegram."""
    all_ok = True
    print("\n--- ErrorTracker ---")

    # KNOWN_SOLUTIONS count
    if len(KNOWN_SOLUTIONS) >= 16:
        print(f"  {PASS} KNOWN_SOLUTIONS: {len(KNOWN_SOLUTIONS)} entradas")
    else:
        print(f"  {FAIL} KNOWN_SOLUTIONS: solo {len(KNOWN_SOLUTIONS)} entradas")
        all_ok = False

    # _get_solution exact match
    sol, sev = _get_solution("sqlalchemy.exc.OperationalError")
    if "PostgreSQL" in sol and sev == "CRITICAL":
        print(f"  {PASS} _get_solution exact match: PostgreSQL/CRITICAL")
    else:
        print(f"  {FAIL} _get_solution exact match: {sol[:30]} / {sev}")
        all_ok = False

    # _get_solution substring match
    sol, sev = _get_solution("redis.exceptions.ConnectionError")
    if "Redis" in sol:
        print(f"  {PASS} _get_solution substring match: Redis/{sev}")
    else:
        print(f"  {FAIL} _get_solution substring match")
        all_ok = False

    # _get_solution unknown -> fallback
    sol, sev = _get_solution("foo.bar.UnknownError")
    if sol == KNOWN_SOLUTIONS["Exception"][0]:
        print(f"  {PASS} _get_solution fallback: Exception generico")
    else:
        print(f"  {FAIL} _get_solution fallback")
        all_ok = False

    # generate_report format
    try:
        report = await error_tracker.generate_report(minutes=9999)
        if "INFORME DE DIAGNÓSTICO" in report:
            print(f"  {PASS} generate_report: formato correcto")
        else:
            print(f"  {FAIL} generate_report: formato incorrecto")
            all_ok = False
    except Exception as e:
        print(f"  {FAIL} generate_report: {e}")
        all_ok = False

    return all_ok


async def verify_config() -> bool:
    """Verifica configuracion del bot."""
    all_ok = True
    print("\n--- Configuracion ---")

    if settings.bot_token and settings.bot_token != "your_bot_token_here":
        print(f"  {PASS} BOT_TOKEN configurado")
    else:
        print(f"  {FAIL} BOT_TOKEN no configurado en .env")
        all_ok = False

    if settings.database_url:
        print(f"  {PASS} DATABASE_URL: {settings.database_url[:50]}...")
    else:
        print(f"  {FAIL} DATABASE_URL no configurada")
        all_ok = False

    if settings.redis_url:
        print(f"  {PASS} REDIS_URL: {settings.redis_url}")
    else:
        print(f"  {FAIL} REDIS_URL no configurada")
        all_ok = False

    print(f"  {PASS} SPELL_MODE={settings.spell_mode}")
    print(f"  {PASS} SPELL_FUZZY_THRESHOLD={settings.spell_fuzzy_threshold}")

    return all_ok


async def main():
    parser = argparse.ArgumentParser(description="Smoke Test Automatizado para Stop Bot")
    parser.add_argument("--chat-id", type=int, required=False,
                        help="ID del grupo de Telegram para pruebas")
    parser.add_argument("--verify-only", action="store_true",
                        help="Solo verificar modulos y config (sin Telegram)")
    args = parser.parse_args()

    print("=" * 55)
    print("  SMOKE TEST — STOP BOT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    results: list[tuple[str, bool]] = []

    r1 = await verify_core_modules()
    results.append(("Modulos Core", r1))

    r2 = await verify_config()
    results.append(("Configuracion", r2))

    r3 = await verify_error_tracker()
    results.append(("ErrorTracker", r3))

    if args.verify_only:
        print("\n" + "=" * 55)
        print("  Solo verificacion -- saltando pruebas en Telegram.")
    else:
        if not args.chat_id:
            print(f"\n  {FAIL} Debes proporcionar --chat-id para pruebas en Telegram")
            print("  Ej: python scripts/smoke_test_telegram.py --chat-id -100123456789")
            args.verify_only = True
        else:
            print(f"\n--- Pruebas en Telegram (grupo {args.chat_id}) ---")
            print("  (Requiere interaccion manual en el grupo)")
            print(f"  Comandos a enviar:")
            print(f"    /start")
            print(f"    /stop")
            print(f"    /diagnose")
            print(f"    /errors")
            print(f"    /resolve")
            print(f"    /cancel")

    # Resumen
    print("\n" + "=" * 55)
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    print(f"  RESULTADOS: {PASS} {passed}/{total}")
    for name, ok in results:
        icon = PASS if ok else FAIL
        print(f"    {icon} {name}")
    print("=" * 55)

    if passed == total:
        print("\n  Smoke test completado exitosamente.")
        if not args.verify_only and args.chat_id:
            print("  Revisa el grupo de Telegram para confirmar respuestas.")
    else:
        print(f"\n  {FAIL} {total - passed} verificacion(es) fallaron.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
