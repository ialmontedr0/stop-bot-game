# Fase 6 — Leaderboard semanal, XP, rachas y estadísticas avanzadas

**Objetivo:** Sistema de progresión (XP/niveles), leaderboard semanal persistente, rachas de juego, estadísticas avanzadas por jugador y eventos estacionales.

---

## Estado Actual

| Componente | Estado |
|---|---|
| `WeeklyLeaderboard` | Modelo y tabla existen, NUNCA se escribe |
| `LeaderboardService` | Servicio existe (`leaderboard.py`) pero no se usa en ningún handler |
| `/profile` | Handler existe, muestra stats básicas (partidas, wins, MVP, accuracy) |
| `/stats` | Handler existe, muestra top 10 del grupo y actividad semanal |
| XP / Niveles | No existe |
| Rachas (streaks) | No existe |
| Eventos estacionales | No existe |
| `leaderboard_router` | No registrado en `bot.py` |
| `matplotlib` / `pillow` | Ya instalados (Fase 5) |

---

## Vista General de Cambios

```
backend/
├── locales/
│   └── {es,en,pt}/LC_MESSAGES/bot.po   # +claves de leaderboard, XP, streaks
├── src/
│   ├── bot.py                           # +leaderboard_router, +scheduler startup
│   ├── db/
│   │   ├── models.py                    # +PlayerXP, +Streak, +SeasonalEvent (NUEVOS)
│   │   └── repositories/
│   │       ├── leaderboard_repository.py   # NUEVO — upsert semanal
│   │       └── xp_repository.py            # NUEVO — XP/levels/streaks
│   ├── handlers/game/
│   │   ├── __init__.py                  # +leaderboard_router
│   │   ├── leaderboard.py               # NUEVO — /leaderboard, /top
│   │   ├── profile.py                   # MODIFICAR — +XP, +streak, +gráficos
│   │   └── stats.py                     # MODIFICAR — +desglose por categoría
│   ├── keyboards/
│   │   └── leaderboard.py               # NUEVO — botones de leaderboard
│   └── services/
│       ├── game_orchestrator.py         # MODIFICAR — llamar a WeeklyLeaderboard.upsert al finalizar
│       ├── leaderboard.py               # MODIFICAR — +upsert_week, +get_player_rank_by_telegram
│       ├── round_manager.py             # MODIFICAR — _end_game: otorgar XP
│       ├── xp_service.py                # NUEVO — cálculo de XP, niveles, rachas
│       └── event_service.py             # NUEVO — eventos estacionales (multiplicadores)
├── requirements/requirements.txt        # +apscheduler
└── tests/
    ├── test_leaderboard.py              # NUEVO
    ├── test_xp_service.py               # NUEVO
    └── test_event_service.py            # NUEVO
```

---

## Dependencias Nuevas

Añadir a `requirements/requirements.txt`:

```
# === Fase 6: Leaderboard semanal, XP, streaks, eventos ===
apscheduler>=3.10,<4.0          # Tarea programada: cierre semanal
```

`apscheduler` se usa para una tarea programada que, cada lunes a las 00:00, archiva la tabla semanal, asigna rangos finales y resetea `total_score` a 0 (o borra la tabla para la nueva semana).

---

## Tarea 6.1 — Nuevos modelos: PlayerXP, Streak, SeasonalEvent

### Modificar `backend/src/db/models.py`

Añadir **después** de `WeeklyLeaderboard` (antes de `GroupConfig`):

