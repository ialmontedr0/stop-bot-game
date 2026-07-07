"""Tests de integracion para el modo AI/Hybrid de SpellCorrector.

NOTA: Requiere SPELL_API_KEY configurada en .env.
"""

import os
import pytest
from dotenv import load_dotenv
from src.services.spell_corrector import SpellCorrector

load_dotenv()


def has_api_key():
    return bool(os.getenv("SPELL_API_KEY"))


pytestmark = pytest.mark.skipif(
    not has_api_key(),
    reason="Requiere SPELL_API_KEY en .env",
)


def _make_sc(**kwargs):
    return SpellCorrector(
        mode="hybrid",
        ai_provider=kwargs.get("ai_provider", os.getenv("SPELL_AI_PROVIDER", "openai")),
        api_key=kwargs.get("api_key", os.getenv("SPELL_API_KEY")),
        api_url=kwargs.get(
            "api_url",
            os.getenv("SPELL_API_URL",
                       "https://api.groq.com/openai/v1"),
        ),
        ai_model=kwargs.get("ai_model", os.getenv("SPELL_AI_MODEL")),
        fuzzy_threshold=kwargs.get("fuzzy_threshold", 75),
    )


class TestAICorrection:
    @pytest.mark.asyncio
    async def test_correct_spanish_word(self):
        """IA corrige una palabra con typo al espanol correcto."""
        sc = _make_sc()
        corrected = await sc._ai_correct("Fenando")
        assert corrected is not None
        assert "fernando" in corrected.lower()

    @pytest.mark.asyncio
    async def test_correct_already_correct(self):
        """IA devuelve la misma palabra si ya es correcta."""
        sc = _make_sc()
        corrected = await sc._ai_correct("Messi")
        assert corrected is not None
        assert corrected.lower() == "messi"

    @pytest.mark.asyncio
    async def test_correct_timeout_returns_none(self):
        """Timeout en llamada a IA retorna None sin crash."""
        sc = _make_sc(api_url="https://httpbin.org/delay/30")
        result = await sc._ai_correct("Hola")
        assert result is None  # Timeout


class TestAIValidation:
    @pytest.mark.asyncio
    async def test_validate_valid_artist(self):
        """IA reconoce a Shakira como artista."""
        sc = _make_sc()
        sc._word_lists["artista"] = set()
        result = await sc._ai_validate("Shakira", "Artista")
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_invalid_artist(self):
        """IA reconoce que 'Mesa' NO es un artista."""
        sc = _make_sc()
        sc._word_lists["artista"] = set()
        result = await sc._ai_validate("Mesa", "Artista")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_full_pipeline_hybrid(self):
        """Pipeline hybrid completo: fuzzy falla -> IA valida -> aprende."""
        sc = _make_sc()
        sc._word_lists["artista"] = {"picasso", "dali"}

        result = await sc.validate("Frida", "Artista")
        assert result is True
        assert "frida" in sc._word_lists["artista"]

    @pytest.mark.asyncio
    async def test_validate_rejects_gibberish(self):
        """IA rechaza palabras sin sentido."""
        sc = _make_sc()
        sc._word_lists["nombre"] = set()
        result = await sc._ai_validate("Xyzzyqwert", "Nombre")
        assert result is False
