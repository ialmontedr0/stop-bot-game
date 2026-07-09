import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import Player
from src.services.round_manager import (
    ALPHABET,
    ANSWER_REGEX,
    CATEGORIES,
    NUM_STOP_BUTTONS,
    ROUND_DURATION,
    TOTAL_ROUNDS,
    RoundManager,
    RoundState,
    parse_answers,
)


@pytest.fixture(autouse=True)
def mock_db():
    rm_mod = sys.modules["src.services.round_manager"]
    with patch.object(rm_mod, "async_session_factory") as m:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_result.one_or_none.return_value = None
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        m.return_value.__aenter__.return_value = mock_session
        yield


# ── ANSWER_REGEX ────────────────────────────────────────────────────────────


class TestAnswerRegex:
    def test_basic_match(self):
        m = ANSWER_REGEX.match("Nombre: Juan")
        assert m is not None
        assert m.group(1).strip() == "Nombre"
        assert m.group(2).strip() == "Juan"

    def test_match_with_spaces(self):
        m = ANSWER_REGEX.match("  País o Ciudad :  Buenos Aires  ")
        assert m is not None
        assert m.group(1).strip() == "País o Ciudad"
        assert m.group(2).strip() == "Buenos Aires"

    def test_match_with_empty_value(self):
        m = ANSWER_REGEX.match("Color: ")
        assert m is not None
        assert m.group(1).strip() == "Color"
        assert m.group(2).strip() == ""

    def test_multiline(self):
        text = "Nombre: Juan\nColor: Rojo\nAnimal: Perro"
        matches = ANSWER_REGEX.findall(text)
        assert len(matches) == 3

    def test_no_match_without_colon(self):
        m = ANSWER_REGEX.match("Nombre Juan")
        assert m is None


# ── parse_answers ──────────────────────────────────────────────────────────


class TestParseAnswers:
    def test_parses_single_answer(self):
        result = parse_answers("Nombre: Juan", CATEGORIES)
        assert result == {"Nombre": "Juan"}

    def test_parses_multiple_answers(self):
        text = "Nombre: Juan\nColor: Rojo\nFruta: Manzana"
        result = parse_answers(text, CATEGORIES)
        assert result["Nombre"] == "Juan"
        assert result["Color"] == "Rojo"
        assert result["Fruta"] == "Manzana"

    def test_case_insensitive_category(self):
        result = parse_answers("nombre: juan\nCOLOR: rojo", CATEGORIES)
        assert result["Nombre"] == "juan"
        assert result["Color"] == "rojo"

    def test_ignores_unknown_categories(self):
        result = parse_answers("Nombre: Juan\nUnknown: Value", CATEGORIES)
        assert result == {"Nombre": "Juan"}

    def test_empty_input(self):
        result = parse_answers("", CATEGORIES)
        assert result == {}

    def test_no_valid_categories(self):
        result = parse_answers("Foo: Bar\nBaz: Qux", CATEGORIES)
        assert result == {}

    def test_whitespace_handling(self):
        text = "  Nombre  :  Juan  \n  Color:Rojo  "
        result = parse_answers(text, CATEGORIES)
        assert result["Nombre"] == "Juan"
        assert result["Color"] == "Rojo"

    def test_returns_only_valid_categories(self):
        text = "Nombre: Juan\nApellido: Pérez\nColor: Azul"
        result = parse_answers(text, CATEGORIES)
        assert len(result) == 3
        assert "Nombre" in result
        assert "Apellido" in result
        assert "Color" in result


# ── RoundState ─────────────────────────────────────────────────────────────


class TestRoundState:
    def test_defaults(self):
        state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=42,
            total_players=3,
            host_telegram_id=111,
        )
        assert state.submitted_player_ids == set()
        assert state.complete_player_ids == set()
        assert state.first_completer_id is None
        assert state.first_completer_name is None
        assert state.stop_presses == 0
        assert state.stop_message_chat_id is None
        assert state.stop_message_id is None
        assert state.player_names == {}


# ── RoundManager ───────────────────────────────────────────────────────────


@pytest.fixture
def fresh_round_manager():
    return RoundManager()


class TestRoundManagerQueries:
    def test_get_active_round_none(self, fresh_round_manager):
        assert fresh_round_manager.get_active_round(1) is None

    def test_get_active_round_by_group_none(self, fresh_round_manager):
        assert fresh_round_manager.get_active_round_by_group(-100) is None

    def test_get_active_round_after_setup(self, fresh_round_manager):
        state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=42,
            total_players=2,
            host_telegram_id=111,
        )
        fresh_round_manager._rounds[1] = state
        assert fresh_round_manager.get_active_round(1) is state
        assert fresh_round_manager.get_active_round_by_group(-100) is state

    def test_get_active_round_by_group_with_multiple(self, fresh_round_manager):
        s1 = RoundState(
            game_id=1,
            group_chat_id=-1,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-1,
            message_id=1,
            total_players=2,
            host_telegram_id=111,
        )
        s2 = RoundState(
            game_id=2,
            group_chat_id=-2,
            round_number=1,
            letter="B",
            categories=CATEGORIES,
            message_chat_id=-2,
            message_id=2,
            total_players=2,
            host_telegram_id=222,
        )
        fresh_round_manager._rounds[1] = s1
        fresh_round_manager._rounds[2] = s2
        assert fresh_round_manager.get_active_round_by_group(-2) is s2


