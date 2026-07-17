import asyncio
import contextlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramRetryAfter

import pytest

from src.db.models import Player
from src.services.round_manager import (
    ALPHABET,
    CATEGORIES,
    LINE_REGEX,
    NUM_STOP_BUTTONS,
    ROUND_DURATION,
    TOTAL_ROUNDS,
    RoundManager,
    RoundState,
    get_alphabet,
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


# ── LINE_REGEX ──────────────────────────────────────────────────────────────


class TestLineRegex:
    def test_basic_match(self):
        m = LINE_REGEX.match("Nombre: Juan")
        assert m is not None
        assert m.group(1).strip() == "Nombre"
        assert m.group(2).strip() == "Juan"

    def test_match_with_spaces(self):
        m = LINE_REGEX.match("  País o Ciudad :  Buenos Aires  ")
        assert m is not None
        assert m.group(1).strip() == "País o Ciudad"
        assert m.group(2).strip() == "Buenos Aires"

    def test_match_with_empty_value(self):
        m = LINE_REGEX.match("Color: ")
        assert m is not None
        assert m.group(1).strip() == "Color"
        assert m.group(2).strip() == ""

    def test_no_match_without_colon(self):
        m = LINE_REGEX.match("Nombre Juan")
        assert m is None


# ── parse_answers ──────────────────────────────────────────────────────────


class TestParseAnswers:
    def test_parses_single_answer(self):
        result = parse_answers("Nombre: Juan", CATEGORIES)
        assert result["Nombre"] == "Juan"
        for cat in CATEGORIES:
            if cat != "Nombre":
                assert result[cat] == "", f"{cat} should be empty"

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
        assert result["Nombre"] == "Juan"
        for cat in CATEGORIES:
            if cat != "Nombre":
                assert result[cat] == ""

    def test_empty_input(self):
        result = parse_answers("", CATEGORIES)
        assert result == {cat: "" for cat in CATEGORIES}

    def test_no_valid_categories(self):
        result = parse_answers("Foo: Bar\nBaz: Qux", CATEGORIES)
        assert result == {cat: "" for cat in CATEGORIES}

    def test_whitespace_handling(self):
        text = "  Nombre  :  Juan  \n  Color:Rojo  "
        result = parse_answers(text, CATEGORIES)
        assert result["Nombre"] == "Juan"
        assert result["Color"] == "Rojo"

    def test_returns_only_valid_categories(self):
        text = "Nombre: Juan\nApellido: Pérez\nColor: Azul"
        result = parse_answers(text, CATEGORIES)
        assert result["Nombre"] == "Juan"
        assert result["Apellido"] == "Pérez"
        assert result["Color"] == "Azul"
        for cat in CATEGORIES:
            if cat not in ("Nombre", "Apellido", "Color"):
                assert result[cat] == ""


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
        with contextlib.suppress(asyncio.CancelledError):
            await state.timer_task
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
        with contextlib.suppress(asyncio.CancelledError):
            await old_timer
        new_state.timer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await new_state.timer_task


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
        with contextlib.suppress(asyncio.CancelledError):
            await state.timer_task

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
        with contextlib.suppress(asyncio.CancelledError):
            await state.timer_task
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

        with contextlib.suppress(asyncio.CancelledError):
            await timer
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
        assert result["Nombre"] == "Juan"
        assert result["Color"] == "Rojo"
        for cat in CATEGORIES:
            if cat not in ("Nombre", "Color"):
                assert result[cat] == ""

    def test_parse_answers_case_insensitive(self):
        text = "NOMBRE: Juan\ncolor: rojo\nPAÍS: Bogotá"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Juan"
        assert result.get("Color") == "rojo"
        assert result.get("País") == "Bogotá"


class TestParseAnswersPlural:
    """M5: parse_answers debe matchear plurales."""

    def test_plural_paises(self):
        result = parse_answers("Paises: Argentina", CATEGORIES)
        assert result.get("País") == "Argentina"

    def test_plural_colores(self):
        result = parse_answers("Colores: Azul", CATEGORIES)
        assert result.get("Color") == "Azul"

    def test_plural_frutas(self):
        result = parse_answers("Frutas: Manzana", CATEGORIES)
        assert result.get("Fruta") == "Manzana"

    def test_plural_nombres(self):
        result = parse_answers("Nombres: Juan", CATEGORIES)
        assert result.get("Nombre") == "Juan"

    def test_plural_animales(self):
        result = parse_answers("Animales: Perro", CATEGORIES)
        assert result.get("Animal") == "Perro"

    def test_plural_cosas(self):
        result = parse_answers("Cosas: Mesa", CATEGORIES)
        assert result.get("Cosa") == "Mesa"

    def test_plural_artistas(self):
        result = parse_answers("Artistas: Shakira", CATEGORIES)
        assert result.get("Artista") == "Shakira"

    def test_apellidos(self):
        result = parse_answers("Apellidos: García", CATEGORIES)
        assert result.get("Apellido") == "García"


class TestParseAnswersEdgeCases:
    def test_empty_input(self):
        assert parse_answers("", CATEGORIES) == {cat: "" for cat in CATEGORIES}

    def test_only_whitespace(self):
        assert parse_answers("   \n  \t  ", CATEGORIES) == {cat: "" for cat in CATEGORIES}

    def test_no_colon(self):
        result = parse_answers("Nombre Ana\nColor Rojo", CATEGORIES)
        assert result == {cat: "" for cat in CATEGORIES}

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

    def test_blank_category_does_not_swallow_next(self):
        text = "País: \nArtista: R"
        result = parse_answers(text, CATEGORIES)
        assert "País" not in result or result.get("País") == ""
        assert result.get("Artista") == "R"


class TestInlineCategories:
    """E7: dos categorías en la misma línea."""

    def test_two_categories_inline(self):
        text = "Nombre: Juan Color: Rojo"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Juan"
        assert result.get("Color") == "Rojo"

    def test_three_categories_inline(self):
        text = "Nombre: Juan Color: Rojo Animal: Perro"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Juan"
        assert result.get("Color") == "Rojo"
        assert result.get("Animal") == "Perro"

    def test_inline_with_regular_lines(self):
        text = "Nombre: Juan\nColor: Rojo Animal: Perro\nFruta: Manzana"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Juan"
        assert result.get("Color") == "Rojo"
        assert result.get("Animal") == "Perro"
        assert result.get("Fruta") == "Manzana"

    def test_inline_mixed_with_plural(self):
        text = "Paises: Argentina Colores: Azul"
        result = parse_answers(text, CATEGORIES)
        assert result.get("País") == "Argentina"
        assert result.get("Color") == "Azul"

    def test_value_contains_category_word_no_colon(self):
        """'Colorado' contiene 'color' pero sin ':' → no se extrae."""
        result = parse_answers("Color: Colorado", CATEGORIES)
        assert result.get("Color") == "Colorado"
        assert len(result) == len(CATEGORIES)

    def test_inline_first_category_empty_value(self):
        text = "Nombre: Color: Rojo"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Color") == "Rojo"
        assert "Nombre" in result

    def test_inline_preserves_existing_line_separated(self):
        text = "Nombre: Juan\nColor: Rojo"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Juan"
        assert result.get("Color") == "Rojo"
        assert len(result) == len(CATEGORIES)

    def test_value_with_extra_colon_not_category(self):
        """'Cosa: Tiene: valor' → no se extrae porque 'tiene' no es categoría."""
        result = parse_answers("Cosa: Tiene: valor", CATEGORIES)
        assert result.get("Cosa") == "Tiene: valor"

    def test_inline_same_category_on_same_line(self):
        text = "Color: Rojo Color: Verde"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Color") == "Rojo"

    def test_realistic_mobile_usage(self):
        """Escenario típico mobile: varias categorías en un renglón."""
        text = "Nombre: Ana Color: Azul Paises: Chile Animal: Gato"
        result = parse_answers(text, CATEGORIES)
        assert result.get("Nombre") == "Ana"
        assert result.get("Color") == "Azul"
        assert result.get("País") == "Chile"
        assert result.get("Animal") == "Gato"
        assert len(result) == len(CATEGORIES)


class TestRoundManagerConstants:
    def test_constants(self):
        assert NUM_STOP_BUTTONS == 10
        assert ROUND_DURATION == 60
        assert TOTAL_ROUNDS == 5
        assert len(ALPHABET) == 26
        assert "Ñ" not in ALPHABET


class TestHandleNextRound:
    """Verifica que handle_next_round y handle_stop_game rechacen
    calls con _letter_pending stale si ya hay una ronda en _rounds."""

    @pytest.mark.asyncio
    async def test_next_round_stale_letter_pending_with_active_round(self):
        """C2: Si _rounds[game_id] existe, handle_next_round debe rechazar."""
        rm = RoundManager()
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        pending_state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=10,
            total_players=2,
            host_telegram_id=999,
            leader_id=111,
        )
        active_state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=2,
            letter="B",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=20,
            total_players=2,
            host_telegram_id=999,
        )
        rm._letter_pending[1] = pending_state
        rm._rounds[1] = active_state

        await rm.handle_next_round(1, 111, callback, bot)

        callback.answer.assert_awaited_once_with(
            "⏳ La ronda ya está en curso. Espera a que termine.",
            show_alert=True,
        )
        # No debe avanzar a _prompt_letter_selection
        bot.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stop_game_stale_letter_pending_with_active_round(self):
        """C2: Si _rounds[game_id] existe, handle_stop_game debe rechazar."""
        rm = RoundManager()
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        pending_state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=10,
            total_players=2,
            host_telegram_id=999,
            leader_id=111,
        )
        active_state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=2,
            letter="B",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=20,
            total_players=2,
            host_telegram_id=999,
        )
        rm._letter_pending[1] = pending_state
        rm._rounds[1] = active_state

        await rm.handle_stop_game(1, 999, callback, bot)

        callback.answer.assert_awaited_once_with(
            "⏳ La ronda ya está en curso. Espera a que termine.",
            show_alert=True,
        )
        # No debe llamar a _end_game
        bot.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_next_round_only_letter_pending_proceeds(self):
        """C2: Sin _rounds[game_id], handle_next_round llama _prompt_letter_selection."""
        rm = RoundManager()
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        pending_state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=10,
            total_players=2,
            host_telegram_id=999,
            leader_id=111,
        )
        rm._letter_pending[1] = pending_state

        with patch.object(rm, "_prompt_letter_selection", AsyncMock()) as mock_prompt:
            await rm.handle_next_round(1, 111, callback, bot)

        callback.answer.assert_awaited_once_with(
            "▶️ Avanzando a la siguiente ronda...", show_alert=False
        )
        mock_prompt.assert_awaited_once_with(pending_state, bot)

    @pytest.mark.asyncio
    async def test_stop_game_only_letter_pending_proceeds(self):
        """C2: Sin _rounds[game_id], handle_stop_game llama _end_game."""
        rm = RoundManager()
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        pending_state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=10,
            total_players=2,
            host_telegram_id=999,
        )
        rm._letter_pending[1] = pending_state

        with patch.object(rm, "_end_game", AsyncMock()) as mock_end_game:
            await rm.handle_stop_game(1, 999, callback, bot)

        callback.answer.assert_awaited_once_with(
            "⏹ Partida detenida. Calculando puntuaciones...", show_alert=False
        )
        mock_end_game.assert_awaited_once_with(pending_state, bot)

    @pytest.mark.asyncio
    async def test_next_round_no_pending_state(self):
        """C2: Sin _letter_pending ni _rounds, mensaje "no activa"."""
        rm = RoundManager()
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        await rm.handle_next_round(1, 111, callback, bot)

        callback.answer.assert_awaited_once_with(
            "❌ Esta partida ya no está activa.",
            show_alert=True,
        )


