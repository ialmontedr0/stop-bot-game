# Fase 3 — Motor de puntuación (Score Engine)

**Objetivo:** Evaluar respuestas, calcular puntos con reglas reales de Stop, detectar duplicados, persistir puntuaciones y finalizar partidas correctamente.

---

## Arquitectura

### Flujo de puntuación por ronda

```
_close_round()
  └─ _persist_round_scores()                    # nuevo, reemplaza versión anterior
       ├─ get_answers_by_player(round_id)       # RoundRepository
       ├─ ScoreEngine.evaluate()                # 50 pts única, 50/N compartida, +10 bonus
       ├─ update Answer.score, Answer.is_correct
       ├─ update GamePlayer.score (acumulado)
       └─ commit

_build_summary()
  └─ ScoreEngine.evaluate()                     # mismo cálculo, solo para mostrar
```

### Flujo de fin de partida

```
_end_game()
  ├─ update Game.status = "finished"
  ├─ set Game.finished_at = now
  ├─ calcular ganador desde GamePlayer.score
  └─ enviar podio 🥇 🥈 🥉
```

---

## Cambios respecto a Fase 2

| Aspecto | Fase 2 (actual) | Fase 3 (nuevo) |
|---------|-----------------|----------------|
| Puntos único | 10 | 50 |
| Puntos compartido | 5 | 50 / N (truncado a entero) |
| Bonus 1er completo | 5 | 10 |
| Método principal | `calculate()` | `evaluate()` |
| Validación respuesta | solo no-vacía | alfabética + espacios + guiones |
| Persistencia Answer | no | sí (score, is_correct) |
| Persistencia GamePlayer | sí (pero bug) | sí (corregido) |
| Fin de partida | básico | finished_at + podio completo |

### Bug corregido: inconsistencia telegram_id vs player.id

`get_answers_by_player()` en `RoundRepository` usa `a.player.telegram_id` como clave del dict, pero `_persist_round_scores` buscaba `GamePlayer.player_id` (que es `Player.id`). Esto impedía que las puntuaciones se persistieran realmente.

La corrección: `_persist_round_scores` ahora hace JOIN con `Player` para traducir `telegram_id` → `player.id`.

---

## Archivos a modificar

| Archivo | Acción |
|---------|--------|
| `src/services/score_engine.py` | **REESCRIBIR** completo |
| `src/db/repositories/round_repository.py` | +2 métodos: `update_answer_scores`, `get_game_player_by_telegram` |
| `src/services/round_manager.py` | modificar `_persist_round_scores`, `_build_summary`, `_end_game` |
| `tests/test_score_engine.py` | **NUEVO** — tests completos del motor |
| `tests/test_round_manager.py` | actualizar tests existentes |

---

## 1. `src/services/score_engine.py` (REESCRIBIR COMPLETO)

