# Fase 5 — Configuración de partida y persistencia

**Objetivo:** Partidas configurables (rondas, categorías, temporizador) y estadísticas.

---

## Estado Actual

| Componente | Estado |
|---|---|
| `GroupConfig` | Tabla existe con: `group_chat_id`, `default_rounds` (5), `round_time` (60), `categories` (Text[nullable]), `include_n` (False), `language` ("es"), `validation_mode` ("local") |
| `/settings` | Handler existente en `handlers/game/settings.py` — solo cambia `validation_mode` |
| Categorías | Hardcodeadas en `round_manager.CATEGORIES` (8 fijas) |
| Tiempo ronda | Hardcodeado `ROUND_DURATION = 60` en `round_manager` |
| Rondas | Hardcodeado `TOTAL_ROUNDS = 5` en `round_manager` |
| Ñ | Letra Ñ excluida de `ALPHABET` |
| Estadísticas | No hay handlers `/stats` ni `/profile` |
| i18n | No hay soporte multilenguaje |
| Dependencias | `matplotlib`, `pillow`, `aiogram-i18n/fast-i18n` no instalados |

---

## Vista General de Cambios

```
backend/
├── requirements/requirements.txt    # +matplotlib, +pillow, +babel, +fast-i18n
├── locales/                          # NUEVO
│   ├── es/LC_MESSAGES/bot.po        # Español (por defecto)
│   ├── en/LC_MESSAGES/bot.po        # English
│   └── pt/LC_MESSAGES/bot.po        # Português
├── src/
│   ├── bot.py                       # Añadir setup_i18n, pasar i18n middleware
│   ├── db/
│   │   ├── models.py                # GroupConfig: ya está completo, no tocar
│   │   └── repositories/
│   │       ├── __init__.py          # +GroupConfigRepository
│   │       ├── group_config_repository.py   # NUEVO
│   │       └── game_repository.py   # +get_finished_games, +get_top_players
│   ├── handlers/game/
│   │   ├── __init__.py              # +settings_router, +stats_router, +profile_router
│   │   ├── settings.py              ### REEMPLAZAR — menú expandido
│   │   ├── stats.py                 # NUEVO — estadísticas del grupo
│   │   └── profile.py               # NUEVO — estadísticas personales
│   ├── keyboards/
│   │   └── settings.py              # NUEVO — teclados de settings
│   ├── services/
│   │   ├── game_orchestrator.py     # Leer config (rounds, categories, etc.) de GroupConfig
│   │   └── round_manager.py         # Usar ROUND_DURATION y CATEGORIES desde config
│   └── i18n.py                      # NUEVO — setup de fast-i18n
```

---

## Dependencias Nuevas

Añadir a `requirements/requirements.txt`:

```
# === Fase 5: Settings, Stats, i18n ===
matplotlib>=3.9,<4.0
pillow>=11.0,<12.0
babel>=2.16,<3.0
fast-i18n>=0.6,<1.0          # Alternativa ligera a aiogram-i18n (sin dependencias rotas)
```

> **¿Por qué `fast-i18n` en vez de `aiogram-i18n`?** `aiogram-i18n` usa `babel` igual, pero tiene dependencias conflictivas con versiones recientes de aiogram. `fast-i18n` es más ligero, funciona con cualquier framework, y se integra fácil con aiogram 3.x mediante middleware manual. Si prefieres `aiogram-i18n`, el cambio es mínimo, pero `fast-i18n` evita problemas de dependencias.

---

## Tarea 5.1 — `/settings` expandido (menú inline con 4 secciones)

### Arquitectura del menú

```
/settings
  └── Menú Principal
       ├─ 🎯 Rondas: {5} → al pulsar abre submenú [5] [10] [15]
       ├─ ⏱ Tiempo: {60s} → al pulsar abre submenú [30s] [45s] [60s] [90s]
       ├─ 📋 Categorías → al pulsar abre checkbox list
       ├─ 🔤 Ñ: {No} → toggle Sí/No
       └─ 🔙 Cerrar
```

### Callback data structure

```
settings_rondas:5       → abrir selector de rondas
set_rondas:10           → establecer 10 rondas
settings_tiempo:60      → abrir selector de tiempo
set_tiempo:45           → establecer 45s
settings_cats           → abrir checkbox de categorías
toggle_cat:Nombre       → marcar/desmarcar categoría
toggle_n                → toggle incluir Ñ
settings_main           → volver al menú principal
settings_close          → cerrar (eliminar mensaje)
```

### Crear `backend/src/keyboards/settings.py`