```python
class PlayerXP(Base):
    __tablename__ = "player_xp"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), unique=True, index=True
    )
    xp: Mapped[int] = mapped_column(default=0)
    level: Mapped[int] = mapped_column(default=1)
    total_xp_earned: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    player: Mapped["Player"] = relationship(backref="xp", uselist=False)


class Streak(Base):
    __tablename__ = "streaks"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), unique=True, index=True
    )
    current_streak: Mapped[int] = mapped_column(default=0)
    max_streak: Mapped[int] = mapped_column(default=0)
    last_played_date: Mapped[Optional[date]] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())

    player: Mapped["Player"] = relationship(backref="streak", uselist=False)


class SeasonalEvent(Base):
    __tablename__ = "seasonal_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    multiplier: Mapped[float] = mapped_column(default=1.0)  # ej: 2.0 = doble XP
    starts_at: Mapped[datetime] = mapped_column()
    ends_at: Mapped[datetime] = mapped_column()
    active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### Añadir relación en Player

Dentro de la clase `Player`, añadir:

```python
xp: Mapped[Optional["PlayerXP"]] = relationship(
    back_populates="player", uselist=False, cascade="all, delete-orphan"
)
streak: Mapped[Optional["Streak"]] = relationship(
    back_populates="player", uselist=False, cascade="all, delete-orphan"
)
```

> **Nota:** `uselist=False` porque es una relación uno-a-uno. No confundir con `weekly_leaderboards` que es uno-a-muchos.

### Migración Alembic

```bash
cd backend
alembic revision --autogenerate -m "add_player_xp_streak_seasonal_events"
alembic upgrade head
```

---

## Tarea 6.2 — XP Service

### Crear `backend/src/services/xp_service.py`

```python
"""Sistema de XP, niveles y rachas."""
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select

from src.db.engine import async_session_factory
from src.db.models import PlayerXP, Streak, Player

logger = logging.getLogger(__name__)

# Niveles: (level, xp_required)
LEVEL_TABLE = [
    (1, 0),
    (2, 100),
    (3, 250),
    (4, 500),
    (5, 800),
    (6, 1200),
    (7, 1700),
    (8, 2300),
    (9, 3000),
    (10, 4000),
    (11, 5000),
    (12, 6500),
    (13, 8000),
    (14, 10000),
    (15, 12500),
    (16, 15000),
    (17, 18000),
    (18, 21000),
    (19, 25000),
    (20, 30000),
]

# XP por acciones
XP_PER_GAME = 50          # XP base por partida completada
XP_PER_WIN = 100          # XP bonus por quedar 1º
XP_PER_STOP = 25          # XP bonus por ser el que hace Stop
XP_PER_UNIQUE = 10        # XP extra por respuesta única en una ronda
XP_STREAK_BONUS = 20      # XP extra por mantener racha >= 3

RANK_TITLES = {
    1: "Novato",
    5: "Aprendiz",
    10: "Veterano",
    15: "Maestro",
    20: "Leyenda",
}


def _calculate_level(total_xp: int) -> int:
    level = 1
    for lvl, required in reversed(LEVEL_TABLE):
        if total_xp >= required:
            level = lvl
            break
    return level


def _get_xp_for_next_level(current_level: int) -> int:
    for lvl, required in LEVEL_TABLE:
        if lvl == current_level + 1:
            return required
    return 999999


async def _ensure_xp_record(player_id: int) -> PlayerXP:
    async with async_session_factory() as session:
        stmt = select(PlayerXP).where(PlayerXP.player_id == player_id)
        result = await session.execute(stmt)
        xp_record = result.scalar_one_or_none()
        if not xp_record:
            xp_record = PlayerXP(player_id=player_id)
            session.add(xp_record)
            await session.flush()
            await session.refresh(xp_record)
        return xp_record


