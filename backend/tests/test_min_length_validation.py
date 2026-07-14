"""
TEST: Respuestas de 1 solo caracter (letra suelta) deben ser invalidas (0 pts).

Escenario real reportado:
  - Ronda letra R, jugador escribe "Nombre: R"
  - El bot valida "R" como correcto via IA y le asigna 50 pts
  - Ademas agrega "r" a la word list en BD como "learned"

Este test verifica que:
  1. _is_valid_word() rechaza textos de 1 caracter
  2. SpellCorrector.validate() rechaza textos de 1 caracter
  3. ScoreEngine.evaluate() asigna 0 pts a respuestas de 1 caracter
  4. No se contamina la word list con palabras de 1 caracter
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

from src.db.models import Answer
from src.services.score_engine import ScoreEngine, _is_valid_word
from src.services.spell_corrector import SpellCorrector

A_ID, B_ID = 111, 222


def ans(aid: int, slot: str, text: str, pid: int) -> Answer:
    return Answer(
        id=aid,
        round_id=1,
        player_id=pid,
        game_player_id=pid,
        word_slot=slot,
        raw_text=text,
        normalized_text=SpellCorrector.normalize(text) if text else "",
    )


SEED_LISTS = {
    "nombre": {"raul", "ana", "maria"},
    "color": {"rojo", "azul", "verde"},
    "animal": {"rata", "arana", "abeja"},
    "cosa": {"reloj", "avion", "mesa"},
}


class TestMinLengthValidation:

    @pytest.mark.asyncio
    async def test_is_valid_word_rechaza_1_caracter(self):
        casos = [
            ("R", "R", False),       # letra suelta
            ("r", "R", False),       # minuscula
            ("R", None, False),      # sin letra de ronda
            ("R.", "R", False),      # con punto (se trima en submit)
            ("R", "A", False),       # ni siquiera coincide con letra
            ("RR", "R", True),       # 2 caracteres valido
            ("Raul", "R", True),     # nombre completo valido
            ("Ro", "R", True),       # 2 caracteres valido
            ("", "R", False),        # vacio
            ("  ", "R", False),      # solo espacios
        ]
        for text, letter, expected in casos:
            got = _is_valid_word(text, letter=letter)
            assert got == expected, f"_is_valid_word({text!r}, letter={letter!r}) = {got}, esperado {expected}"

    @pytest.mark.asyncio
    async def test_validate_rechaza_1_caracter(self):
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75)
        sc._word_lists = {k: set(v) for k, v in SEED_LISTS.items()}
        sc.api_limit = 200

        ctx = patch.object(sc, "_ai_validate", AsyncMock(return_value=True))
        ctx2 = patch.object(sc, "_ai_correct", AsyncMock(side_effect=lambda w: w))
        ctx.start()
        ctx2.start()

        try:
            # Letra suelta debe ser rechazada incluso con IA que dice "si"
            result = await sc.validate("R", "nombre", mode="hybrid")
            assert result is False, "validate('R', 'nombre') debe ser False"

            # "r" no debe estar en la word list
            assert "r" not in sc._word_lists.get("nombre", set()), \
                "validate() no debe agregar 'r' a la word list"

            # 2 caracteres debe pasar
            result2 = await sc.validate("Ro", "nombre", mode="hybrid")
            assert result2 is True, "validate('Ro', 'nombre') debe ser True"

            # Palabra valida en word list debe pasar
            result3 = await sc.validate("Raul", "nombre", mode="hybrid")
            assert result3 is True, "validate('Raul', 'nombre') debe ser True"
        finally:
            ctx.stop()
            ctx2.stop()

    @pytest.mark.asyncio
    async def test_evaluate_asigna_0_a_letra_suelta(self):
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75)
        sc._word_lists = {k: set(v) for k, v in SEED_LISTS.items()}
        sc.api_limit = 200

        ctx = patch.object(sc, "_ai_validate", AsyncMock(return_value=True))
        ctx2 = patch.object(sc, "_ai_correct", AsyncMock(side_effect=lambda w: w))
        ctx.start()
        ctx2.start()

        engine = ScoreEngine()

        try:
            # Simular una ronda con letra R:
            #   A escribe "Nombre: R" (letra suelta → 0)
            #   B escribe "Nombre: Raul" (valido → 50 unico)
            raw = {
                A_ID: [ans(1, "Nombre", "R", A_ID)],
                B_ID: [ans(2, "Nombre", "Raul", B_ID)],
            }

            totals, details = engine.evaluate(
                raw,
                num_categories=1,
                first_completer_id=None,
                spell_corrector=sc,
                letter="R",
            )

            assert totals.get(A_ID, 0) == 0, f"A debe tener 0 pts, obtuvo {totals.get(A_ID, 0)}"
            assert totals.get(B_ID, 0) == 50, f"B debe tener 50 pts, obtuvo {totals.get(B_ID, 0)}"

            # Verificar source en detalles
            a_detail = details.get(A_ID, [])
            if a_detail:
                assert a_detail[0]["validation_source"] in ("default", "too_short"), \
                    f"Source para A debe ser default/too_short, obtuvo {a_detail[0]['validation_source']}"
        finally:
            ctx.stop()
            ctx2.stop()

    @pytest.mark.asyncio
    async def test_word_list_no_se_contamina_con_1_caracter(self):
        """Verificar que validate() no agrega palabras de 1 char a _word_lists."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75)
        sc._word_lists = {k: set(v) for k, v in SEED_LISTS.items()}
        sc.api_limit = 200

        ctx = patch.object(sc, "_ai_validate", AsyncMock(return_value=True))
        ctx2 = patch.object(sc, "_ai_correct", AsyncMock(side_effect=lambda w: w))
        ctx.start()
        ctx2.start()

        try:
            word_list_size = len(sc._word_lists.get("nombre", set()))

            # Validar letras sueltas en todas las categorias
            for cat in ["nombre", "color", "animal", "cosa"]:
                for letter in ["A", "R", "Z", "M", "S", "C"]:
                    await sc.validate(letter, cat, mode="hybrid")

            # La word list no debe haber crecido
            assert len(sc._word_lists.get("nombre", set())) == word_list_size, \
                "validate() no debe agregar letras sueltas a nombre"
            assert len(sc._word_lists.get("color", set())) == word_list_size, \
                "validate() no debe agregar letras sueltas a color"
            assert len(sc._word_lists.get("animal", set())) == word_list_size, \
                "validate() no debe agregar letras sueltas a animal"
            assert len(sc._word_lists.get("cosa", set())) == word_list_size, \
                "validate() no debe agregar letras sueltas a cosa"
        finally:
            ctx.stop()
            ctx2.stop()
