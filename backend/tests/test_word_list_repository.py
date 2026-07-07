import pytest
from datetime import datetime
from src.db.models import WordListItem
from src.db.repositories.word_list_repository import WordListRepository


class TestWordListRepository:
    async def test_bulk_insert_and_get(self, async_session):
        repo = WordListRepository(async_session)
        words = [("rojo", "Rojo"), ("azul", "Azul")]
        count = await repo.bulk_insert("color", words, source="seed")
        assert count == 2

        retrieved = await repo.get_words_by_category("color")
        assert sorted(retrieved) == ["azul", "rojo"]

    async def test_bulk_insert_skips_duplicates(self, async_session):
        repo = WordListRepository(async_session)
        words = [("rojo", "Rojo"), ("rojo", "Rojo")]
        count = await repo.bulk_insert("color", words, source="seed")
        assert count == 1

    async def test_clear_category(self, async_session):
        repo = WordListRepository(async_session)
        await repo.bulk_insert("color", [("rojo", "Rojo")], source="seed")
        deleted = await repo.clear_category("color")
        assert deleted >= 1
        assert await repo.count_by_category("color") == 0

    async def test_word_exists(self, async_session):
        repo = WordListRepository(async_session)
        await repo.bulk_insert("color", [("rojo", "Rojo")], source="seed")
        assert await repo.word_exists("rojo", "color") is True
        assert await repo.word_exists("azul", "color") is False

    async def test_count_by_category(self, async_session):
        repo = WordListRepository(async_session)
        await repo.bulk_insert("color", [("rojo", "Rojo"), ("azul", "Azul")], source="seed")
        assert await repo.count_by_category("color") == 2

    async def test_seed_massive_lists(self, async_session):
        """Verifica que las listas masivas se insertan correctamente."""
        repo = WordListRepository(async_session)

        words = [(f"TestWord{i}", f"TestWord{i}") for i in range(100)]
        count = await repo.bulk_insert("test_cat", words, source="seed")
        assert count == 100

        loaded = await repo.get_words_by_category("test_cat")
        assert len(loaded) == 100

    async def test_persistent_auto_expansion(self, async_session):
        """Verifica que add_to_word_list_persistent funciona."""
        from src.core.text_utils import normalize_text

        repo = WordListRepository(async_session)
        # Insertar palabra aprendida
        async_session.add(
            WordListItem(
                category="nombre",
                word="TestNombre",
                normalized=normalize_text("TestNombre"),
                source="learned",
            )
        )
        await async_session.commit()

        loaded = await repo.get_words_by_category("nombre")
        assert normalize_text("TestNombre") in loaded
