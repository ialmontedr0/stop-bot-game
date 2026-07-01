import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Game, GamePlayer, Player
from src.db.repositories.game_repository import GameRepository
from src.db.repositories.player_repository import PlayerRepository


# ── PlayerRepository ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_player_get_or_create_creates_new(async_session: AsyncSession):
    repo = PlayerRepository(async_session)
    player = await repo.get_or_create(
        telegram_id=99999,
        username="newuser",
        first_name="New",
        language_code="en",
    )
    assert player.id is not None
    assert player.telegram_id == 99999
    assert player.username == "newuser"


@pytest.mark.asyncio
async def test_player_get_or_create_returns_existing(async_session: AsyncSession):
    repo = PlayerRepository(async_session)
    p1 = await repo.get_or_create(
        telegram_id=88888,
        username="existing",
        first_name="Exist",
    )
    p2 = await repo.get_or_create(
        telegram_id=88888,
        username="existing",
        first_name="Exist",
    )
    assert p1.id == p2.id


@pytest.mark.asyncio
async def test_player_get_by_telegram_id_finds_player(async_session: AsyncSession, player: Player):
    repo = PlayerRepository(async_session)
    found = await repo.get_by_telegram_id(player.telegram_id)
    assert found is not None
    assert found.id == player.id


@pytest.mark.asyncio
async def test_player_get_by_telegram_id_returns_none(async_session: AsyncSession):
    repo = PlayerRepository(async_session)
    found = await repo.get_by_telegram_id(999999)
    assert found is None


# ── GameRepository ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_game(async_session: AsyncSession):
    repo = GameRepository(async_session)
    game = await repo.create_game(group_chat_id=-100500)
    assert game.id is not None
    assert game.group_chat_id == -100500
    assert game.status == "lobby"


@pytest.mark.asyncio
async def test_get_active_game_finds_lobby(async_session: AsyncSession):
    repo = GameRepository(async_session)
    g1 = await repo.create_game(group_chat_id=-1001)
    g2 = await repo.get_active_game(group_chat_id=-1001)
    assert g2 is not None
    assert g2.id == g1.id


@pytest.mark.asyncio
async def test_get_active_game_returns_none_for_no_game(async_session: AsyncSession):
    repo = GameRepository(async_session)
    found = await repo.get_active_game(group_chat_id=-999999)
    assert found is None


@pytest.mark.asyncio
async def test_get_active_game_returns_none_for_cancelled(async_session: AsyncSession):
    repo = GameRepository(async_session)
    game = await repo.create_game(group_chat_id=-1002)
    await repo.update_game_status(game, "cancelled")
    found = await repo.get_active_game(group_chat_id=-1002)
    assert found is None


@pytest.mark.asyncio
async def test_get_by_id(async_session: AsyncSession):
    repo = GameRepository(async_session)
    game = await repo.create_game(group_chat_id=-1003)
    found = await repo.get_by_id(game.id)
    assert found is not None
    assert found.id == game.id


@pytest.mark.asyncio
async def test_get_by_id_returns_none(async_session: AsyncSession):
    repo = GameRepository(async_session)
    found = await repo.get_by_id(99999)
    assert found is None


@pytest.mark.asyncio
async def test_add_player_to_game(async_session: AsyncSession, player: Player):
    repo = GameRepository(async_session)
    game = await repo.create_game(group_chat_id=-1004)
    gp = await repo.add_player_to_game(game, player, is_host=True)
    assert gp.id is not None
    assert gp.game_id == game.id
    assert gp.player_id == player.id
    assert gp.is_host is True


@pytest.mark.asyncio
async def test_is_player_in_game(async_session: AsyncSession, player: Player):
    repo = GameRepository(async_session)
    game = await repo.create_game(group_chat_id=-1005)
    assert not await repo.is_player_in_game(game, player)

    await repo.add_player_to_game(game, player, is_host=True)
    assert await repo.is_player_in_game(game, player)


@pytest.mark.asyncio
async def test_get_players_for_game(async_session: AsyncSession, player: Player):
    repo = GameRepository(async_session)
    game = await repo.create_game(group_chat_id=-1006)
    await repo.add_player_to_game(game, player, is_host=True)

    rows = await repo.get_players_for_game(game)
    assert len(rows) == 1
    gp, p = rows[0]
    assert gp.game_id == game.id
    assert p.id == player.id


@pytest.mark.asyncio
async def test_get_player_count(async_session: AsyncSession, player: Player):
    repo = GameRepository(async_session)
    game = await repo.create_game(group_chat_id=-1007)
    assert await repo.get_player_count(game) == 0

    await repo.add_player_to_game(game, player, is_host=True)
    assert await repo.get_player_count(game) == 1


@pytest.mark.asyncio
async def test_update_game_status(async_session: AsyncSession):
    repo = GameRepository(async_session)
    game = await repo.create_game(group_chat_id=-1008)
    await repo.update_game_status(game, "playing")
    updated = await repo.get_by_id(game.id)
    assert updated.status == "playing"
