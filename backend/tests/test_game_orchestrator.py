import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import Player
from src.services.game_orchestrator import (
    MAX_PLAYERS,
    MIN_PLAYERS_TO_START,
    LobbyManager,
    LobbyState,
)

# Use the module directly (not through services.__init__ which re-exports the
# game_orchestrator singleton). This allows patch.object to work correctly.
_game_orch_mod = sys.modules["src.services.game_orchestrator"]


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
        result = LobbyManager._format_lobby_message("Title", count=3, players=players)
        for name in players:
            assert name in result

    def test_format_no_players(self):
        result = LobbyManager._format_lobby_message("Title", count=0, players=[])
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
            game_id=1,
            group_chat_id=-1,
            host_telegram_id=1,
            host_name="A",
            message_chat_id=-1,
            message_id=1,
        )
        s2 = LobbyState(
            game_id=2,
            group_chat_id=-2,
            host_telegram_id=2,
            host_name="B",
            message_chat_id=-2,
            message_id=2,
        )
        fresh_manager._lobbies[-1] = s1
        fresh_manager._lobbies[-2] = s2
        assert fresh_manager.get_lobby_by_game(2) is s2
        assert fresh_manager.get_lobby_by_game(3) is None


class TestCreateLobby:
    @patch.object(_game_orch_mod, "async_session_factory")
    @patch.object(_game_orch_mod, "GameRepository")
    @patch.object(_game_orch_mod, "event_service")
    async def test_create_lobby_success(
        self,
        mock_event_service,
        mock_repo_cls,
        mock_session_factory,
        fresh_manager,
        mock_host_player,
        mock_bot,
    ):
        mock_event_service.get_active_events = AsyncMock(return_value=[])
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
        assert mock_bot.send_message.await_count == 3  # lobby msg + DM intro + placeholder

    @patch.object(_game_orch_mod, "async_session_factory")
    @patch.object(_game_orch_mod, "GameRepository")
    async def test_create_lobby_rejects_duplicate(
        self,
        mock_repo_cls,
        mock_session_factory,
        fresh_manager,
        mock_host_player,
        mock_bot,
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
        assert result == "⚠️ Ya hay una partida en curso en este grupo."


class TestJoinLobby:
    @pytest.mark.asyncio
    async def test_join_nonexistent_lobby(
        self,
        fresh_manager,
        mock_player,
        mock_callback,
        mock_bot,
    ):
        mock_callback.data = "join:999"
        await fresh_manager.join_lobby(999, mock_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited()
        assert "no existe" in mock_callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_join_when_already_in_lobby(
        self,
        fresh_manager,
        mock_host_player,
        mock_callback,
        mock_bot,
    ):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
            player_telegram_ids=[999],
            player_display_names=["Host"],
        )
        fresh_manager._lobbies[-100] = state
        mock_callback.data = "join:1"

        await fresh_manager.join_lobby(1, mock_host_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited()
        assert "ya esta" in mock_callback.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_join_full_lobby(
        self,
        fresh_manager,
        mock_player,
        mock_callback,
        mock_bot,
    ):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
            player_telegram_ids=list(range(MAX_PLAYERS)),
            player_display_names=[f"P{i}" for i in range(MAX_PLAYERS)],
        )
        fresh_manager._lobbies[-100] = state
        await fresh_manager.join_lobby(1, mock_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited()
        assert str(MAX_PLAYERS) in mock_callback.answer.call_args[0][0]


class TestStartGame:
    @pytest.mark.asyncio
    async def test_start_nonexistent(
        self,
        fresh_manager,
        mock_host_player,
        mock_callback,
        mock_bot,
    ):
        await fresh_manager.start_game(999, mock_host_player, mock_callback, mock_bot)
        mock_callback.answer.assert_awaited()
        assert "no encontrada" in mock_callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_start_not_host(
        self,
        fresh_manager,
        mock_player,
        mock_callback,
        mock_bot,
    ):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
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
        self,
        fresh_manager,
        mock_host_player,
        mock_callback,
        mock_bot,
    ):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
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
    @patch.object(_game_orch_mod, "async_session_factory")
    @patch.object(_game_orch_mod, "GameRepository")
    async def test_cancel_no_active_game(
        self,
        mock_repo_cls,
        mock_session_factory,
        fresh_manager,
        mock_host_player,
        mock_bot,
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
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=1,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
        )
        fresh_manager._lobbies[-100] = state
        fresh_manager._cleanup(state)
        assert not fresh_manager.has_lobby(-100)

    @pytest.mark.asyncio
    async def test_cleanup_cancels_tasks(self, fresh_manager):
        task = asyncio.get_event_loop().create_task(asyncio.sleep(100))
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=1,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
            expire_task=task,
        )
        fresh_manager._lobbies[-100] = state
        fresh_manager._cleanup(state)
        await asyncio.sleep(0)
        assert task.cancelled()

    def test_cleanup_does_not_crash_on_none_tasks(self, fresh_manager):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=1,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
        )
        fresh_manager._lobbies[-100] = state
        fresh_manager._cleanup(state)


