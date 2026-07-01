import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import Player
from src.services.game_orchestrator import (
    LOBBY_EXPIRE,
    MAX_PLAYERS,
    MIN_PLAYERS_TO_START,
    LobbyManager,
    LobbyState,
    lobby_manager,
)


# ── LobbyState dataclass ────────────────────────────────────────────────────


def test_lobby_state_defaults():
    state = LobbyState(
        game_id=1,
        group_chat_id=-100,
        host_telegram_id=123,
        host_name="Host",
        message_chat_id=-100,
        message_id=1,
    )
    assert state.player_telegram_ids == []
    assert state.player_display_names == []
    assert state.expire_task is None
    assert state.animation_task is None
    assert state.auto_start_task is None


# ── _format_lobby_message ───────────────────────────────────────────────────


class TestFormatLobbyMessage:
    def test_format_basic(self):
        result = LobbyManager._format_lobby_message(
            "🛑 STOP - Sala abierta", count=1, players=["Host"]
        )
        assert "Sala abierta" in result
        assert "Jugadores: 1/10" in result
        assert "Host" in result
        assert "Inicio automático" in result
        assert str(MIN_PLAYERS_TO_START) in result
        assert str(MAX_PLAYERS) in result

    def test_format_with_multiple_players(self):
        players = ["Alice", "Bob", "Charlie"]
        result = LobbyManager._format_lobby_message(
            "Title", count=3, players=players
        )
        for name in players:
            assert name in result

    def test_format_no_players(self):
        result = LobbyManager._format_lobby_message(
            "Title", count=0, players=[]
        )
        assert "1." not in result


# ── LobbyManager (unit tests with mocked dependencies) ──────────────────────


@pytest.fixture
def fresh_manager():
    return LobbyManager()


@pytest.fixture
def mock_player():
    p = MagicMock(spec=Player)
    p.id = 1
    p.telegram_id = 123456789
    p.first_name = "TestUser"
    p.username = "testuser"
    return p


@pytest.fixture
def mock_host_player():
    p = MagicMock(spec=Player)
    p.id = 1
    p.telegram_id = 999
    p.first_name = "Host"
    p.username = "hostuser"
    return p


class TestLobbyManagerQueries:
    def test_has_lobby_initial(self, fresh_manager):
        assert not fresh_manager.has_lobby(-100)

    def test_get_lobby_returns_none(self, fresh_manager):
        assert fresh_manager.get_lobby(-100) is None

    def test_get_lobby_by_game_returns_none(self, fresh_manager):
        assert fresh_manager.get_lobby_by_game(1) is None

    def test_has_lobby_after_insert(self, fresh_manager):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=123,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
        )
        fresh_manager._lobbies[-100] = state
        assert fresh_manager.has_lobby(-100)
        assert fresh_manager.get_lobby(-100) is state
        assert fresh_manager.get_lobby_by_game(1) is state

    def test_get_lobby_by_game_with_multiple(self, fresh_manager):
        s1 = LobbyState(
            game_id=1, group_chat_id=-1, host_telegram_id=1, host_name="A",
            message_chat_id=-1, message_id=1,
        )
        s2 = LobbyState(
            game_id=2, group_chat_id=-2, host_telegram_id=2, host_name="B",
            message_chat_id=-2, message_id=2,
        )
        fresh_manager._lobbies[-1] = s1
        fresh_manager._lobbies[-2] = s2
        assert fresh_manager.get_lobby_by_game(2) is s2
        assert fresh_manager.get_lobby_by_game(3) is None


