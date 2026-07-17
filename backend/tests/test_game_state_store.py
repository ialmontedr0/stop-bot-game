import json

import pytest
from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.engine import async_session_factory
from src.db.models import Base, GameStateCache
from src.services.game_orchestrator import LobbyState
from src.services.game_state_store import (
    PgGameStateStore,
    dict_to_lobby,
    dict_to_round,
    lobby_to_dict,
    round_to_dict,
)
from src.services.round_manager import CATEGORIES, RoundState


# ── Fixture para PgGameStateStore con SQLite in-memory ──────────────────────


@pytest.fixture
async def pg_store():
    # SQLite in-memory engine for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    store = PgGameStateStore(session_factory=session_factory)
    yield store
    await engine.dispose()


# ── Test LobbyState serialization ───────────────────────────────────────────


class TestLobbySerialization:
    def test_lobby_to_dict_roundtrip(self):
        original = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="Host",
            message_chat_id=-100,
            message_id=42,
            player_telegram_ids=[999, 888],
            player_display_names=["Host", "Player2"],
            started=False,
        )
        data = lobby_to_dict(original)
        restored = dict_to_lobby(data)
        assert restored.game_id == original.game_id
        assert restored.group_chat_id == original.group_chat_id
        assert restored.host_telegram_id == original.host_telegram_id
        assert restored.host_name == original.host_name
        assert restored.message_chat_id == original.message_chat_id
        assert restored.message_id == original.message_id
        assert restored.player_telegram_ids == original.player_telegram_ids
        assert restored.player_display_names == original.player_display_names
        assert restored.started == original.started

    def test_lobby_serializable_to_json(self):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="Host",
            message_chat_id=-100,
            message_id=42,
        )
        data = lobby_to_dict(state)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = dict_to_lobby(parsed)
        assert restored.game_id == 1
        assert restored.group_chat_id == -100

    def test_lobby_serialization_omits_non_serializable(self):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="Host",
            message_chat_id=-100,
            message_id=42,
        )
        data = lobby_to_dict(state)
        assert "expire_task" not in data
        assert "animation_task" not in data
        assert "auto_start_task" not in data
        assert "start_lock" not in data

    def test_lobby_started_flag(self):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="Host",
            message_chat_id=-100,
            message_id=42,
            started=True,
        )
        data = lobby_to_dict(state)
        assert data["started"] is True
        restored = dict_to_lobby(data)
        assert restored.started is True

    def test_lobby_empty_player_lists(self):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="Host",
            message_chat_id=-100,
            message_id=42,
            player_telegram_ids=[],
            player_display_names=[],
        )
        data = lobby_to_dict(state)
        restored = dict_to_lobby(data)
        assert restored.player_telegram_ids == []
        assert restored.player_display_names == []


# ── Test RoundState serialization ────────────────────────────────────────────


def _make_round_state(**kwargs) -> RoundState:
    defaults = dict(
        game_id=1,
        group_chat_id=-100,
        round_number=1,
        letter="A",
        categories=CATEGORIES,
        message_chat_id=-100,
        message_id=42,
        host_telegram_id=999,
        total_players=2,
        player_names={111: "Alice", 222: "Bob"},
    )
    defaults.update(kwargs)
    return RoundState(**defaults)