```python
import logging
import re
import unicodedata
from collections import defaultdict
from typing import Optional

from src.db.models import Answer

logger = logging.getLogger(__name__)

UNIQUE_POINTS = 50
FIRST_COMPLETER_BONUS = 10


def _normalize(text: str) -> str:
    """Normaliza: lowercase, sin tildes, solo alfanumérico."""
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


def _is_valid_word(text: str) -> bool:
    """Criterio de respuesta correcta (Fase 3):
    - No vacía
    - Solo letras (incluyendo acentos), espacios y guiones
    - Al menos 2 caracteres alfabéticos
    """
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if len(stripped) < 1:
        return False
    # Permitir letras (incluyendo acentos/ñ), espacios, guiones, apóstrofes
    if not re.match(r"^[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ\s\-']+$", stripped):
        return False
    return True


def _group_by_category(
    answers_by_player: dict[int, list[Answer]],
) -> dict[str, list[tuple[int, Answer]]]:
    """Agrupa respuestas por categoría (word_slot)."""
    categories: dict[str, list[tuple[int, Answer]]] = {}
    for pid, answers in answers_by_player.items():
        for answer in answers:
            slot = answer.word_slot
            if slot not in categories:
                categories[slot] = []
            categories[slot].append((pid, answer))
    return categories


def _determine_answer_scores(
    player_answers: list[tuple[int, Answer]],
) -> dict[int, tuple[bool, int]]:
    """Determina por jugador si su respuesta es única y cuánto vale.

    Returns:
        dict[player_telegram_id, (is_unique, score)]
        - is_unique: True si la respuesta normalizada es única en esta categoría
        - score: puntos que recibe (50 si única, 50/N si compartida, 0 si inválida)
    """
    norm_map: dict[str, list[int]] = {}
    answer_map: dict[int, Answer] = {}

    for pid, answer in player_answers:
        answer_map[pid] = answer
        txt = answer.raw_text.strip()
        if not txt or not _is_valid_word(txt):
            continue
        norm = _normalize(txt)
        if norm:
            norm_map.setdefault(norm, []).append(pid)

    result: dict[int, tuple[bool, int]] = {}
    unique_players: set[int] = set()
    shared_groups: dict[int, int] = {}  # pid -> group size

    for norm, pids in norm_map.items():
        if len(pids) == 1:
            unique_players.add(pids[0])
        else:
            share = UNIQUE_POINTS // len(pids)
            for p in pids:
                shared_groups[p] = share

    all_pids = {pid for pid, _ in player_answers}
    for pid in all_pids:
        if pid in unique_players and pid not in shared_groups:
            result[pid] = (True, UNIQUE_POINTS)
        elif pid in shared_groups:
            result[pid] = (False, shared_groups[pid])
        else:
            result[pid] = (False, 0)

    return result


class ScoreEngine:
    """Motor de puntuación para Stop Bot.

    Puntos por categoría:
      - Única (solo 1 jugador dio esa respuesta normalizada): 50 pts
      - Compartida (N jugadores dieron la misma respuesta): 50 / N pts (entero)
      - Vacía o inválida: 0 pts

    Bonus:
      - Primer jugador en completar todas las categorías: +10 pts
    """

    def evaluate(
        self,
        answers_by_player: dict[int, list[Answer]],
        num_categories: int,
        first_completer_id: Optional[int] = None,
    ) -> dict[int, tuple[int, list[dict]]]:
        """Evalúa todas las respuestas de una ronda.

        Args:
            answers_by_player: dict[player_telegram_id, list[Answer]]
            num_categories: número total de categorías en la ronda
            first_completer_id: telegram_id del primer jugador en completar (opcional)

        Returns:
            dict[player_telegram_id, (total_score, per_answer_details)]
            donde per_answer_details es lista de dicts con:
              - answer_id: int
              - word_slot: str
              - raw_text: str
              - is_correct: bool
              - score: int
        """
        totals: dict[int, int] = defaultdict(int)
        details: dict[int, list[dict]] = defaultdict(list)

        if not answers_by_player:
            return dict(totals)

        categories = _group_by_category(answers_by_player)

        for canonical_cat, player_answers in categories.items():
            answer_scores = _determine_answer_scores(player_answers)
            for pid, (is_unique, cat_score) in answer_scores.items():
                totals[pid] += cat_score
                # Buscar el Answer original para este pid en esta categoría
                for p_id, ans in player_answers:
                    if p_id == pid:
                        details[pid].append({
                            "answer_id": ans.id,
                            "word_slot": canonical_cat,
                            "raw_text": ans.raw_text,
                            "is_correct": cat_score > 0,
                            "score": cat_score,
                        })
                        break

        # Asegurar que todos los jugadores aparezcan, incluso con 0 pts
        for pid in answers_by_player:
            if pid not in totals:
                totals[pid] = 0
                details[pid] = [
                    {
                        "answer_id": ans.id,
                        "word_slot": ans.word_slot,
                        "raw_text": ans.raw_text,
                        "is_correct": False,
                        "score": 0,
                    }
                    for ans in answers_by_player[pid]
                ]

        # Bonus de velocidad
        if first_completer_id is not None and first_completer_id in totals:
            totals[first_completer_id] += FIRST_COMPLETER_BONUS

        return dict(totals), dict(details)

    @staticmethod
    def apply_bonus(
        player_id: int,
        scores: dict[int, int],
    ) -> int:
        """Aplica el bonus de velocidad a un jugador específico.
        Devuelve los puntos extra sumados (0 si no aplica).
        Usado externamente si se necesita el bonus fuera de evaluate().
        """
        if player_id in scores:
            scores[player_id] += FIRST_COMPLETER_BONUS
            return FIRST_COMPLETER_BONUS
        return 0

    @staticmethod
    def is_answer_valid(raw_text: str) -> bool:
        """Verifica si una respuesta individual es válida (correcta)."""
        return _is_valid_word(raw_text)
```