class TestStartRound:
    @pytest.mark.asyncio
    async def test_start_round_creates_state(self, fresh_round_manager):
        bot = AsyncMock()
        msg = MagicMock()
        msg.chat.id = -100
        msg.message_id = 42
        bot.send_message.return_value = msg

        await fresh_round_manager.start_round(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="F",
            total_players=3,
            player_names={111: "Alice", 222: "Bob", 333: "Charlie"},
            bot=bot,
        )

        state = fresh_round_manager.get_active_round(1)
        assert state is not None
        assert state.round_number == 1
        assert state.letter == "F"
        assert state.total_players == 3
        assert state.player_names == {111: "Alice", 222: "Bob", 333: "Charlie"}
        assert state.timer_task is not None
        assert not state.timer_task.done()
        state.timer_task.cancel()
        try:
            await state.timer_task
        except asyncio.CancelledError:
            pass
        bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_round_replaces_existing(self, fresh_round_manager):
        bot = AsyncMock()
        msg = MagicMock()
        msg.chat.id = -100
        msg.message_id = 42
        bot.send_message.return_value = msg

        await fresh_round_manager.start_round(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            total_players=2,
            player_names={111: "A"},
            bot=bot,
        )

        old_state = fresh_round_manager.get_active_round(1)
        old_timer = old_state.timer_task

        await fresh_round_manager.start_round(
            game_id=1,
            group_chat_id=-100,
            round_number=2,
            letter="B",
            total_players=2,
            player_names={111: "A"},
            bot=bot,
        )

        new_state = fresh_round_manager.get_active_round(1)
        assert new_state is not old_state
        assert new_state.round_number == 2
        assert new_state.letter == "B"
        old_timer.cancel()
        try:
            await old_timer
        except asyncio.CancelledError:
            pass
        new_state.timer_task.cancel()
        try:
            await new_state.timer_task
        except asyncio.CancelledError:
            pass