class TestResetAutoStart:
    @pytest.mark.asyncio
    async def test_auto_start_created_with_enough_players(self, fresh_manager):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=1,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
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
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=1,
            host_name="H",
            message_chat_id=-100,
            message_id=1,
            player_telegram_ids=[1],
            player_display_names=["A"],
        )
        bot = MagicMock()
        fresh_manager._reset_auto_start(state, bot)
        assert state.auto_start_task is None


# --- CI: _expire_timer no debe cancelar partidas activas ---


class TestExpireTimer:
    """Verifica que _expire_timer respete state.started"""

    @pytest.mark.asyncio
    async def test_expire_timer_returns_early_when_started(self, fresh_manager, mock_bot):
        """CI: state_started=True -> _expire_timer debe retornar sin hacer nada.

        Args:
            fresh_manager (_type_): _description_
            mock_bot (_type_): _description_
        """
        with patch.object(_game_orch_mod, "LOBBY_EXPIRE", 0.01):
            state = LobbyState(
                game_id=1,
                group_chat_id=-100,
                host_telegram_id=999,
                host_name="Host",
                message_chat_id=-100,
                message_id=1,
                started=True,
            )
            fresh_manager._lobbies[-100] = state

            await fresh_manager._expire_timer(state, mock_bot)
            await asyncio.sleep(0.02)

            # No debe haber eliminado el mensaje del lobby
            mock_bot.delete_message.assert_not_awaited()

            # No debe haber enviado elmensaje de "cerrado"
            mock_bot.send_message.assert_not_awaited()

            # No debe haber limpiado el lobby del dict
            assert fresh_manager.has_lobby(-100)

    @patch.object(_game_orch_mod, "async_session_factory")
    @patch.object(_game_orch_mod, "GameRepository")
    async def test_expire_timer_cancels_when_not_started(
        self, mock_repo_cls, mock_session_factory, fresh_manager, mock_bot
    ):
        """CI: state.started=False -> _expire_timer debe cancelar partida.

        Args:
            mock_repo_cls (_type_): _description_
            mock_session_factory (_type_): _description_
            mock_bot (_type_): _description_
        """
        with patch.object(_game_orch_mod, "LOBBY_EXPIRE", 0.01):
            mock_session = MagicMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session

            mock_repo = AsyncMock()
            mock_db_game = MagicMock()
            mock_db_game.status = "lobby"
            mock_repo.get_by_id.return_value = mock_db_game
            mock_repo_cls.return_value = mock_repo

            state = LobbyState(
                game_id=1,
                group_chat_id=-100,
                host_telegram_id=999,
                host_name="Host",
                message_chat_id=-100,
                message_id=1,
                started=False,
            )
            fresh_manager._lobbies[-100] = state

            await fresh_manager._expire_timer(state, mock_bot)
            await asyncio.sleep(0.02)

            # Debe haber eliminado el mensaje del lobby
            mock_bot.delete_message.assert_awaited_once_with(
                chat_id=state.message_chat_id, message_id=state.message_id
            )

            # Debe haber actualizado el estado en DB a "cancelled"
            mock_repo.update_game_status.assert_awaited_once_with(
                mock_db_game,
                "cancelled",
            )
            # Debe haber enviado mensaje de cerrado
            mock_bot.send_message.assert_awaited_once_with(
                state.group_chat_id,
                "⌛ <b>Lobby cerrado por inactividad.</b>",
            )
            # Debe haber limpiado el lobby del dict
            assert not fresh_manager.has_lobby(-100)

    @pytest.mark.asyncio
    async def test_expire_timer_cancelled_error_caught(
        self,
        fresh_manager,
        mock_bot,
    ):
        """C1: Si la tarea es cancelada externamente, CancelledError se captura.

        Args:
            fresh_manager (_type_): _description_
            mock_bot (_type_): _description_
        """
        with patch.object(_game_orch_mod, "LOBBY_EXPIRE", 0.5):
            state = LobbyState(
                game_id=1,
                group_chat_id=-100,
                host_telegram_id=999,
                host_name="Host",
                message_chat_id=-100,
                message_id=1,
                started=False,
            )
            fresh_manager._lobbies[-100] = state
            state.expire_task = asyncio.create_task(fresh_manager._expire_timer(state, mock_bot))
            # Cancelar antes de que expire
            state.expire_task.cancel()
            await asyncio.sleep(0.1)
            # No debe haber hecho nada porque ya fue cancelado

            mock_bot.delete_message.assert_not_awaited()
            # El lobby debe seguir existiendo (no se llamo a _cleanup)
            assert fresh_manager.has_lobby(-100)