**Puntos clave:**
- `evaluate()` ahora retorna `tuple[dict, dict]`: (totales, detalles por respuesta)
- Los detalles permiten persistir `Answer.score` y `Answer.is_correct`
- `_is_valid_word()` rechaza respuestas con números, símbolos, o vacías
- `_determine_answer_scores()` calcula 50/N para respuestas compartidas
- `apply_bonus()` existe como método público independiente
- Funciones auxiliares son module-level para testabilidad

---

## 2. `src/db/repositories/round_repository.py` — métodos nuevos

Agregar al final de la clase `RoundRepository`:

```python
async def update_answer_scores(
    self,
    answer_scores: list[tuple[int, bool, int]],  # (answer_id, is_correct, score)
) -> None:
    """Actualiza score e is_correct para una lista de Answers."""
    for answer_id, is_correct, score in answer_scores:
        ans = await self.session.get(Answer, answer_id)
        if ans:
            ans.is_correct = is_correct
            ans.score = score
    await self.session.flush()


async def get_game_player_by_telegram(
    self,
    game_id: int,
    telegram_id: int,
) -> Optional[GamePlayer]:
    """Busca un GamePlayer por game_id + telegram_id del Player."""
    from sqlalchemy.orm import joinedload
    stmt = (
        select(GamePlayer)
        .join(Player, GamePlayer.player_id == Player.id)
        .where(
            GamePlayer.game_id == game_id,
            Player.telegram_id == telegram_id,
        )
    )
    result = await self.session.execute(stmt)
    return result.scalar_one_or_none()
```

Además, importar `Player` al inicio del archivo (ya está importado `GamePlayer`):

```python
from src.db.models import Answer, GamePlayer, Player, Round
```

---

## 3. `src/services/round_manager.py` — cambios

### 3a. `_persist_round_scores` — reescribir

Reemplazar el método actual:

```python
async def _persist_round_scores(
    self,
    round_id: int,
    state: RoundState,
) -> None:
    async with async_session_factory() as session:
        repo = RoundRepository(session)
        answers_by_player = await repo.get_answers_by_player(round_id)

        engine = ScoreEngine()
        totals, details = engine.evaluate(
            answers_by_player,
            len(state.categories),
            first_completer_id=state.first_completer_id,
        )

        # Persistir Answer.score y Answer.is_correct
        for pid, answer_list in details.items():
            answer_updates = []
            for ad in answer_list:
                answer_updates.append((
                    ad["answer_id"],
                    ad["is_correct"],
                    ad["score"],
                ))
            if answer_updates:
                await repo.update_answer_scores(answer_updates)

        # Persistir GamePlayer.score (acumulado)
        for telegram_id, round_score in totals.items():
            gp = await repo.get_game_player_by_telegram(state.game_id, telegram_id)
            if gp:
                gp.score = (gp.score or 0) + round_score

        await session.commit()
```

### 3b. `_build_summary` — actualizar

Cambiar el llamado a `engine.calculate()` por `engine.evaluate()`:

```python
async def _build_summary(
    self, round_id: Optional[int], state: RoundState
) -> str:
    if round_id is None:
        return (
            f"<b>📊 Ronda {state.round_number} — Resumen</b>\n"
            f"No se pudieron recuperar las respuestas."
        )

    async with async_session_factory() as session:
        repo = RoundRepository(session)
        all_rounds_answers = await repo.get_answers_by_player(round_id)

        engine = ScoreEngine()
        scores, _ = engine.evaluate(
            all_rounds_answers,
            len(state.categories),
            first_completer_id=state.first_completer_id,
        )

    lines = [
        f"<b>📊 Ronda {state.round_number} — Resumen</b>",
        f"  Letra: <b>{state.letter}</b>",
        "",
    ]

    for pid, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        name = state.player_names.get(pid, f"Jugador {pid}")
        lines.append(f"  {name}: {score} pts")

    if state.first_completer_name:
        lines.append("")
        lines.append(
            f"⭐ <b>{state.first_completer_name}</b> fue el primero "
            f"en completar todas las categorías."
        )

    # Mostrar bonus si aplica
    if state.first_completer_name and (
        state.stop_presses >= NUM_STOP_BUTTONS
        or state.first_completer_id
    ):
        lines.append(
            f"  🏎️ Bonus velocidad: +{FIRST_COMPLETER_BONUS} pts"
        )

    return "\n".join(lines)
```

