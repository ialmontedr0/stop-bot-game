import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.repositories.leaderboard_repository import LeaderboardRepository


def _mock_session(scalar_one_or_none_value=None, scalars_all_value=None):
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = scalar_one_or_none_value
    if scalars_all_value is not None:
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = scalars_all_value
        mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    return mock_session


class TestUpsertPlayerWeek:
    @pytest.fixture(autouse=True)
    def mock_db(self):
        mod = sys.modules["src.db.repositories.leaderboard_repository"]
        with patch.object(mod, "async_session_factory") as m:
            self._mock_session = _mock_session(scalar_one_or_none_value=None)
            m.return_value.__aenter__.return_value = self._mock_session
            yield

    @pytest.mark.asyncio
    async def test_creates_new_entry(self):
        await LeaderboardRepository.upsert_player_week(1, 100)
        # Verificar que la query incluye group_chat_id=0 por defecto
        call_args = self._mock_session.execute.call_args
        stmt = call_args[0][0]
        stmt_str = str(stmt)
        assert "group_chat_id" in stmt_str
        self._mock_session.add.assert_called_once()
        self._mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_new_entry_with_group(self):
        await LeaderboardRepository.upsert_player_week(1, 100, group_chat_id=-100123)
        call_args = self._mock_session.execute.call_args
        stmt = call_args[0][0]
        stmt_str = str(stmt)
        assert "group_chat_id" in stmt_str
        assert ":group_chat_id_1" in stmt_str or "-100123" in stmt_str
        self._mock_session.add.assert_called_once()
        self._mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_entry(self):
        existing = MagicMock()
        existing.total_score = 50
        existing.games_played = 1

        mock_ses = _mock_session(scalar_one_or_none_value=existing)
        mod = sys.modules["src.db.repositories.leaderboard_repository"]
        with patch.object(mod, "async_session_factory") as m:
            m.return_value.__aenter__.return_value = mock_ses
            await LeaderboardRepository.upsert_player_week(1, 100)
            assert existing.total_score == 150
            assert existing.games_played == 2


class TestRecalculateRanks:
    @pytest.mark.asyncio
    async def test_recalculates_ranks(self):
        e1 = MagicMock()
        e1.rank = 0
        e2 = MagicMock()
        e2.rank = 0

        mock_ses = _mock_session(scalars_all_value=[e1, e2])
        mod = sys.modules["src.db.repositories.leaderboard_repository"]
        with patch.object(mod, "async_session_factory") as m:
            m.return_value.__aenter__.return_value = mock_ses
            await LeaderboardRepository.recalculate_ranks()
            assert e1.rank == 1
            assert e2.rank == 2

    @pytest.mark.asyncio
    async def test_recalculates_ranks_per_group(self):
        e1 = MagicMock()
        e1.rank = 0

        mock_ses = _mock_session(scalars_all_value=[e1])
        mod = sys.modules["src.db.repositories.leaderboard_repository"]
        with patch.object(mod, "async_session_factory") as m:
            m.return_value.__aenter__.return_value = mock_ses
            await LeaderboardRepository.recalculate_ranks(group_chat_id=-100456)
            assert e1.rank == 1
            call_args = mock_ses.execute.call_args
            stmt_str = str(call_args[0][0])
            assert "group_chat_id" in stmt_str
