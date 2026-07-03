import pytest

from src.db.models import WordListItem
from src.db.repositories.word_list_repository import WordListRepository


class TestWordListRepository:
    async def test_bulk_insert_and_get(self, async_session):
        repo = WordListRepository(async_session)
        words = [("rojo", "Rojo"), ("azul", "Azul")]
        count = await repo.bulk_insert("color", words)
        assert count == 2

        retrieved = await repo.get_words_by_category("color")
        assert sorted(retrieved) == ["azul", "rojo"]

    async def test_bulk_insert_skips_duplicates(self, async_session):
        repo = WordListRepository(async_session)
        words = [("rojo", "Rojo"), ("rojo", "Rojo")]
        count = await repo.bulk_insert("color", words)
        assert count == 1

    async def test_clear_category(self, async_session):
        repo = WordListRepository(async_session)
        await repo.bulk_insert("color", [("rojo", "Rojo")])
        deleted = await repo.clear_category("color")
        assert deleted >= 1
        assert await repo.count_by_category("color") == 0

    async def test_word_exists(self, async_session):
        repo = WordListRepository(async_session)
        await repo.bulk_insert("color", [("rojo", "Rojo")])
        assert await repo.word_exists("rojo", "color") is True
        assert await repo.word_exists("azul", "color") is False

    async def test_count_by_category(self, async_session):
        repo = WordListRepository(async_session)
        await repo.bulk_insert("color", [("rojo", "Rojo"), ("azul", "Azul")])
        assert await repo.count_by_category("color") == 2