(Añadir `FIRST_COMPLETER_BONUS` a los imports:)
```python
from src.services.score_engine import ScoreEngine, FIRST_COMPLETER_BONUS
```

### 3c. `_end_game` — mejorar con `finished_at`

```python
async def _end_game(self, state: RoundState, bot: Bot) -> None:
    async with async_session_factory() as session:
        repo = GameRepository(session)
        db_game = await repo.get_by_id(state.game_id)
        if db_game:
            db_game.status = "finished"
            db_game.finished_at = datetime.utcnow()
            await session.commit()

        winners = await self._get_standings(state.game_id)

    lines = ["<b>🏆 ¡Partida finalizada!</b>", ""]
    if winners:
        for i, (pid, score) in enumerate(winners[:3]):
            medals = ["🥇", "🥈", "🥉"]
            name = state.player_names.get(pid, f"Jugador {pid}")
            lines.append(f"{medals[i] if i < 3 else i + 1}. {name} — {score} pts")
    else:
        lines.append("  No hay puntuaciones registradas.")
    lines.append("")
    lines.append("<i>Gracias por jugar 🛑 Stop!</i>")
    await bot.send_message(state.group_chat_id, "\n".join(lines))
    self._letter_pending.pop(state.game_id, None)
    self._rounds_by_group.pop(state.group_chat_id, None)
```

Agregar `from datetime import datetime` al inicio del archivo si no existe.

### 3d. Actualizar import de ScoreEngine

Verificar que el import en `round_manager.py` sea:

```python
from src.services.score_engine import ScoreEngine, FIRST_COMPLETER_BONUS
```

---

## 4. `tests/test_score_engine.py` — NUEVO

