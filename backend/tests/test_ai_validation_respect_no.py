"""
TEST: validate() respeta el "no" de la IA en modo hybrid/ai.

Comportamiento esperado despues del fix:
  1. IA dice "si"  -> validate() = True,  source = "ai",     se agrega a word list
  2. IA dice "no"  -> validate() = False, source = "ai_rejected", NO se agrega a word list
  3. IA falla/None -> validate() = True,  source = "default" (fallback permisivo)
  4. Cache: si IA ya dijo "no", no se vuelve a preguntar
  5. Prompt de IA NO contiene 'En caso de duda responde si'
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.services.spell_corrector import SpellCorrector

SEED = {
    "nombre": {"raul", "ana", "maria"},
    "artista": {"romeo santos", "madonna"},
    "color": {"rojo", "azul", "verde"},
}


class TestAIValidationRespectsNo:

    @pytest.mark.asyncio
    async def test_ai_dice_si_retorna_true(self):
        """IA acepta -> validate=True, source=ai, palabra va a word list."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, api_key="sk-test", api_url="https://api.openai.com/v1")
        sc._word_lists = {k: set(v) for k, v in SEED.items()}
        sc.api_limit = 200

        with patch.object(sc, "_ai_validate", AsyncMock(return_value=True)):
            result = await sc.validate("Antony Santos", "artista", mode="hybrid")

        assert result is True, "IA dijo si -> debe retornar True"
        assert "antony santos" in sc._word_lists.get("artista", set()), \
            "palabra aceptada debe estar en word list"
        source = sc.get_validation_source(0, "artista:antony santos")
        assert source == "ai", f"source debe ser 'ai', obtuvo '{source}'"

    @pytest.mark.asyncio
    async def test_ai_dice_no_retorna_false(self):
        """IA rechaza -> validate=False, source=ai_rejected, NO va a word list."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, api_key="sk-test", api_url="https://api.openai.com/v1")
        sc._word_lists = {k: set(v) for k, v in SEED.items()}
        sc.api_limit = 200

        with patch.object(sc, "_ai_validate", AsyncMock(return_value=False)):
            result = await sc.validate("Antony Paez", "artista", mode="hybrid")

        assert result is False, "IA dijo no -> debe retornar False"
        assert "antony paez" not in sc._word_lists.get("artista", set()), \
            "palabra rechazada NO debe estar en word list"
        source = sc.get_validation_source(0, "artista:antony paez")
        expected_source = "ai_rejected"
        assert source == expected_source, f"source debe ser '{expected_source}', obtuvo '{source}'"

    @pytest.mark.asyncio
    async def test_ai_falla_retorna_true_default(self):
        """IA falla (None) -> validate=True, source=default (fallback permisivo)."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, api_key="sk-test", api_url="https://api.openai.com/v1")
        sc._word_lists = {k: set(v) for k, v in SEED.items()}
        sc.api_limit = 200

        with patch.object(sc, "_ai_validate", AsyncMock(return_value=None)):
            result = await sc.validate("Qqqqq", "nombre", mode="hybrid")

        assert result is True, "IA falla -> fallback permisivo -> True"
        source = sc.get_validation_source(0, "nombre:qqqqq")
        assert source == "default_temp", f"source debe ser 'default_temp', obtuvo '{source}'"

    @pytest.mark.asyncio
    async def test_ai_sin_api_key_cae_default(self):
        """Sin API key configurada -> validate llama _ai_validate
        que retorna None -> cae a default permisivo."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75)
        sc._word_lists = {k: set(v) for k, v in SEED.items()}

        # No seteamos api_key ni api_url -> _ai_validate retorna None
        with patch.object(sc, "_ai_validate", AsyncMock(return_value=None)):
            result = await sc.validate("Algo", "nombre", mode="hybrid")

        assert result is True, "Sin API key -> fallback permisivo -> True"

    @pytest.mark.asyncio
    async def test_cache_rechazo_no_vuelve_a_preguntar(self):
        """Si IA ya rechazo, el cache devuelve False sin llamar a IA de nuevo."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, api_key="sk-test", api_url="https://api.openai.com/v1")
        sc._word_lists = {k: set(v) for k, v in SEED.items()}
        sc.api_limit = 200

        mock_ai = AsyncMock(return_value=False)
        with patch.object(sc, "_ai_validate", mock_ai):
            # Primera llamada: IA dice no
            r1 = await sc.validate("Inventado", "artista", mode="hybrid")
            assert r1 is False

        # Segunda llamada: debe usar cache, NO llamar a _ai_validate otra vez
        # Reset counter para verificar que no se incrementa
        calls_before = sc._api_calls.copy()
        with patch.object(sc, "_ai_validate", AsyncMock(side_effect=Exception("NO DEBE LLAMAR"))):
            r2 = await sc.validate("Inventado", "artista", mode="hybrid")

        assert r2 is False, "cache debe retornar False sin llamar a IA"
        assert sc._api_calls == calls_before, \
            "_api_calls NO debe incrementarse (no hubo llamada real a IA)"

    @pytest.mark.asyncio
    async def test_prompt_no_contiene_en_caso_de_duda(self):
        """Verificar que el prompt de _ai_validate NO contiene la frase permisiva."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75)

        # Forzar que _ai_validate ejecute el prompt real
        # No podemos parchearlo porque queremos inspeccionar el codigo
        # En vez de eso, verificamos el codigo fuente directamente
        import inspect
        source = inspect.getsource(sc._ai_validate)

        assert "En caso de duda responde" not in source, \
            "El prompt NO debe contener 'En caso de duda responde si'. " \
            "Revisa el system_prompt en _ai_validate()"

    @pytest.mark.asyncio
    async def test_letra_suelta_sigue_siendo_rechazada(self):
        """El fix anterior (min length) debe seguir funcionando."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, api_key="sk-test", api_url="https://api.openai.com/v1")
        sc._word_lists = {k: set(v) for k, v in SEED.items()}
        sc.api_limit = 200

        result = await sc.validate("R", "artista", mode="hybrid")
        assert result is False, "letra suelta debe seguir siendo False"
        assert "r" not in sc._word_lists.get("artista", set()), \
            "letra suelta no debe estar en word list"

    @pytest.mark.asyncio
    async def test_palabra_en_word_list_no_llama_ia(self):
        """Si ya esta en word list, ni siquiera pregunta a IA."""
        sc = SpellCorrector(mode="hybrid", fuzzy_threshold=75, api_key="sk-test", api_url="https://api.openai.com/v1")
        sc._word_lists = {k: set(v) for k, v in SEED.items()}
        sc.api_limit = 200

        mock_ai = AsyncMock(side_effect=Exception("NO DEBE LLAMAR"))
        with patch.object(sc, "_ai_validate", mock_ai):
            result = await sc.validate("Raul", "nombre", mode="hybrid")

        assert result is True
        source = sc.get_validation_source(0, "nombre:raul")
        assert source == "word_list", f"source debe ser 'word_list', obtuvo '{source}'"
