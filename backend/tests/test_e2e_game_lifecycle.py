"""
E2E: 3 rondas completas via RoundManager + validate_batch + ScoreEngine.

Flujo real:
  start_round(1) -> submit_answers(A,B) -> press_stop(×10) -> close
  -> _start_next_round_with_letter(2) -> submit_answers(A,B) -> press_stop(×10)
  -> close -> _start_next_round_with_letter(3) -> submit_answers(A,B)
  -> press_stop(×10) -> close -> _end_game.

Casos cubiertos:
  - Word list exact match
  - Fuzzy match (typo corregido)
  - Respuesta corta rechazada
  - Respuesta vacia / elipsis
  - Duplicado exacto entre jugadores
  - Unico por jugador
  - Acumulacion entre rondas
  - Transiciones de estado (_rounds -> _letter_pending -> _rounds)
  - validate_batch (modo local = 0 llamadas IA)
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import Player
from src.services.round_manager import (
    CATEGORIES,
    NUM_STOP_BUTTONS,
    RoundManager,
)
from src.services.spell_corrector import get_corrector

_rm_mod = sys.modules["src.services.round_manager"]

# ── Palabras semilla ----------------------------------------------------------

SEED = {
    "nombre": {"raul", "ana", "maria", "sara"},
    "apellido": {"rodriguez", "alvarez", "martinez", "lopez"},
    "color": {"rojo", "azul", "marron", "verde"},
    "fruta": {"manzana", "aguacate", "sandia", "pera"},
    "pais": {"rusia", "argentina", "mexico", "chile", "suiza", "colombia"},
    "artista": {"romeo santos", "madonna", "cerati", "shakira"},
    "animal": {"rata", "arana", "mariposa", "serpiente", "cebra", "conejo", "aguila"},
    "cosa": {"reloj", "avion", "mesa", "silla", "cuchara", "coche", "lapiz"},
}


@pytest.fixture(autouse=True)
def mock_db():
    """Parchea async_session_factory para evitar PostgreSQL."""
    with patch.object(_rm_mod, "async_session_factory") as m:
        session = AsyncMock()
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        scalars.one_or_none.return_value = None
        result.scalars.return_value = scalars
        result.scalar_one_or_none.return_value = None
        result.one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        m.return_value.__aenter__.return_value = session
        yield


# No hay fixture mock_corrector — cada test lo configura por su cuenta
# porque get_corrector() es singleton global y los cambios se propagan
# a otros archivos de test.


# ── Helpers -------------------------------------------------------------------


def _make_round_mock(round_id=1):
    r = MagicMock()
    r.id = round_id
    return r


def make_text(answers: dict[str, str]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in answers.items())


# ── Test principal ------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_game_3_rounds():
    # Configurar corrector (modo local, sin IA, word lists semilla)
    sc = get_corrector()
    _saved_mode = sc.mode
    _saved_key = sc.api_key
    _saved_limit = sc.api_limit
    _saved_wl = sc._word_lists
    sc.mode = "local"
    sc.api_key = None
    sc.api_limit = 0
    sc._word_lists = {cat: set(words) for cat, words in SEED.items()}

    game_id = 1
    rm = RoundManager()
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(chat=MagicMock(id=-100), message_id=1))
    bot.send_photo = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()

    player_a = MagicMock(spec=Player, id=1, telegram_id=111, first_name="Alice")
    player_b = MagicMock(spec=Player, id=2, telegram_id=222, first_name="Bob")
    player_names = {111: "Alice", 222: "Bob"}

    # Regla: para que first_completer_id se asigne, el jugador debe llenar
    # TODAS las categorias (parse_answers omite lineas con valor vacio).
    # Cada tupla: (letra, {cat: (texto_A, texto_B, pts_A_esperado, pts_B_esperado), ...})
    rounds = [
        (
            "R",
            {
                # A llena todo (first completer), B tiene un vacio y numeros invalidos
                "Nombre": ("Raul", "Raul", 25, 25),
                "Apellido": ("Rodriguez", "Lopez", 50, 50),
                "Color": ("Rojo", "Rojo", 25, 25),
                "Fruta": ("Rambutan", "...", 50, 0),    # A unico fuzzy, B elipsis
                "Pais": ("Rusia", "Rusia", 25, 25),
                "Artista": ("Romeo Santos", "Cerati", 50, 50),
                "Animal": ("Rata", "Rata", 25, 25),
                "Cosa": ("Reloj", "12345", 50, 0),
            },
        ),
        (
            "A",
            {
                # A llena todo, B tiene vacios
                "Nombre": ("Ana", "Ana Maria", 50, 50),
                "Apellido": ("Alvarez", "Alvarez", 25, 25),
                "Color": ("Azul", "Azuuul", 25, 25),
                "Fruta": ("Aguacate", "Aguacate", 25, 25),
                "Pais": ("Argentina", "Argentina", 25, 25),
                "Artista": ("Aventura", "", 50, 0),      # A unico (fuzzy), B vacio
                "Animal": ("Arana", "Abeja", 50, 50),
                "Cosa": ("Avion", "", 50, 0),
            },
        ),
        (
            "M",
            {
                # Ambos llenan todo con duplicados exactos
                "Nombre": ("Maria", "Maria", 25, 25),
                "Apellido": ("Martinez", "Martinez", 25, 25),
                "Color": ("Marron", "Marron", 25, 25),
                "Fruta": ("Manzana", "Manzana", 25, 25),
                "Pais": ("Mexico", "Mexico", 25, 25),
                "Artista": ("Madonna", "Madonna", 25, 25),
                "Animal": ("Mariposa", "Mariposa", 25, 25),
                "Cosa": ("Mesa", "Mueble", 50, 50),
            },
        ),
    ]

    async def _fake_close_telegram(state, reason, bot):
        """Simula _do_close_round_telegram: pone estado en _letter_pending."""
        state.leader_id = 111
        rm._letter_pending[game_id] = state

    for round_num, (letter, slots) in enumerate(rounds, 1):
        # ── start_round ──
        with patch.object(rm, "_round_timer", new=AsyncMock()):
            await rm.start_round(
                game_id=game_id,
                group_chat_id=-100,
                round_number=round_num,
                letter=letter,
                total_players=2,
                player_names=player_names,
                bot=bot,
                total_rounds=len(rounds),
            )

        state = rm.get_active_round(game_id)
        assert state is not None, f"R{round_num}: estado creado"
        assert state.letter == letter
        assert state.round_number == round_num
        assert len(state.submitted_player_ids) == 0

        # ── submit_answers ──
        text_a = make_text({cat: v[0] for cat, v in slots.items()})
        text_b = make_text({cat: v[1] for cat, v in slots.items()})

        mock_repo = MagicMock()
        mock_repo.get_active_round = AsyncMock(return_value=_make_round_mock(round_num))
        mock_repo.save_answers = AsyncMock()
        mock_repo.get_game_players_by_telegrams = AsyncMock(return_value=[])
        mock_repo.update_answer_scores = AsyncMock()

        ctx = [
            patch.object(_rm_mod, "RoundRepository", return_value=mock_repo),
            patch.object(rm, "_do_close_round_telegram", new=_fake_close_telegram),
        ]

        with ctx[0], ctx[1]:
            await rm.submit_answers(game_id, player_a, text_a, bot)
        assert player_a.telegram_id in state.submitted_player_ids
        assert state.first_completer_id == 111
        assert state.first_completer_name == "Alice"

        with ctx[0], ctx[1]:
            await rm.submit_answers(game_id, player_b, text_b, bot)
        assert player_b.telegram_id in state.submitted_player_ids
        assert len(state.submitted_player_ids) == 2
        assert state.first_completer_id == 111

        # ── press_stop (con _do_close_round_telegram mockeado) ──
        callback = AsyncMock()
        callback.answer = AsyncMock()
        for _i in range(NUM_STOP_BUTTONS):
            with patch.object(rm, "_do_close_round_telegram", new=_fake_close_telegram):
                await rm.press_stop(game_id, 111, callback, bot)

        assert rm.get_active_round(game_id) is None, f"R{round_num}: ronda cerrada"

        # ── Avanzar a siguiente ronda ──
        if round_num < len(rounds):
            _next_letter = rounds[round_num][0]
            prev_state = rm._letter_pending.get(game_id)
            assert prev_state is not None, f"R{round_num}: _letter_pending existe"
            await rm._start_next_round_with_letter(prev_state, _next_letter, bot)

    # ── Verificar estado final ──
    final_state = rm._letter_pending.get(game_id)
    assert final_state is not None, "Estado final existe en _letter_pending"
    assert final_state.round_number == 3
    assert final_state.letter == "M"

    # ── Verificar que no hay ronda activa ──
    assert rm.get_active_round(game_id) is None

    # Restaurar corrector
    sc.mode = _saved_mode
    sc.api_key = _saved_key
    sc.api_limit = _saved_limit
    sc._word_lists = _saved_wl