```python
import pytest

from src.db.models import Answer
from src.services.score_engine import (
    ScoreEngine,
    _normalize,
    _is_valid_word,
    _group_by_category,
    _determine_answer_scores,
    UNIQUE_POINTS,
    FIRST_COMPLETER_BONUS,
)


def make_answer(
    answer_id: int,
    word_slot: str,
    raw_text: str,
    player_id: int = 1,
) -> Answer:
    ans = Answer(
        id=answer_id,
        round_id=1,
        player_id=player_id,
        game_player_id=player_id,
        word_slot=word_slot,
        raw_text=raw_text,
    )
    ans.id = answer_id
    return ans


# ── _normalize ───────────────────────────────────────────────────────


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("HOLA") == "hola"

    def test_remove_accents(self):
        assert _normalize("Canción") == "cancion"

    def test_remove_non_alphanumeric(self):
        assert _normalize("¡Hola, mundo!") == "holamundo"

    def test_strip_spaces(self):
        assert _normalize("  Perro  ") == "perro"

    def test_handle_n(self):
        assert _normalize("Muñoz") == "munoz"

    def test_empty_string(self):
        assert _normalize("") == ""


# ── _is_valid_word ───────────────────────────────────────────────────


class TestIsValidWord:
    def test_valid_word(self):
        assert _is_valid_word("Fernando") is True

    def test_valid_with_spaces(self):
        assert _is_valid_word("Buenos Aires") is True

    def test_valid_with_hyphen(self):
        assert _is_valid_word("María-José") is True

    def test_valid_with_accents(self):
        assert _is_valid_word("Canción") is True

    def test_valid_with_n(self):
        assert _is_valid_word("Muñoz") is True

    def test_valid_with_apostrophe(self):
        assert _is_valid_word("O'Brien") is True

    def test_invalid_with_numbers(self):
        assert _is_valid_word("Juan123") is False

    def test_invalid_with_symbols(self):
        assert _is_valid_word("Hola!!!") is False

    def test_invalid_empty(self):
        assert _is_valid_word("") is False

    def test_invalid_whitespace_only(self):
        assert _is_valid_word("   ") is False

    def test_invalid_single_char(self):
        assert _is_valid_word("A") is True  # una letra es válida


# ── _group_by_category ──────────────────────────────────────────────


class TestGroupByCategory:
    def test_groups_by_word_slot(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Color", "Rojo", 1)
        a3 = make_answer(3, "Nombre", "María", 2)
        grouped = _group_by_category({111: [a1, a2], 222: [a3]})
        assert "Nombre" in grouped
        assert "Color" in grouped
        assert len(grouped["Nombre"]) == 2
        assert len(grouped["Color"]) == 1


# ── _determine_answer_scores ────────────────────────────────────────


class TestDetermineAnswerScores:
    def test_unique_answer_gets_50(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        result = _determine_answer_scores([(111, a1)])
        assert result[111] == (True, UNIQUE_POINTS)

    def test_shared_answer_splits_50(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Nombre", "Juan", 2)
        result = _determine_answer_scores([(111, a1), (222, a2)])
        # 50 / 2 = 25
        assert result[111] == (False, 25)
        assert result[222] == (False, 25)

    def test_shared_among_three(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Nombre", "Juan", 2)
        a3 = make_answer(3, "Nombre", "Juan", 3)
        result = _determine_answer_scores([(111, a1), (222, a2), (333, a3)])
        # 50 / 3 = 16 (truncado a entero)
        assert result[111] == (False, 16)
        assert result[222] == (False, 16)
        assert result[333] == (False, 16)

    def test_empty_answer_gets_0(self):
        a1 = make_answer(1, "Nombre", "", 1)
        result = _determine_answer_scores([(111, a1)])
        assert result[111] == (False, 0)

    def test_invalid_answer_gets_0(self):
        a1 = make_answer(1, "Nombre", "123!!!", 1)
        result = _determine_answer_scores([(111, a1)])
        assert result[111] == (False, 0)

    def test_mixed_unique_and_shared(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Nombre", "Pedro", 2)
        a3 = make_answer(3, "Nombre", "Pedro", 3)
        result = _determine_answer_scores([(111, a1), (222, a2), (333, a3)])
        assert result[111] == (True, 50)    # único
        assert result[222] == (False, 25)   # compartido con 333
        assert result[333] == (False, 25)   # compartido con 222

    def test_case_insensitive_matching(self):
        a1 = make_answer(1, "Nombre", "Juan", 1)
        a2 = make_answer(2, "Nombre", "juan", 2)  # mismo normalizado
        result = _determine_answer_scores([(111, a1), (222, a2)])
        assert result[111] == (False, 25)
        assert result[222] == (False, 25)

    def test_accent_insensitive_matching(self):
        a1 = make_answer(1, "Nombre", "Canción", 1)
        a2 = make_answer(2, "Nombre", "cancion", 2)
        result = _determine_answer_scores([(111, a1), (222, a2)])
        assert result[111] == (False, 25)
        assert result[222] == (False, 25)


# ── ScoreEngine.evaluate ────────────────────────────────────────────


class TestScoreEngineEvaluate:
    def test_empty_answers(self):
        engine = ScoreEngine()
        totals, details = engine.evaluate({}, 8)
        assert totals == {}
        assert details == {}

    def test_single_player_all_unique(self):
        engine = ScoreEngine()
        answers = {
            111: [
                make_answer(1, "Nombre", "Juan"),
                make_answer(2, "Color", "Rojo"),
                make_answer(3, "Fruta", "Manzana"),
            ],
        }
        totals, details = engine.evaluate(answers, 3)
        assert totals[111] == UNIQUE_POINTS * 3  # 150
        assert len(details[111]) == 3
        assert all(d["is_correct"] is True for d in details[111])
        assert all(d["score"] == UNIQUE_POINTS for d in details[111])

    def test_two_players_all_shared(self):
        engine = ScoreEngine()
        answers = {
            111: [
                make_answer(1, "Nombre", "Juan"),
                make_answer(2, "Color", "Rojo"),
            ],
            222: [
                make_answer(3, "Nombre", "Juan"),
                make_answer(4, "Color", "Rojo"),
            ],
        }
        totals, details = engine.evaluate(answers, 2)
        # Cada jugador: 25 + 25 = 50
        assert totals[111] == 50
        assert totals[222] == 50

    def test_first_completer_bonus(self):
        engine = ScoreEngine()
        answers = {
            111: [make_answer(1, "Nombre", "Juan")],
            222: [make_answer(2, "Nombre", "Pedro")],
        }
        totals, details = engine.evaluate(answers, 1, first_completer_id=111)
        assert totals[111] == UNIQUE_POINTS + FIRST_COMPLETER_BONUS  # 60
        assert totals[222] == UNIQUE_POINTS  # 50

    def test_bonus_only_if_player_in_scores(self):
        engine = ScoreEngine()
        answers = {
            111: [make_answer(1, "Nombre", "Juan")],
        }
        totals, details = engine.evaluate(answers, 1, first_completer_id=999)
        assert totals[111] == UNIQUE_POINTS  # 50, bonus no aplica porque 999 no está

    def test_complex_scenario(self):
        """3 jugadores, 3 categorías, mezcla de único/compartido/vacío."""
        engine = ScoreEngine()
        answers = {
            111: [
                make_answer(1, "Nombre", "Juan"),
                make_answer(2, "Color", "Rojo"),
                make_answer(3, "Fruta", "Manzana"),
            ],
            222: [
                make_answer(4, "Nombre", "María"),
                make_answer(5, "Color", "Rojo"),
                make_answer(6, "Fruta", "Pera"),
            ],
            333: [
                make_answer(7, "Nombre", "Juan"),
                make_answer(8, "Color", ""),
                make_answer(9, "Fruta", "Manzana"),
            ],
        }
        totals, details = engine.evaluate(answers, 3, first_completer_id=111)

        # Nombre: 111 y 333 comparten "Juan" → 25 c/u, 222 único "María" → 50
        # Color: 111 y 222 comparten "Rojo" → 25 c/u, 333 vacío → 0
        # Fruta: 111 y 333 comparten "Manzana" → 25 c/u, 222 único "Pera" → 50
        esperado_111 = 25 + 25 + 25 + FIRST_COMPLETER_BONUS  # 100
        esperado_222 = 50 + 25 + 50  # 125
        esperado_333 = 25 + 0 + 25  # 50

        assert totals[111] == esperado_111
        assert totals[222] == esperado_222
        assert totals[333] == esperado_333

        # Verificar detalles
        assert details[333][1]["is_correct"] is False  # Color vacío
        assert details[333][1]["score"] == 0

    def test_per_answer_details_shape(self):
        engine = ScoreEngine()
        answers = {
            111: [make_answer(42, "Nombre", "Juan")],
        }
        totals, details = engine.evaluate(answers, 1)
        entry = details[111][0]
        assert "answer_id" in entry
        assert "word_slot" in entry
        assert "raw_text" in entry
        assert "is_correct" in entry
        assert "score" in entry
        assert entry["answer_id"] == 42
        assert entry["word_slot"] == "Nombre"
        assert entry["raw_text"] == "Juan"


# ── ScoreEngine.apply_bonus ─────────────────────────────────────────


class TestApplyBonus:
    def test_apply_bonus_adds_points(self):
        scores = {111: 100, 222: 50}
        result = ScoreEngine.apply_bonus(111, scores)
        assert result == FIRST_COMPLETER_BONUS
        assert scores[111] == 100 + FIRST_COMPLETER_BONUS

    def test_apply_bonus_unknown_player(self):
        scores = {111: 100}
        result = ScoreEngine.apply_bonus(999, scores)
        assert result == 0
        assert scores[111] == 100


# ── ScoreEngine.is_answer_valid ─────────────────────────────────────


class TestIsAnswerValid:
    def test_valid(self):
        assert ScoreEngine.is_answer_valid("Buenos Aires") is True

    def test_invalid_with_numbers(self):
        assert ScoreEngine.is_answer_valid("Perro123") is False

    def test_invalid_empty(self):
        assert ScoreEngine.is_answer_valid("") is False
```