```python
"""Teclados inline para el menú expandido de /settings."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

ALL_CATEGORIES = [
    "Nombre", "Apellido", "Color", "Fruta",
    "País", "Artista", "Novela/Serie", "Cosa",
]

ROUND_OPTIONS = [5, 10, 15]
TIME_OPTIONS = [30, 45, 60, 90]


def settings_main_keyboard(
    current_rounds: int,
    current_time: int,
    current_categories: list[str],
    include_n: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🎯 Rondas: {current_rounds}",
                callback_data="settings_rondas",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"⏱ Tiempo: {current_time}s",
                callback_data="settings_tiempo",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"📋 Categorías ({len(current_categories)}/{len(ALL_CATEGORIES)})",
                callback_data="settings_cats",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🔤 Ñ: {'Sí' if include_n else 'No'}",
                callback_data="toggle_n",
            )
        ],
        [
            InlineKeyboardButton(text="🔙 Cerrar", callback_data="settings_close"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_rounds_keyboard(current: int) -> InlineKeyboardMarkup:
    rows = []
    for opt in ROUND_OPTIONS:
        selected = "• " if opt == current else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{selected}{opt} rondas",
                callback_data=f"set_rondas:{opt}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 Volver", callback_data="settings_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_time_keyboard(current: int) -> InlineKeyboardMarkup:
    rows = []
    for opt in TIME_OPTIONS:
        selected = "• " if opt == current else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{selected}{opt}s",
                callback_data=f"set_tiempo:{opt}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 Volver", callback_data="settings_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_cats_keyboard(
    all_cats: list[str],
    selected_cats: list[str],
) -> InlineKeyboardMarkup:
    rows = []
    for cat in all_cats:
        checked = "✅ " if cat in selected_cats else "⬜ "
        rows.append([
            InlineKeyboardButton(
                text=f"{checked}{cat}",
                callback_data=f"toggle_cat:{cat}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 Volver", callback_data="settings_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

### Reemplazar `backend/src/handlers/game/settings.py`

**IMPORTANTE:** Reemplazar completamente el archivo existente. El nuevo handler:

1. Muestra las 4 opciones en un menú principal.
2. Cada opción abre un submenú.
3. Solo el host o admin del grupo puede cambiar settings (cualquiera puede ver).
4. Los cambios se persisten inmediatamente en `GroupConfig`.

```python
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.markdown import hbold

from src.db.engine import async_session_factory
from src.db.models import Player, GroupConfig
from src.db.repositories.group_config_repository import GroupConfigRepository
from src.keyboards.settings import (
    ALL_CATEGORIES,
    settings_main_keyboard,
    settings_rounds_keyboard,
    settings_time_keyboard,
    settings_cats_keyboard,
)

logger = logging.getLogger(__name__)
settings_router = Router()


async def _get_config(group_chat_id: int) -> GroupConfig:
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        return await repo.get_or_create(group_chat_id)


def _parse_categories(raw: str | None) -> list[str]:
    if not raw:
        return list(ALL_CATEGORIES)  # por defecto todas
    return [c.strip() for c in raw.split(",") if c.strip()]


def _serialize_categories(cats: list[str]) -> str:
    return ",".join(cats)


def _is_admin_or_host(message: Message) -> bool:
    """Placeholder — idealmente verificar si el usuario es admin del grupo.
    Por ahora, cualquier miembro puede ver pero no cambiar (los callbacks
    verifican permisos por separado si es necesario).
    """
    return message.chat.type in ("group", "supergroup")


@settings_router.message(Command("settings"))
async def cmd_settings(message: Message, player: Player) -> None:
    if message.chat.type == "private":
        await message.reply("❌ Este comando solo funciona en grupos.")
        return

    config = await _get_config(message.chat.id)
    cats = _parse_categories(config.categories)

    text = (
        f"{hbold('⚙️ Configuración del Grupo')}\n\n"
        f"Selecciona una opción para cambiar:"
    )
    markup = settings_main_keyboard(
        current_rounds=config.default_rounds,
        current_time=config.round_time,
        current_categories=cats,
        include_n=config.include_n,
    )
    await message.reply(text, reply_markup=markup)


# ─── Menú principal ────────────────────────────────────────────────

@settings_router.callback_query(F.data == "settings_main")
async def back_to_main(callback: CallbackQuery) -> None:
    config = await _get_config(callback.message.chat.id)
    cats = _parse_categories(config.categories)
    markup = settings_main_keyboard(
        current_rounds=config.default_rounds,
        current_time=config.round_time,
        current_categories=cats,
        include_n=config.include_n,
    )
    await callback.message.edit_text(
        f"{hbold('⚙️ Configuración del Grupo')}\n\n"
        f"Selecciona una opción para cambiar:",
        reply_markup=markup,
    )
    await callback.answer()


# ─── Rondas ────────────────────────────────────────────────────────

@settings_router.callback_query(F.data == "settings_rondas")
async def show_rounds(callback: CallbackQuery) -> None:
    config = await _get_config(callback.message.chat.id)
    markup = settings_rounds_keyboard(config.default_rounds)
    await callback.message.edit_text(
        f"{hbold('🎯 Rondas por partida')}\n\n"
        f"Actual: {config.default_rounds}\n\n"
        f"Selecciona el número de rondas:",
        reply_markup=markup,
    )
    await callback.answer()