class TestStopGameLockBehavior:
    """Verifica que handle_stop_game libere el lock antes de _end_game."""

    @pytest.mark.asyncio
    async def test_end_game_called_outside_lock(self):
        """A1: _end_game debe ejecutarse después de liberar el lock."""
        rm = RoundManager()
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        pending_state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=10,
            total_players=2,
            host_telegram_id=999,
        )
        rm._letter_pending[1] = pending_state

        lock_held_during_end_game = True

        original_end_game = rm._end_game

        async def end_game_wrapper(state, bot):
            nonlocal lock_held_during_end_game
            lock_held_during_end_game = rm._locks[1].locked()
            await original_end_game(state, bot)

        rm._end_game = end_game_wrapper

        import sys
        rm_mod = sys.modules["src.services.round_manager"]
        mock_gpi = MagicMock(return_value=None)

        # Evita que bot intente descargar fotos reales
        bot.get_user_profile_photos = AsyncMock(
            return_value=MagicMock(total_count=0)
        )

        # _get_standings retorna lista vacía (no hay players en el mock)
        rm._get_standings = AsyncMock(return_value=[])

        with (
            patch.object(rm, "_do_close_round_telegram", AsyncMock()),
            patch.object(rm_mod, "async_session_factory") as mock_asf,
            patch.object(rm_mod, "generate_podium_image", mock_gpi),
            patch("src.services.event_service.event_service.get_active_events", AsyncMock(return_value=[])),
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=MagicMock(status="lobby"))
            mock_session.commit = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[]))
            )
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_asf.return_value.__aenter__.return_value = mock_session
            await rm.handle_stop_game(1, 999, callback, bot)

        assert not lock_held_during_end_game, (
            "_end_game fue llamado mientras el lock estaba adquirido"
        )