---

## 5. Tests actualizados para `test_round_manager.py`

### 5a. Actualizar `TestCloseRound`

En `test_close_round_removes_state` y `test_close_round_cancels_timer`, el mock de `get_answers_by_player` ahora debe devolver un dict con estructura correcta y debe mockear `get_game_player_by_telegram`:

```python
class TestCloseRound:
    @pytest.mark.asyncio
    async def test_close_round_removes_state(self, fresh_round_manager):
        import sys
        rm_mod = sys.modules["src.services.round_manager"]

        bot = AsyncMock()
        msg = MagicMock()
        msg.chat.id = -100
        msg.message_id = 42
        bot.send_message.return_value = msg

        await fresh_round_manager.start_round(
            game_id=1, group_chat_id=-100, round_number=1, letter="A",
            total_players=1, player_names={111: "Alice"}, bot=bot,
        )

        state = fresh_round_manager.get_active_round(1)
        state.timer_task = None

        fresh_round_manager._transition_next_round = AsyncMock()

        mock_db_round = MagicMock()
        mock_db_round.id = 1

        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_active_round.return_value = mock_db_round
            mock_repo.get_answers_by_player = AsyncMock(return_value={})
            mock_repo.get_game_player_by_telegram = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            await fresh_round_manager._close_round(1, "stop", bot)

        assert fresh_round_manager.get_active_round(1) is None

    @pytest.mark.asyncio
    async def test_close_round_cancels_timer(self, fresh_round_manager):
        import sys
        rm_mod = sys.modules["src.services.round_manager"]

        bot = AsyncMock()
        msg = MagicMock()
        msg.chat.id = -100
        msg.message_id = 42
        bot.send_message.return_value = msg

        fresh_round_manager._get_leader_telegram_id = AsyncMock(return_value=None)
        fresh_round_manager._get_standings = AsyncMock(return_value=[])
        fresh_round_manager._start_next_round_with_random = AsyncMock()

        await fresh_round_manager.start_round(
            game_id=1, group_chat_id=-100, round_number=1, letter="A",
            total_players=1, player_names={111: "Alice"}, bot=bot,
        )

        state = fresh_round_manager.get_active_round(1)
        timer = state.timer_task

        mock_db_round = MagicMock()
        mock_db_round.id = 1

        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_active_round.return_value = mock_db_round
            mock_repo.get_answers_by_player = AsyncMock(return_value={})
            mock_repo.get_game_player_by_telegram = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            await fresh_round_manager._close_round(1, "stop", bot)

        try:
            await timer
        except asyncio.CancelledError:
            pass
        assert timer.cancelled()
```

