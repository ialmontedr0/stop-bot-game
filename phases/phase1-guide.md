# Phase 1 — Registro de grupos y unión a partidas

> **Objetivo:** Lobby funcional, unión de hasta 10 jugadores, inicio manual/automático.

---

## Archivos a crear

| # | Archivo | Propósito |
|---|---------|-----------|
| 1 | `src/handlers/game/lobby.py` | Comando `/stop`, callbacks join/start |
| 2 | `src/handlers/game/__init__.py` | Exportar router |
| 3 | `src/keyboards/lobby.py` | Inline keyboards para el lobby |

## Archivos a modificar

| # | Archivo | Cambio |
|---|---------|--------|
| 4 | `src/db/repositories/game_repository.py` | Añadir métodos para lobby |
| 5 | `src/services/game_orchestrator.py` | Escribir `LobbyManager` completo |
| 6 | `src/bot.py` | Registrar `game_router` |

---

## 1. `src/handlers/game/lobby.py`

```python
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.db.models import Player
from src.keyboards.lobby import lobby_keyboard
from src.services.game_orchestrator import lobby_manager

game_router = Router()


@game_router.message(Command("stop"))
async def cmd_stop(message: Message, player: Player, bot: Bot) -> None:
    if message.chat.type == "private":
        await message.answer("❌ Este comando solo funciona en grupos.")
        return

    if lobby_manager.has_lobby(message.chat.id):
        await message.answer("⚠️ Ya hay una sala abierta en este grupo.")
        return

    result = await lobby_manager.create_lobby(
        group_chat_id=message.chat.id,
        host_player=player,
        bot=bot,
    )
    if isinstance(result, str):
        await message.answer(result)


@game_router.callback_query(F.data.startswith("join:"))
async def callback_join(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    game_id = int(callback.data.split(":")[1])
    await lobby_manager.join_lobby(
        game_id=game_id,
        player=player,
        callback=callback,
        bot=bot,
    )


@game_router.callback_query(F.data.startswith("start:"))
async def callback_start(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    game_id = int(callback.data.split(":")[1])
    await lobby_manager.start_game(
        game_id=game_id,
        player=player,
        callback=callback,
        bot=bot,
    )
```

---

## 2. `src/handlers/game/__init__.py`

```python
from .lobby import game_router

__all__ = ["game_router"]
```

---