class XPService:
    @staticmethod
    async def award_game_xp(
        player_id: int,
        final_position: int,
        was_stopper: bool = False,
        unique_answers: int = 0,
    ) -> dict:
        """Otorga XP al finalizar una partida. Retorna dict con XP ganado y si subió de nivel."""
        xp_record = await _ensure_xp_record(player_id)
        old_level = xp_record.level

        xp_gained = XP_PER_GAME
        if final_position == 1:
            xp_gained += XP_PER_WIN
        if was_stopper:
            xp_gained += XP_PER_STOP
        xp_gained += unique_answers * XP_PER_UNIQUE

        # Streak bonus
        streak = await self.get_or_create_streak(player_id)
        if streak.current_streak >= 3:
            xp_gained += XP_STREAK_BONUS

        # Multiplicador por evento activo
        from src.services.event_service import event_service
        multiplier = await event_service.get_active_multiplier()
        xp_gained = int(xp_gained * multiplier)

        xp_record.xp += xp_gained
        xp_record.total_xp_earned += xp_gained
        xp_record.level = _calculate_level(xp_record.total_xp_earned)

        async with async_session_factory() as session:
            session.add(xp_record)
            await session.commit()

        leveled_up = xp_record.level > old_level
        new_title = RANK_TITLES.get(xp_record.level)

        return {
            "xp_gained": xp_gained,
            "total_xp": xp_record.total_xp_earned,
            "level": xp_record.level,
            "leveled_up": leveled_up,
            "title": new_title,
            "multiplier": multiplier,
        }

    @staticmethod
    async def get_or_create_streak(player_id: int) -> Streak:
        async with async_session_factory() as session:
            stmt = select(Streak).where(Streak.player_id == player_id)
            result = await session.execute(stmt)
            streak = result.scalar_one_or_none()
            if not streak:
                streak = Streak(player_id=player_id)
                session.add(streak)
                await session.flush()
                await session.refresh(streak)
            return streak

    @staticmethod
    async def update_streak(player_id: int) -> dict:
        """Actualiza la racha del jugador. Retorna info de la racha."""
        streak = await XPService.get_or_create_streak(player_id)
        today = date.today()

        if streak.last_played_date is None:
            streak.current_streak = 1
        elif streak.last_played_date == today:
            # Ya jugó hoy, no incrementar
            pass
        elif streak.last_played_date == today.replace(day=today.day - 1):
            streak.current_streak += 1
        else:
            streak.current_streak = 1

        if streak.current_streak > streak.max_streak:
            streak.max_streak = streak.current_streak

        streak.last_played_date = today

        async with async_session_factory() as session:
            session.add(streak)
            await session.commit()

        return {
            "current_streak": streak.current_streak,
            "max_streak": streak.max_streak,
        }

    @staticmethod
    async def get_profile(player_id: int) -> dict | None:
        async with async_session_factory() as session:
            stmt = select(PlayerXP).where(PlayerXP.player_id == player_id)
            result = await session.execute(stmt)
            xp_record = result.scalar_one_or_none()

            streak_stmt = select(Streak).where(Streak.player_id == player_id)
            streak_result = await session.execute(streak_stmt)
            streak = streak_result.scalar_one_or_none()

        if not xp_record:
            return None

        next_level_xp = _get_xp_for_next_level(xp_record.level)
        current_level_xp = 0
        for lvl, required in LEVEL_TABLE:
            if lvl == xp_record.level:
                current_level_xp = required
                break

        progress = 0
        if next_level_xp > current_level_xp:
            progress = (
                (xp_record.total_xp_earned - current_level_xp)
                / (next_level_xp - current_level_xp)
                * 100
            )

        return {
            "xp": xp_record.xp,
            "total_xp": xp_record.total_xp_earned,
            "level": xp_record.level,
            "title": RANK_TITLES.get(xp_record.level, ""),
            "next_level_xp": next_level_xp,
            "current_level_xp": current_level_xp,
            "progress_pct": round(progress, 1),
            "streak": streak.current_streak if streak else 0,
            "max_streak": streak.max_streak if streak else 0,
        }


xp_service = XPService()
```

---

## Tarea 6.3 — Event Service (multiplicadores estacionales)

### Crear `backend/src/services/event_service.py`

```python
"""Gestión de eventos estacionales (multiplicadores de XP/score)."""
import logging
from datetime import datetime

from sqlalchemy import select

from src.db.engine import async_session_factory
from src.db.models import SeasonalEvent

logger = logging.getLogger(__name__)


