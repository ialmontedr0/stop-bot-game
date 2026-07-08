import pytest
from src.services.xp_service import XPService, _calculate_level, LEVEL_TABLE


@pytest.mark.asyncio
async def test_calculate_level():
    assert _calculate_level(0) == 1
    assert _calculate_level(50) == 1


@pytest.mark.asyncio
async def test_level_up():
    # Simula otorgar XP hasta subir de nivel
    ...


@pytest.mark.asyncio
async def test_streak_update(async_session): ...
