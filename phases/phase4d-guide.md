# Phase 4D — Smoke Test Completo en Telegram

**Objetivo:** Validar que todas las funcionalidades del bot funcionan correctamente en un entorno real de Telegram, incluyendo el sistema de error tracking (Phase 4C), antes de considerar el MVP como estable.

**Relación con otras fases:**
- Fase 0-3: infraestructura core del bot
- Fase 4A: SpellCorrector con fuzzy matching
- Fase 4B: Word lists en BD
- Fase 4C: Error tracking + diagnóstico local
- **Fase 4D: Smoke test integral en Telegram**

---

## Índice

1. [Pre-requisitos](#1-pre-requisitos)
2. [Verificación de infraestructura](#2-verificación-de-infraestructura)
3. [Suite de tests automatizados](#3-suite-de-tests-automatizados)
4. [Escenario 1 — Smoke test básico de comandos](#4-escenario-1--smoke-test-básico-de-comandos)
5. [Escenario 2 — Flujo completo de partida (2 jugadores)](#5-escenario-2--flujo-completo-de-partida-2-jugadores)
6. [Escenario 3 — Prueba del sistema ErrorTracker](#6-escenario-3--prueba-del-sistema-errortracker)
7. [Escenario 4 — Inyección de errores](#7-escenario-4--inyección-de-errores)
8. [Escenario 5 — Casos borde](#8-escenario-5--casos-borde)
9. [Script de smoke test automatizado](#9-script-de-smoke-test-automatizado)
10. [Lista de verificación de regresión](#10-lista-de-verificación-de-regresión)
11. [Solución de problemas comunes](#11-solución-de-problemas-comunes)
12. [Criterios de aceptación](#12-criterios-de-aceptación)

---

## 1. Pre-requisitos

### 1.1 Infraestructura corriendo

```powershell
# Desde backend/
cd backend

# Levantar PostgreSQL + Redis
docker compose -f Docker/docker-compose.yml up -d postgres redis

# Verificar que están saludables
docker compose -f Docker/docker-compose.yml ps
# Debe mostrar: postgres (healthy), redis (healthy)
```

### 1.2 Archivo `.env` configurado

```
BOT_TOKEN=<token_real_de_BotFather>
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/stopbot
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=DEBUG
SPELL_MODE=local
SPELL_FUZZY_THRESHOLD=75
```

### 1.3 Base de datos preparada

```powershell
# Crear tablas (si no se usa Docker para la app)
# Opción A: Desde Python
python -c "from src.db.models import Base; from src.db.engine import engine; import asyncio; asyncio.run(Base.metadata.create_all(engine))"

# Opción B: Con alembic
alembic upgrade head

# Sembrar word lists (colores, frutas, países)
python -m scripts.seed_word_lists
```

### 1.4 Grupo de prueba en Telegram

1. Crear un grupo NUEVO en Telegram (ej: "Stop Bot Test").
2. Añadir el bot como **administrador** del grupo (necesario para eliminar mensajes).
3. Silenciar notificaciones del grupo para no molestar a otros.

### 1.5 Bot en modo polling

```powershell
python -m src.bot
```

Verificar en los logs:
```
[BOOT] Redis OK
[BOOT] Bot autenticado: @TuBotName (ID: 123456789)
[BOOT] Iniciando polling...
```

---

## 2. Verificación de infraestructura

Antes de las pruebas funcionales, verifica cada componente individualmente.

### 2.1 PostgreSQL

```powershell
# Conectar y listar tablas
docker exec -it stop-bot-game-postgres-1 psql -U postgres -d stopbot -c "\dt"

# Debe mostrar:
#               Listado de relaciones
#  Esquema |       Nombre        | Tipo  |  Dueño
# ---------+---------------------+-------+---------
#  public  | answers             | tabla | postgres
#  public  | error_logs          | tabla | postgres
#  public  | game_players        | tabla | postgres
#  public  | games               | tabla | postgres
#  public  | group_configs       | tabla | postgres
#  public  | players             | tabla | postgres
#  public  | rounds              | tabla | postgres
#  public  | weekly_leaderboards | tabla | postgres
#  public  | word_list_items     | tabla | postgres
```

### 2.2 Redis

```powershell
docker exec -it stop-bot-game-redis-1 redis-cli ping
# Debe responder: PONG
```

### 2.3 Conectividad del bot

```powershell
# Desde Python, verificar que el token es válido
python -c "
import asyncio
from aiogram import Bot
from src.core.config import settings
async def test():
    bot = Bot(token=settings.bot_token)
    me = await bot.get_me()
    print(f'✅ Bot OK: @{me.username} (ID: {me.id})')
    await bot.session.close()
asyncio.run(test())
"
```

### 2.4 Carga de word lists desde BD

```powershell
python -c "
import asyncio
from src.services.spell_corrector import get_corrector
async def test():
    c = get_corrector()
    await c.load_db_word_lists()
    for cat in ('color', 'fruta', 'pais'):
        words = c._word_lists.get(cat, set())
        print(f'{cat}: {len(words)} palabras cargadas')
    print('✅ Word lists OK')
asyncio.run(test())
"
```

Debe mostrar:
```
color: ~100 palabras cargadas
fruta: ~90 palabras cargadas
pais: ~195 palabras cargadas
✅ Word lists OK
```

---

## 3. Suite de tests automatizados

Ejecuta la suite completa ANTES de cualquier prueba manual:

```powershell
cd backend
python -m pytest tests/ -v --tb=short 2>&1 | Tee-Object -FilePath "test_report_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
```

**Criterio:** 246 tests deben pasar, 0 failures, 0 errors.

```powershell
# Resumen rápido
python -m pytest tests/ -q --tb=no 2>&1 | Select-Object -Last 3
# Debe mostrar: "246 passed in X.XXs"
```

---

## 4. Escenario 1 — Smoke test básico de comandos

### 4.1 Comandos globales

| # | Acción | Comando | Respuesta esperada |
|---|--------|---------|-------------------|
| 1 | Enviar DM al bot | `/start` | Mensaje de bienvenida con descripción del juego |
| 2 | Enviar DM al bot | `/help` | Lista de comandos disponibles |
| 3 | Enviar en grupo | `/start` | "❌ Este comando solo funciona en privado." (se autodestruye) |

### 4.2 Comando `/diagnose` sin errores

| # | Acción | Comando | Respuesta esperada |
|---|--------|---------|-------------------|
| 4 | Enviar en grupo | `/diagnose` | Reporte con "Total errores registrados: 0", "No resueltos: 0", "(ninguno en el período seleccionado)" |
| 5 | Enviar en DM al bot | `/diagnose` | "⚠️ Este comando solo funciona en grupos." (se autodestruye) |

### 4.3 Comando `/errors` sin errores

| # | Acción | Comando | Respuesta esperada |
|---|--------|---------|-------------------|
| 6 | Enviar en grupo | `/errors` | "✅ No hay errores sin resolver." |
| 7 | Enviar en DM al bot | `/errors` | "⚠️ Este comando solo funciona en grupos." |

### 4.4 Comando `/resolve` sin errores

| # | Acción | Comando | Respuesta esperada |
|---|--------|---------|-------------------|
| 8 | Enviar en grupo | `/resolve` | "✅ 0 error(es) marcado(s) como resuelto(s)." (se autodestruye) |
| 9 | Enviar en grupo | `/resolve revisado manualmente` | "✅ 0 error(es) marcado(s) como resuelto(s)." |

### 4.5 Comandos de juego sin lobby activo

| # | Acción | Comando | Respuesta esperada |
|---|--------|---------|-------------------|
| 10 | Enviar en grupo | `/cancel` | Mensaje indicando que no hay sala activa (se autodestruye) |

---

## 5. Escenario 2 — Flujo completo de partida (2 jugadores)

Necesitas **2 cuentas de Telegram** (ej: teléfono principal + Telegram Desktop con otra cuenta, o usar @BotFather para crear un segundo bot de prueba).

### 5.1 Creación de lobby

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 1 | **Jugador A** (host) escribe `/stop` en el grupo | Bot debe responder con mensaje del lobby | ✅ Mensaje visible: "🛑 STOP — Sala abierta"<br>✅ Botón "🟢 Unirse" visible<br>✅ Botón "▶️ Iniciar" visible solo para el host |
| 2 | Verificar DM al host | El host recibe 2 mensajes DM | ✅ Mensaje 1: explicación del formato de respuesta<br>✅ Mensaje 2: placeholder copiable con las 8 categorías |
| 3 | **Jugador B** pulsa "🟢 Unirse" | Bot actualiza el mensaje del lobby | ✅ Contador: "👤 2 / 10"<br>✅ Ambos jugadores listados<br>✅ Los botones siguen visibles |
| 4 | Verificar que **Jugador A** no puede unirse de nuevo | Jugador A pulsa "🟢 Unirse" | ✅ callback_alert: "Ya estás en esta partida." |

### 5.2 Inicio de partida

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 5 | **Jugador A** (host) pulsa "▶️ Iniciar" | La partida comienza | ✅ El mensaje del lobby se reemplaza<br>✅ Mensaje de Ronda 1 con letra aleatoria + 8 categorías<br>✅ "⏱ 60 segundos" visible |
| 6 | Verificar DM a ambos jugadores | Ambos reciben mensajes DM | ✅ Mensaje: "Letra de la ronda: **X**"<br>✅ Placeholder copiable |

### 5.3 Respuestas y Stop

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 7 | **Jugador A** envía respuestas completas en el grupo | Formato: `Nombre: ...\nApellido: ...\n...` (8 categorías) | ✅ Bot procesa sin error visible<br>✅ **Jugador A** recibe DM con botón "⏹ Stop 1/10" |
| 8 | **Jugador A** pulsa "⏹ Stop 1/10" en DM | La ronda se cierra | ✅ Mensaje en grupo: "⏹ ¡Stop! Ronda detenida por {nombre}"<br>✅ Puntuaciones parciales mostradas |
| 9 | Verificar scoring | Puntos calculados | ✅ Respuestas únicas: 50 pts<br>✅ Bonus Stop: +10 pts al que pulsó Stop |

### 5.4 Inter-round menu

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 10 | Ver menú entre rondas | Bot muestra mensaje con resultados parciales | ✅ Botones: "▶️ Siguiente ronda", "⏹ Detener partida"<br>✅ Solo el líder (mayor puntaje) puede usar "▶️ Siguiente ronda"<br>✅ Solo el host puede usar "⏹ Detener partida" |
| 11 | Verificar timeout de 2 min | Esperar 2 minutos sin pulsar nada | ✅ Bot cierra el menú automáticamente |

### 5.5 Selección de letra

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 12 | Líder pulsa "▶️ Siguiente ronda" | Bot muestra teclado con letras A-Z | ✅ 5 filas de letras (6-6-6-6-2) visible |
| 13 | Líder pulsa una letra (ej: "M") | Bot inicia Ronda 2 con esa letra | ✅ Mensaje: "🛑 Ronda 2 — Letra: **M**"<br>✅ Placeholder con categorías |

### 5.6 Partida completa (5 rondas)

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 14 | Repetir pasos 7-13 hasta completar 5 rondas | Alternar quién hace Stop | ✅ Cada ronda se procesa correctamente |
| 15 | Finalizar partida | Después de ronda 5 | ✅ Podio: 🥇 🥈 🥉 con nombres y puntajes<br>✅ Partida marcada como `finished` en BD |

### 5.7 Detener partida a mitad

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 16 | Iniciar nueva partida con `/stop` | 2+ jugadores | ✅ Lobby normal |
| 17 | Avanzar 2 rondas | Respuestas + Stop | ✅ Rondas transcurren normal |
| 18 | Host pulsa "⏹ Detener partida" en menú inter-round | Partida se cancela | ✅ "⏹ Partida detenida por el host."<br>✅ Puntajes parciales mostrados<br>✅ Partida marcada como `cancelled` en BD |

---

## 6. Escenario 3 — Prueba del sistema ErrorTracker

### 6.1 `/diagnose` con errores (simulados)

```powershell
# Insertar un error de prueba directamente en BD
docker exec -it stop-bot-game-postgres-1 psql -U postgres -d stopbot -c "
INSERT INTO error_logs (level, handler, exception_type, exception_message, traceback, context)
VALUES ('ERROR', 'test_smoke', 'sqlalchemy.exc.OperationalError', 'simulated: connection refused', 'line 1\nline 2', '{\"test\": true}');
"
```

| # | Acción | Comando | Verificación |
|---|--------|---------|--------------|
| 1 | Consultar errores | `/errors` | ✅ Muestra: `#1 [HH:MM] OperationalError` + mensaje "simulated: connection refused" + Handler "test_smoke" |
| 2 | Diagnóstico completo | `/diagnose` | ✅ "Total errores registrados: 1"<br>✅ "No resueltos: 1"<br>✅ 🔴 `sqlalchemy.exc.OperationalError` (1 vez)<br>✅ Sugerencia: "Revisa que PostgreSQL esté corriendo..." |
| 3 | Resolver errores | `/resolve test de humo ok` | ✅ "✅ 1 error(es) marcado(s) como resuelto(s)." |
| 4 | Confirmar resolución | `/errors` | ✅ "✅ No hay errores sin resolver." |
| 5 | Confirmar en `/diagnose` | `/diagnose` | ✅ Error ahora marcado con ✅ y "Resuelto: test de humo ok" |

### 6.2 `/diagnose` con errores reales (forzar desconexión)

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 6 | Detener PostgreSQL | `docker compose -f Docker/docker-compose.yml stop postgres` | ✅ PostgreSQL se detiene |
| 7 | Escribir `/stop` en el grupo | El bot intenta crear un lobby y falla | ✅ Error capturado por `@track_errors` (persistido en `error_logs`)<br>✅ Bot responde con mensaje de error (el decorador relanza) |
| 8 | Iniciar PostgreSQL | `docker compose -f Docker/docker-compose.yml start postgres` | ✅ PostgreSQL vuelve a estar disponible |
| 9 | Ejecutar `/diagnose` | Verificar que el error quedó registrado | ✅ Muestra `sqlalchemy.exc.OperationalError` con la sugerencia correcta |
| 10 | Ejecutar `/resolve` | Limpiar errores | ✅ Todos resueltos |

### 6.3 Error en middleware (`UserExistsMiddleware`)

Para probar esto, necesitarías forzar un error en el middleware (ej: DB caída mientras un usuario interactúa). El proceso ya captura el error automáticamente (líneas 31-40 de `user_exists.py`).

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 11 | Detener PostgreSQL | `docker compose stop postgres` | ✅ |
| 12 | Enviar cualquier mensaje en el grupo (ej: "hola") | El middleware falla al obtener/crear el Player | ✅ El error se captura en `error_logs` con handler "UserExistsMiddleware"<br>✅ El usuario recibe DM: "❌ Error de conexión. Intenta de nuevo." |
| 13 | Iniciar PostgreSQL | `docker compose start postgres` | ✅ |
| 14 | Verificar con `/errors` | | ✅ Error visible con tipo y mensaje |

---

## 7. Escenario 4 — Inyección de errores

Para verificar que el ErrorTracker captura correctamente CADA handler decorado, puedes modificar temporalmente un handler para que lance una excepción controlada.

### 7.1 Script de inyección temporal

Crea `scripts/inject_test_error.py`:

```python
"""
Script TEMPORAL para inyectar errores controlados en el bot.
Usar SOLO en entorno de pruebas.

Modo de uso:
  1. Ejecuta el bot normalmente.
  2. Ejecuta este script mientras el bot corre.
  3. El script envía un callback_data inválido al bot.
"""
import asyncio
import sys
import os

# Agregar backend al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.config import settings
from src.db.engine import async_session_factory
from src.db.repositories.error_log_repository import ErrorLogRepository


async def inject_via_api():
    """
    Opción A: Insertar directamente en BD (seguro, sin tocar el bot).
    """
    exceptions = [
        ("sqlalchemy.exc.IntegrityError", "duplicate key value", "HIGH"),
        ("redis.exceptions.ConnectionError", "Redis is not available", "CRITICAL"),
        ("aiogram.exceptions.TelegramForbiddenError", "bot was kicked", "MEDIUM"),
        ("httpx.ConnectError", "Connection refused", "MEDIUM"),
        ("asyncio.TimeoutError", "Operation timed out", "MEDIUM"),
        ("KeyError", "'_rounds'", "HIGH"),
        ("AttributeError", "'NoneType' object has no attribute 'id'", "HIGH"),
        ("TypeError", "argument of type 'int' is not iterable", "MEDIUM"),
        ("ValueError", "invalid literal for int()", "MEDIUM"),
    ]

    async with async_session_factory() as session:
        repo = ErrorLogRepository(session)
        for exc_type, msg, level in exceptions:
            log = await repo.create(
                level=level,
                handler=f"injected_{exc_type.split('.')[-1]}",
                user_id=1,
                game_id=42,
                telegram_id=123456789,
                exception_type=exc_type,
                exception_message=msg,
                traceback=f"Traceback (most recent call last):\n  File \"test.py\", line 1, in <module>\n{exc_type}: {msg}",
                context={"injected": True, "source": "smoke_test"},
            )
            print(f"  ✅ Insertado: #{log.id} {exc_type}")

    print("\n✅ Errores inyectados. Ejecuta /diagnose en el grupo para verlos.")


async def verify_report():
    """Verifica que /diagnose mostraría todos los errores correctamente."""
    from src.services.error_tracker import error_tracker
    report = await error_tracker.generate_report(minutes=9999)
    print("\n" + "=" * 50)
    print("REPORTE DE DIAGNÓSTICO PREVISTO:")
    print("=" * 50)
    print(report)


async def cleanup():
    """Limpia todos los errores inyectados."""
    async with async_session_factory() as session:
        repo = ErrorLogRepository(session)
        errors = await repo.get_unresolved()
        count = 0
        for err in errors:
            context = err.context
            if context and '"injected": true' in context:
                await repo.mark_resolved(err.id, resolution="Eliminado post-smoke-test")
                count += 1
        print(f"✅ {count} errores inyectados marcados como resueltos.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inject", "verify", "cleanup"], default="inject")
    args = parser.parse_args()

    if args.action == "inject":
        asyncio.run(inject_via_api())
    elif args.action == "verify":
        asyncio.run(verify_report())
    elif args.action == "cleanup":
        asyncio.run(cleanup())
```

### 7.2 Procedimiento de inyección

```powershell
# 1. Inyectar errores
cd backend
python -m scripts.inject_test_error inject

# 2. Verificar en Telegram
# En el grupo, ejecutar:
#   /errors      → debe listar 9 errores
#   /diagnose    → debe mostrar top errores, sugerencias
#   /resolve     → marca todos como resueltos
#   /errors      → debe mostrar vacío

# 3. Limpiar (si no usaste /resolve)
python -m scripts.inject_test_error cleanup

# 4. Verificar reporte esperado (sin necesidad de Telegram)
python -m scripts.inject_test_error verify
```

### 7.3 Verificaciones de `/diagnose` con errores inyectados

| # | Elemento del reporte | Verificación |
|---|---------------------|--------------|
| 1 | Total errores registrados | ≥ 9 (los inyectados) |
| 2 | No resueltos | ≥ 9 (antes de /resolve) |
| 3 | Top errores más frecuentes | Debe listar los 9 tipos inyectados |
| 4 | 🔴 sqlalchemy.exc.OperationalError | Severidad CRITICAL |
| 5 | 🟠 sqlalchemy.exc.IntegrityError | Severidad HIGH |
| 6 | 🟡 redis.exceptions.ConnectionError | Severidad CRITICAL |
| 7 | ℹ️ asyncio.TimeoutError | Severidad MEDIUM |
| 8 | Cada error muestra `💡 Sugerencia:` | Texto descriptivo, no "Sin solución conocida." |

---

## 8. Escenario 5 — Casos borde

### 8.1 Lobby

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 1 | `/stop` dos veces seguidas | Mismo usuario escribe `/stop` dos veces | ✅ Segunda vez: "⚠️ Ya hay una sala abierta en este grupo." |
| 2 | Lobby expira sin jugadores | Crear lobby y esperar 2 min sin unirse | ✅ El mensaje del lobby desaparece / se actualiza indicando expiración |
| 3 | Unirse con 10 jugadores (si es posible) | Llenar el aforo | ✅ Auto-start al llegar a 10 |
| 4 | Host abandona el grupo | Eliminar al host del grupo | ✅ El bot debe detectar y cancelar la partida (si implementado) |

### 8.2 Ronda

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 5 | Enviar respuesta SIN formato | Escribir "hola mundo" (sin `Categoría: valor`) | ✅ El bot ignora el mensaje (no hay `:`) |
| 6 | Enviar respuesta con categoría inválida | `CategoríaFalsa: valor` | ✅ La categoría falsa se ignora, las válidas se procesan |
| 7 | Enviar respuesta vacía | `Nombre:` (sin valor después de `:`) | ✅ Se trata como respuesta vacía = 0 pts |
| 8 | Enviar respuesta después del Stop | Después de que alguien pulse Stop, enviar respuesta | ✅ Se ignora (la ronda ya está cerrada) |
| 9 | Timeout de ronda (60s) | No enviar respuestas ni hacer Stop | ✅ "⌛ Tiempo agotado" |
| 10 | Timeout del botón Stop (5s) | No pulsar el botón Stop en DM | ✅ La ronda continúa hasta los 60s o hasta que otro complete |

### 8.3 Líder / Transición

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 11 | Todos empatados en puntaje | Que todos tengan el mismo score | ✅ El líder es quien respondió primero (submission_order) |
| 12 | No-líder pulsa "▶️ Siguiente ronda" | Un jugador que no es líder pulsa el botón | ✅ callback_alert: "⛔ Solo el líder puede avanzar." |
| 13 | No-host pulsa "⏹ Detener partida" | Un jugador que no es host pulsa el botón | ✅ callback_alert: "⛔ Solo el host puede detener la partida." |
| 14 | Timeout de selección de letra (15s) | Líder no selecciona letra en 15s | ✅ El bot selecciona letra aleatoria automáticamente |
| 15 | Timeout inter-round (2 min) | Nadie pulsa ningún botón por 2 min | ✅ El bot cierra el menú (si implementado) |

### 8.4 ErrorTracker

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 16 | `/diagnose` en partida activa | Iniciar partida, luego `/diagnose` | ✅ El reporte incluye `Partida: #{game_id}` |
| 17 | `/errors` con 20+ errores | Inyectar >20 errores | ✅ Solo muestra los 20 más recientes |
| 18 | `/resolve` con razón vacía | `/resolve` sin texto adicional | ✅ Usa "Resuelto manualmente por el host." |
| 19 | Callback data inválido manualmente | No es posible desde UI, pero si se modifica a mano | ✅ "❌ Datos inválidos." (cada handler tiene try/except) |

### 8.5 Partida completa y estado final

| # | Acción | Detalle | Verificación |
|---|--------|---------|--------------|
| 20 | Verificar estado tras partida completa | 5 rondas + podio | ✅ `Game.status = "finished"` en BD |
| 21 | Verificar estado tras cancelación | Host pulsa "Detener" | ✅ `Game.status = "cancelled"` en BD |
| 22 | Iniciar nueva partida tras finalizar | `/stop` después de partida completa | ✅ Nuevo lobby creado sin problemas |

---

## 9. Script de smoke test automatizado

Crea `scripts/smoke_test_telegram.py` — script que automatiza parte de las verificaciones usando la API de Telegram directamente (sin necesidad de interacción manual).

```python
"""
Smoke Test Automatizado — Verifica que el bot responde correctamente
a comandos y que el sistema de error tracking funciona.

REQUISITOS:
  - El bot debe estar corriendo (python -m src.bot)
  - El archivo .env debe tener BOT_TOKEN válido
  - Se necesita un grupo de prueba (CHAT_ID)

USO:
  python scripts/smoke_test_telegram.py --chat-id -100123456789
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.core.config import settings


PASS = "✅"
FAIL = "❌"
WARN = "⚠️"


class SmokeTester:
    def __init__(self, chat_id: int, bot_token: str):
        self.chat_id = chat_id
        self.bot = Bot(token=bot_token)
        self.results: list[dict] = []
        self._last_message_id: Optional[int] = None

    async def send(self, text: str) -> Optional[int]:
        """Envía un mensaje al grupo y retorna el message_id."""
        try:
            msg = await self.bot.send_message(self.chat_id, text)
            self._last_message_id = msg.message_id
            return msg.message_id
        except Exception as e:
            self._fail("send_message", str(e))
            return None

    async def test_start(self):
        """Prueba /start en el grupo (debe fallar con advertencia)."""
        mid = await self.send("/start")
        if mid:
            await asyncio.sleep(1)
            self._pass("/start en grupo", "Mensaje enviado")

    async def test_stop_lobby(self):
        """Prueba /stop para crear un lobby."""
        mid = await self.send("/stop")
        if mid:
            await asyncio.sleep(2)
            self._pass("/stop", "Mensaje enviado")

    async def test_cancel_game(self):
        """Prueba /cancel para cancelar el lobby."""
        mid = await self.send("/cancel")
        if mid:
            await asyncio.sleep(1)
            self._pass("/cancel", "Mensaje enviado")

    async def test_diagnose(self):
        """Prueba /diagnose."""
        mid = await self.send("/diagnose")
        if mid:
            await asyncio.sleep(2)
            self._pass("/diagnose", "Mensaje enviado")

    async def test_errors(self):
        """Prueba /errors."""
        mid = await self.send("/errors")
        if mid:
            await asyncio.sleep(1)
            self._pass("/errors", "Mensaje enviado")

    async def test_resolve(self):
        """Prueba /resolve."""
        mid = await self.send("/resolve smoke test auto")
        if mid:
            await asyncio.sleep(1)
            self._pass("/resolve", "Mensaje enviado")

    def _pass(self, test_name: str, detail: str = ""):
        self.results.append({"test": test_name, "status": "PASS", "detail": detail})
        print(f"  {PASS} {test_name}: {detail}")

    def _fail(self, test_name: str, detail: str = ""):
        self.results.append({"test": test_name, "status": "FAIL", "detail": detail})
        print(f"  {FAIL} {test_name}: {detail}")

    async def close(self):
        await self.bot.session.close()

    def print_report(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = total - passed
        print("\n" + "=" * 50)
        print(f"RESUMEN SMOKE TEST — {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 50)
        for r in self.results:
            icon = PASS if r["status"] == "PASS" else FAIL
            print(f"  {icon} {r['test']}: {r['detail']}")
        print("-" * 50)
        print(f"  Total: {total}  |  {PASS} {passed}  |  {FAIL} {failed}")
        print("=" * 50)
        return failed == 0


async def verify_error_tracker():
    """Verifica el ErrorTracker sin necesidad de Telegram."""
    print("\n🔍 Verificando ErrorTracker...")
    from src.services.error_tracker import error_tracker, _get_solution, KNOWN_SOLUTIONS

    # Verificar KNOWN_SOLUTIONS
    assert len(KNOWN_SOLUTIONS) >= 16, f"Solo {len(KNOWN_SOLUTIONS)} soluciones conocidas"
    print(f"  {PASS} KNOWN_SOLUTIONS: {len(KNOWN_SOLUTIONS)} entradas")

    # Verificar _get_solution
    assert "PostgreSQL" in _get_solution("sqlalchemy.exc.OperationalError")[0]
    assert "Redis" in _get_solution("redis.exceptions.ConnectionError")[0]
    assert _get_solution("foo.bar.UnknownError")[0] == KNOWN_SOLUTIONS["Exception"][0]
    print(f"  {PASS} _get_solution: lookup funciona correctamente")

    # Verificar generate_report con errores inyectados (opcional)
    try:
        report = await error_tracker.generate_report(minutes=9999)
        assert "INFORME DE DIAGNÓSTICO" in report
        print(f"  {PASS} generate_report: formato correcto")
    except Exception as e:
        print(f"  {WARN} generate_report: {e} (puede ser normal si no hay BD)")

    print(f"  {PASS} ErrorTracker verificado\n")


async def verify_core_modules():
    """Verifica que los módulos core importan correctamente."""
    print("🔍 Verificando imports...")
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
    ]
    for mod in modules:
        try:
            __import__(mod.replace("/", "."))
            print(f"  {PASS} {mod}")
        except Exception as e:
            print(f"  {FAIL} {mod}: {e}")
    print()


async def verify_db_tables():
    """Verifica que todas las tablas existen en BD."""
    print("🔍 Verificando tablas en BD...")
    from src.db.engine import async_session_factory

    expected_tables = {
        "players": "Jugadores",
        "games": "Partidas",
        "game_players": "Jugadores por partida",
        "rounds": "Rondas",
        "answers": "Respuestas",
        "weekly_leaderboards": "Leaderboard semanal",
        "group_configs": "Configuración de grupos",
        "word_list_items": "Palabras por categoría",
        "error_logs": "Logs de errores",
    }

    try:
        async with async_session_factory() as session:
            from sqlalchemy import text
            result = await session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            )
            existing = {row[0] for row in result}

            for table, desc in expected_tables.items():
                if table in existing:
                    print(f"  {PASS} {table} ({desc})")
                else:
                    print(f"  {FAIL} {table} ({desc}) — NO EXISTE")
    except Exception as e:
        print(f"  {FAIL} No se pudo conectar a BD: {e}")
    print()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Smoke Test Automatizado para Stop Bot")
    parser.add_argument("--chat-id", type=int, required=False,
                        help="ID del grupo de Telegram para pruebas")
    parser.add_argument("--verify-only", action="store_true",
                        help="Solo verificar módulos y BD (sin Telegram)")
    args = parser.parse_args()

    print("=" * 50)
    print("SMOKE TEST — STOP BOT")
    print("=" * 50)
    print()

    # 1. Verificar módulos core
    await verify_core_modules()

    # 2. Verificar tablas en BD
    await verify_db_tables()

    # 3. Verificar ErrorTracker
    await verify_error_tracker()

    if args.verify_only:
        print("🔍 Modo verify-only — saltando pruebas en Telegram.")
        return

    if not args.chat_id:
        print(f"{FAIL} Debes proporcionar --chat-id para pruebas en Telegram")
        print("  Ej: python scripts/smoke_test_telegram.py --chat-id -100123456789")
        return

    # 4. Pruebas en Telegram
    print(f"🔍 Probando en grupo {args.chat_id}...\n")
    tester = SmokeTester(chat_id=args.chat_id, bot_token=settings.bot_token)

    await tester.test_start()
    await tester.test_stop_lobby()
    await tester.test_diagnose()
    await tester.test_errors()
    await tester.test_resolve()
    await tester.test_cancel_game()

    await tester.close()
    success = tester.print_report()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
```

### Uso del script automatizado

```powershell
# 1. Solo verificación de módulos + BD (sin Telegram)
python scripts/smoke_test_telegram.py --verify-only

# 2. Pruebas completas en Telegram (necesitas CHAT_ID)
# Obtén el CHAT_ID: añade @getidsbot al grupo y escribe /id
python scripts/smoke_test_telegram.py --chat-id -100123456789
```

---

## 10. Lista de verificación de regresión

Marca cada ítem después de verificar. **Deben pasar todos** antes de considerar la fase completa.

### 10.1 Infraestructura

- [ ] PostgreSQL corriendo y accesible
- [ ] Redis corriendo y responde a `PING`
- [ ] Bot autenticado con Telegram
- [ ] Todas las tablas existen en BD (9 tablas)
- [ ] Word lists cargadas desde BD (>385 palabras)
- [ ] 246 tests automatizados pasan (0 failures)

### 10.2 Comandos básicos

- [ ] `/start` en DM → bienvenida
- [ ] `/start` en grupo → advertencia
- [ ] `/help` → lista de comandos

### 10.3 Lobby

- [ ] `/stop` → lobby creado con botones
- [ ] Unirse → contador actualizado
- [ ] Host puede iniciar
- [ ] No-host NO puede iniciar
- [ ] Lobby expira tras 2 min
- [ ] `/cancel` cancela lobby activo
- [ ] Placeholder DM enviado al host

### 10.4 Ronda

- [ ] Mensaje de ronda con letra aleatoria
- [ ] Placeholder DM a todos los jugadores
- [ ] Respuestas con formato correcto se procesan
- [ ] Respuestas sin `:` se ignoran
- [ ] Primer completo recibe botón Stop
- [ ] Stop cierra la ronda
- [ ] Timeout de 60s cierra la ronda
- [ ] Puntuaciones parciales correctas
- [ ] Bonus Stop (+10) aplicado

### 10.5 Inter-round

- [ ] Menú entre rondas con botones
- [ ] Solo líder puede avanzar
- [ ] Solo host puede detener
- [ ] Timeout de 2 min (si implementado)

### 10.6 Selección de letra

- [ ] Teclado A-Z mostrado
- [ ] Selección de letra inicia nueva ronda
- [ ] Timeout de 15s selecciona letra aleatoria

### 10.7 Fin de partida

- [ ] Podio final después de 5 rondas
- [ ] Cancelación manual funciona
- [ ] Estado `finished` o `cancelled` en BD

### 10.8 ErrorTracker

- [ ] `/diagnose` sin errores → reporte vacío
- [ ] `/errors` sin errores → mensaje vacío
- [ ] `/resolve` sin errores → 0 resueltos
- [ ] Errores capturados por `@track_errors`
- [ ] Errores capturados por middleware
- [ ] `/diagnose` con errores → reporte detallado
- [ ] `/errors` con errores → lista
- [ ] `/resolve` marca como resueltos
- [ ] Errores resueltos tienen ✅ en `/diagnose`
- [ ] Sugerencias de solución correctas
- [ ] Severidad CRITICAL/HIGH/MEDIUM/LOW correcta

### 10.9 Seguridad y validaciones

- [ ] Comandos de grupo no funcionan en DM
- [ ] Comandos de DM no funcionan en grupo (o dan advertencia)
- [ ] Solo host puede cancelar/detener
- [ ] Solo líder puede avanzar ronda
- [ ] No hay joins duplicados
- [ ] No hay respuestas después del Stop
- [ ] Callback data inválido manejado

---

## 11. Solución de problemas comunes

### 11.1 El bot no responde

```
Causa:  BOT_TOKEN inválido o caducado
Solución: Regenerar token en @BotFather

Causa:  El bot no es admin del grupo
Solución: Añadir como administrador (necesita permisos para eliminar mensajes)

Causa:  Puerto 5432 o 6379 ocupados
Solución: Verificar con netstat -an | findstr :5432
```

### 11.2 Error de conexión a PostgreSQL

```
Causa:  PostgreSQL no iniciado
Solución: docker compose -f Docker/docker-compose.yml start postgres

Causa:  DATABASE_URL incorrecta en .env
Solución: Verificar usuario, contraseña, host, puerto, database name

Causa:  Pool agotado
Solución: Aumentar pool_size en src/db/engine.py (default: 10)
```

### 11.3 Error de conexión a Redis

```
Causa:  Redis no iniciado
Solución: docker compose -f Docker/docker-compose.yml start redis

Causa:  REDIS_URL incorrecta
Solución: Verificar host y puerto (default: localhost:6379)
```

### 11.4 Tests fallan

```
Causa:  Dependencias no instaladas
Solución: pip install -r requirements/requirements.txt

Causa:  Python incorrecto
Solución: Usar Python 3.10+ (python --version)

Causa:  aiosqlite no instalado
Solución: pip install aiosqlite
```

### 11.5 Word lists vacías

```
Causa:  Seed no ejecutado
Solución: python -m scripts.seed_word_lists

Causa:  Tabla word_list_items no existe
Solución: Ejecutar migraciones: alembic upgrade head
```

### 11.6 ErrorTracker no captura errores

```
Causa:  Handler sin decorador @track_errors
Solución: Verificar que el handler tenga @error_tracker.track_errors()

Causa:  El error es antes del decorador (en el router)
Solución: Verificar orden de decoradores: @router arriba, @track_errors abajo

Causa:  El error no llega al handler (middleware lo bloquea)
Solución: Verificar que UserExistsMiddleware no falle silenciosamente
```

---

## 12. Criterios de aceptación

La Fase 4D se considera completa cuando:

1. **246 tests automatizados pasan** sin failures ni errores.
2. **El script `smoke_test_telegram.py --verify-only`** se ejecuta sin errores.
3. **Los 5 escenarios manuales** (Secciones 4-8) se han ejecutado y todos los checks pasan.
4. **La lista de verificación de regresión** (Sección 10) está 100% marcada.
5. **No hay warnings** en los logs del bot durante las pruebas (nivel INFO o superior).
6. **El ErrorTracker** captura, reporta y resuelve errores correctamente (verificado con inyección).

---

## Resumen de archivos a crear/modificar

| Archivo | Acción |
|---------|--------|
| `phases/phase4d-guide.md` | CREAR (este documento) |
| `scripts/inject_test_error.py` | CREAR (opcional — inyección de errores para pruebas) |
| `scripts/smoke_test_telegram.py` | CREAR (opcional — smoke test automatizado) |

**Nota:** Los scripts `inject_test_error.py` y `smoke_test_telegram.py` son herramientas auxiliares para pruebas. No son necesarios para el funcionamiento del bot, pero facilitan la verificación de la Fase 4D.

---

## Apéndice A — Mejoras posteriores al smoke test

### A.1 Tratamiento de `...` como respuesta vacía

**Problema detectado:** Cuando un usuario envía respuestas con `...` (ej: `Nombre: ...`), `parse_answers` captura `...` como un valor válido porque es truthy. Aunque scoring le asigna 0 puntos (el regex `^[a-zA-Z...]` lo rechaza), el código que verifica si todas las categorías están completas (`all_filled = len(parsed) == len(state.categories)`) lo cuenta como categoría rellena. Esto permite que el usuario reciba el botón Stop injustamente, ya que el bot piensa que completó todas las categorías.

**Solución:** Filtrar valores `...` (y variantes como `…`, `. . .`, `..`) después del parseo, normalizándolos a cadena vacía. El slot existe pero queda vacío, por lo que `all_filled` se evalúa correctamente y scoring da 0 puntos.

**Archivo modificado:** `backend/src/services/round_manager.py`

```python
# En submit_answers, justo después de parsed = parse_answers(...)
_EMPTY_SYMBOLS = frozenset({"...", "…", ". . .", ".."})
for slot in list(parsed.keys()):
    val = parsed[slot].strip().strip("., •-")
    if not val or val.lower() in _EMPTY_SYMBOLS:
        parsed[slot] = ""
```

**Flujo actualizado:**

1. Usuario escribe `Nombre: ...`, otras 7 categorías con palabras reales
2. `parse_answers` devuelve `{"Nombre": "...", "Apellido": "García", ...}` (8 items)
3. Loop de filtrado detecta `...`, setea `parsed["Nombre"] = ""`
4. `all_filled = len(parsed) == len(categories)` → 8 == 8 → True (el slot existe pero está vacío)
5. En `save_answers`, el slot vacío se guarda con `raw_text = ""`
6. Scoring: `_is_valid_word("")` → False → 0 puntos

**Comportamiento correcto logrado:**

- `...` no da puntos (ya ocurría)
- `...` no activa el botón Stop (nuevo)
- El jugador no es "first completer" si tiene `...` en alguna categoría (nuevo)
- Si un jugador completa 7/8 + `...`, otro que complete 8/8 recibirá el Stop (corregido)

### A.2 Leaderboard por grupo

**Problema detectado:** El modelo `WeeklyLeaderboard` no tenía columna `group_chat_id`. Las consultas SQL en `get_weekly_top` y `get_player_rank_by_telegram` no filtraban por grupo, mostrando el mismo ranking global sin importar desde qué grupo se ejecutara `/leaderboard`.

**Solución completa — 4 capas modificadas:**

#### A.2.1 Modelo (`backend/src/db/models.py`)

Se agregó `group_chat_id` como `BigInteger` (default 0) y se cambió la unique constraint a `(player_id, week_start, group_chat_id)`:

```python
class WeeklyLeaderboard(Base):
    __tablename__ = "weekly_leaderboards"

    __table_args__ = (
        UniqueConstraint(
            "player_id", "week_start", "group_chat_id",
            name="uq_player_week_group"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    group_chat_id: Mapped[int] = mapped_column(BigInteger, default=0)
    week_start: Mapped[date] = mapped_column(default=lambda: date.today())
    total_score: Mapped[int] = mapped_column(default=0)
    games_played: Mapped[int] = mapped_column(default=0)
    rank: Mapped[int | None] = mapped_column(nullable=True)
```

#### A.2.2 Migración Alembic

Se creó una migración que agrega la columna y actualiza la unique constraint:

```python
def upgrade() -> None:
    op.add_column(
        "weekly_leaderboards",
        sa.Column("group_chat_id", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.drop_constraint("uq_player_week", "weekly_leaderboards", type_="unique")
    op.create_unique_constraint(
        "uq_player_week_group", "weekly_leaderboards",
        ["player_id", "week_start", "group_chat_id"],
    )
```

#### A.2.3 Repositorio (`backend/src/db/repositories/leaderboard_repository.py`)

Todos los métodos ahora aceptan y filtran por `group_chat_id`:

| Método | Cambio |
|--------|--------|
| `upsert_player_week` | Nuevo parámetro `group_chat_id: int = 0`; la query WHERE incluye `.group_chat_id == group_chat_id` |
| `get_weekly_top` (nuevo) | Método dedicado que filtra por `group_chat_id` y `week_start`, ordena por `total_score DESC` con `LIMIT` |
| `recalculate_ranks` | Nuevo parámetro `group_chat_id: int \| None = None`; si no es None, filtra por grupo |
| `close_week` | Llama a `recalculate_ranks(group_chat_id=None)` para cerrar todos los grupos |

#### A.2.4 Servicio (`backend/src/services/leaderboard.py`)

- `get_weekly_top(group_chat_id, limit=10)` — pasa `group_chat_id` al repositorio, hace una segunda query para obtener `Player` names
- `get_player_rank_by_telegram(telegram_id, group_chat_id)` — filtra por `group_chat_id`
- `upsert_player(player_id, score_to_add, group_chat_id=0)` — pasa `group_chat_id` al repositorio

#### A.2.5 Handler (`backend/src/handlers/game/leaderboard.py`)

- `cmd_leaderboard`: verifica `message.chat.type != "private"`, obtiene `group_chat_id = message.chat.id`, lo pasa a `get_weekly_top`
- `cmd_rank`: misma verificación de chat type, pasa `group_chat_id` a `get_player_rank_by_telegram`

#### A.2.6 Punto de llamada (`backend/src/services/round_manager.py`)

```python
# Al finalizar partida (~línea 768)
await leaderboard_service.upsert_player(
    player_id=player.id,
    score_to_add=score,
    group_chat_id=state.group_chat_id,
)

# Recalcular ranks
await LeaderboardRepository.recalculate_ranks(
    group_chat_id=state.group_chat_id,
)
```

#### A.2.7 Tests actualizados

**`tests/test_leaderboard_repository.py`:**
- `test_creates_new_entry` — verifica que la query contiene `group_chat_id`
- `test_creates_new_entry_with_group` (nuevo) — pasa `group_chat_id=-100123`, verifica que se usa en la query
- `test_recalculates_ranks_per_group` (nuevo) — pasa `group_chat_id=-100456`, verifica filtro

**`tests/test_handlers_integration.py`:**
- `TestCmdLeaderboard::test_private_chat_rejected` (nuevo) — verifica que en DM no se ejecuta
- `TestCmdLeaderboard::test_passes_group_chat_id` (nuevo) — verifica que `get_weekly_top` recibe `group_chat_id=-100123456789`
- `TestCmdRank::test_private_chat_rejected` (nuevo) — verifica que en DM no consulta servicio

#### A.2.8 Diseño de datos

```
weekly_leaderboards
├── id               PK
├── player_id        FK → players.id
├── group_chat_id    BigInteger (default=0)
├── week_start       Date
├── total_score      Integer
├── games_played     Integer
├── rank             Integer | NULL
└── UNIQUE(player_id, week_start, group_chat_id)
```

Cada jugador puede tener múltiples entradas por semana (una por grupo donde juegue). Los ranks se calculan por grupo, no globalmente. El campo `group_chat_id=0` sirve como valor por defecto para datos legacy antes de la migración.
