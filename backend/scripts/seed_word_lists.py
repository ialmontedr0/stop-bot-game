"""
Script para probar la tabla word_list_items con colores, frutas y paises.

Uso:
    cd backend
    python -m scripts.seed_word_lists

Es idempotente: limpia cada categoria antes de reinsertar.
"""

import asyncio
import os
import sys

# Asegurar que podemos importar desde src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.text_utils import normalize_text
from src.db.engine import async_session_factory
from src.db.repositories.word_list_repository import WordListRepository

from .word_list_data import WORD_LIST_DATA


async def seed_category(repo: WordListRepository, category: str, words: list[str]) -> None:
    """Inserta todas las palabras de una categoria, limpiando primero.

    Args:
        repo (WordListRepository): _description_
        category (str): _description_
        words (list[str]): _description_
    """
    await repo.clear_category(category)

    items = [(normalize_text(w), w.strip()) for w in words if w.strip()]
    # Eliminar duplicados normalizados dentro de la misma categoria
    seen: set[str] = set()
    unique_items: list[tuple[str, str]] = []
    for norm, orig in items:
        if norm not in seen:
            seen.add(norm)
            unique_items.append((norm, orig))

    await repo.bulk_insert(category, unique_items)
    await repo.count_by_category(category)


async def main() -> None:

    for category, words in WORD_LIST_DATA.items():
        async with async_session_factory() as session:
            repo = WordListRepository(session)
            await seed_category(repo, category, words)

    # Mostrar resumen final
    async with async_session_factory() as session:
        repo = WordListRepository(session)
        for cat in WORD_LIST_DATA:
            await repo.count_by_category(cat)


if __name__ == "__main__":
    asyncio.run(main())
