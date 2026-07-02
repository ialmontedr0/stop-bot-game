# Fase 2 — Ciclo de ronda: letra, envío, Stop y evaluación

**Objetivo:** Núcleo del juego — rondas completas con temporizador, Stop, y transición entre rondas.

Fases anteriores completadas: Fase 0 (fundación) + Fase 1 (lobby).

---

## Arquitectura

### Nuevos componentes

| Componente | Archivo | Propósito |
|-----------|---------|-----------|
| `RoundManager` | `src/services/round_manager.py` | Gestiona el ciclo de vida de cada ronda (inicio, respuestas, stop, cierre) |
| `RoundState` | `src/services/round_manager.py` | Estado en memoria de una ronda activa |
| `parse_answers()` | `src/services/round_manager.py` | Parser de respuestas con regex `categoría: valor` |
| `RoundRepository` | `src/db/repositories/round_repository.py` | CRUD para rondas y respuestas en DB |
| `stop_keyboard()` | `src/keyboards/round.py` | Teclado inline con botón "Stop N" progresivo |
| `letter_keyboard()` | `src/keyboards/round.py` | Teclado inline con el alfabeto para líder |
| `round_router` | `src/handlers/game/round.py` | Handlers de respuestas, stop y selección de letra |

### Flujo de una ronda completa

```
_do_start() [game_orchestrator]
  └─ round_manager.start_round()
       ├─ Crea Round en DB (status="active")
       ├─ Envía mensaje al grupo con letra + categorías
       └─ Inicia timer de 60s

Jugadores envían respuestas
  └─ handle_round_answer() [round.py]
       ├─ parse_answers() extrae pares categoría:valor
       ├─ RoundRepository.save_answers() guarda en DB
       └─ Si es primer completo → envía DM con botón Stop 1

Stop mechanic
  └─ callback_stop() [round.py]
       ├─ Solo el primer completo puede presionar
       ├─ Avanza Stop N → Stop N+1
       └─ Al llegar a Stop 10 → _close_round()

Round cierra (stop | timeout | all_submitted)
  └─ _close_round()
       ├─ Edita mensaje del grupo con resultado
       ├─ Envía resumen de ronda
       └─ Transición: líder elige letra → countdown → nueva ronda
```

---

## Archivos a crear

### 1. `backend/src/db/repositories/round_repository.py`

```python
from typing import Optional

from sqlalchemy import select

from src.db.models import Answer, GamePlayer, Round

from .base import BaseRepository


class RoundRepository(BaseRepository[Round]):
    def __init__(self, session):
        super().__init__(Round, session)

    async def create_round(
        self,
        game_id: int,
        round_number: int,
        letter: str,
    ) -> Round:
        r = Round(
            game_id=game_id,
            round_number=round_number,
            letter=letter,
            status="active",
        )
        self.session.add(r)
        await self.session.commit()
        await self.session.refresh(r)
        return r

    async def get_active_round(self, game_id: int) -> Optional[Round]:
        stmt = (
            select(Round)
            .where(Round.game_id == game_id)
            .where(Round.status == "active")
            .order_by(Round.round_number.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        round_id: int,
        status: str,
        stopped_by_player_id: Optional[int] = None,
    ) -> Round:
        r = await self.session.get(Round, round_id)
        if not r:
            raise ValueError(f"Round {round_id} not found")
        r.status = status
        if stopped_by_player_id is not None:
            r.stopped_by_player_id = stopped_by_player_id
        await self.session.commit()
        await self.session.refresh(r)
        return r

    async def save_answers(
        self,
        round_id: int,
        game_id: int,
        player_id: int,
        answers: dict[str, str],
    ) -> list[Answer]:
        stmt = select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.player_id == player_id,
        )
        gp = (await self.session.execute(stmt)).scalar_one_or_none()
        if not gp:
            raise ValueError(f"GamePlayer not found for game={game_id} player={player_id}")

        old = await self.session.execute(
            select(Answer).where(
                Answer.round_id == round_id,
                Answer.player_id == player_id,
            )
        )
        for a in old.scalars():
            await self.session.delete(a)
        await self.session.flush()

        result = []
        for slot, value in answers.items():
            a = Answer(
                round_id=round_id,
                player_id=player_id,
                game_player_id=gp.id,
                word_slot=slot,
                raw_text=value,
            )
            self.session.add(a)
            result.append(a)
        await self.session.commit()
        for a in result:
            await self.session.refresh(a)
        return result

    async def get_answers_by_player(
        self, round_id: int
    ) -> dict[int, list[Answer]]:
        stmt = (
            select(Answer)
            .where(Answer.round_id == round_id)
            .order_by(Answer.player_id)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        result: dict[int, list[Answer]] = {}
        for a in rows:
            result.setdefault(a.player_id, []).append(a)
        return result

    async def get_total_rounds(self, game_id: int) -> int:
        stmt = select(Round).where(Round.game_id == game_id)
        result = await self.session.execute(stmt)
        return len(result.scalars().all())
```

