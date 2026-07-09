import pytest

from src.services.spell_corrector import SpellCorrector, normalize_text


class TestSpellCorrectorEdgeCases:
    def test_normalize_empty_string(self):
        assert normalize_text("") == ""

    def test_normalize_only_symbols(self):
        assert normalize_text("!!!@#$%") == ""

    def test_normalize_mixed_accents(self):
        assert normalize_text("Cancion") == "cancion"
        assert normalize_text("Ultimo") == "ultimo"
        assert normalize_text("Nono") == "nono"

    def test_normalize_multi_spaces(self):
        assert normalize_text("  el   auto  ") == "el auto"

    def test_normalize_hyphen_preserved(self):
        result = normalize_text("Bienvenido-a-mi-casa")
        assert "bienvenido-a-mi-casa" in result

    @pytest.mark.asyncio
    async def test_correct_unknown_category(self):
        corrector = SpellCorrector(mode="local")
        result = await corrector.correct("xyz123", "NonExistentCategory")
        assert result == "xyz123" or result == normalize_text("xyz123")

    def test_validate_empty_word_returns_false(self):
        corrector = SpellCorrector()
        assert corrector.is_in_word_list("", "color") is False

    def test_fuzzy_threshold_below(self):
        corrector = SpellCorrector()
        corrector._word_lists["color"] = {"rojo", "azul", "verde"}
        best, score = corrector.fuzzy_match("abcdefxyz", list(corrector._word_lists["color"]))
        assert best is None

    def test_get_api_metrics_defaults(self):
        corrector = SpellCorrector()
        metrics = corrector.get_api_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["failed_calls"] == 0
        assert metrics["mode"] == "local"