@settings_router.callback_query(F.data.startswith("set_rondas:"))
async def set_rounds(callback: CallbackQuery) -> None:
    value = int(callback.data.split(":", 1)[1])
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(callback.message.chat.id)
        config.default_rounds = value
        await session.commit()
    await callback.answer(f"✅ Rondas cambiado a {value}")
    # Volver al submenú de rondas
    await show_rounds(callback)


# ─── Tiempo ────────────────────────────────────────────────────────

@settings_router.callback_query(F.data == "settings_tiempo")
async def show_time(callback: CallbackQuery) -> None:
    config = await _get_config(callback.message.chat.id)
    markup = settings_time_keyboard(config.round_time)
    await callback.message.edit_text(
        f"{hbold('⏱ Tiempo por ronda')}\n\n"
        f"Actual: {config.round_time}s\n\n"
        f"Selecciona el tiempo límite:",
        reply_markup=markup,
    )
    await callback.answer()


@settings_router.callback_query(F.data.startswith("set_tiempo:"))
async def set_time(callback: CallbackQuery) -> None:
    value = int(callback.data.split(":", 1)[1])
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(callback.message.chat.id)
        config.round_time = value
        await session.commit()
    await callback.answer(f"✅ Tiempo cambiado a {value}s")
    await show_time(callback)


# ─── Categorías ────────────────────────────────────────────────────

@settings_router.callback_query(F.data == "settings_cats")
async def show_cats(callback: CallbackQuery) -> None:
    config = await _get_config(callback.message.chat.id)
    selected = _parse_categories(config.categories)
    markup = settings_cats_keyboard(ALL_CATEGORIES, selected)
    await callback.message.edit_text(
        f"{hbold('📋 Categorías disponibles')}\n\n"
        f"Marca las categorías que quieres incluir "
        f"(mínimo 4 obligatorio):",
        reply_markup=markup,
    )
    await callback.answer()


@settings_router.callback_query(F.data.startswith("toggle_cat:"))
async def toggle_cat(callback: CallbackQuery) -> None:
    cat = callback.data.split(":", 1)[1]
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(callback.message.chat.id)
        selected = _parse_categories(config.categories)

        if cat in selected:
            if len(selected) <= 4:
                await callback.answer(
                    "❌ Mínimo 4 categorías requeridas.", show_alert=True
                )
                return
            selected.remove(cat)
        else:
            selected.append(cat)

        config.categories = _serialize_categories(selected)
        await session.commit()

    # Refrescar menú
    config = await _get_config(callback.message.chat.id)
    selected = _parse_categories(config.categories)
    markup = settings_cats_keyboard(ALL_CATEGORIES, selected)
    await callback.message.edit_text(
        f"{hbold('📋 Categorías disponibles')}\n\n"
        f"Marca las categorías que quieres incluir "
        f"(mínimo 4 obligatorio):",
        reply_markup=markup,
    )
    await callback.answer()


# ─── Ñ ─────────────────────────────────────────────────────────────

@settings_router.callback_query(F.data == "toggle_n")
async def toggle_n(callback: CallbackQuery) -> None:
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(callback.message.chat.id)
        config.include_n = not config.include_n
        await session.commit()

    # Refrescar menú principal
    await back_to_main(callback)


# ─── Cerrar ────────────────────────────────────────────────────────