class EventService:
    @staticmethod
    async def get_active_multiplier() -> float:
        """Retorna el multiplicador activo más alto (default 1.0)."""
        now = datetime.utcnow()
        async with async_session_factory() as session:
            stmt = (
                select(SeasonalEvent.multiplier)
                .where(SeasonalEvent.active == True)
                .where(SeasonalEvent.starts_at <= now)
                .where(SeasonalEvent.ends_at >= now)
                .order_by(SeasonalEvent.multiplier.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row or 1.0

    @staticmethod
    async def get_active_events() -> list[dict]:
        now = datetime.utcnow()
        async with async_session_factory() as session:
            stmt = (
                select(SeasonalEvent)
                .where(SeasonalEvent.active == True)
                .where(SeasonalEvent.starts_at <= now)
                .where(SeasonalEvent.ends_at >= now)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()
            return [
                {
                    "id": e.id,
                    "name": e.name,
                    "description": e.description,
                    "multiplier": e.multiplier,
                    "ends_at": e.ends_at.isoformat(),
                }
                for e in events
            ]


event_service = EventService()
```

### Admin command para gestionar eventos (opcional)

Crear `backend/src/handlers/admin/events.py`:

```python
@admin_router.message(Command("addevent"))
async def cmd_add_event(message: Message) -> None:
    # Uso: /addevent Nombre|desc|2.0|2026-12-25|2026-12-26
    ...
```

Este handler es opcional. Los eventos pueden crearse directamente en BD o mediante un panel de admin. Por ahora, se crean manualmente con SQL o Alembic seed.

---

## Tarea 6.4 — Leaderboard Repository + Service ampliado

### Crear `backend/src/db/repositories/leaderboard_repository.py`

```python
"""Repositorio para WeeklyLeaderboard — upsert y ranking."""
import logging
from datetime import date, timedelta

from sqlalchemy import select, func, desc
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.engine import async_session_factory
from src.db.models import WeeklyLeaderboard, Player

logger = logging.getLogger(__name__)


def _current_week_start() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())  # Lunes


class LeaderboardRepository:
    @staticmethod
    async def upsert_player_week(
        player_id: int,
        score_to_add: int,
        week_start: date | None = None,
    ) -> None:
        """Acumula score semanal del jugador (upsert)."""
        ws = week_start or _current_week_start()
        async with async_session_factory() as session:
            stmt = select(WeeklyLeaderboard).where(
                WeeklyLeaderboard.player_id == player_id,
                WeeklyLeaderboard.week_start == ws,
            )
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()

            if entry:
                entry.total_score += score_to_add
                entry.games_played += 1
            else:
                entry = WeeklyLeaderboard(
                    player_id=player_id,
                    week_start=ws,
                    total_score=score_to_add,
                    games_played=1,
                )
                session.add(entry)

            await session.commit()

    @staticmethod
    async def recalculate_ranks(week_start: date | None = None) -> None:
        """Recalcula los ranks de todos los jugadores para la semana."""
        ws = week_start or _current_week_start()
        async with async_session_factory() as session:
            stmt = (
                select(WeeklyLeaderboard)
                .where(WeeklyLeaderboard.week_start == ws)
                .order_by(desc(WeeklyLeaderboard.total_score))
            )
            result = await session.execute(stmt)
            entries = result.scalars().all()

            for i, entry in enumerate(entries):
                entry.rank = i + 1

            await session.commit()
            logger.info("Ranks recalculados para semana %s: %s entries", ws, len(entries))

    @staticmethod
    async def close_week(week_start: date | None = None) -> None:
        """Cierra la semana: recalcula ranks finales. No borra datos (histórico)."""
        ws = week_start or _current_week_start()
        await LeaderboardRepository.recalculate_ranks(ws)
        logger.info("Semana %s cerrada. Los datos permanecen como histórico.", ws)
```

### Modificar `backend/src/services/leaderboard.py`

Añadir método `upsert_player` y corregir `get_player_rank` para aceptar `telegram_id`:

```python
class LeaderboardService:
    # ... (métodos existentes) ...

    @staticmethod
    async def upsert_player(player_id: int, score_to_add: int) -> None:
        await LeaderboardRepository.upsert_player_week(player_id, score_to_add)

    @staticmethod
    async def get_player_rank_by_telegram(telegram_id: int) -> dict | None:
        """Busca por telegram_id en vez de player.id interno."""
        async with async_session_factory() as session:
            player_stmt = select(Player).where(Player.telegram_id == telegram_id)
            player_result = await session.execute(player_stmt)
            player = player_result.scalar_one_or_none()
            if not player:
                return None

            stmt = select(WeeklyLeaderboard).where(
                WeeklyLeaderboard.player_id == player.id
            )
            result = await session.execute(stmt)
            entry = result.scalar_one_or_none()
            if not entry:
                return None
            return {
                "rank": entry.rank,
                "score": entry.total_score,
                "games": entry.games_played,
            }
```

Añadir al principio del archivo:

```python
from src.db.repositories.leaderboard_repository import LeaderboardRepository
```

---

## Tarea 6.5 — `/leaderboard` command

### Crear `backend/src/handlers/game/leaderboard.py`

```python
import logging
from datetime import date, timedelta

from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from aiogram.utils.markdown import hbold

from src.services.leaderboard import leaderboard_service

logger = logging.getLogger(__name__)
leaderboard_router = Router()


def _current_week_range() -> str:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return f"{monday.strftime('%d/%m')} - {sunday.strftime('%d/%m')}"


@leaderboard_router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message) -> None:
    """Muestra el top 10 semanal."""
    status_msg = await message.reply("📊 Cargando leaderboard...")

    try:
        rows = await leaderboard_service.get_weekly_top(limit=10)

        if not rows:
            await status_msg.edit_text(
                "📊 <b>Leaderboard Semanal</b>\n\n"
                "Aún no hay datos esta semana.\n"
                "¡Juega una partida para aparecer aquí!"
            )
            return

        lines = [
            f"{hbold('🏆 Leaderboard Semanal')}",
            f"📅 {_current_week_range()}\n",
        ]

        medals = ["🥇", "🥈", "🥉"]
        for entry in rows:
            rank = entry["rank"]
            medal = medals[rank - 1] if rank <= 3 else f"{rank}."
            name = entry["name"]
            score = entry["score"]
            games = entry["games"]
            lines.append(f"{medal} {name} — {score} pts ({games} partidas)")

        text = "\n".join(lines)
        await status_msg.edit_text(text)

    except Exception as e:
        logger.exception("Error en /leaderboard")
        await status_msg.edit_text(
            "❌ Error al cargar el leaderboard. Intenta de nuevo más tarde."
        )


@leaderboard_router.message(Command("rank"))
async def cmd_rank(message: Message) -> None:
    """Muestra el rank semanal del jugador."""
    from src.middlewares.user_exists import get_player_from_data
    player = message.from_user
    if not player:
        return

    data = await leaderboard_service.get_player_rank_by_telegram(player.id)
    if not data:
        await message.reply(
            "Aún no apareces en el leaderboard semanal.\n"
            "¡Juega una partida para empezar!"
        )
        return

    medal = ""
    if data["rank"] == 1:
        medal = "🥇 "
    elif data["rank"] == 2:
        medal = "🥈 "
    elif data["rank"] == 3:
        medal = "🥉 "

    await message.reply(
        f"{hbold('📊 Tu Rank Semanal')}\n\n"
        f"{medal}Puesto: #{data['rank']}\n"
        f"⭐ Puntaje: {data['score']} pts\n"
        f"🎮 Partidas: {data['games']}"
    )
```

### Registrar en `backend/src/handlers/game/__init__.py`

```python
from .leaderboard import leaderboard_router

__all__ = [
    # ... existentes ...
    "leaderboard_router",
]
```

### Registrar en `backend/src/bot.py`

```python
from src.handlers.game.leaderboard import leaderboard_router

# En main():
dp.include_router(leaderboard_router)
```

---

## Tarea 6.6 — Integrar XP, streaks y leaderboard al finalizar partida

### Modificar `backend/src/services/round_manager.py` — `_end_game`

Reemplazar el método `_end_game` para otorgar XP, actualizar streaks y escribir al leaderboard semanal:

```python
async def _end_game(self, state: RoundState, bot: Bot) -> None:
    async with async_session_factory() as session:
        repo = GameRepository(session)
        db_game = await repo.get_by_id(state.game_id)
        if db_game:
            db_game.status = "finished"
            db_game.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.commit()

        winners = await self._get_standings(state.game_id)

    # ── Otorgar XP, streaks, leaderboard ──
    xp_results = {}
    for position, (telegram_id, score) in enumerate(winners):
        # Buscar player_id interno
        async with async_session_factory() as session:
            stmt = select(Player).where(Player.telegram_id == telegram_id)
            result = await session.execute(stmt)
            player = result.scalar_one_or_none()
            if not player:
                continue

        # Streak
        await xp_service.update_streak(player.id)

        # XP
        was_stopper = telegram_id == state.first_completer_id if state else False
        # unique_answers: contar respuestas únicas de este jugador en la última ronda
        unique_answers = 0  # Simplificado; idealmente contar desde details
        xp_info = await xp_service.award_game_xp(
            player_id=player.id,
            final_position=position + 1,
            was_stopper=was_stopper,
            unique_answers=unique_answers,
        )
        xp_results[telegram_id] = xp_info

        # Leaderboard semanal
        from src.services.leaderboard import leaderboard_service
        await leaderboard_service.upsert_player(
            player_id=player.id,
            score_to_add=score,
        )

    # ── Recalcular ranks semanales ──
    from src.db.repositories.leaderboard_repository import LeaderboardRepository
    await LeaderboardRepository.recalculate_ranks()

    # ── Mensaje de finalización con XP ──
    lines = ["<b>🏆 ¡Partida finalizada!</b>", ""]
    if winners:
        for i, (pid, score) in enumerate(winners[:3]):
            medals = ["🥇", "🥈", "🥉"]
            name = state.player_names.get(pid, f"Jugador {pid}")
            xp_info = xp_results.get(pid, {})
            xp_text = f" (+{xp_info.get('xp_gained', 0)} XP)" if xp_info else ""
            lines.append(f"{medals[i] if i < 3 else i + 1}. {name} — {score} pts{xp_text}")

            # Mensaje de subida de nivel
            if xp_info.get("leveled_up"):
                title = xp_info.get("title", "")
                title_text = f" | 🎖 {title}" if title else ""
                await bot.send_message(
                    state.group_chat_id,
                    f"🎉 <b>{name} ha subido al nivel {xp_info['level']}!</b>{title_text}",
                )
    else:
        lines.append("  No hay puntuaciones registradas.")

    # Evento activo
    from src.services.event_service import event_service
    active_events = await event_service.get_active_events()
    for event in active_events:
        lines.append("")
        lines.append(
            f"🎉 <b>Evento activo: {event['name']}</b> "
            f"(×{event['multiplier']} XP)"
        )

    lines.append("")
    lines.append("<i>Gracias por jugar 🛑 Stop!</i>")
    await bot.send_message(state.group_chat_id, "\n".join(lines))
    self._letter_pending.pop(state.game_id, None)
    self._rounds_by_group.pop(state.group_chat_id, None)
```

> **IMPORTANTE:** Añadir imports al inicio de `round_manager.py`:
> ```python
> from src.services.xp_service import xp_service
> from src.db.models import Player
> ```

---

## Tarea 6.7 — Modificar `/profile` para incluir XP, nivel y racha

### Modificar `backend/src/handlers/game/profile.py`

Añadir al handler `cmd_profile`, después de las stats existentes:

```python
from src.services.xp_service import xp_service

# Dentro de cmd_profile, después de calcular accuracy:
xp_data = await xp_service.get_profile(player.id)

lines = [
    f"{hbold('👤 Tu Perfil')}\n",
    f"🎮 Partidas jugadas: {total_games}",
    f"🏆 Victorias: {wins_count}",
    f"⭐ MVP (Stops): {mvp_count}",
    f"📊 Puntaje total: {total_score} pts",
    f"🎯 Rating de aciertos: {accuracy:.1f}% "
    f"({correct_answers}/{total_answers})",
]

# Sección XP
if xp_data:
    title_text = f" ({xp_data['title']})" if xp_data["title"] else ""
    lines.append("")
    lines.append(f"{hbold('⚡ XP y Nivel')}")
    lines.append(f"🎖 Nivel {xp_data['level']}{title_text}")
    lines.append(f"✨ XP total: {xp_data['total_xp']}")
    lines.append(
        f"📈 Progreso al nivel {xp_data['level'] + 1}: "
        f"{xp_data['progress_pct']}%"
    )
    # Barra de progreso simple
    bar_len = 10
    filled = int(xp_data['progress_pct'] / 100 * bar_len)
    bar = "▓" * filled + "░" * (bar_len - filled)
    lines.append(f"  {bar}")

# Sección racha
if xp_data and xp_data["streak"] > 0:
    fire = "🔥" if xp_data["streak"] >= 3 else "⭐"
    lines.append("")
    lines.append(f"{hbold('📅 Racha')}")
    lines.append(f"{fire} Racha actual: {xp_data['streak']} días")
    lines.append(f"🏅 Mejor racha: {xp_data['max_streak']} días")

# Rank semanal (opcional)
from src.services.leaderboard import leaderboard_service
rank_data = await leaderboard_service.get_player_rank_by_telegram(
    player.telegram_id
)
if rank_data:
    lines.append("")
    lines.append(f"{hbold('📊 Rank Semanal')}")
    lines.append(f"  Puesto #{rank_data['rank']} — {rank_data['score']} pts")
```

---

## Tarea 6.8 — Tarea programada semanal con APScheduler

### Modificar `backend/src/bot.py` — `on_startup`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.db.repositories.leaderboard_repository import LeaderboardRepository

# Variable global para el scheduler
_scheduler: AsyncIOScheduler | None = None


async def on_startup() -> None:
    # ... existente ...

    # ── Scheduler semanal: cerrar leaderboard los lunes 00:00 ──
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
```

### Modificar `backend/src/bot.py` — `on_shutdown`

```python
async def on_shutdown() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
    # ... existente ...
```

### Añadir a `requirements.txt`

```
apscheduler>=3.10,<4.0
```

---

## Tarea 6.9 — Tests

### Tests para XP Service

Crear `backend/tests/test_xp_service.py`:

```python
import pytest
from src.services.xp_service import XPService, _calculate_level, LEVEL_TABLE

@pytest.mark.asyncio
async def test_calculate_level():
    assert _calculate_level(0) == 1
    assert _calculate_level(50) == 1

@pytest.mark.asyncio
async def test_level_up():
    # Simula otorgar XP hasta subir de nivel
    ...

@pytest.mark.asyncio
async def test_streak_update(async_session):
    ...
```

### Tests para LeaderboardRepository

Crear `backend/tests/test_leaderboard_repository.py`:

```python
import pytest
from datetime import date
from src.db.repositories.leaderboard_repository import LeaderboardRepository

@pytest.mark.asyncio
async def test_upsert_and_rank(async_session):
    ...
```

---

## Tarea 6.10 — Traducciones (i18n)

Añadir a `locales/es/LC_MESSAGES/bot.po`:

```po
msgid "leaderboard_title"
msgstr "🏆 Leaderboard Semanal"

msgid "leaderboard_empty"
msgstr "Aún no hay datos esta semana.\n¡Juega una partida para aparecer aquí!"

msgid "rank_title"
msgstr "📊 Tu Rank Semanal"

msgid "xp_title"
msgstr "⚡ XP y Nivel"

msgid "streak_title"
msgstr "📅 Racha"

msgid "level_up"
msgstr "🎉 {name} ha subido al nivel {level}!"

msgid "event_active"
msgstr "🎉 Evento activo: {name} (×{multiplier} XP)"

msgid "profile_rank"
msgstr "📊 Rank Semanal"
```

Añadir equivalentes en `en/` y `pt/`.

---

## Orden de Implementación

1. **Paso 1:** Añadir `apscheduler` a `requirements.txt`, instalar.
2. **Paso 2:** Añadir modelos `PlayerXP`, `Streak`, `SeasonalEvent` a `models.py`.
3. **Paso 3:** Generar migración Alembic y ejecutarla.
4. **Paso 4:** Crear `backend/src/services/xp_service.py`.
5. **Paso 5:** Crear `backend/src/services/event_service.py`.
6. **Paso 6:** Crear `backend/src/db/repositories/leaderboard_repository.py`.
7. **Paso 7:** Modificar `backend/src/services/leaderboard.py` (añadir `upsert_player`, `get_player_rank_by_telegram`).
8. **Paso 8:** Modificar `backend/src/services/round_manager.py` (`_end_game`: XP, streaks, leaderboard).
9. **Paso 9:** Crear `backend/src/handlers/game/leaderboard.py` (`/leaderboard`, `/rank`).
10. **Paso 10:** Registrar `leaderboard_router` en `__init__.py` y `bot.py`.
11. **Paso 11:** Modificar `backend/src/handlers/game/profile.py` (añadir XP, streak, rank).
12. **Paso 12:** Configurar APScheduler en `bot.py` (`on_startup`/`on_shutdown`).
13. **Paso 13:** Añadir traducciones a los archivos `.po` y recompilar.
14. **Paso 14:** Escribir tests.
15. **Paso 15:** Probar en Telegram: jugar una partida, verificar `/profile` (XP, streak), `/leaderboard`, `/rank`.

---

## Resumen de Archivos Nuevos/Modificados

| Archivo | Acción |
|---|---|
| `requirements/requirements.txt` | Modificar (+apscheduler) |
| `src/db/models.py` | Modificar (+PlayerXP, +Streak, +SeasonalEvent, +relaciones en Player) |
| `src/db/repositories/leaderboard_repository.py` | **NUEVO** |
| `src/services/xp_service.py` | **NUEVO** |
| `src/services/event_service.py` | **NUEVO** |
| `src/services/leaderboard.py` | Modificar (+upsert_player, +get_player_rank_by_telegram) |
| `src/services/round_manager.py` | Modificar (_end_game: XP, streaks, leaderboard) |
| `src/handlers/game/leaderboard.py` | **NUEVO** |
| `src/handlers/game/profile.py` | Modificar (+XP, +streak, +rank semanal) |
| `src/handlers/game/__init__.py` | Modificar (+leaderboard_router) |
| `src/handlers/game/stats.py` | Modificar (opcional: desglose por categoría) |
| `src/keyboards/leaderboard.py` | **NUEVO** (opcional) |
| `src/bot.py` | Modificar (+leaderboard_router, +APScheduler) |
| `locales/*/LC_MESSAGES/bot.po` | Modificar (+claves nuevas) |
| `tests/test_xp_service.py` | **NUEVO** |
| `tests/test_leaderboard_repository.py` | **NUEVO** |
| `tests/test_event_service.py` | **NUEVO** |

---

## Consideraciones Técnicas

1. **APScheduler en producción:** Si el bot se ejecuta en múltiples instancias (horizontal scaling), el scheduler se ejecutará en cada instancia. Para evitar duplicados, considera:
   - Usar un lock en Redis (`setnx`) alrededor del job.
   - O ejecutar el scheduler solo en una instancia designada.
   - O usar una tarea cron externa (ej: GitHub Actions, cron en el servidor) que llame a un endpoint.

2. **XP Balance:** Los valores de `XP_PER_GAME`, `XP_PER_WIN`, etc. están pensados para partidas de 5 rondas. Ajustar según feedback de jugadores. La tabla de niveles (`LEVEL_TABLE`) usa curva exponencial suave; los primeros 5 niveles son rápidos, luego se vuelve más lento.

3. **Rachas (streaks):** Se calculan en UTC. Un jugador que juega a las 23:59 y luego a las 00:05 tendrá racha de 2 días consecutivos. Esto es intencional. Si se quiere racha por "día de juego" (no calendario), habría que usar un periodo de 24h desde la primera partida del día.

4. **Leaderboard semanal:** La semana comienza en lunes (ISO). `_current_week_start()` calcula el lunes de la semana actual. El job de APScheduler del lunes 00:00 cierra la semana anterior (recalcula ranks finales). Los datos no se borran — quedan como histórico.

5. **Eventos estacionales:** `SeasonalEvent` permite activar multiplicadores de XP (ej: 2.0 = doble XP). Se pueden crear eventos navideños, de fin de semana, etc. El `EventService` busca el multiplicador activo más alto (varios eventos pueden solaparse).

6. **Unique answers para XP extra:** El contador de `unique_answers` está simplificado a 0 en `_end_game`. Para implementarlo correctamente, pasar los `details` del ScoreEngine (que indican qué respuestas fueron únicas) y contar cuántas tuvo cada jugador:

   ```python
   # En _persist_round_scores, retornar también details
   # Luego en _end_game:
   unique_count = sum(
       1 for ad in details.get(telegram_id, []) if ad.get("is_correct") and ad.get("score") == UNIQUE_POINTS
   )
   ```
