"""
Script idempotente que siembra las 8 categorias completas en word_list_items.

Uso:
    cd backend
    python -m scripts.seed_all_word_lists

Es idempotente: no duplica entradas (usa bulk_insert que chequea unique constraint).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.text_utils import normalize_text
from src.db.engine import async_session_factory
from src.db.repositories.word_list_repository import WordListRepository

# Importar listas completas
from .word_list_data import COLORS, COUNTRIES, FRUITS
from .word_list_data_full import ANIMALS, ARTISTS, NAMES, SURNAMES, THINGS

ALL_CATEGORIES: dict[str, list[str]] = {
    "color": COLORS,
    "fruta": FRUITS,
    "pais": COUNTRIES,
    "nombre": NAMES,
    "apellido": SURNAMES,
    "artista": ARTISTS,
    "animal": ANIMALS,
    "cosa": THINGS,
}


async def seed_all() -> None:

    async with async_session_factory() as session:
        repo = WordListRepository(session)

        for category, words in ALL_CATEGORIES.items():
            # Normalizar y deduplicar
            items = [(normalize_text(w), w.strip()) for w in words if w.strip()]
            seen: set[str] = set()
            unique: list[tuple[str, str]] = []
            for norm, orig in items:
                if norm not in seen:
                    seen.add(norm)
                    unique.append((norm, orig))

            # Contar antes
            await repo.count_by_category(category)
            await repo.bulk_insert(category, unique, source="seed")
            await repo.count_by_category(category)

        # Resumen final
        total = 0
        for cat in ALL_CATEGORIES:
            c = await repo.count_by_category(cat)
            total += c


if __name__ == "__main__":
    asyncio.run(seed_all())