class TestSubmitAnswersRaceCondition:
    """A3: DB write antes del lock (para evitar perder respuestas por AI lenta)
    con guard dentro del lock para detectar round ya cerrado."""

    @pytest.mark.asyncio
    async def test_race_with_close_round_returns_false(self, fresh_round_manager):
        """Estado removido antes de submit_answers → retorna False en early return (no state)."""
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
        with contextlib.suppress(asyncio.CancelledError):
            await state.timer_task

        player = MagicMock(spec=Player)
        player.telegram_id = 111
        player.id = 1
        player.first_name = "Alice"

        # Simular que _close_round ya removió el estado de _rounds
        fresh_round_manager._rounds.pop(1, None)

        rm_mod = sys.modules["src.services.round_manager"]
        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo

            result = await fresh_round_manager.submit_answers(
                game_id=1, player=player, text="Nombre: Juan", bot=bot,
            )
            assert result is False
            mock_repo.save_answers.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_answers_writes_db_before_lock(self, fresh_round_manager):
        """submit_answers escribe BD (antes del lock) y actualiza estado dentro del lock."""
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
        with contextlib.suppress(asyncio.CancelledError):
            await state.timer_task

        player = MagicMock(spec=Player)
        player.telegram_id = 111
        player.id = 1
        player.first_name = "Alice"

        rm_mod = sys.modules["src.services.round_manager"]
        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_db_round = MagicMock()
            mock_db_round.id = 1
            mock_repo = MagicMock()
            mock_repo.get_active_round = AsyncMock(return_value=mock_db_round)
            mock_repo.save_answers = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            full_text = (
                "Nombre: Juan\nApellido: Pérez\nColor: Rojo\nFruta: Manzana\n"
                "País: México\nArtista: Shakira\nAnimal: Perro\nCosa: Mesa"
            )
            result = await fresh_round_manager.submit_answers(
                game_id=1,
                player=player,
                text=full_text,
                bot=bot,
            )
            assert result is True
            mock_repo.save_answers.assert_awaited_once()
            assert 111 in state.submitted_player_ids
            assert 111 in state.complete_player_ids
            assert state.first_completer_id == 111

    @pytest.mark.asyncio
    async def test_db_failure_does_not_mutate_state(self, fresh_round_manager):
        """Si DB write falla (antes del lock), retorna False sin modificar estado."""
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
        with contextlib.suppress(asyncio.CancelledError):
            await state.timer_task

        player = MagicMock(spec=Player)
        player.telegram_id = 111
        player.id = 1
        player.first_name = "Alice"

        rm_mod = sys.modules["src.services.round_manager"]
        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_active_round = AsyncMock(side_effect=Exception("DB error"))
            mock_repo_cls.return_value = mock_repo

            full_text = (
                "Nombre: Juan\nApellido: Pérez\nColor: Rojo\nFruta: Manzana\n"
                "País: México\nArtista: Shakira\nAnimal: Perro\nCosa: Mesa"
            )
            result = await fresh_round_manager.submit_answers(
                game_id=1,
                player=player,
                text=full_text,
                bot=bot,
            )
            assert result is False
            assert 111 not in state.submitted_player_ids
            assert 111 not in state.complete_player_ids