### 5b. Actualizar constantes

```python
class TestRoundManagerConstants:
    def test_constants(self):
        assert NUM_STOP_BUTTONS == 10
        assert ROUND_DURATION == 60
        assert TOTAL_ROUNDS == 5
        assert len(ALPHABET) == 26
        assert "Ñ" not in ALPHABET
```

No necesita cambios — las constantes no se modifican en Fase 3.

---

## 6. Orden de implementación

Sigue este orden para minimizar conflictos:

```
1. score_engine.py        # Reescribir completo (no depende de nadie)
2. round_repository.py    # Agregar 2 métodos (depende de models)
3. round_manager.py       # Modificar 3 métodos (depende de score_engine + repo)
4. test_score_engine.py   # Nuevo archivo (depende de score_engine)
5. test_round_manager.py  # Actualizar mocks (depende de round_manager)
```

---

## 7. Verificación

Después de implementar todo, ejecutar:

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

Esperado: **all tests pass** (los 128 existentes + los nuevos de score_engine = ~165 tests).

Además, verificar manualmente con `pytest tests/test_score_engine.py -v --tb=long` para asegurar que los tests del motor de puntuación cubren todos los casos.

---

## 8. Resumen de cambios

| Archivo | Líneas aprox | Cambio |
|---------|-------------|--------|
| `score_engine.py` | ~150 | Reescribir: evaluate(), _is_valid_word, 50/50-N/10, detalles por answer |
| `round_repository.py` | +30 | 2 métodos nuevos: update_answer_scores, get_game_player_by_telegram |
| `round_manager.py` | ~20 | Modificar _persist_round_scores, _build_summary, _end_game |
| `test_score_engine.py` | ~280 | Nuevo: 30+ tests para normalización, validación, puntuación |
| `test_round_manager.py` | ~10 | Actualizar mocks en TestCloseRound |
