import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.group_config_repository import GroupConfigRepository


@pytest.mark.asyncio
async def test_get_or_create_creates_new(async_session: AsyncSession):
    repo = GroupConfigRepository(async_session)
    config = await repo.get_or_create(-123456789)
    assert config.group_chat_id == -123456789
    assert config.default_rounds == 5
    assert config.round_time == 60
    assert config.categories is None
    assert config.include_n is False


@pytest.mark.asyncio
async def test_get_or_create_returns_existing(async_session: AsyncSession):
    repo = GroupConfigRepository(async_session)
    config1 = await repo.get_or_create(-987654321)
    config1.default_rounds = 10
    await async_session.flush()

    config2 = await repo.get_or_create(-987654321)
    assert config2.id == config1.id
    assert config2.default_rounds == 10