class TestPersistRoundScoresRetry:
    """A4: _persist_round_scores con retry + cancelación si falla permanentemente."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self, fresh_round_manager):
        """_persist_round_scores falla 1 vez, luego funciona; juego continúa."""
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

        mock_persist = AsyncMock(side_effect=[Exception("DB error"), {111: 100}])
        fresh_round_manager._persist_round_scores = mock_persist

        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_active_round.return_value = mock_db_round
            mock_repo.get_answers_by_player = AsyncMock(return_value={})
            mock_repo.get_game_player_by_telegram = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            await fresh_round_manager._close_round(1, "stop", bot)

        assert mock_persist.await_count == 2, (
            f"_persist_round_scores debería haberse llamado 2 veces, "
            f"se llamó {mock_persist.await_count}"
        )
        fresh_round_manager._transition_next_round.assert_awaited_once()
        assert state.cancelled is False

    @pytest.mark.asyncio
    async def test_retry_cancels_game_after_3_failures(self, fresh_round_manager):
        """_persist_round_scores falla siempre → state.cancelled, no transiciona."""
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

        mock_persist = AsyncMock(side_effect=Exception("DB error persistent"))
        fresh_round_manager._persist_round_scores = mock_persist

        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_active_round.return_value = mock_db_round
            mock_repo.get_answers_by_player = AsyncMock(return_value={})
            mock_repo.get_game_player_by_telegram = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            await fresh_round_manager._close_round(1, "stop", bot)

        assert mock_persist.await_count == 3, (
            f"_persist_round_scores debería haberse llamado 3 veces, "
            f"se llamó {mock_persist.await_count}"
        )
        fresh_round_manager._transition_next_round.assert_not_awaited()
        assert state.cancelled is True

    @pytest.mark.asyncio
    async def test_retry_sends_error_message_on_failure(self, fresh_round_manager):
        """Tras 3 fallos, se envía mensaje de error al grupo."""
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

        mock_persist = AsyncMock(side_effect=Exception("DB error"))
        fresh_round_manager._persist_round_scores = mock_persist

        with patch.object(rm_mod, "RoundRepository") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_active_round.return_value = mock_db_round
            mock_repo.get_answers_by_player = AsyncMock(return_value={})
            mock_repo.get_game_player_by_telegram = AsyncMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            await fresh_round_manager._close_round(1, "stop", bot)

        bot.send_message.assert_any_await(
            state.group_chat_id,
            "❌ Ocurrió un error al guardar los puntajes. La partida se cancelará.",
        )


# ── A5: N+1 sesiones BD en _end_game ─────────────────────────────────────────


class TestEndGameNSessions:
    """Verifica que _end_game no abra N sesiones BD por jugador."""

    @pytest.mark.asyncio
    async def test_end_game_reuses_session_for_multiple_winners(self):
        """A5: _end_game debe abrir <=3 sesiones BD para N=3 ganadores."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import sys

        rm_mod = sys.modules["src.services.round_manager"]

        rm = RoundManager()
        bot = AsyncMock()

        state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=5,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=10,
            total_players=3,
            host_telegram_id=999,
            leader_id=111,
            player_names={111: "Alice", 222: "Bob", 333: "Carol"},
        )

        # _get_standings retorna 3 ganadores
        rm._get_standings = AsyncMock(
            return_value=[(111, 100), (222, 80), (333, 60)]
        )

        # XP, leaderboard, image generator y event service mockeados
        with (
            patch.object(rm_mod, "xp_service") as mock_xp,
            patch.object(rm_mod, "generate_podium_image", return_value=None),
            patch("src.services.leaderboard.leaderboard_service") as mock_lb,
            patch(
                "src.db.repositories.leaderboard_repository."
                "LeaderboardRepository.recalculate_ranks",
                AsyncMock(),
            ),
            patch(
                "src.services.event_service.event_service.get_active_events",
                AsyncMock(return_value=[]),
            ),
        ):
            mock_xp.award_all_players = AsyncMock(
                return_value=[
                    {"telegram_id": 111, "xp_gained": 50, "level": 2, "leveled_up": False},
                    {"telegram_id": 222, "xp_gained": 50, "level": 2, "leveled_up": False},
                    {"telegram_id": 333, "xp_gained": 50, "level": 2, "leveled_up": False},
                ]
            )
            mock_lb.upsert_player = AsyncMock()

            # Evita que bot intente descargar fotos reales
            bot.get_user_profile_photos = AsyncMock(
                return_value=MagicMock(total_count=0)
            )

            session_count = 0

            class _CountingSessionManager:
                """Async context manager que cuenta entradas."""

                async def __aenter__(self):
                    nonlocal session_count
                    session_count += 1
                    session = AsyncMock()
                    session.get = AsyncMock(
                        return_value=MagicMock(status="lobby")
                    )
                    session.commit = AsyncMock()
                    mock_player = MagicMock()
                    mock_player.telegram_id = 111
                    mock_player.id = 1
                    result_mock = MagicMock()
                    result_mock.scalar_one_or_none = MagicMock(
                        return_value=mock_player
                    )
                    result_mock.scalars = MagicMock(
                        return_value=MagicMock(
                            all=MagicMock(return_value=[mock_player])
                        )
                    )
                    session.execute = AsyncMock(return_value=result_mock)
                    return session

                async def __aexit__(self, *args):
                    pass

            with patch.object(
                rm_mod,
                "async_session_factory",
                new=lambda: _CountingSessionManager(),
            ):
                await rm._end_game(state, bot)

            # Tras el fix, deben abrirse <= 3 sesiones (get_standings +
            # batch XP/streaks + batch leaderboard).
            # El código actual abre 4 sesiones para 3 jugadores
            # (1 game update + 3 player lookups).
            assert (
                session_count <= 3
            ), (
                f"_end_game abrió {session_count} sesiones BD "
                f"para 3 ganadores (esperado <= 3 tras batch fix)"
            )


