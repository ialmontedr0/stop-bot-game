import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import Answer
from src.services.round_manager import CATEGORIES, RoundManager
from src.services.score_engine import ScoreEngine

_rm_mod = sys.modules["src.services.round_manager"]


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(chat=MagicMock(id=-100), message_id=1))
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.get_user_profile_photos = AsyncMock(return_value=MagicMock(total_count=0))
    return bot


@pytest.mark.asyncio
async def test_round_state_lifecycle(mock_bot):
    game_id = 1
    player_names = {111: "Alice", 222: "Bob"}
    rm = RoundManager()

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_repo = MagicMock()
    mock_repo.create_round = AsyncMock(return_value=MagicMock(id=1))
    mock_repo.get_active_round = AsyncMock(return_value=MagicMock(id=1))
    mock_repo.save_answers = AsyncMock()

    with patch.object(_rm_mod, "async_session_factory", return_value=mock_session):
        with patch.object(_rm_mod, "RoundRepository", return_value=mock_repo):
            with patch.object(rm, "_round_timer", new=AsyncMock()):
                await rm.start_round(
                    game_id=game_id,
                    group_chat_id=-100123,
                    round_number=1,
                    letter="A",
                    total_players=2,
                    player_names=player_names,
                    bot=mock_bot,
                    total_rounds=3,
                )

    state = rm.get_active_round(game_id)
    assert state is not None
    assert state.letter == "A"
    assert state.round_number == 1
    assert len(state.submitted_player_ids) == 0

    player1 = MagicMock()
    player1.id = 1
    player1.telegram_id = 111
    player1.first_name = "Alice"

    player2 = MagicMock()
    player2.id = 2
    player2.telegram_id = 222
    player2.first_name = "Bob"

    text1 = "\n".join(f"{cat}: valor_{cat}_1" for cat in CATEGORIES)
    with patch.object(_rm_mod, "async_session_factory", return_value=mock_session):
        with patch.object(_rm_mod, "RoundRepository", return_value=mock_repo):
            result1 = await rm.submit_answers(game_id, player1, text1, mock_bot)

    assert state.first_completer_id == 111
    assert state.first_completer_name == "Alice"

    assert len(state.submitted_player_ids) == 1

    with patch.object(rm, "_do_close_round_telegram", new=AsyncMock()) as mock_close:
        await rm._close_round(game_id, "stop", mock_bot)
        mock_close.assert_called_once()

    assert rm.get_active_round(game_id) is None

    engine = ScoreEngine()
    answers_by_player = {
        111: [
            Answer(
                id=1,
                player_id=1,
                word_slot="Nombre",
                raw_text="Ana",
                normalized_text="ana",
                score=0,
            )
        ],
    }
    totals, details = engine.evaluate(answers_by_player, 1, first_completer_id=111)
    assert 111 in totals
    assert totals[111] >= 60

    await rm.cancel_game(game_id)