---

### 2. `backend/src/keyboards/round.py`

```python
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

LETTERS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I",
    "J", "K", "L", "M", "N", "O", "P", "Q", "R",
    "S", "T", "U", "V", "W", "X", "Y", "Z",
]


def stop_keyboard(game_id: int, stop_number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⏹ Stop {stop_number}/10",
                    callback_data=f"stop:{game_id}:{stop_number}",
                )
            ]
        ]
    )


def letter_keyboard(game_id: int) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, letter in enumerate(LETTERS):
        row.append(
            InlineKeyboardButton(
                text=letter,
                callback_data=f"letter:{game_id}:{letter}",
            )
        )
        if len(row) == 6 or i == len(LETTERS) - 1:
            rows.append(row)
            row = []
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

---

### 3. `backend/src/services/round_manager.py`

```python
import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

from src.db.engine import async_session_factory
from src.db.models import Player, GamePlayer
from src.db.repositories.game_repository import GameRepository
from src.db.repositories.round_repository import RoundRepository
from src.keyboards.round import stop_keyboard, letter_keyboard

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────────────────

NUM_STOP_BUTTONS = 10
ROUND_DURATION = 60
TOTAL_ROUNDS = 5

CATEGORIES = [
    "Nombre", "Apellido", "Color", "Fruta",
    "País o Ciudad", "Artista o Banda", "Película o Serie", "Cosa",
    "Animal", "Profesión", "Deporte", "Marca",
]

CATEGORIES_DISPLAY = "\n".join(
    f"  <b>{cat}:</b> ..." for cat in CATEGORIES
)

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ── Estado en memoria ───────────────────────────────────────────────────────


@dataclass
class RoundState:
    game_id: int
    group_chat_id: int
    round_number: int
    letter: str
    categories: list[str]
    message_chat_id: int
    message_id: int
    timer_task: Optional[asyncio.Task] = None
    submitted_player_ids: set[int] = field(default_factory=set)
    complete_player_ids: set[int] = field(default_factory=set)
    first_completer_id: Optional[int] = None
    first_completer_name: Optional[str] = None
    stop_presses: int = 0
    total_players: int = 0
    stop_message_chat_id: Optional[int] = None
    stop_message_id: Optional[int] = None
    player_names: dict[int, str] = field(default_factory=dict)


# ── RoundManager ────────────────────────────────────────────────────────────