# ── TelegramRetryAfter en _end_game ──


class TestEndGameTelegramRetry:
    """B2+: TelegramRetryAfter en _end_game se reintenta."""

    @pytest.mark.asyncio
    async def test_retry_send_message_succeeds_on_second_attempt(self):
        """send_message lanza TelegramRetryAfter 1 vez, luego funciona."""
        import sys

        rm_mod = sys.modules["src.services.round_manager"]

        rm = RoundManager()
        bot = AsyncMock()

        state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=5,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=10,
            total_players=1,
            host_telegram_id=999,
            leader_id=111,
            player_names={111: "Alice"},
        )
        rm._get_standings = AsyncMock(return_value=[(111, 100)])
        state.timer_task = None

        send_call_count = 0

        async def _failing_send(*args, **kwargs):
            nonlocal send_call_count
            send_call_count += 1
            if send_call_count == 1:
                exc = TelegramRetryAfter(
                    method="SendMessage",
                    message="Too Many Requests: retry after 1",
                    retry_after=1,
                )
                raise exc
            return MagicMock()

        bot.send_message = _failing_send
        bot.send_photo = AsyncMock()
        bot.get_user_profile_photos = AsyncMock(
            return_value=MagicMock(total_count=0)
        )

        with (
            patch.object(rm_mod, "xp_service") as mock_xp,
            patch.object(rm_mod, "generate_podium_image", return_value=None),
            patch("src.services.leaderboard.leaderboard_service") as mock_lb,
            patch(
                "src.db.repositories.leaderboard_repository."
                "LeaderboardRepository.recalculate_ranks",
                AsyncMock(),
            ),
            patch(
                "src.services.event_service.event_service.get_active_events",
                AsyncMock(return_value=[]),
            ),
        ):
            mock_xp.award_all_players = AsyncMock(
                return_value=[{"telegram_id": 111, "xp_gained": 50, "level": 2, "leveled_up": False}]
            )
            mock_lb.upsert_player = AsyncMock()
            await rm._end_game(state, bot)

        assert send_call_count == 2, (
            f"send_message debería haberse llamado 2 veces (1 fallo + 1 éxito), "
            f"se llamó {send_call_count}"
        )

    @pytest.mark.asyncio
    async def test_retry_send_message_propagates_after_3_failures(self):
        """send_message falla 3 veces seguidas → TelegramRetryAfter se propaga."""
        import sys

        rm_mod = sys.modules["src.services.round_manager"]

        rm = RoundManager()
        bot = AsyncMock()

        state = RoundState(
            game_id=1,
            group_chat_id=-100,
            round_number=5,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=-100,
            message_id=10,
            total_players=1,
            host_telegram_id=999,
            leader_id=111,
            player_names={111: "Alice"},
        )
        rm._get_standings = AsyncMock(return_value=[(111, 100)])
        state.timer_task = None

        async def _always_failing(*args, **kwargs):
            raise TelegramRetryAfter(method="SendMessage", message="Too Many Requests: retry after 1", retry_after=1)

        bot.send_message = _always_failing
        bot.send_photo = AsyncMock()
        bot.get_user_profile_photos = AsyncMock(
            return_value=MagicMock(total_count=0)
        )

        with (
            patch.object(rm_mod, "xp_service") as mock_xp,
            patch.object(rm_mod, "generate_podium_image", return_value=None),
            patch("src.services.leaderboard.leaderboard_service") as mock_lb,
            patch(
                "src.db.repositories.leaderboard_repository."
                "LeaderboardRepository.recalculate_ranks",
                AsyncMock(),
            ),
            patch(
                "src.services.event_service.event_service.get_active_events",
                AsyncMock(return_value=[]),
            ),
        ):
            mock_xp.award_all_players = AsyncMock(
                return_value=[{"telegram_id": 111, "xp_gained": 50, "level": 2, "leveled_up": False}]
            )
            mock_lb.upsert_player = AsyncMock()
            with pytest.raises(TelegramRetryAfter):
                await rm._end_game(state, bot)