class TestCreateLobby:
    @patch("src.services.game_orchestrator.async_session_factory")
    @patch("src.services.game_orchestrator.GameRepository")
    async def test_create_lobby_success(
        self, mock_repo_cls, mock_session_factory, fresh_manager,
        mock_host_player, mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_repo = AsyncMock()
        mock_repo.get_active_game.return_value = None
        mock_game = MagicMock()
        mock_game.id = 42
        mock_repo.create_game.return_value = mock_game
        mock_repo_cls.return_value = mock_repo

        result = await fresh_manager.create_lobby(
            group_chat_id=-100, host_player=mock_host_player, bot=mock_bot
        )

        assert result is None
        assert fresh_manager.has_lobby(-100)
        mock_bot.send_message.assert_awaited_once()

    @patch("src.services.game_orchestrator.async_session_factory")
    @patch("src.services.game_orchestrator.GameRepository")
    async def test_create_lobby_rejects_duplicate(
        self, mock_repo_cls, mock_session_factory, fresh_manager,
        mock_host_player, mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_repo = AsyncMock()
        existing = MagicMock()
        existing.status = "playing"
        mock_repo.get_active_game.return_value = existing
        mock_repo_cls.return_value = mock_repo

        result = await fresh_manager.create_lobby(
            group_chat_id=-100, host_player=mock_host_player, bot=mock_bot
        )
        assert result == "⚠️ Ya hay una sala abierta en este grupo."


class TestJoinLobby:
    @pytest.mark.asyncio
    async def test_join_nonexistent_lobby(
        self, fresh_manager, mock_player, mock_callback, mock_bot,
    ):
        mock_callback.data = "join:999"
        await fresh_manager.join_lobby(999, mock_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited_with(
            "❌ Esta sala ya no existe.", show_alert=True
        )

    @pytest.mark.asyncio
    async def test_join_when_already_in_lobby(
        self, fresh_manager, mock_host_player, mock_callback, mock_bot,
    ):
        state = LobbyState(
            game_id=1, group_chat_id=-100, host_telegram_id=999, host_name="H",
            message_chat_id=-100, message_id=1,
            player_telegram_ids=[999],
            player_display_names=["Host"],
        )
        fresh_manager._lobbies[-100] = state
        mock_callback.data = "join:1"

        await fresh_manager.join_lobby(1, mock_host_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited_with(
            "✅ Ya estás en la partida", show_alert=False
        )

    @pytest.mark.asyncio
    async def test_join_full_lobby(
        self, fresh_manager, mock_player, mock_callback, mock_bot,
    ):
        state = LobbyState(
            game_id=1, group_chat_id=-100, host_telegram_id=999, host_name="H",
            message_chat_id=-100, message_id=1,
            player_telegram_ids=list(range(MAX_PLAYERS)),
            player_display_names=[f"P{i}" for i in range(MAX_PLAYERS)],
        )
        fresh_manager._lobbies[-100] = state
        await fresh_manager.join_lobby(1, mock_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited_with(
            f"❌ La partida ya tiene {MAX_PLAYERS} jugadores.", show_alert=True
        )


class TestStartGame:
    @pytest.mark.asyncio
    async def test_start_nonexistent(
        self, fresh_manager, mock_host_player, mock_callback, mock_bot,
    ):
        await fresh_manager.start_game(999, mock_host_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited_with(
            "❌ Sala no encontrada.", show_alert=True
        )

    @pytest.mark.asyncio
    async def test_start_not_host(
        self, fresh_manager, mock_player, mock_callback, mock_bot,
    ):
        state = LobbyState(
            game_id=1, group_chat_id=-100, host_telegram_id=999, host_name="H",
            message_chat_id=-100, message_id=1,
            player_telegram_ids=[999, 888],
            player_display_names=["H", "P"],
        )
        fresh_manager._lobbies[-100] = state
        await fresh_manager.start_game(1, mock_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited_with(
            "❌ Solo el host puede iniciar la partida.", show_alert=True
        )

    @pytest.mark.asyncio
    async def test_start_not_enough_players(
        self, fresh_manager, mock_host_player, mock_callback, mock_bot,
    ):
        state = LobbyState(
            game_id=1, group_chat_id=-100, host_telegram_id=999, host_name="H",
            message_chat_id=-100, message_id=1,
            player_telegram_ids=[999],
            player_display_names=["H"],
        )
        fresh_manager._lobbies[-100] = state
        await fresh_manager.start_game(1, mock_host_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited_with(
            f"❌ Se necesitan al menos {MIN_PLAYERS_TO_START} jugadores.",
            show_alert=True,
        )


class TestCancelGame:
    @patch("src.services.game_orchestrator.async_session_factory")
    @patch("src.services.game_orchestrator.GameRepository")
    async def test_cancel_no_active_game(
        self, mock_repo_cls, mock_session_factory, fresh_manager,
        mock_host_player, mock_bot,
    ):
        mock_session = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_repo = AsyncMock()
        mock_repo.get_active_game.return_value = None
        mock_repo_cls.return_value = mock_repo

        result = await fresh_manager.cancel_game(-100, mock_host_player, mock_bot)
        assert result == "❌ No hay una partida activa en este grupo."


class TestCleanup:
    def test_cleanup_removes_from_dict(self, fresh_manager):
        state = LobbyState(
            game_id=1, group_chat_id=-100, host_telegram_id=1, host_name="H",
            message_chat_id=-100, message_id=1,
        )
        fresh_manager._lobbies[-100] = state
        fresh_manager._cleanup(state)
        assert not fresh_manager.has_lobby(-100)

    @pytest.mark.asyncio
    async def test_cleanup_cancels_tasks(self, fresh_manager):
        task = asyncio.get_event_loop().create_task(asyncio.sleep(100))
        state = LobbyState(
            game_id=1, group_chat_id=-100, host_telegram_id=1, host_name="H",
            message_chat_id=-100, message_id=1,
            expire_task=task,
        )
        fresh_manager._lobbies[-100] = state
        fresh_manager._cleanup(state)
        await asyncio.sleep(0)
        assert task.cancelled()

    def test_cleanup_does_not_crash_on_none_tasks(self, fresh_manager):
        state = LobbyState(
            game_id=1, group_chat_id=-100, host_telegram_id=1, host_name="H",
            message_chat_id=-100, message_id=1,
        )
        fresh_manager._lobbies[-100] = state
        fresh_manager._cleanup(state)


class TestResetAutoStart:
    @pytest.mark.asyncio
    async def test_auto_start_created_with_enough_players(self, fresh_manager):
        state = LobbyState(
            game_id=1, group_chat_id=-100, host_telegram_id=1, host_name="H",
            message_chat_id=-100, message_id=1,
            player_telegram_ids=[1, 2],
            player_display_names=["A", "B"],
        )
        bot = MagicMock()
        fresh_manager._reset_auto_start(state, bot)
        assert state.auto_start_task is not None
        assert not state.auto_start_task.done()
        state.auto_start_task.cancel()

    def test_auto_start_not_created_with_one_player(self, fresh_manager):
        state = LobbyState(
            game_id=1, group_chat_id=-100, host_telegram_id=1, host_name="H",
            message_chat_id=-100, message_id=1,
            player_telegram_ids=[1],
            player_display_names=["A"],
        )
        bot = MagicMock()
        fresh_manager._reset_auto_start(state, bot)
        assert state.auto_start_task is None
