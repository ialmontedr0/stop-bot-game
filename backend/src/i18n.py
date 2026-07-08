"""Configuracion de internacionalizacion con gettext"""

import gettext
from pathlib import Path
from typing import Optional

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

LOCALE_MAP = {
    "es": "es",
    "en": "en",
    "pt": "pt",
    "pt-br": "pt",
    "es-ar": "es",
    "es-mx": "es",
    "en-us": "en",
    "en-gb": "en",
}

_translations: dict[str, gettext.GNUTranslations] = {}


def _get_translation(locale: str) -> gettext.GNUTranslations:
    if locale not in _translations:
        mo_path = LOCALES_DIR / locale / "LC_MESSAGES" / "bot.mo"
        if mo_path.exists():
            with open(mo_path, "rb") as f:
                _translations[locale] = gettext.GNUTranslations(f)
        else:
            _translations[locale] = gettext.NullTranslations()
    return _translations[locale]


def get_user_locale(player: Optional["Player"]) -> str:  # noqa
    if not player or not player.language_code:
        return "es"
    code = player.language_code.lower()
    return LOCALE_MAP.get(code, "es")


def t(key: str, locale: str = "es", **kwargs) -> str:
    tr = _get_translation(locale)
    translated = tr.gettext(key)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except KeyError:
            return translated
    return translated
