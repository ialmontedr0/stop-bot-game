from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import WordListItem


class WordListRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_words_by_category(self, category: str) -> list[str]:
        stmt = (
            select(WordListItem.normalized)
            .where(WordListItem.category == category)
            .order_by(WordListItem.normalized)
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result]

    async def get_words_with_originals(self, category: str) -> list[tuple[str, str]]:
        """Retorna (normalized, original_word) para cada entrada."""
        stmt = select(WordListItem.normalized, WordListItem.word).where(
            WordListItem.category == category
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result]

    async def word_exists(self, normalized: str, category: str) -> bool:
        stmt = (
            select(WordListItem.id)
            .where(
                WordListItem.category == category,
                WordListItem.normalized == normalized,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def bulk_insert(self, category: str, words: list[tuple[str, str]], source: str) -> int:
        """Inserta múltiples palabras. Cada tupla es (normalized, original).
        Returns cantidad de inserts.
        """
        existing = set(await self.get_words_by_category(category))
        seen_in_batch: set[str] = set()
        count = 0
        for norm, word in words:
            if norm not in existing and norm not in seen_in_batch:
                self.session.add(
                    WordListItem(category=category, word=word, normalized=norm, source=source)
                )
                seen_in_batch.add(norm)
                count += 1
        if count:
            await self.session.commit()
        return count

    async def clear_category(self, category: str) -> int:
        """Elimina todas las palabras de una categoría. Retorna cantidad eliminada."""
        stmt = delete(WordListItem).where(WordListItem.category == category)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    async def count_by_category(self, category: str) -> int:
        stmt = select(func.count(WordListItem.id)).where(WordListItem.category == category)
        result = await self.session.execute(stmt)
        return result.scalar() or 0