class TestRoundSerialization:
    def test_round_to_dict_roundtrip(self):
        original = _make_round_state(
            submitted_player_ids={111},
            complete_player_ids={111},
            first_completer_id=111,
            first_completer_db_id=1,
            first_completer_name="Alice",
            stop_presses=3,
            validation_mode="local",
        )
        data = round_to_dict(original)
        restored = dict_to_round(data)
        assert restored.game_id == original.game_id
        assert restored.round_number == original.round_number
        assert restored.letter == original.letter
        assert restored.categories == original.categories
        assert restored.submitted_player_ids == original.submitted_player_ids
        assert restored.complete_player_ids == original.complete_player_ids
        assert restored.first_completer_id == original.first_completer_id
        assert restored.first_completer_db_id == original.first_completer_db_id
        assert restored.first_completer_name == original.first_completer_name
        assert restored.stop_presses == original.stop_presses
        assert restored.total_players == original.total_players
        assert restored.validation_mode == original.validation_mode

    def test_round_player_names_roundtrip(self):
        original = _make_round_state(player_names={111: "Alice", 222: "Bob"})
        data = round_to_dict(original)
        restored = dict_to_round(data)
        assert restored.player_names == {111: "Alice", 222: "Bob"}

    def test_round_serializable_to_json(self):
        state = _make_round_state()
        data = round_to_dict(state)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = dict_to_round(parsed)
        assert restored.game_id == 1
        assert restored.letter == "A"
        assert restored.categories == CATEGORIES

    def test_round_omits_task_fields(self):
        state = _make_round_state()
        data = round_to_dict(state)
        assert "timer_task" not in data
        assert "letter_timeout_task" not in data
        assert "update_task" not in data
        assert "inter_round_timeout_task" not in data

    def test_round_sets_convert_to_lists(self):
        state = _make_round_state(
            submitted_player_ids={111, 222},
            complete_player_ids={111},
        )
        data = round_to_dict(state)
        assert isinstance(data["submitted_player_ids"], list)
        assert isinstance(data["complete_player_ids"], list)
        assert set(data["submitted_player_ids"]) == {111, 222}
        assert set(data["complete_player_ids"]) == {111}

    def test_round_empty_sets(self):
        state = _make_round_state()
        data = round_to_dict(state)
        restored = dict_to_round(data)
        assert restored.submitted_player_ids == set()
        assert restored.complete_player_ids == set()
        assert restored.submission_order == []

    def test_round_default_fields(self):
        state = _make_round_state()
        data = round_to_dict(state)
        restored = dict_to_round(data)
        assert restored.cancelled is False
        assert restored.validation_mode == "local"
        assert restored.include_n is False
        assert restored.round_time == 60
        assert restored.total_rounds == 5


# ── Test PgGameStateStore CRUD ──────────────────────────────────────────────


class TestPgStore:
    async def test_set_and_get(self, pg_store):
        await pg_store.set("test:key1", "hello")
        result = await pg_store.get("test:key1")
        assert result == "hello"

    async def test_get_nonexistent(self, pg_store):
        result = await pg_store.get("test:nonexistent")
        assert result is None

    async def test_overwrite(self, pg_store):
        await pg_store.set("test:key", "first")
        await pg_store.set("test:key", "second")
        result = await pg_store.get("test:key")
        assert result == "second"

    async def test_delete(self, pg_store):
        await pg_store.set("test:key", "value")
        await pg_store.delete("test:key")
        result = await pg_store.get("test:key")
        assert result is None

    async def test_delete_nonexistent(self, pg_store):
        await pg_store.delete("test:nonexistent")
        # Should not raise

    async def test_keys_with_prefix(self, pg_store):
        await pg_store.set("cat:a", "1")
        await pg_store.set("cat:b", "2")
        await pg_store.set("dog:c", "3")
        keys = await pg_store.keys("cat:")
        assert sorted(keys) == ["cat:a", "cat:b"]

    async def test_get_all_with_prefix(self, pg_store):
        await pg_store.set("lobby:1", '{"gcid": -100}')
        await pg_store.set("lobby:2", '{"gcid": -200}')
        await pg_store.set("round:1", '{"gid": 1}')
        result = await pg_store.get_all("lobby:")
        assert len(result) == 2
        assert "lobby:1" in result
        assert "lobby:2" in result
        assert json.loads(result["lobby:1"]) == {"gcid": -100}

    async def test_get_all_no_match(self, pg_store):
        await pg_store.set("lobby:1", "x")
        result = await pg_store.get_all("round:")
        assert result == {}

    async def test_clear_all(self, pg_store):
        await pg_store.set("a:1", "x")
        await pg_store.set("a:2", "y")
        await pg_store.clear_all()
        assert await pg_store.get("a:1") is None
        assert await pg_store.get("a:2") is None


# ── Test Lobby CRUD via PgStore ─────────────────────────────────────────────