# ── E4: _cancelled flag previene race en cancelación simultánea ──────────


class TestCancelledFlag:
    """Verifica que _cancelled flag impida operaciones concurrentes."""

    @pytest.mark.asyncio
    async def test_cancel_game_sets_flag_and_cleans_up(self):
        """E4: cancel_game setea _cancelled antes del lock y lo limpia al final."""
        rm = RoundManager()
        game_id = 1

        state = RoundState(
            game_id=game_id, group_chat_id=-100, round_number=1,
            letter="A", categories=CATEGORIES, message_chat_id=-100,
            message_id=10, total_players=2, host_telegram_id=999,
        )
        rm._rounds[game_id] = state

        async with rm._lock_for(game_id):
            cancel_task = asyncio.create_task(rm.cancel_game(game_id))
            await asyncio.sleep(0.02)
            assert rm._cancelled.get(game_id) is True

        await cancel_task
        assert rm._cancelled.get(game_id) is None

    @pytest.mark.asyncio
    async def test_submit_answers_checks_flag(self):
        """E4: submit_answers debe retornar False si _cancelled está seteado."""
        rm = RoundManager()
        game_id = 1
        player = MagicMock()
        player.telegram_id = 111
        player.id = 1
        bot = AsyncMock()

        state = RoundState(
            game_id=game_id, group_chat_id=-100, round_number=1,
            letter="A", categories=CATEGORIES, message_chat_id=-100,
            message_id=10, total_players=2, host_telegram_id=999,
        )
        rm._rounds[game_id] = state

        rm._cancelled[game_id] = True

        result = await rm.submit_answers(game_id, player, "Nombre: Juan", bot)
        assert result is False

    @pytest.mark.asyncio
    async def test_press_stop_checks_flag(self):
        """E4: press_stop debe responder 'Partida cancelada' si _cancelled."""
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        rm._cancelled[game_id] = True

        await rm.press_stop(game_id, 111, callback, bot)
        callback.answer.assert_awaited_once()
        assert "cancelada" in callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_next_round_checks_flag(self):
        """E4: handle_next_round debe responder 'cancelada' si _cancelled."""
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        rm._cancelled[game_id] = True

        await rm.handle_next_round(game_id, 111, callback, bot)
        callback.answer.assert_awaited_once()
        assert "cancelada" in callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_stop_game_checks_flag(self):
        """E4: handle_stop_game debe responder 'cancelada' si _cancelled."""
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        rm._cancelled[game_id] = True

        await rm.handle_stop_game(game_id, 999, callback, bot)
        callback.answer.assert_awaited_once()
        assert "cancelada" in callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_letter_selection_checks_flag(self):
        """E4: handle_letter_selection debe responder 'cancelada' si _cancelled."""
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        rm._cancelled[game_id] = True

        await rm.handle_letter_selection(game_id, 111, "A", callback, bot)
        callback.answer.assert_awaited_once()
        assert "cancelada" in callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_double_check_catches_race(self):
        """E4: check después del lock debe detectar cancelación entre check-pre y lock."""
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        state = RoundState(
            game_id=game_id, group_chat_id=-100, round_number=1,
            letter="A", categories=CATEGORIES, message_chat_id=-100,
            message_id=10, total_players=2, host_telegram_id=999,
            leader_id=111,
        )
        rm._letter_pending[game_id] = state

        class CancellingLock:
            """Wraps a real lock but sets _cancelled after acquisition."""

            def __init__(self, real_lock):
                self._lock = real_lock
                self._cancelled_set = False

            async def __aenter__(self):
                await self._lock.__aenter__()
                rm._cancelled[game_id] = True
                return self

            async def __aexit__(self, *args):
                return await self._lock.__aexit__(*args)

        original_lock_for = rm._lock_for

        def patched_lock_for(gid):
            return CancellingLock(original_lock_for(gid))

        with patch.object(rm, "_lock_for", patched_lock_for):
            await rm.handle_next_round(game_id, 111, callback, bot)

        callback.answer.assert_awaited_once()
        assert "cancelada" in callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_flag_cleaned_after_cancel(self):
        """E4: después de cancel_game, _cancelled[game_id] debe ser limpiado."""
        rm = RoundManager()
        game_id = 1

        state = RoundState(
            game_id=game_id, group_chat_id=-100, round_number=1,
            letter="A", categories=CATEGORIES, message_chat_id=-100,
            message_id=10, total_players=2, host_telegram_id=999,
        )
        rm._rounds[game_id] = state

        await rm.cancel_game(game_id)

        assert rm._cancelled.get(game_id) is None


