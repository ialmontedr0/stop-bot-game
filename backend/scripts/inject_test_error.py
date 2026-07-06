"""
Script para inyectar errores controlados en la BD y probar el ErrorTracker.

USO:
    python -m scripts.inject_test_error inject    # Inyecta 9 errores de prueba
    python -m scripts.inject_test_error verify    # Muestra el reporte esperado
    python -m scripts.inject_test_error cleanup   # Marca errores inyectados como resueltos
"""
import asyncio
import argparse
import sys

from src.db.engine import async_session_factory
from src.db.repositories.error_log_repository import ErrorLogRepository
from src.services.error_tracker import error_tracker


EXCEPTIONS = [
    ("sqlalchemy.exc.OperationalError", "could not connect to server: Connection refused", "CRITICAL"),
    ("sqlalchemy.exc.IntegrityError", "duplicate key value violates unique constraint", "HIGH"),
    ("sqlalchemy.exc.ProgrammingError", 'relation "games" does not exist', "CRITICAL"),
    ("sqlalchemy.exc.TimeoutError", "queue pool size exceeded", "MEDIUM"),
    ("redis.exceptions.ConnectionError", "Error 10061 connecting to localhost:6379", "CRITICAL"),
    ("aiogram.exceptions.TelegramForbiddenError", "bot was kicked from the group", "MEDIUM"),
    ("httpx.ConnectError", "[Errno 11001] getaddrinfo failed", "MEDIUM"),
    ("KeyError", "'_rounds'", "HIGH"),
    ("asyncio.TimeoutError", "", "MEDIUM"),
]


async def inject():
    print("Inyectando errores de prueba en error_logs...")
    async with async_session_factory() as session:
        repo = ErrorLogRepository(session)
        for exc_type, msg, level in EXCEPTIONS:
            log = await repo.create(
                level=level,
                handler=f"injected_{exc_type.split('.')[-1]}",
                user_id=1,
                game_id=42,
                telegram_id=123456789,
                exception_type=exc_type,
                exception_message=msg or "(sin mensaje)",
                traceback=(
                    f'Traceback (most recent call last):\n'
                    f'  File "smoke_test.py", line 1, in <module>\n'
                    f'    raise {exc_type}("{msg}")\n'
                    f'{exc_type}: {msg}'
                ),
                context={"injected": True, "source": "smoke_test", "phase": "4D"},
            )
            print(f"  OK #{log.id} {exc_type}")
    print(f"\nInyectados {len(EXCEPTIONS)} errores. Ejecuta /diagnose en el grupo para verlos.")


async def verify():
    print("\n" + "=" * 55)
    print("  REPORTE DE DIAGNÓSTICO PREVISTO")
    print("=" * 55)
    report = await error_tracker.generate_report(minutes=9999)
    ascii_safe = report.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    print(ascii_safe)


async def cleanup():
    async with async_session_factory() as session:
        repo = ErrorLogRepository(session)
        errors = await repo.get_unresolved()
        count = 0
        for err in errors:
            if err.context and '"injected": true' in err.context:
                await repo.mark_resolved(err.id, resolution="Eliminado post-smoke-test-4D")
                count += 1
        print(f"Marcados {count} errores inyectados como resueltos.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inyecta errores de prueba en error_logs")
    parser.add_argument("action", choices=["inject", "verify", "cleanup"], default="inject")
    args = parser.parse_args()

    if args.action == "inject":
        asyncio.run(inject())
    elif args.action == "verify":
        asyncio.run(verify())
    elif args.action == "cleanup":
        asyncio.run(cleanup())
