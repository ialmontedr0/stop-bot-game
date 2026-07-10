from unittest.mock import MagicMock, patch

from src.i18n import LOCALE_MAP, _get_translation, _translations, get_user_locale, t


class TestGetUserLocale:
    def test_none_player_returns_es(self):
        assert get_user_locale(None) == "es"

    def test_player_no_language_code_returns_es(self):
        player = MagicMock()
        player.language_code = None
        assert get_user_locale(player) == "es"

    def test_spanish_code(self):
        player = MagicMock()
        player.language_code = "es"
        assert get_user_locale(player) == "es"

    def test_english_code(self):
        player = MagicMock()
        player.language_code = "en"
        assert get_user_locale(player) == "en"

    def test_portuguese_code(self):
        player = MagicMock()
        player.language_code = "pt"
        assert get_user_locale(player) == "pt"

    def test_pt_br_maps_to_pt(self):
        player = MagicMock()
        player.language_code = "pt-br"
        assert get_user_locale(player) == "pt"

    def test_es_ar_maps_to_es(self):
        player = MagicMock()
        player.language_code = "es-ar"
        assert get_user_locale(player) == "es"

    def test_unknown_code_falls_back_to_es(self):
        player = MagicMock()
        player.language_code = "fr"
        assert get_user_locale(player) == "es"

    def test_case_insensitive(self):
        player = MagicMock()
        player.language_code = "EN"
        assert get_user_locale(player) == "en"


class TestGetTranslation:
    def setup_method(self):
        _translations.clear()

    def test_nonexistent_locale_returns_null(self):
        tr = _get_translation("zz")
        assert tr is not None

    def test_mo_file_not_found_falls_back_to_null(self):
        _translations.clear()
        with patch("src.i18n.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value.exists.return_value = False
            tr = _get_translation("es")
            assert tr is not None

    def test_cache_hit(self):
        _translations.clear()
        with patch("src.i18n.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value.exists.return_value = False
            tr1 = _get_translation("es")
            tr2 = _get_translation("es")
            assert tr1 is tr2


class TestT:
    def setup_method(self):
        _translations.clear()

    def test_basic_translation(
        self,
    ):
        tr = _get_translation("es")
        _translations["es"] = tr
        result = t("Hola", locale="es")
        assert isinstance(result, str)

    def test_translation_with_kwargs(self):
        tr = _get_translation("es")
        _translations["es"] = tr
        _translations["es"].gettext = MagicMock(return_value="Hola {name}")
        result = t("Hello {name}", locale="es", name="Mundo")
        assert result == "Hola Mundo"

    def test_kwargs_key_error_returns_unformatted(self):
        tr = _get_translation("es")
        _translations["es"] = tr
        _translations["es"].gettext = MagicMock(return_value="Hola {name}")
        result = t("Hello {name}", locale="es", wrong="test")
        assert result == "Hola {name}"


class TestLocaleMap:
    def test_contains_expected_keys(self):
        assert "es" in LOCALE_MAP
        assert "en" in LOCALE_MAP
        assert "pt" in LOCALE_MAP
        assert "pt-br" in LOCALE_MAP
        assert "es-ar" in LOCALE_MAP

    def test_values_match(self):
        assert LOCALE_MAP["es"] == "es"
        assert LOCALE_MAP["en"] == "en"
        assert LOCALE_MAP["pt-br"] == "pt"
        assert LOCALE_MAP["es-ar"] == "es"