## 3. `src/keyboards/lobby.py`

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def lobby_keyboard(game_id: int, is_host: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🟢 Unirse", callback_data=f"join:{game_id}")],
    ]
    if is_host:
        buttons.append(
            [InlineKeyboardButton(text="▶️ Iniciar", callback_data=f"start:{game_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

---

## 4. `src/db/repositories/game_repository.py`

Contenido **completo** (reemplaza el actual):

```python
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.db.models import Game, GamePlayer, Player

from .base import BaseRepository


class GameRepository(BaseRepository[Game]):
    def __init__(self, session):
        super().__init__(Game, session)

    async def get_active_game(self, group_chat_id: int) -> Optional[Game]:
        stmt = (
            select(Game)
            .where(Game.group_chat_id == group_chat_id)
            .where(Game.status.in_(["lobby", "playing"]))
            .order_by(Game.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, game_id: int) -> Optional[Game]:
        return await self.session.get(Game, game_id)

    async def create_game(
        self, group_chat_id: int, total_rounds: int = 5
    ) -> Game:
        game = Game(
            group_chat_id=group_chat_id,
            status="lobby",
            total_rounds=total_rounds,
        )
        self.session.add(game)
        await self.session.commit()
        await self.session.refresh(game)
        return game

    async def add_player_to_game(
        self,
        game: Game,
        player: Player,
        is_host: bool = False,
    ) -> GamePlayer:
        gp = GamePlayer(
            game_id=game.id,
            player_id=player.id,
            is_host=is_host,
        )
        self.session.add(gp)
        await self.session.commit()
        await self.session.refresh(gp)
        return gp

    async def get_players_for_game(
        self, game: Game
    ) -> list[tuple[GamePlayer, Player]]:
        stmt = (
            select(GamePlayer, Player)
            .join(Player, GamePlayer.player_id == Player.id)
            .where(GamePlayer.game_id == game.id)
            .order_by(GamePlayer.joined_at)
        )
        result = await self.session.execute(stmt)
        return result.all()

    async def get_player_count(self, game: Game) -> int:
        stmt = (
            select(GamePlayer)
            .where(GamePlayer.game_id == game.id)
        )
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    async def is_player_in_game(
        self, game: Game, player: Player
    ) -> bool:
        stmt = (
            select(GamePlayer)
            .where(GamePlayer.game_id == game.id)
            .where(GamePlayer.player_id == player.id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def update_game_status(
        self, game: Game, status: str
    ) -> Game:
        game.status = status
        await self.session.commit()
        await self.session.refresh(game)
        return game
```

---

## 5. `src/services/game_orchestrator.py`

Contenido **completo** (reemplaza el actual):

```python
import asyncio
from dataclasses import dataclass, field
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from src.db.engine import async_session_factory
from src.db.models import Player
from src.db.repositories import GameRepository
from src.keyboards.lobby import lobby_keyboard

MAX_PLAYERS = 10
AUTO_START_DELAY = 30  # segundos tras el ultimo join
LOBBY_EXPIRE = 120  # segundos de inactividad total
MIN_PLAYERS_TO_START = 2


@dataclass
class LobbyState:
    game_id: int
    group_chat_id: int
    host_telegram_id: int
    host_name: str
    message_chat_id: int
    message_id: int
    player_telegram_ids: list[int] = field(default_factory=list)
    player_display_names: list[str] = field(default_factory=list)
    expire_task: Optional[asyncio.Task] = None
    animation_task: Optional[asyncio.Task] = None
    auto_start_task: Optional[asyncio.Task] = None


class LobbyManager:
    """Gestiona las salas activas en memoria, indexadas por group_chat_id."""

    def __init__(self) -> None:
        self._lobbies: dict[int, LobbyState] = {}

    # ── Consultas ───────────────────────────────────────────

    def has_lobby(self, group_chat_id: int) -> bool:
        return group_chat_id in self._lobbies

    def get_lobby(self, group_chat_id: int) -> Optional[LobbyState]:
        return self._lobbies.get(group_chat_id)

    def get_lobby_by_game(self, game_id: int) -> Optional[LobbyState]:
        for state in self._lobbies.values():
            if state.game_id == game_id:
                return state
        return None

    # ── Crear lobby ─────────────────────────────────────────

    async def create_lobby(
        self,
        group_chat_id: int,
        host_player: Player,
        bot: Bot,
    ) -> Optional[str]:
        """Crea partida en DB, envia mensaje lobby, inicia timers.
        Devuelve None si ok, str con error si falla."""

        async with async_session_factory() as session:
            repo = GameRepository(session)

            existing = await repo.get_active_game(group_chat_id)
            if existing:
                return "⚠️ Ya hay una partida en curso en este grupo."

            game = await repo.create_game(group_chat_id)
            await repo.add_player_to_game(game, host_player, is_host=True)

        host_name = host_player.first_name or host_player.username or f"ID{host_player.telegram_id}"

        text = self._format_lobby_message(
            title="🛑 STOP — Sala abierta",
            count=1,
            players=[host_name],
        )
        keyboard = lobby_keyboard(game.id, is_host=True)
        msg = await bot.send_message(group_chat_id, text, reply_markup=keyboard)

        state = LobbyState(
            game_id=game.id,
            group_chat_id=group_chat_id,
            host_telegram_id=host_player.telegram_id,
            host_name=host_name,
            message_chat_id=msg.chat.id,
            message_id=msg.message_id,
            player_telegram_ids=[host_player.telegram_id],
            player_display_names=[host_name],
        )
        state.expire_task = asyncio.create_task(
            self._expire_timer(state, bot)
        )
        state.animation_task = asyncio.create_task(
            self._animation_loop(state, bot)
        )
        self._lobbies[group_chat_id] = state
        return None

    # ── Unirse ──────────────────────────────────────────────

    async def join_lobby(
        self,
        game_id: int,
        player: Player,
        callback: CallbackQuery,
        bot: Bot,
    ) -> None:
        state = self.get_lobby_by_game(game_id)
        if not state:
            await callback.answer("❌ Esta sala ya no existe.", show_alert=True)
            return

        if player.telegram_id in state.player_telegram_ids:
            await callback.answer("✅ Ya estás en la partida.", show_alert=False)
            return

        if len(state.player_telegram_ids) >= MAX_PLAYERS:
            await callback.answer(
                f"❌ La partida ya tiene {MAX_PLAYERS} jugadores.", show_alert=True
            )
            return

        async with async_session_factory() as session:
            repo = GameRepository(session)
            db_game = await repo.get_by_id(game_id)
            if not db_game or db_game.status != "lobby":
                await callback.answer("❌ La partida ya inició.", show_alert=True)
                # limpiar estado huérfano
                self._cleanup(state)
                return

            # Doble check en DB
            if await repo.is_player_in_game(db_game, player):
                await callback.answer("✅ Ya estás registrado.", show_alert=False)
                return

            await repo.add_player_to_game(db_game, player, is_host=False)

        name = player.first_name or player.username or f"ID{player.telegram_id}"
        state.player_telegram_ids.append(player.telegram_id)
        state.player_display_names.append(name)

        await callback.answer("✅ Te has unido a la partida.", show_alert=False)

        # Resetear auto-start si hay suficientes jugadores
        self._reset_auto_start(state, bot)

        # Si llega a 10 → auto-start inmediato
        if len(state.player_telegram_ids) >= MAX_PLAYERS:
            await self._do_start(state, bot)
            return

    # ── Iniciar ─────────────────────────────────────────────

    async def start_game(
        self,
        game_id: int,
        player: Player,
        callback: CallbackQuery,
        bot: Bot,
    ) -> None:
        state = self.get_lobby_by_game(game_id)
        if not state:
            await callback.answer("❌ Sala no encontrada.", show_alert=True)
            return

        if player.telegram_id != state.host_telegram_id:
            await callback.answer(
                "❌ Solo el host puede iniciar la partida.", show_alert=True
            )
            return

        if len(state.player_telegram_ids) < MIN_PLAYERS_TO_START:
            await callback.answer(
                f"❌ Se necesitan al menos {MIN_PLAYERS_TO_START} jugadores.",
                show_alert=True,
            )
            return

        await self._do_start(state, bot)

    # ── Auto-start ──────────────────────────────────────────

    def _reset_auto_start(self, state: LobbyState, bot: Bot) -> None:
        if state.auto_start_task and not state.auto_start_task.done():
            state.auto_start_task.cancel()
        if len(state.player_telegram_ids) >= MIN_PLAYERS_TO_START:
            state.auto_start_task = asyncio.create_task(
                self._auto_start_timer(state, bot)
            )

    async def _auto_start_timer(self, state: LobbyState, bot: Bot) -> None:
        try:
            await asyncio.sleep(AUTO_START_DELAY)
            if state.group_chat_id in self._lobbies:
                await self._do_start(state, bot)
        except asyncio.CancelledError:
            pass

    # ── Expiración por inactividad ──────────────────────────

    async def _expire_timer(self, state: LobbyState, bot: Bot) -> None:
        try:
            await asyncio.sleep(LOBBY_EXPIRE)
            text = self._format_lobby_message(
                "⌛ Tiempo agotado — Sala cerrada por inactividad.",
                len(state.player_telegram_ids),
                state.player_display_names,
            )
            try:
                await bot.edit_message_text(
                    text,
                    chat_id=state.message_chat_id,
                    message_id=state.message_id,
                )
            except TelegramBadRequest:
                pass
            self._cleanup(state)
        except asyncio.CancelledError:
            pass

    # ── Animación cada 5s ───────────────────────────────────

    async def _animation_loop(self, state: LobbyState, bot: Bot) -> None:
        try:
            dots = 0
            while True:
                await asyncio.sleep(5)
                if state.group_chat_id not in self._lobbies:
                    break
                dots = (dots % 3) + 1
                title = "🛑 STOP — Sala abierta" + "." * dots
                text = self._format_lobby_message(
                    title,
                    len(state.player_telegram_ids),
                    state.player_display_names,
                )
                is_host = state.player_telegram_ids[0] == state.host_telegram_id
                keyboard = lobby_keyboard(state.game_id, is_host=is_host)
                try:
                    await bot.edit_message_text(
                        text,
                        chat_id=state.message_chat_id,
                        message_id=state.message_id,
                        reply_markup=keyboard,
                    )
                except TelegramBadRequest:
                    pass
        except asyncio.CancelledError:
            pass

    # ── Iniciar partida (placeholder Fase 2) ────────────────

    async def _do_start(self, state: LobbyState, bot: Bot) -> None:
        """Actualiza estado a 'playing' y muestra mensaje.
        La logica real de ronda se implementa en Fase 2."""

        async with async_session_factory() as session:
            repo = GameRepository(session)
            db_game = await repo.get_by_id(state.game_id)
            if db_game:
                await repo.update_game_status(db_game, "playing")

        self._cleanup(state)

        # ── Placeholder: Aqui se llamara a Fase 2 ──────────
        participants = "\n".join(
            f"  {i+1}. {name}"
            for i, name in enumerate(state.player_display_names)
        )
        await bot.send_message(
            state.group_chat_id,
            f"🎮 <b>¡Partida iniciada!</b>\n\n"
            f"{len(state.player_telegram_ids)} jugadores:\n"
            f"{participations}\n\n"
            f"<i>Preparando ronda 1...</i>",
        )

    # ── Limpieza ────────────────────────────────────────────

    def _cleanup(self, state: LobbyState) -> None:
        self._lobbies.pop(state.group_chat_id, None)
        for task in (state.expire_task, state.animation_task, state.auto_start_task):
            if task and not task.done():
                task.cancel()

    # ── Formateo de mensaje ─────────────────────────────────

    @staticmethod
    def _format_lobby_message(
        title: str,
        count: int,
        players: list[str],
    ) -> str:
        lines = [f"<b>{title}</b>", "", f"👤 Jugadores: {count}/{MAX_PLAYERS}", ""]
        if players:
            lines.extend(f"  {i+1}. {name}" for i, name in enumerate(players))
            lines.append("")
        lines.append(
            "⏱ La partida comenzará automáticamente al completarse "
            f"{MAX_PLAYERS} jugadores o cuando el host presione <b>Iniciar</b>."
        )
        return "\n".join(lines)


# Singleton
lobby_manager = LobbyManager()
```

---

## 6. `src/bot.py`

Agrega la línea `from src.handlers.game import game_router` entre los imports
y el `dp.include_router(game_router)` junto a los otros routers.

Las líneas a modificar son:

**En los imports** (después de `from src.handlers.start import start_router`):

```python
from src.handlers.start import start_router
from src.handlers.game import game_router
```

**En el bloque de routers** (después de `dp.include_router(group_router)`):

```python
    dp.include_router(start_router)
    dp.include_router(group_router)
    dp.include_router(game_router)
```

---

## 7. Comandos de verificación

```powershell
# 1. Reinicia el bot con recarga automática
watchfiles "python -m src.bot" src

# 2. Prueba en Telegram:
#    - Escribe /stop en el grupo → debe aparecer el mensaje lobby
#    - Pulsa "🟢 Unirse" → debe aparecer "Te has unido"
#    - El host ve el botón "▶️ Iniciar"
#    - Los demás jugadores ven solo "🟢 Unirse"
#    - Al alcanzar 10 → auto-start
#    - A los 30s del ultimo join (si >=2 jugadores) → auto-start
#    - A los 2 min sin joins → lobby se cierra
```

---

## Diagrama de flujo del lobby

```
User escribe /stop
    │
    ▼
Bot crea Game (status="lobby")
    │
    ▼
Bot envia mensaje lobby con botones
    │
    ├── Usuario pulsa "🟢 Unirse" ──────────┐
    │   │                                   │
    │   ├→ ¿Ya en partida? → alerta        │
    │   ├→ ¿Partida iniciada? → alerta     │
    │   ├→ ¿10 jugadores? → alerta         │
    │   └→ Añadir GamePlayer + reset timer │
    │                                       │
    ├── Host pulsa "▶️ Iniciar" ────────────┤
    │   │                                   │
    │   ├→ ¿Es host? → alerta si no        │
    │   ├→ ¿>=2 jug? → alerta si no        │
    │   └→ _do_start() ─→ status=playing   │
    │                                       │
    ├── 30s timer expira (>=2 jug) ────────┤
    │   → _do_start()                      │
    │                                       │
    ├── 10 jugadores alcanzados ───────────┤
    │   → _do_start()                      │
    │                                       │
    └── 2 min timer expira ────────────────┘
        → Cancelar lobby + cleanup
```

---

## Resumen de clases creadas/modificadas

| Clase | Archivo | Propósito |
|-------|---------|-----------|
| `LobbyManager` | `services/game_orchestrator.py` | Gestiona lobbies en memoria, timers, animación |
| `LobbyState` | `services/game_orchestrator.py` | Estado de una sala activa |
| `game_router` (`/stop`) | `handlers/game/lobby.py` | Handler del comando |
| `callback_join` | `handlers/game/lobby.py` | Procesar join inline |
| `callback_start` | `handlers/game/lobby.py` | Procesar start inline |
| `lobby_keyboard()` | `keyboards/lobby.py` | Generar inline keyboard |

---

*Documento generado para la implementación de la Fase 1.*
