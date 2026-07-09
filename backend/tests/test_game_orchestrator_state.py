from unittest.mock import MagicMock

from src.services.game_orchestrator import LobbyManager, LobbyState


class TestLobbyStateTransitions:
    def test_initial_state(self):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100123,
            host_telegram_id=111,
            host_name="TestHost",
            message_chat_id=-100123,
            message_id=1,
        )
        assert state.game_id == 1
        assert state.group_chat_id == -100123
        assert state.host_telegram_id == 111
        assert state.started is False
        assert state.player_telegram_ids == []

    def test_has_lobby_checks_correctly(self):
        manager = LobbyManager()
        assert manager.has_lobby(-100123) is False
        state = LobbyState(
            game_id=1,
            group_chat_id=-100123,
            host_telegram_id=111,
            host_name="H",
            message_chat_id=-100123,
            message_id=1,
        )
        manager._lobbies[-100123] = state
        assert manager.has_lobby(-100123) is True

    def test_get_lobby_returns_none(self):
        manager = LobbyManager()
        assert manager.get_lobby(99999) is None

    def test_get_lobby_finds(self):
        manager = LobbyManager()
        state = LobbyState(
            game_id=1,
            group_chat_id=-100123,
            host_telegram_id=111,
            host_name="H",
            message_chat_id=-100123,
            message_id=1,
        )
        manager._lobbies[-100123] = state
        assert manager.get_lobby(-100123) is state

    def test_get_lobby_by_game(self):
        manager = LobbyManager()
        state = LobbyState(
            game_id=42,
            group_chat_id=-100123,
            host_telegram_id=111,
            host_name="H",
            message_chat_id=-100123,
            message_id=1,
        )
        manager._lobbies[-100123] = state
        assert manager.get_lobby_by_game(42) is state
        assert manager.get_lobby_by_game(99) is None

    def test_multiple_lobbies(self):
        manager = LobbyManager()
        s1 = LobbyState(
            game_id=1,
            group_chat_id=-1001,
            host_telegram_id=111,
            host_name="A",
            message_chat_id=-1001,
            message_id=1,
        )
        s2 = LobbyState(
            game_id=2,
            group_chat_id=-1002,
            host_telegram_id=222,
            host_name="B",
            message_chat_id=-1002,
            message_id=2,
        )
        manager._lobbies[-1001] = s1
        manager._lobbies[-1002] = s2
        assert len(manager._lobbies) == 2
        assert manager.get_lobby(-1001) is s1
        assert manager.get_lobby(-1002) is s2

    def test_cleanup_cancels_tasks(self):
        manager = LobbyManager()
        state = LobbyState(
            game_id=1,
            group_chat_id=-100123,
            host_telegram_id=111,
            host_name="H",
            message_chat_id=-100123,
            message_id=1,
        )
        task = MagicMock()
        task.done.return_value = False
        state.expire_task = task
        state.animation_task = task
        state.auto_start_task = task
        manager._lobbies[-100123] = state

        manager._cleanup(state)
        assert task.cancel.called
        assert task.cancel.call_count == 3