class TestSubmitAnswers:
    @pytest.mark.asyncio
    async def test_submit_answers_no_active_round(self, fresh_round_manager):
        player = MagicMock(spec=Player)
        result = await fresh_round_manager.submit_answers(
            game_id=1, player=player, text="Nombre: Juan", bot=AsyncMock()
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_submit_answers_invalid_format(self, fresh_round_manager):
        bot = AsyncMock()
        msg = MagicMock()
        msg.chat.id = -100
        msg.message_id = 42
        bot.send_message.return_value = msg

        await fresh_round_manager.start_round(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            total_players=2,
            player_names={111: "Alice"},
            bot=bot,
        )

        state = fresh_round_manager.get_active_round(1)
        state.timer_task.cancel()
        try:
            await state.timer_task
        except asyncio.CancelledError:
            pass

        player = MagicMock(spec=Player)
        player.telegram_id = 111
        player.id = 1
        player.first_name = "Alice"

        result = await fresh_round_manager.submit_answers(
            game_id=1,
            player=player,
            text="some random text",
            bot=bot,
        )
        assert result is False


class TestPressStop:
    @pytest.mark.asyncio
    async def test_press_stop_no_active_round(self, fresh_round_manager):
        callback = AsyncMock()
        await fresh_round_manager.press_stop(
            game_id=1,
            player_id=111,
            callback=callback,
            bot=AsyncMock(),
        )
        callback.answer.assert_awaited_with("❌ Esta ronda ya terminó.", show_alert=False)

    @pytest.mark.asyncio
    async def test_press_stop_not_first_completer(self, fresh_round_manager):
        bot = AsyncMock()
        msg = MagicMock()
        msg.chat.id = -100
        msg.message_id = 42
        bot.send_message.return_value = msg

        await fresh_round_manager.start_round(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            total_players=2,
            player_names={111: "Alice", 222: "Bob"},
            bot=bot,
        )

        state = fresh_round_manager.get_active_round(1)
        state.timer_task.cancel()
        try:
            await state.timer_task
        except asyncio.CancelledError:
            pass
        state.first_completer_id = 111

        callback = AsyncMock()
        await fresh_round_manager.press_stop(
            game_id=1,
            player_id=222,
            callback=callback,
            bot=bot,
        )
        callback.answer.assert_awaited_with(
            "❌ Solo puedes usar Stop si completaste todas las categorías.",
            show_alert=False,
        )


class TestCloseRound:
    @pytest.mark.asyncio
    async def test_close_round_removes_state(self, fresh_round_manager):
        import sys

        rm_mod = sys.modules["src.services.round_manager"]

        bot = AsyncMock()
        msg = MagicMock()
        msg.chat.id = -100
        msg.message_id = 42
        bot.send_message.return_value = msg

        await fresh_round_manager.start_round(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            total_players=1,
            player_names={111: "Alice"},
            bot=bot,
        )

        state = fresh_round_manager.get_active_round(1)
        state.timer_task = None

        fresh_round_manager._transition_next_round = AsyncMock()

        mock_db_round = MagicMock()
        mock_db_round.id = 1

        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_active_round.return_value = mock_db_round
            mock_repo.get_answers_by_player = AsyncMock(return_value={})
            mock_repo.get_game_player_by_telegram = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            await fresh_round_manager._close_round(1, "stop", bot)

        assert fresh_round_manager.get_active_round(1) is None

    @pytest.mark.asyncio
    async def test_close_round_cancels_timer(self, fresh_round_manager):
        import sys

        rm_mod = sys.modules["src.services.round_manager"]

        bot = AsyncMock()
        msg = MagicMock()
        msg.chat.id = -100
        msg.message_id = 42
        bot.send_message.return_value = msg

        fresh_round_manager._get_leader_telegram_id = AsyncMock(return_value=None)
        fresh_round_manager._get_standings = AsyncMock(return_value=[])
        fresh_round_manager._start_next_round_with_random = AsyncMock()

        await fresh_round_manager.start_round(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            total_players=1,
            player_names={111: "Alice"},
            bot=bot,
        )

        state = fresh_round_manager.get_active_round(1)
        timer = state.timer_task

        mock_db_round = MagicMock()
        mock_db_round.id = 1

        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_active_round.return_value = mock_db_round
            mock_repo.get_answers_by_player = AsyncMock(return_value={})
            mock_repo.get_game_player_by_telegram = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            await fresh_round_manager._close_round(1, "stop", bot)

        try:
            await timer
        except asyncio.CancelledError:
            pass
        assert timer.cancelled()


class TestParseAnswersFunction:
    def test_parse_answers_all_categories(self):
        text = "\n".join(f"{cat}: test" for cat in CATEGORIES)
        result = parse_answers(text, CATEGORIES)
        assert len(result) == len(CATEGORIES)
        for cat in CATEGORIES:
            assert result[cat] == "test"

    def test_parse_answers_partial(self):
        text = "Nombre: Juan\nColor: Rojo"
        result = parse_answers(text, CATEGORIES)
        assert len(result) == 2

    def test_parse_answers_case_insensitive(self):
        text = "NOMBRE: Juan\ncolor: rojo\nPAÍS: Bogotá"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Juan"
        assert result.get("Color") == "rojo"
        assert result.get("País") == "Bogotá"


class TestParseAnswersEdgeCases:
    def test_empty_input(self):
        assert parse_answers("", CATEGORIES) == {}

    def test_only_whitespace(self):
        assert parse_answers("   \n  \t  ", CATEGORIES) == {}

    def test_no_colon(self):
        result = parse_answers("Nombre Ana\nColor Rojo", CATEGORIES)
        assert result == {}

    def test_malformed_category(self):
        result = parse_answers(": valor\nNombre: Ana", CATEGORIES)
        assert "Nombre" in result
        assert result["Nombre"] == "Ana"

    def test_extra_whitespace_in_value(self):
        result = parse_answers("Nombre:   Juan   ", CATEGORIES)
        assert result.get("Nombre") == "Juan"

    def test_multiline_value_not_allowed(self):
        text = "Nombre: Juan\n  Perez\nColor: Rojo"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Juan"
        assert "Color" in result

    def test_repeated_category_overwrites(self):
        text = "Nombre: Ana\nNombre: Luis"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Luis"

    def test_accent_insensitive_category(self):
        result = parse_answers("pais: Argentina", CATEGORIES)
        assert "País" in result

    def test_unknown_categories_ignored(self):
        text = "Nombre: Juan\nFakeCategory: valor\nColor: Rojo"
        result = parse_answers(text, CATEGORIES)
        assert "Nombre" in result
        assert "Color" in result
        assert "FakeCategory" not in result


class TestRoundManagerConstants:
    def test_constants(self):
        assert NUM_STOP_BUTTONS == 10
        assert ROUND_DURATION == 60
        assert TOTAL_ROUNDS == 5
        assert len(ALPHABET) == 26
        assert "Ñ" not in ALPHABET