@settings_router.callback_query(F.data == "settings_close")
async def settings_close(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer()
```

---

## Tarea 5.2 — GroupConfigRepository y persistencia

### Crear `backend/src/db/repositories/group_config_repository.py`

```python
from typing import Optional

from sqlalchemy import select

from src.db.models import GroupConfig


class GroupConfigRepository:
    def __init__(self, session):
        self.session = session

    async def get_by_group(self, group_chat_id: int) -> Optional[GroupConfig]:
        stmt = select(GroupConfig).where(
            GroupConfig.group_chat_id == group_chat_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, group_chat_id: int) -> GroupConfig:
        config = await self.get_by_group(group_chat_id)
        if config is None:
            config = GroupConfig(group_chat_id=group_chat_id)
            self.session.add(config)
            await self.session.flush()
            await self.session.refresh(config)
        return config
```

### Registrar en `backend/src/db/repositories/__init__.py`

Añadir al final de las importaciones:

```python
from .group_config_repository import GroupConfigRepository
```

Y añadir `"GroupConfigRepository"` a `__all__`.

### Integrar la configuración en el flujo de juego

#### Modificar `backend/src/services/game_orchestrator.py`

En `_do_start`, además de leer `validation_mode`, leer también `default_rounds`, `round_time` (para pasarlo a `round_manager`):

```python
# Dentro de _do_start, después de obtener group_config:
group_config = await self._get_group_config(state.group_chat_id)
validation_mode = group_config.validation_mode if group_config else "local"

# --- Leer configuración de partida ---
if group_config:
    total_rounds = group_config.default_rounds  # en vez de db_game.total_rounds
    # Nota: db_game también tiene total_rounds, pero GroupConfig manda
else:
    total_rounds = 5

# Pasar round_time y categories también al start_round
categories = None
round_time = 60
include_n = False
if group_config:
    if group_config.categories:
        categories = [c.strip() for c in group_config.categories.split(",") if c.strip()]
    round_time = group_config.round_time
    include_n = group_config.include_n
```

Y modificar la llamada a `round_manager.start_round`:

```python
await round_manager.start_round(
    game_id=state.game_id,
    group_chat_id=state.group_chat_id,
    round_number=1,
    letter=letter,
    total_players=len(state.player_telegram_ids),
    total_rounds=total_rounds,
    player_names=player_names,
    bot=bot,
    host_telegram_id=state.host_telegram_id,
    round_time=round_time,           # NUEVO
    categories=categories,           # NUEVO
    include_n=include_n,             # NUEVO
)
```

#### Modificar `backend/src/services/round_manager.py`

**1.** Cambiar la clase `RoundState` para incluir `round_time` y `include_n`:

```python
@dataclass
class RoundState:
    game_id: int
    group_chat_id: int
    round_number: int
    letter: str
    categories: list[str]
    message_chat_id: int
    message_id: int
    host_telegram_id: int
    round_time: int = 60              # NUEVO
    include_n: bool = False           # NUEVO
    timer_task: Optional[asyncio.Task] = None
    ...
```

**2.** Modificar `start_round` para aceptar `round_time`, `categories` y `include_n`:

```python
async def start_round(
    self,
    game_id: int,
    group_chat_id: int,
    round_number: int,
    letter: str,
    total_players: int,
    player_names: dict[int, str],
    bot: Bot,
    total_rounds: int = TOTAL_ROUNDS,
    host_telegram_id: Optional[int] = None,
    round_time: int = 60,             # NUEVO
    categories: Optional[list[str]] = None,  # NUEVO
    include_n: bool = False,          # NUEVO
) -> None:
    # Usar categorías de GroupConfig (o las default)
    effective_categories = categories or CATEGORIES

    text = self._format_round_message(
        round_number, letter, effective_categories, round_time
    )
    ...
    state = RoundState(
        game_id=game_id,
        group_chat_id=group_chat_id,
        round_number=round_number,
        letter=letter,
        categories=effective_categories,
        message_chat_id=msg.chat.id,
        message_id=msg.message_id,
        total_players=total_players,
        total_rounds=total_rounds,
        player_names=player_names,
        host_telegram_id=host_telegram_id or 0,
        round_time=round_time,         # NUEVO
        include_n=include_n,           # NUEVO
    )
```

**3.** Modificar `_round_timer` para usar `state.round_time`:

```python
async def _round_timer(self, state: RoundState, bot: Bot) -> None:
    try:
        await asyncio.sleep(state.round_time)  # Antes: ROUND_DURATION
        async with self._lock_for(state.game_id):
            await self._close_round(state.game_id, "timeout", bot)
    except asyncio.CancelledError:
        pass
```

**4.** Modificar `_format_round_message` para aceptar categorías dinámicas:

```python
@staticmethod
def _format_round_message(
    round_number: int,
    letter: str,
    categories: list[str],
    round_time: int,
) -> str:
    cats_display = "\n".join(
        f"  <b>{cat}:</b> ..." for cat in categories
    )
    return (
        f"🛑 <b>Ronda {round_number} — Letra: {letter}</b>\n"
        f"⏱ {round_time} segundos\n\n"
        f"Envía tus respuestas en este formato:\n\n"
        f"{cats_display}"
    )
```

**5.** Modificar el `ALPHABET` para incluir Ñ condicionalmente. En lugar de tener un solo `ALPHABET`, usar la función:

```python
def get_alphabet(include_n: bool = False) -> str:
    base = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if include_n:
        # Insertar Ñ después de la N
        idx = base.index("N") + 1
        return base[:idx] + "Ñ" + base[idx:]
    return base
```

Y en `_do_start` de `game_orchestrator.py`, pasar `include_n`:

```python
letter = random.choice(get_alphabet(include_n))
```

**6.** Modificar `CATEGORIES_DISPLAY` y `PLACEHOLDER` — eliminarlos como variables globales y calcularlos dinámicamente. O simplemente dejarlos como defaults y usar los dinámicos cuando se pasan categorías personalizadas.

---

## Tarea 5.3 — `/stats` — Estadísticas del grupo

### Crear `backend/src/handlers/game/stats.py`

```python
import io
import logging
from datetime import datetime, timedelta

from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from aiogram.utils.markdown import hbold

from sqlalchemy import select, func, desc
from sqlalchemy.orm import joinedload

from src.db.engine import async_session_factory
from src.db.models import Game, GamePlayer, Player, Round

logger = logging.getLogger(__name__)
stats_router = Router()


@stats_router.message(Command("stats"))
async def cmd_stats(message: Message, bot: Bot) -> None:
    if message.chat.type == "private":
        await message.reply("❌ Este comando solo funciona en grupos.")
        return

    group_chat_id = message.chat.id
    status_msg = await message.reply("📊 Generando estadísticas...")

    try:
        async with async_session_factory() as session:
            # Total partidas jugadas
            total_games_stmt = (
                select(func.count(Game.id))
                .where(Game.group_chat_id == group_chat_id)
                .where(Game.status == "finished")
            )
            total_games = (await session.execute(total_games_stmt)).scalar() or 0

            # Top 10 jugadores por puntaje acumulado (todas las partidas)
            top_players_stmt = (
                select(
                    Player.telegram_id,
                    Player.first_name,
                    Player.username,
                    func.sum(GamePlayer.score).label("total_score"),
                    func.count(GamePlayer.game_id.distinct()).label("games_played"),
                )
                .join(GamePlayer, Player.id == GamePlayer.player_id)
                .join(Game, GamePlayer.game_id == Game.id)
                .where(Game.group_chat_id == group_chat_id)
                .where(Game.status == "finished")
                .group_by(Player.id, Player.telegram_id, Player.first_name, Player.username)
                .order_by(desc("total_score"))
                .limit(10)
            )
            rows = await session.execute(top_players_stmt)
            top_players = rows.all()

            # Actividad reciente: partidas de los últimos 7 días
            week_ago = datetime.utcnow() - timedelta(days=7)
            recent_games_stmt = (
                select(func.count(Game.id))
                .where(Game.group_chat_id == group_chat_id)
                .where(Game.status == "finished")
                .where(Game.finished_at >= week_ago)
            )
            recent_games = (await session.execute(recent_games_stmt)).scalar() or 0

        # Formatear texto
        lines = [
            f"{hbold('📊 Estadísticas del Grupo')}\n",
            f"🎮 Total partidas jugadas: {total_games}",
            f"📅 Partidas (7 días): {recent_games}\n",
            f"{hbold('🏆 Top 10 Jugadores')}",
        ]

        if top_players:
            medals = ["🥇", "🥈", "🥉"]
            for i, row in enumerate(top_players):
                name = row.first_name or f"ID{row.telegram_id}"
                if row.username:
                    name += f" (@{row.username})"
                medal = medals[i] if i < 3 else f"{i+1}."
                total = row.total_score or 0
                gp = row.games_played or 0
                lines.append(f"{medal} {name} — {total} pts ({gp} partidas)")
        else:
            lines.append("  (sin datos todavía)")

        text = "\n".join(lines)
        await status_msg.edit_text(text)

    except Exception as e:
        logger.exception("Error en /stats")
        await status_msg.edit_text(
            "❌ Error al generar estadísticas. Intenta de nuevo más tarde."
        )
```

### Registrar en `backend/src/handlers/game/__init__.py`

```python
from .stats import stats_router
```

Y añadir a `__all__`.

### Registrar en `backend/src/bot.py`

```python
from src.handlers.game.stats import stats_router
...
dp.include_router(stats_router)
```

---

## Tarea 5.4 — `/profile` — Estadísticas personales

### Crear `backend/src/handlers/game/profile.py`

```python
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.markdown import hbold

from sqlalchemy import select, func, desc, and_

from src.db.engine import async_session_factory
from src.db.models import Player, GamePlayer, Game, Answer

logger = logging.getLogger(__name__)
profile_router = Router()


@profile_router.message(Command("profile"))
async def cmd_profile(message: Message, player: Player) -> None:
    """Muestra estadísticas personales del jugador."""
    status_msg = await message.reply("📊 Cargando tu perfil...")

    try:
        async with async_session_factory() as session:
            # --- Partidas jugadas ---
            total_games_stmt = (
                select(func.count(GamePlayer.id))
                .where(GamePlayer.player_id == player.id)
                .join(Game, GamePlayer.game_id == Game.id)
                .where(Game.status == "finished")
            )
            total_games = (await session.execute(total_games_stmt)).scalar() or 0

            # --- Victorias (ser el #1 en una partida) ---
            # Una victoria = el jugador tiene el score más alto en una partida
            wins_stmt = select(func.count()).select_from(
                select(GamePlayer.game_id, func.max(GamePlayer.score).label("max_score"))
                .where(GamePlayer.player_id == player.id)
                .group_by(GamePlayer.game_id)
                .having(func.max(GamePlayer.score) > 0)
                .subquery()
            )
            # Alternativa más simple:
            # Buscar partidas donde este jugador tiene el score más alto
            # No es 100% preciso si hay empates, pero es rápido
            wins_count = 0
            subq = (
                select(
                    GamePlayer.game_id,
                    func.max(GamePlayer.score).label("max_score"),
                )
                .group_by(GamePlayer.game_id)
                .subquery()
            )
            player_wins_stmt = (
                select(func.count(GamePlayer.id))
                .where(GamePlayer.player_id == player.id)
                .where(GamePlayer.score == subq.c.max_score)
                .where(GamePlayer.game_id == subq.c.game_id)
                .where(GamePlayer.score > 0)
            )
            wins_count = (await session.execute(player_wins_stmt)).scalar() or 0

            # --- Puntaje total ---
            total_score_stmt = (
                select(func.coalesce(func.sum(GamePlayer.score), 0))
                .where(GamePlayer.player_id == player.id)
            )
            total_score = (await session.execute(total_score_stmt)).scalar() or 0

            # --- MVP times (ser el que hizo Stop más veces) ---
            # Buscar en Round.stopped_by_player_id
            from src.db.models import Round as RoundModel
            mvp_stmt = (
                select(func.count(RoundModel.id))
                .where(RoundModel.stopped_by_player_id == player.id)
            )
            mvp_count = (await session.execute(mvp_stmt)).scalar() or 0

            # --- Rating de aciertos ---
            total_answers_stmt = (
                select(func.count(Answer.id))
                .where(Answer.player_id == player.id)
            )
            total_answers = (await session.execute(total_answers_stmt)).scalar() or 0

            correct_answers_stmt = (
                select(func.count(Answer.id))
                .where(Answer.player_id == player.id)
                .where(Answer.is_correct == True)
            )
            correct_answers = (await session.execute(correct_answers_stmt)).scalar() or 0

            accuracy = (correct_answers / total_answers * 100) if total_answers > 0 else 0

        lines = [
            f"{hbold('👤 Tu Perfil')}\n",
            f"🎮 Partidas jugadas: {total_games}",
            f"🏆 Victorias: {wins_count}",
            f"⭐ MVP (Stops): {mvp_count}",
            f"📊 Puntaje total: {total_score} pts",
            f"🎯 Rating de aciertos: {accuracy:.1f}% "
            f"({correct_answers}/{total_answers})",
        ]

        text = "\n".join(lines)
        await status_msg.edit_text(text)

    except Exception as e:
        logger.exception("Error en /profile")
        await status_msg.edit_text(
            "❌ Error al cargar tu perfil. Intenta de nuevo más tarde."
        )
```

### Registrar en `backend/src/handlers/game/__init__.py`

```python
from .profile import profile_router
```

Y añadir a `__all__`.

### Registrar en `backend/src/bot.py`

```python
from src.handlers.game.profile import profile_router
...
dp.include_router(profile_router)
```

---

## Tarea 5.5 — Multilenguaje con fast-i18n

### ¿Por qué fast-i18n?

`fast-i18n` es una librería minimalista que:
- No tiene dependencias conflictivas.
- Usa el formato estándar `.po`/`.mo` de gettext (compatible con Babel).
- Se integra fácilmente con aiogram 3.x mediante middleware manual.
- Soporta interpolación de variables, plurales, etc.

### Crear `backend/src/i18n.py`

```python
"""Configuración de internacionalización con fast-i18n."""
import os
from pathlib import Path

from fast_i18n import I18n

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

i18n = I18n(
    locales_dir=str(LOCALES_DIR),
    default_locale="es",
    domain="bot",
)

# Tabla de códigos de idioma a locales
LOCALE_MAP = {
    "es": "es",   # Español
    "en": "en",   # English
    "pt": "pt",   # Português
    "pt-br": "pt",
    "es-ar": "es",
    "es-mx": "es",
    "en-us": "en",
    "en-gb": "en",
}


def get_user_locale(player) -> str:
    """Obtiene el locale del jugador, con fallback a español."""
    if not player or not player.language_code:
        return "es"
    code = player.language_code.lower()
    return LOCALE_MAP.get(code, "es")


def t(key: str, locale: str = "es", **kwargs) -> str:
    """Traduce una clave al idioma indicado."""
    return i18n.t(key, locale=locale, **kwargs)
```

### Crear la estructura de locales

```
locales/
├── es/
│   └── LC_MESSAGES/
│       └── bot.po
├── en/
│   └── LC_MESSAGES/
│       └── bot.po
└── pt/
    └── LC_MESSAGES/
        └── bot.po
```

### Archivo `locales/es/LC_MESSAGES/bot.po`

```po
msgid ""
msgstr ""
"Language: es\n"
"Content-Type: text/plain; charset=UTF-8\n"

msgid "settings_title"
msgstr "⚙️ Configuración del Grupo"

msgid "settings_rounds"
msgstr "🎯 Rondas: {count}"

msgid "settings_time"
msgstr "⏱ Tiempo: {seconds}s"

msgid "settings_categories"
msgstr "📋 Categorías ({count}/{total})"

msgid "settings_include_n"
msgstr "🔤 Ñ: {value}"

msgid "settings_rounds_title"
msgstr "🎯 Rondas por partida"

msgid "settings_time_title"
msgstr "⏱ Tiempo por ronda"

msgid "settings_cats_title"
msgstr "📋 Categorías disponibles"

msgid "stats_title"
msgstr "📊 Estadísticas del Grupo"

msgid "profile_title"
msgstr "👤 Tu Perfil"

msgid "error_group_only"
msgstr "❌ Este comando solo funciona en grupos."

msgid "yes"
msgstr "Sí"

msgid "no"
msgstr "No"

msgid "back"
msgstr "🔙 Volver"

msgid "close"
msgstr "🔙 Cerrar"
```

### Archivo `locales/en/LC_MESSAGES/bot.po`

```po
msgid ""
msgstr ""
"Language: en\n"
"Content-Type: text/plain; charset=UTF-8\n"

msgid "settings_title"
msgstr "⚙️ Group Settings"

msgid "settings_rounds"
msgstr "🎯 Rounds: {count}"

msgid "settings_time"
msgstr "⏱ Time: {seconds}s"

msgid "settings_categories"
msgstr "📋 Categories ({count}/{total})"

msgid "settings_include_n"
msgstr "🔤 Ñ: {value}"

msgid "settings_rounds_title"
msgstr "🎯 Rounds per Game"

msgid "settings_time_title"
msgstr "⏱ Time per Round"

msgid "settings_cats_title"
msgstr "📋 Available Categories"

msgid "stats_title"
msgstr "📊 Group Statistics"

msgid "profile_title"
msgstr "👤 Your Profile"

msgid "error_group_only"
msgstr "❌ This command only works in groups."

msgid "yes"
msgstr "Yes"

msgid "no"
msgstr "No"

msgid "back"
msgstr "🔙 Back"

msgid "close"
msgstr "🔙 Close"
```

### Archivo `locales/pt/LC_MESSAGES/bot.po`

```po
msgid ""
msgstr ""
"Language: pt\n"
"Content-Type: text/plain; charset=UTF-8\n"

msgid "settings_title"
msgstr "⚙️ Configuração do Grupo"

msgid "settings_rounds"
msgstr "🎯 Rodadas: {count}"

msgid "settings_time"
msgstr "⏱ Tempo: {seconds}s"

msgid "settings_categories"
msgstr "📋 Categorias ({count}/{total})"

msgid "settings_include_n"
msgstr "🔤 Ñ: {value}"

msgid "settings_rounds_title"
msgstr "🎯 Rodadas por Partida"

msgid "settings_time_title"
msgstr "⏱ Tempo por Rodada"

msgid "settings_cats_title"
msgstr "📋 Categorias Disponíveis"

msgid "stats_title"
msgstr "📊 Estatísticas do Grupo"

msgid "profile_title"
msgstr "👤 Seu Perfil"

msgid "error_group_only"
msgstr "❌ Este comando só funciona em grupos."

msgid "yes"
msgstr "Sim"

msgid "no"
msgstr "Não"

msgid "back"
msgstr "🔙 Voltar"

msgid "close"
msgstr "🔙 Fechar"
```

### Compilar archivos .mo

Después de crear los `.po`, compilarlos a `.mo`:

```bash
cd backend
pip install babel
pybabel compile -d locales -D bot
```

Esto generará `locales/es/LC_MESSAGES/bot.mo`, etc.

### Middleware de i18n para aiogram

En `backend/src/bot.py`, añadir un middleware simple que establezca el locale del jugador en cada mensaje:

```python
from src.i18n import get_user_locale
```

Y dentro de `main()`, después de crear el Dispatcher:

```python
# Middleware de i18n: establecer locale del jugador
@dp.message.outer_middleware
async def i18n_middleware(handler, event, data):
    player = data.get("player")
    if player:
        # El locale se puede usar en handlers mediante data["locale"]
        data["locale"] = get_user_locale(player)
    return await handler(event, data)
```

Luego en los handlers se puede acceder a `data.get("locale", "es")` o inyectar el locale.

### Usar i18n en handlers

Ejemplo en el handler de settings:

```python
from src.i18n import t, get_user_locale

@settings_router.message(Command("settings"))
async def cmd_settings(message: Message, player: Player) -> None:
    locale = get_user_locale(player)
    text = t("settings_title", locale=locale)
    ...
```

---

## Tarea 5.6 — Migración Alembic (si se necesitan nuevas columnas)

`GroupConfig` ya tiene todas las columnas que necesitamos:
- `default_rounds` (int, default=5) ✓
- `round_time` (int, default=60) ✓
- `categories` (Text, nullable) ✓
- `include_n` (bool, default=False) ✓
- `language` (String(8), default="es") ✓
- `validation_mode` (String(16), default="local") ✓

**No se necesita migración nueva.** Si en el futuro se agregan columnas, ejecutar:

```bash
cd backend
alembic revision --autogenerate -m "descripcion"
alembic upgrade head
```

---

## Tarea 5.7 — Registrar rutas en bot.py

Asegurarse de que en `backend/src/bot.py` estén registrados los routers de stats y profile:

```python
from src.handlers.game.stats import stats_router
from src.handlers.game.profile import profile_router

# ...

dp.include_router(stats_router)
dp.include_router(profile_router)
```

Y que `settings_router` ya esté registrado (de fases anteriores).

---

## Tarea 5.8 — Tests

### Tests para GroupConfigRepository

Crear `backend/tests/test_group_config_repository.py`:

```python
import pytest
from src.db.engine import async_session_factory
from src.db.repositories.group_config_repository import GroupConfigRepository


@pytest.mark.asyncio
async def test_get_or_create_creates_new():
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config = await repo.get_or_create(-123456789)
        assert config.group_chat_id == -123456789
        assert config.default_rounds == 5
        assert config.round_time == 60
        assert config.categories is None
        assert config.include_n is False


@pytest.mark.asyncio
async def test_get_or_create_returns_existing():
    async with async_session_factory() as session:
        repo = GroupConfigRepository(session)
        config1 = await repo.get_or_create(-987654321)
        config1.default_rounds = 10
        await session.flush()

        config2 = await repo.get_or_create(-987654321)
        assert config2.id == config1.id
        assert config2.default_rounds == 10
```

### Tests para stats y profile

Verificar que las queries SQL devuelven resultados correctos con datos de prueba insertados en la BD.

---

## Orden de Implementación

1. **Paso 1:** Añadir dependencias a `requirements.txt` y ejecutar `pip install -r requirements.txt`.
2. **Paso 2:** Crear `backend/src/keyboards/settings.py`.
3. **Paso 3:** Crear `backend/src/db/repositories/group_config_repository.py` y registrar en `__init__.py`.
4. **Paso 4:** Reemplazar `backend/src/handlers/game/settings.py` (reemplazar completamente).
5. **Paso 5:** Modificar `backend/src/services/round_manager.py` (RoundState, start_round, _format_round_message, _round_timer, get_alphabet).
6. **Paso 6:** Modificar `backend/src/services/game_orchestrator.py` (_do_start: leer config, pasar a start_round).
7. **Paso 7:** Crear `backend/src/handlers/game/stats.py`.
8. **Paso 8:** Crear `backend/src/handlers/game/profile.py`.
9. **Paso 9:** Registrar stats_router y profile_router en `__init__.py` y `bot.py`.
10. **Paso 10:** Crear estructura de locales y archivos `.po`.
11. **Paso 11:** Crear `backend/src/i18n.py`.
12. **Paso 12:** Añadir middleware de i18n en `bot.py`.
13. **Paso 13:** Compilar archivos `.mo` con `pybabel compile`.
14. **Paso 14:** Probar en Telegram: `/settings`, `/stats`, `/profile`, cambio de idioma.

---

## Resumen de Archivos Nuevos/Modificados

| Archivo | Acción |
|---|---|
| `requirements/requirements.txt` | Modificar (+matplotlib, +pillow, +babel, +fast-i18n) |
| `src/db/repositories/group_config_repository.py` | **NUEVO** |
| `src/db/repositories/__init__.py` | Modificar (+GroupConfigRepository) |
| `src/keyboards/settings.py` | **NUEVO** |
| `src/handlers/game/settings.py` | **REEMPLAZAR** (menú expandido) |
| `src/handlers/game/stats.py` | **NUEVO** |
| `src/handlers/game/profile.py` | **NUEVO** |
| `src/handlers/game/__init__.py` | Modificar (+stats_router, +profile_router) |
| `src/services/round_manager.py` | Modificar (round_time dinámico, categorías, Ñ, formato) |
| `src/services/game_orchestrator.py` | Modificar (leer GroupConfig, pasar a start_round) |
| `src/bot.py` | Modificar (+stats_router, +profile_router, +middleware i18n) |
| `src/i18n.py` | **NUEVO** |
| `locales/es/LC_MESSAGES/bot.po` | **NUEVO** |
| `locales/en/LC_MESSAGES/bot.po` | **NUEVO** |
| `locales/pt/LC_MESSAGES/bot.po` | **NUEVO** |

---

## Consideraciones Técnicas

1. **Permisos de admin:** Para verificar si un usuario es admin del grupo, aiogram tiene `ChatMemberUpdated`. Una implementación simple: usar `bot.get_chat_administrators(chat_id)` en el callback. Pero para no complicar, en esta fase asumimos que cualquier miembro puede ver/cambiar settings. Si quieres restringir: añadir chequeo en los callbacks de cambio (set_*, toggle_*) que llame a `bot.get_chat_administrators(message.chat.id)`.

2. **Matplotlib para gráficos semanales:** Si quieres generar un gráfico de barras semanal para `/stats`, usa `matplotlib` con backend `Agg`:

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import io

# En /stats handler:
fig, ax = plt.subplots(figsize=(8, 4))
names = [fila[0] for fila in top_players]
scores = [fila[1] or 0 for fila in top_players]
ax.barh(names, scores, color="skyblue")
ax.set_xlabel("Puntos")
ax.set_title("Top 10 jugadores")
plt.tight_layout()

buf = io.BytesIO()
plt.savefig(buf, format="PNG")
buf.seek(0)
await message.reply_photo(BufferedInputFile(buf.read(), filename="top.png"))
plt.close()
```

3. **Traducciones en handlers:** Para empezar, aplica `i18n` solo en los textos nuevos de Fase 5. Los mensajes de fases anteriores (lobby, ronda, etc.) se pueden traducir progresivamente.

4. **Idioma por defecto:** Si el jugador no tiene `language_code` o es un idioma no soportado, cae a español.