class RoundManager:
    """Gestiona rondas activas en memoria, indexadas por game_id."""

    def __init__(self) -> None:
        self._rounds: dict[int, RoundState] = {}

    # ── Consultas ───────────────────────────────────────────────────────────

    def get_active_round(self, game_id: int) -> Optional[RoundState]:
        return self._rounds.get(game_id)

    # ── Iniciar ronda ───────────────────────────────────────────────────────

    async def start_round(
        self,
        game_id: int,
        group_chat_id: int,
        round_number: int,
        letter: str,
        total_players: int,
        player_names: dict[int, str],
        bot: Bot,
    ) -> None:
        text = self._format_round_message(round_number, letter)

        msg = await bot.send_message(group_chat_id, text)

        state = RoundState(
            game_id=game_id,
            group_chat_id=group_chat_id,
            round_number=round_number,
            letter=letter,
            categories=CATEGORIES,
            message_chat_id=msg.chat.id,
            message_id=msg.message_id,
            total_players=total_players,
            player_names=player_names,
        )

        state.timer_task = asyncio.create_task(
            self._round_timer(state, bot)
        )
        self._rounds[game_id] = state
        logger.info(
            "Ronda iniciada",
            game_id=game_id,
            round=round_number,
            letter=letter,
        )

    # ── Recibir respuestas ──────────────────────────────────────────────────

    async def submit_answers(
        self,
        game_id: int,
        player: Player,
        text: str,
        bot: Bot,
    ) -> bool:
        """Procesa respuestas. Retorna True si el jugador es el primer completo."""
        state = self.get_active_round(game_id)
        if not state:
            return False

        parsed = parse_answers(text, state.categories)
        if not parsed:
            return False

        async with async_session_factory() as session:
            repo = RoundRepository(session)
            db_round = await repo.get_active_round(game_id)
            if not db_round:
                return False
            await repo.save_answers(
                round_id=db_round.id,
                game_id=game_id,
                player_id=player.id,
                answers=parsed,
            )

        state.submitted_player_ids.add(player.telegram_id)
        self._update_round_message(state, bot)

        all_filled = len(parsed) == len(state.categories)

        if all_filled:
            state.complete_player_ids.add(player.telegram_id)

            if state.first_completer_id is None:
                state.first_completer_id = player.telegram_id
                name = player.first_name or player.username or f"ID{player.telegram_id}"
                state.first_completer_name = name

                await self._send_stop_message(state, bot)

        await self._check_all_submitted(state, bot)
        return all_filled and state.first_completer_id == player.telegram_id

    # ── Sistema Stop ────────────────────────────────────────────────────────

    async def press_stop(
        self,
        game_id: int,
        player_id: int,
        callback,
        bot: Bot,
    ) -> None:
        state = self.get_active_round(game_id)
        if not state:
            await callback.answer("❌ Esta ronda ya terminó.", show_alert=True)
            return

        if player_id != state.first_completer_id:
            await callback.answer(
                "❌ Solo puedes usar Stop si completaste todas las categorías.",
                show_alert=True,
            )
            return

        state.stop_presses += 1

        if state.stop_presses >= NUM_STOP_BUTTONS:
            await callback.answer("⏹ ¡Ronda detenida!", show_alert=False)
            await self._close_round(game_id, "stop", bot)
            return

        progress = state.stop_presses
        await callback.answer(
            f"⏹ Stop {progress}/{NUM_STOP_BUTTONS}", show_alert=False
        )

        await bot.edit_message_text(
            self._format_stop_message(progress),
            chat_id=state.stop_message_chat_id,
            message_id=state.stop_message_id,
            reply_markup=stop_keyboard(game_id, progress + 1),
        )

    # ── Cierre de ronda ─────────────────────────────────────────────────────

    async def _close_round(
        self,
        game_id: int,
        reason: str,
        bot: Bot,
    ) -> None:
        state = self._rounds.pop(game_id, None)
        if not state:
            return

        if state.timer_task and not state.timer_task.done():
            state.timer_task.cancel()

        reason_texts = {
            "stop": "⏹ <b>Ronda detenida</b>",
            "timeout": "⌛ <b>Tiempo agotado</b>",
            "all_submitted": "✅ <b>¡Todos respondieron!</b>",
        }
        reason_text = reason_texts.get(reason, "⏹ <b>Ronda cerrada</b>")

        async with async_session_factory() as session:
            repo = RoundRepository(session)
            db_round = await repo.get_active_round(game_id)
            if db_round:
                stopped_by = None
                if reason == "stop" and state.first_completer_id:
                    stopped_by = state.first_completer_id
                await repo.update_status(
                    db_round.id,
                    status="completed",
                    stopped_by_player_id=stopped_by,
                )

        try:
            await bot.edit_message_text(
                f"{reason_text}\n\n"
                f"<b>Ronda {state.round_number}</b> — Letra: <b>{state.letter}</b>\n\n"
                f"<i>Calculando puntuaciones...</i>",
                chat_id=state.message_chat_id,
                message_id=state.message_id,
            )
        except TelegramBadRequest:
            pass

        if state.stop_message_id:
            try:
                await bot.edit_message_text(
                    f"{reason_text}\n\nLa ronda ha finalizado.",
                    chat_id=state.stop_message_chat_id,
                    message_id=state.stop_message_id,
                )
            except TelegramBadRequest:
                pass

        summary = await self._build_summary(game_id, state)
        await bot.send_message(state.group_chat_id, summary)

        await self._transition_next_round(state, bot)

    # ── Transición a siguiente ronda ────────────────────────────────────────

    async def _transition_next_round(
        self,
        state: RoundState,
        bot: Bot,
    ) -> None:
        if state.round_number >= TOTAL_ROUNDS:
            await self._end_game(state, bot)
            return

        leader_id = await self._get_leader_telegram_id(state.game_id)
        if not leader_id:
            leader_id = state.first_completer_id
        if not leader_id:
            await self._start_next_round_with_random(state, bot)
            return

        name = state.player_names.get(leader_id, "El líder")
        msg = await bot.send_message(
            state.group_chat_id,
            f"🏆 <b>{name}, elige la letra de la siguiente ronda:</b>",
            reply_markup=letter_keyboard(state.game_id),
        )
        asyncio.create_task(self._letter_timeout(msg, bot, state))

    async def _letter_timeout(self, msg, bot, state):
        await asyncio.sleep(15)
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        letter = random.choice(ALPHABET)
        await self._start_next_round_with_letter(state, letter, bot)

    async def handle_letter_selection(
        self,
        game_id: int,
        player_id: int,
        letter: str,
        callback,
        bot: Bot,
    ) -> None:
        state = self._rounds.get(game_id)
        if not state:
            await callback.answer("❌ Partida no activa.", show_alert=True)
            return

        next_number = state.round_number + 1

        await callback.answer(f"✅ Letra {letter} seleccionada", show_alert=False)

        countdown = await bot.send_message(
            state.group_chat_id,
            f"<b>Letra: {letter}</b>\n"
            f"⏱ Siguiente ronda en 5 segundos...",
        )
        await asyncio.sleep(5)
        try:
            await countdown.delete()
        except TelegramBadRequest:
            pass

        await self.start_round(
            game_id=game_id,
            group_chat_id=state.group_chat_id,
            round_number=next_number,
            letter=letter,
            total_players=state.total_players,
            player_names=state.player_names,
            bot=bot,
        )

    async def _start_next_round_with_letter(
        self,
        prev_state: RoundState,
        letter: str,
        bot: Bot,
    ) -> None:
        await self.start_round(
            game_id=prev_state.game_id,
            group_chat_id=prev_state.group_chat_id,
            round_number=prev_state.round_number + 1,
            letter=letter,
            total_players=prev_state.total_players,
            player_names=prev_state.player_names,
            bot=bot,
        )

    async def _start_next_round_with_random(self, state, bot):
        letter = random.choice(ALPHABET)
        await self._start_next_round_with_letter(state, letter, bot)

    # ── Fin de partida ──────────────────────────────────────────────────────

    async def _end_game(self, state: RoundState, bot: Bot) -> None:
        async with async_session_factory() as session:
            repo = GameRepository(session)
            db_game = await repo.get_by_id(state.game_id)
            if db_game:
                await repo.update_game_status(db_game, "finished")

            winners = await self._get_standings(state.game_id)
        lines = ["<b>🏆 ¡Partida finalizada!</b>", ""]
        for i, (pid, score) in enumerate(winners[:3]):
            medals = ["🥇", "🥈", "🥉"]
            name = state.player_names.get(pid, f"Jugador {pid}")
            lines.append(f"{medals[i] if i < 3 else i + 1}. {name} — {score} pts")
        lines.append("")
        lines.append("<i>Gracias por jugar 🛑 Stop!</i>")
        await bot.send_message(state.group_chat_id, "\n".join(lines))

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _check_all_submitted(self, state: RoundState, bot: Bot) -> None:
        if len(state.submitted_player_ids) >= state.total_players:
            # Pequeño delay para que llegue el último callback.answer()
            await asyncio.sleep(0.5)
            asyncio.create_task(
                self._close_round(state.game_id, "all_submitted", bot)
            )

    async def _send_stop_message(self, state: RoundState, bot: Bot) -> None:
        text = self._format_stop_message(0)
        stop_msg = await bot.send_message(
            state.first_completer_id,
            text,
            reply_markup=stop_keyboard(state.game_id, 1),
        )
        state.stop_message_chat_id = stop_msg.chat.id
        state.stop_message_id = stop_msg.message_id

        self._update_round_message(state, bot)

    def _update_round_message(self, state: RoundState, bot: Bot) -> None:
        asyncio.create_task(self._do_update_round_message(state, bot))

    async def _do_update_round_message(
        self, state: RoundState, bot: Bot
    ) -> None:
        lines = [self._format_round_message(state.round_number, state.letter)]

        if state.submitted_player_ids:
            lines.append("")
            lines.append("✅ <b>Respondieron:</b>")
            for pid in state.submitted_player_ids:
                name = state.player_names.get(pid, f"Jugador {pid}")
                completed = "⭐" if pid in state.complete_player_ids else "⬜"
                lines.append(f"  {completed} {name}")

        if state.first_completer_id:
            name = state.first_completer_name or "Alguien"
            lines.append("")
            lines.append(f"⏹ <b>{name} completó todas las categorías</b>")
            lines.append(
                f"  Stop: {state.stop_presses}/{NUM_STOP_BUTTONS}"
            )

        try:
            await bot.edit_message_text(
                "\n".join(lines),
                chat_id=state.message_chat_id,
                message_id=state.message_id,
            )
        except TelegramBadRequest:
            pass

    async def _build_summary(
        self, game_id: int, state: RoundState
    ) -> str:
        async with async_session_factory() as session:
            repo = RoundRepository(session)
            db_round = await repo.get_active_round(game_id)
            if db_round:
                await repo.update_status(db_round.id, "scored")
            all_rounds_answers = await repo.get_answers_by_player(
                db_round.id if db_round else 0
            )

        lines = [
            f"<b>📊 Ronda {state.round_number} — Resumen</b>",
            f"  Letra: <b>{state.letter}</b>",
            "",
        ]

        scores = {}
        for pid, answers in all_rounds_answers.items():
            filled = sum(1 for a in answers if a.raw_text.strip())
            scores[pid] = filled

        for pid, score in sorted(
            scores.items(), key=lambda x: x[1], reverse=True
        ):
            name = state.player_names.get(
                pid, f"Jugador {pid}"
            )
            total = len(state.categories)
            lines.append(
                f"  {name}: {score}/{total} categorías"
            )

        if state.first_completer_name:
            lines.append("")
            lines.append(
                f"⭐ <b>{state.first_completer_name}</b> fue el primero "
                f"en completar todas las categorías."
            )

        return "\n".join(lines)

    async def _get_leader_telegram_id(self, game_id: int) -> Optional[int]:
        async with async_session_factory() as session:
            stmt = (
                select(GamePlayer, Player)
                .join(Player, GamePlayer.player_id == Player.id)
                .where(GamePlayer.game_id == game_id)
                .order_by(GamePlayer.score.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.one_or_none()
            if row:
                return row.Player.telegram_id
            return None

    async def _get_standings(
        self, game_id: int
    ) -> list[tuple[int, int]]:
        async with async_session_factory() as session:
            stmt = (
                select(GamePlayer, Player)
                .join(Player, GamePlayer.player_id == Player.id)
                .where(GamePlayer.game_id == game_id)
                .order_by(GamePlayer.score.desc())
            )
            rows = await session.execute(stmt)
            return [(row.Player.telegram_id, row.GamePlayer.score) for row in rows]

    # ── Timer ───────────────────────────────────────────────────────────────

    async def _round_timer(self, state: RoundState, bot: Bot) -> None:
        try:
            await asyncio.sleep(ROUND_DURATION)
            await self._close_round(state.game_id, "timeout", bot)
        except asyncio.CancelledError:
            pass

    # ── Formateo de mensajes ────────────────────────────────────────────────

    @staticmethod
    def _format_round_message(round_number: int, letter: str) -> str:
        return (
            f"🛑 <b>Ronda {round_number} — Letra: {letter}</b>\n"
            f"⏱ {ROUND_DURATION} segundos\n\n"
            f"Envía tus respuestas en este formato:\n\n"
            f"{CATEGORIES_DISPLAY}"
        )

    @staticmethod
    def _format_stop_message(presses: int) -> str:
        return (
            "⏹ <b>¡Has completado todas las categorías!</b>\n\n"
            "Presiona <b>Stop</b> repetidamente para cerrar la ronda.\n"
            f"Progreso: {presses}/{NUM_STOP_BUTTONS}\n\n"
            "<i>Si todos los jugadores responden, la ronda se cerrará "
            "automáticamente.</i>"
        )


# ── Answer Parser ───────────────────────────────────────────────────────────

ANSWER_REGEX = re.compile(r"^\s*(.+?)\s*:\s*(.*?)\s*$", re.MULTILINE)


def parse_answers(text: str, categories: list[str]) -> dict[str, str]:
    """Extrae pares categoría:valor del texto del jugador.
    Retorna dict con las categorías que coincidieron exactamente.
    """
    cat_map = {cat.lower(): cat for cat in categories}
    result = {}

    for match in ANSWER_REGEX.finditer(text):
        raw_cat = match.group(1).strip().lower()
        value = match.group(2).strip()
        if raw_cat in cat_map:
            result[cat_map[raw_cat]] = value

    return result


# Singleton
round_manager = RoundManager()
```

---

### 4. `backend/src/handlers/game/round.py`

```python
import asyncio
import re

from aiogram import Bot, Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from src.db.models import Player
from src.services.game_orchestrator import lobby_manager
from src.services.round_manager import round_manager, parse_answers, CATEGORIES, ALPHABET, ROUND_DURATION

round_router = Router()


# ── Recepción de respuestas ─────────────────────────────────────────────────


@round_router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_round_answer(message: Message, player: Player, bot: Bot) -> None:
    game_id = _find_active_game_id(message.chat.id)
    if not game_id:
        return

    state = round_manager.get_active_round(game_id)
    if not state:
        return

    parsed = parse_answers(message.text, state.categories)
    if not parsed:
        return

    is_first = await round_manager.submit_answers(
        game_id=game_id,
        player=player,
        text=message.text,
        bot=bot,
    )

    name = player.first_name or player.username or f"ID{player.telegram_id}"
    filled = len(parsed)
    total = len(state.categories)

    reply = await message.reply(
        f"✅ <b>{name}</b>, recibimos {filled}/{total} categorías."
    )
    asyncio.create_task(_delete_after(reply))


# ── Sistema Stop (DM) ──────────────────────────────────────────────────────


@round_router.callback_query(F.data.startswith("stop:"))
async def callback_stop(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    _, game_id_str, stop_str = callback.data.split(":")
    game_id = int(game_id_str)

    await round_manager.press_stop(
        game_id=game_id,
        player_id=player.telegram_id,
        callback=callback,
        bot=bot,
    )


# ── Selección de letra (líder) ──────────────────────────────────────────────


@round_router.callback_query(F.data.startswith("letter:"))
async def callback_letter(callback: CallbackQuery, player: Player, bot: Bot) -> None:
    _, game_id_str, letter = callback.data.split(":")
    game_id = int(game_id_str)

    if letter not in ALPHABET:
        await callback.answer("❌ Letra inválida.", show_alert=True)
        return

    await round_manager.handle_letter_selection(
        game_id=game_id,
        player_id=player.telegram_id,
        letter=letter,
        callback=callback,
        bot=bot,
    )


# ── Helpers ─────────────────────────────────────────────────────────────────


def _find_active_game_id(group_chat_id: int) -> Optional[int]:
    """Busca un juego activo en el grupo. Helper temporario hasta
    que tengamos un GameService central."""
    from src.db.engine import async_session_factory
    from src.db.repositories.game_repository import GameRepository
    import asyncio

    async def _inner():
        async with async_session_factory() as session:
            repo = GameRepository(session)
            game = await repo.get_active_game(group_chat_id)
            return game.id if game else None

    # Necesitamos un loop corriendo
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(_inner())
    except RuntimeError:
        return None


async def _delete_after(message: Message, delay: int = 5) -> None:
    """Elimina un mensaje tras N segundos (copia local de delete_after)."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass
```

Wait, `_find_active_game_id` is problematic because it tries to use `run_until_complete` in an async context. Let me redesign this. Instead, I'll store the game_id in the message handler by checking the lobby_manager or making it async properly.

Actually, the simplest approach: make the handler async and use `await` directly:

```python
@round_router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_round_answer(message: Message, player: Player, bot: Bot) -> None:
    game_id = await _find_active_game_id(message.chat.id)
    ...
```

And `_find_active_game_id` becomes an async function.

Let me fix this.

Also, I realize there's a potential issue: the message handler will catch ALL text messages in groups, including `/stop`, `/cancel`, etc. The aiogram router system should handle this because command handlers are registered before the text handler. But to be safe, I should add a filter to skip commands.

Let me add `F.text.regexp(r'^[^/]')` or similar to skip commands.

Actually, the simplest approach: use low priority or check if the message text starts with `/`.

Let me add:
```python
@round_router.message(F.text, ~F.text.startswith("/"), F.chat.type.in_({"group", "supergroup"}))
```

But `F.text.startswith("/")` might not work as intended with aiogram magic filters. Let me just check in the handler body:

```python
async def handle_round_answer(message: Message, player: Player, bot: Bot) -> None:
    if message.text.startswith("/"):
        return
    ...
```

OK, let me rewrite the round.py handler more carefully.

Also, I realize `_find_active_game_id` doing a DB query on every message is wasteful. But since we only process messages when there's an active round AND they parse as valid answers, the DB query only happens when there's a state in memory. Let me optimize: check the in-memory state first, then query DB.

Actually, I can simplify: the handler only proceeds if there's an active round in memory AND the text parses. The DB query is only needed to save answers. So I don't need to look up game_id from DB - I already have it from the RoundState.

Let me restructure:

```python
@round_router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_round_answer(message: Message, player: Player, bot: Bot) -> None:
    if message.text.startswith("/"):
        return

    # Fast path: check if there's an active round for any game in this group
    # We need a way to map group_chat_id -> game_id for active rounds
    ...
```

Hmm, but RoundManager indexes by game_id, not group_chat_id. I need to find which game is active for this group.

Option 1: Add a mapping from group_chat_id to game_id in LobbyManager or RoundManager.
Option 2: Query the DB each time (expensive but simple).
Option 3: Store the mapping in RoundManager.

Let me add a helper to RoundManager:

```python
class RoundManager:
    def __init__(self):
        self._rounds: dict[int, RoundState] = {}
    
    def get_active_game_id(self, group_chat_id: int) -> Optional[int]:
        for game_id, state in self._rounds.items():
            if state.group_chat_id == group_chat_id:
                return game_id
        return None
```

This is O(n) where n = number of active games, which is usually 0 or 1. Good enough.

Let me add this to RoundManager and use it in the handler.

OK let me rewrite the complete round.py with all fixes.

Actually, I realize I'm overcomplicating this. Let me simplify the handler:

```python
@round_router.message(F.text, F.chat.type.in_({"group", "supergroup"}))
async def handle_round_answer(message: Message, player: Player, bot: Bot) -> None:
    if message.text.startswith("/"):
        return

    # Buscar si hay ronda activa en este grupo
    state = round_manager.get_active_round_by_group(message.chat.id)
    if not state:
        return

    parsed = parse_answers(message.text, state.categories)
    if not parsed:
        return

    ...
```

And add `get_active_round_by_group` to RoundManager.

Let me rewrite round_manager.py with this addition and finalize all the code. I'll produce the complete, clean version now.

Let me also handle a key edge case: the `submit_answers` method stores answers per player, but players might send multiple messages. Each new message replaces the previous answers for that round.

Let me finalize everything now and write the complete guide file.<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="read">
<｜｜DSML｜｜parameter name="filePath" string="true">C:\Users\Tony\Documents\bots\stop-bot-game\definitions.md