class TestHandleSkipLetter:
    """E8: handle_skip_letter."""

    @pytest.mark.asyncio
    async def test_skip_letter_selects_random_and_starts(self):
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()
        leader_id = 111

        state = RoundState(
            game_id=game_id,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=0,
            message_id=0,
            host_telegram_id=999,
            leader_id=leader_id,
            player_names={leader_id: "Líder"},
            total_players=2,
            total_rounds=3,
            letter_message_id=10,
            letter_message_chat_id=-100,
        )
        rm._letter_pending[game_id] = state

        with patch.object(rm, "_start_next_round_with_letter", AsyncMock()) as mock_start:
            await rm.handle_skip_letter(game_id, leader_id, callback, bot)

        mock_start.assert_awaited_once()
        letter = mock_start.call_args[0][1]
        assert letter in get_alphabet(state.include_n)
        callback.answer.assert_awaited_once()
        assert "aleatoria" in callback.answer.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_skip_letter_non_leader_rejected(self):
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        state = RoundState(
            game_id=game_id,
            group_chat_id=-100,
            round_number=1,
            letter="A",
            categories=CATEGORIES,
            message_chat_id=0,
            message_id=0,
            host_telegram_id=999,
            leader_id=111,
            player_names={111: "Líder"},
            total_players=2,
            total_rounds=3,
        )
        rm._letter_pending[game_id] = state

        await rm.handle_skip_letter(game_id, 222, callback, bot)
        callback.answer.assert_awaited_once()
        assert "Solo el líder" in callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_skip_letter_no_pending_state(self):
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        await rm.handle_skip_letter(game_id, 111, callback, bot)
        callback.answer.assert_awaited_once()
        assert "No hay selección" in callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_skip_letter_cancelled_game(self):
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        rm._cancelled[game_id] = True

        await rm.handle_skip_letter(game_id, 111, callback, bot)
        callback.answer.assert_awaited_once()
        assert "cancelada" in callback.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_skip_letter_double_check_catches_race(self):
        """E4-style: check post-lock detecta cancelación entre pre-check y lock."""
        rm = RoundManager()
        game_id = 1
        callback = MagicMock()
        callback.answer = AsyncMock()
        bot = AsyncMock()

        state = RoundState(
            game_id=game_id, group_chat_id=-100, round_number=1,
            letter="A", categories=CATEGORIES, message_chat_id=-100,
            message_id=10, total_players=2, host_telegram_id=999,
            leader_id=111,
        )
        rm._letter_pending[game_id] = state

        class CancellingLock:
            def __init__(self, real_lock):
                self._lock = real_lock

            async def __aenter__(self):
                await self._lock.__aenter__()
                rm._cancelled[game_id] = True
                return self

            async def __aexit__(self, *args):
                return await self._lock.__aexit__(*args)

        original_lock_for = rm._lock_for

        def patched_lock_for(gid):
            return CancellingLock(original_lock_for(gid))

        with patch.object(rm, "_lock_for", patched_lock_for):
            await rm.handle_skip_letter(game_id, 111, callback, bot)

        callback.answer.assert_awaited_once()
        assert "cancelada" in callback.answer.call_args[0][0]