class TestPgStoreLobby:
    async def test_set_and_get_lobby(self, pg_store):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="Host",
            message_chat_id=-100,
            message_id=42,
            player_telegram_ids=[999, 888],
            player_display_names=["Host", "P2"],
        )
        await pg_store.set_lobby(state)
        restored = await pg_store.get_lobby(-100)
        assert restored is not None
        assert restored.game_id == 1
        assert restored.group_chat_id == -100
        assert restored.host_telegram_id == 999
        assert restored.player_telegram_ids == [999, 888]

    async def test_get_nonexistent_lobby(self, pg_store):
        result = await pg_store.get_lobby(-999)
        assert result is None

    async def test_delete_lobby(self, pg_store):
        state = LobbyState(
            game_id=1,
            group_chat_id=-100,
            host_telegram_id=999,
            host_name="Host",
            message_chat_id=-100,
            message_id=42,
        )
        await pg_store.set_lobby(state)
        await pg_store.delete_lobby(-100)
        assert await pg_store.get_lobby(-100) is None

    async def test_get_all_lobbies(self, pg_store):
        s1 = LobbyState(game_id=1, group_chat_id=-100, host_telegram_id=999, host_name="H1", message_chat_id=-100, message_id=1)
        s2 = LobbyState(game_id=2, group_chat_id=-200, host_telegram_id=888, host_name="H2", message_chat_id=-200, message_id=2)
        await pg_store.set_lobby(s1)
        await pg_store.set_lobby(s2)
        all_lobbies = await pg_store.get_all_lobbies()
        assert len(all_lobbies) == 2
        assert -100 in all_lobbies
        assert -200 in all_lobbies

    async def test_overwrite_lobby(self, pg_store):
        s1 = LobbyState(game_id=1, group_chat_id=-100, host_telegram_id=999, host_name="H1", message_chat_id=-100, message_id=1)
        s2 = LobbyState(game_id=2, group_chat_id=-100, host_telegram_id=888, host_name="H2", message_chat_id=-100, message_id=2)
        await pg_store.set_lobby(s1)
        await pg_store.set_lobby(s2)
        restored = await pg_store.get_lobby(-100)
        assert restored.game_id == 2
        assert restored.host_name == "H2"


# ── Test Round CRUD via PgStore ─────────────────────────────────────────────


class TestPgStoreRound:
    async def test_set_and_get_round(self, pg_store):
        state = _make_round_state()
        await pg_store.set_round(state)
        restored = await pg_store.get_round(1)
        assert restored is not None
        assert restored.game_id == 1
        assert restored.letter == "A"

    async def test_get_nonexistent_round(self, pg_store):
        result = await pg_store.get_round(999)
        assert result is None

    async def test_delete_round(self, pg_store):
        state = _make_round_state()
        await pg_store.set_round(state)
        await pg_store.delete_round(1)
        assert await pg_store.get_round(1) is None

    async def test_get_all_rounds(self, pg_store):
        s1 = _make_round_state(game_id=1, group_chat_id=-100)
        s2 = _make_round_state(game_id=2, group_chat_id=-200)
        await pg_store.set_round(s1)
        await pg_store.set_round(s2)
        all_r = await pg_store.get_all_rounds()
        assert len(all_r) == 2

    async def test_letter_pending_crud(self, pg_store):
        state = _make_round_state(game_id=1)
        await pg_store.set_letter_pending(state)
        restored = await pg_store.get_letter_pending(1)
        assert restored is not None
        assert restored.game_id == 1
        await pg_store.delete_letter_pending(1)
        assert await pg_store.get_letter_pending(1) is None

    async def test_rounds_by_group_crud(self, pg_store):
        await pg_store.set_rounds_by_group(-100, 42)
        assert await pg_store.get_rounds_by_group(-100) == 42
        all_rbg = await pg_store.get_all_rounds_by_group()
        assert all_rbg == {-100: 42}
        await pg_store.delete_rounds_by_group(-100)
        assert await pg_store.get_rounds_by_group(-100) is None


# ── Typo check helper ────────────────────────────────────────────────────────


def test_restored_field_name_typo():
    """Verify the fixture helper uses correct field names (catches rst/restored typos)."""
    data = lobby_to_dict(
        LobbyState(game_id=1, group_chat_id=-100, host_telegram_id=999, host_name="H", message_chat_id=-100, message_id=1)
    )
    assert "group_chat_id" in data
    assert "host_telegram_id" in data

    data = round_to_dict(_make_round_state())
    assert "submitted_player_ids" in data
    assert "complete_player_ids" in data
    assert "player_names" in data
